from __future__ import annotations

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
    maturity = number(entity.get("maturity_years")) or 10.0
    shock = 15.0 * clip(signals.get("policy_direction", 0), -2, 2)
    if maturity <= 2:
        sensitivity = 1.0
    elif maturity <= 5:
        sensitivity = 0.8
    elif maturity <= 10:
        sensitivity = 0.6
    else:
        sensitivity = 0.4
    point = shock * sensitivity
    return ModelOutput(point, None, interval(point, task.interval_level, 50.0), "policy_direction_maturity_decay")
