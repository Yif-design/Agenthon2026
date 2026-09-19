from __future__ import annotations

import math
import re
from statistics import pstdev
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
    point = number(entity.get("trailing_4wk_net_change_pct_oi")) or 0.0
    current = number(entity.get("net_pct_oi_20241022"))
    history, evidence = _history(corpus, str(entity.get("name") or ""), str(entity.get("entity_id") or ""))
    if current is not None and len(history) >= 8:
        absolute = sorted(abs(value) for value in history)
        cutoff = absolute[max(0, math.ceil(0.9 * len(absolute)) - 1)]
        if abs(current) >= cutoff:
            point *= 0.5
    half = max(4.0, 1.65 * pstdev(history) if len(history) > 1 else 8.0)
    return ModelOutput(
        point,
        None,
        interval(point, task.interval_level, half),
        "trailing_change_crowding_cap",
        evidence=evidence,
        derivation={"trailing_change": number(entity.get("trailing_4wk_net_change_pct_oi")), "history": history},
    )


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
