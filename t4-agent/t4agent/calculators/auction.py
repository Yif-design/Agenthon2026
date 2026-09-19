from __future__ import annotations

import re
from statistics import pstdev
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
    values, evidence = _history(corpus, str(entity.get("tenor") or ""))
    if values:
        recent = values[-6:]
        baseline = sum(recent) / len(recent)
        trend = 0.0 if len(values) < 3 else clip((values[-1] - values[-3]) / 2.0, -0.08, 0.08)
        point = baseline + trend
        half = max(0.15, 1.65 * pstdev(recent) if len(recent) > 1 else 0.0)
    else:
        point, half = 2.5, 0.8
    return ModelOutput(
        point,
        None,
        interval(point, task.interval_level, half),
        "same_tenor_recent_history",
        evidence=evidence,
        derivation={"recent_values": values[-6:], "forecast": point},
    )


def _history(corpus: IndexedCorpus, tenor: str) -> tuple[list[float], list[dict[str, Any]]]:
    wanted = tenor.lower().replace("-", "")
    for doc_id, text in corpus.doc_texts.items():
        first = text.splitlines()[0].lower().replace("-", "") if text else ""
        if wanted not in first or "auction" not in first:
            continue
        values: list[float] = []
        used_lines: list[str] = []
        for line in text.splitlines():
            if not re.match(r"^\d{4}-\d{2}-\d{2}\s*\|", line):
                continue
            cells = [part.strip() for part in line.split("|")]
            if len(cells) > 4:
                value = number(cells[4])
                if value is not None:
                    values.append(value)
                    used_lines.append(line)
        if values:
            quote = "\n".join(used_lines[-6:])
            evidence = [{
                "doc_id": doc_id,
                "quote": quote,
                "claim": f"The frozen TreasuryDirect table reports the recent {tenor} bid-to-cover history used by the forecast.",
                "name": "same_tenor_history",
                "value": values[-6:],
            }] if quote in text else []
            return values, evidence
    return [], []
