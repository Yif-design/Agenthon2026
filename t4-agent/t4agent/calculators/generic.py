from __future__ import annotations

from typing import Any

from ..calc import default_point, interval_for
from ..retrieve import IndexedCorpus
from ..taskio import Task
from .common import ModelOutput


def solve(
    task: Task,
    entity: dict[str, Any],
    signals: dict[str, int],
    parameters: dict[str, float | None],
    corpus: IndexedCorpus,
    row_index: int,
    row_count: int,
) -> ModelOutput:
    name = str(task.target.get("name", ""))
    point = default_point(task.target_type, name, entity, row_index, row_count)
    label = _label(signals.get("directional_signal", 0), task.labels)
    return ModelOutput(point, label, interval_for(point, name, task.interval_level), "generic_baseline")


def _label(signal: int, labels: list[str]) -> str | None:
    if not labels:
        return None
    positive = ("up", "positive", "yes", "beat", "credit_event")
    negative = ("down", "negative", "no", "miss", "no_event")
    candidates = positive if signal > 0 else negative
    for candidate in candidates:
        for label in labels:
            if candidate in label.lower():
                return label
    return labels[0]
