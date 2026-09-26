from __future__ import annotations

import re
from typing import Any

from ..retrieve import IndexedCorpus
from ..taskio import Task
from .common import ModelOutput, interval, number


def solve(
    task: Task,
    entity: dict[str, Any],
    signals: dict[str, int],
    parameters: dict[str, float | None],
    corpus: IndexedCorpus,
    row_index: int,
    row_count: int,
) -> ModelOutput:
    current, current_field = _latest_dated_number(entity, "net_pct_oi")
    point = -0.2 * current if current is not None else 0.0
    history, evidence = _history(corpus, str(entity.get("name") or ""), str(entity.get("entity_id") or ""))
    return ModelOutput(
        point,
        None,
        interval(point, task.interval_level, 11.3),
        "net_position_mean_reversion",
        evidence=evidence,
        derivation={
            "current_net_pct_oi": current,
            "current_net_pct_oi_field": current_field,
            "mean_reversion_coefficient": -0.2,
            "interval_half_width_pct_oi": 11.3,
            "history": history,
        },
    )


def _latest_dated_number(entity: dict[str, Any], prefix: str) -> tuple[float | None, str | None]:
    """Return an exact field or the latest YYYYMMDD-suffixed numeric field."""
    direct = number(entity.get(prefix))
    if direct is not None:
        return direct, prefix
    dated_fields = sorted(
        (key for key in entity if re.fullmatch(rf"{re.escape(prefix)}_\d{{8}}", key)),
        reverse=True,
    )
    for key in dated_fields:
        value = number(entity.get(key))
        if value is not None:
            return value, key
    return None, None


def _history(corpus: IndexedCorpus, name: str, entity_id: str) -> tuple[list[float], list[dict[str, Any]]]:
    terms = [part.lower() for part in re.split(r"[_\s]+", entity_id) if len(part) > 2]
    terms.extend(part.lower() for part in name.split() if len(part) > 3)
    candidates = []
    for doc_id, text in corpus.doc_texts.items():
        if "net_%OI" not in text:
            continue
        score = sum(term in doc_id.lower() or term in text.splitlines()[0].lower() for term in terms)
        candidates.append((score, doc_id, text))
    if not candidates:
        return [], []
    _, doc_id, text = max(candidates, key=lambda item: item[0])
    values: list[float] = []
    used_lines: list[str] = []
    for line in text.splitlines():
        if not re.match(r"^\d{4}-\d{2}-\d{2}\s*\|", line):
            continue
        cells = [part.strip().replace(",", "") for part in line.split("|")]
        if len(cells) > 5:
            value = number(cells[5])
            if value is not None:
                values.append(value)
                used_lines.append(line)
    quote = "\n".join(used_lines)
    evidence = [{
        "doc_id": doc_id,
        "quote": quote,
        "claim": f"The frozen COT table reports the pre-cutoff positioning history for {name or entity_id}.",
        "name": "positioning_history",
        "value": values,
    }] if quote and quote in text else []
    return values, evidence
