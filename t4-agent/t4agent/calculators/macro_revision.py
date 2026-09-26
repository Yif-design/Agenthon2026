from __future__ import annotations

import re
from statistics import median, pstdev
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
    latest = number(entity.get("latest_precutoff_estimate")) or 0.0
    changes, evidence = _revision_changes(corpus, str(entity.get("series_id") or ""))
    revision = median(changes) if changes else 0.0
    point = latest + revision
    label = "up" if revision > 0 else "down"
    half = max(abs(revision) * 3.0, pstdev(changes) * 1.65 if len(changes) > 1 else 0.0, abs(latest) * 0.002, 0.01)
    return ModelOutput(
        point,
        label,
        interval(point, task.interval_level, half),
        "median_historical_revision",
        evidence=evidence,
        derivation={"latest_estimate": latest, "historical_revision_changes": changes, "median_revision": revision},
    )


def _revision_changes(corpus: IndexedCorpus, series_id: str) -> tuple[list[float], list[dict[str, Any]]]:
    pattern = re.compile(
        r"revised\s+(?:UP|DOWN)\s+from\s+([+-]?\d+(?:\.\d+)?)\s+.*?\s+to\s+([+-]?\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    for doc_id, text in corpus.doc_texts.items():
        if series_id and series_id not in doc_id and not text.startswith(series_id):
            continue
        matches = list(pattern.finditer(text))
        changes = [float(match.group(2)) - float(match.group(1)) for match in matches]
        if changes:
            quote = text[matches[0].start() : matches[-1].end()]
            evidence = [{
                "doc_id": doc_id,
                "quote": quote,
                "claim": f"The frozen {series_id} vintage history reports the revisions used to estimate the next revision.",
                "name": "historical_revisions",
                "value": changes,
            }] if quote in text else []
            return changes, evidence
    return [], []
