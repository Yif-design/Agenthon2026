from __future__ import annotations

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
    prior = number(entity.get("prior_year_q_eps")) or 0.0
    signal = signals.get("yoy_earnings_signal", 0)
    label = "up" if signal > 0 else "down"
    step = max(0.05 * abs(prior), 0.01)
    point = prior + step if label == "up" else prior - step
    return ModelOutput(point, label, interval(point, task.interval_level, 3.0 * step), "prior_eps_direction_only")
