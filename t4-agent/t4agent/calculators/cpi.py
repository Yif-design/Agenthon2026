from __future__ import annotations

import re
from statistics import median, pstdev
from typing import Any

from ..retrieve import IndexedCorpus
from ..taskio import Task
from .common import ModelOutput, clip, interval, number


def solve(
    task: Task,
    entity: dict[str, Any],
    signals: dict[str, int],
    parameters: dict[str, float | None],
    corpus: IndexedCorpus,
    row_index: int,
    row_count: int,
) -> ModelOutput:
    latest = number(entity.get("latest_published_mom_pct")) or 0.0
    component = str(entity.get("name") or "")
    history, history_evidence = _history(corpus, component)
    recent_median = median(history[-3:]) if history else latest
    point = 0.7 * latest + 0.3 * recent_median
    entity_id = str(entity.get("entity_id") or "").upper()
    gasoline_change, gasoline_evidence = _gasoline_change(corpus)
    if gasoline_change is not None and entity_id == "CPI_GASOLINE":
        point = clip(gasoline_change, -5.0, 5.0)
    elif gasoline_change is not None and entity_id == "CPI_ENERGY":
        point = 0.4 * clip(gasoline_change, -5.0, 5.0)
    half = max(0.75, 1.65 * pstdev(history)) if len(history) > 1 else 0.75
    evidence = history_evidence
    if entity_id in {"CPI_GASOLINE", "CPI_ENERGY"} and gasoline_evidence:
        evidence = evidence + gasoline_evidence
    return ModelOutput(
        point,
        None,
        interval(point, task.interval_level, half),
        "component_history",
        evidence=evidence,
        derivation={"latest_mom": latest, "recent_median": recent_median, "gasoline_change": gasoline_change},
    )


def _history(corpus: IndexedCorpus, component: str) -> tuple[list[float], list[dict[str, Any]]]:
    for doc_id, text in corpus.doc_texts.items():
        if "CPI-U components" not in text or "month |" not in text:
            continue
        lines = text.splitlines()
        header = next((line for line in lines if line.startswith("month |")), "")
        columns = [part.strip() for part in header.split("|")]
        index = _matching_column(columns, component)
        if index is None:
            return [], []
        values: list[float] = []
        used_lines: list[str] = []
        for line in lines:
            if not re.match(r"^\d{4}-\d{2}\s*\|", line):
                continue
            cells = [part.strip() for part in line.split("|")]
            if index < len(cells):
                value = number(cells[index])
                if value is not None:
                    values.append(value)
                    used_lines.append(line)
        quote = "\n".join(used_lines)
        evidence = []
        if quote and quote in text:
            evidence.append({
                "doc_id": doc_id,
                "quote": quote,
                "claim": f"The frozen CPI vintage table reports the pre-cutoff history used for {component}.",
                "name": "component_history",
                "value": values,
            })
        return values, evidence
    return [], []


def _matching_column(columns: list[str], component: str) -> int | None:
    target = re.sub(r"\s+", " ", component.lower()).strip()
    for index, column in enumerate(columns):
        normalized = re.sub(r"\s+", " ", column.lower()).strip()
        if target == normalized or target in normalized or normalized in target:
            return index
    return None


def _gasoline_change(corpus: IndexedCorpus) -> tuple[float | None, list[dict[str, Any]]]:
    pattern = re.compile(r"October weeks shown .*? is ([+-]?\d+(?:\.\d+)?)% versus", re.IGNORECASE)
    for doc_id, text in corpus.doc_texts.items():
        if "gasoline retail price" not in text.lower():
            continue
        match = pattern.search(text)
        if match:
            value = float(match.group(1))
            return value, [{
                "doc_id": doc_id,
                "quote": match.group(0),
                "claim": f"The pre-cutoff gasoline data show an October-versus-September change of {value:g}%.",
                "name": "gasoline_change",
                "value": value,
            }]
    return None, []
