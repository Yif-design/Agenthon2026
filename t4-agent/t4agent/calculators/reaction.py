from __future__ import annotations

import math
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
    threshold = number(entity.get("flat_threshold_abn_pct")) or 1.0
    signal = signals.get("explicit_forward_outlook_signal", 0)
    point = 0.0 if abs(signal) < 2 else math.copysign(1.25 * threshold, signal)
    if point > threshold:
        label = "positive_reaction"
    elif point < -threshold:
        label = "negative_reaction"
    else:
        label = "flat"
    return ModelOutput(point, label, interval(point, task.interval_level, max(2.5, 2.0 * threshold)), "flat_unless_strong_outlook")
