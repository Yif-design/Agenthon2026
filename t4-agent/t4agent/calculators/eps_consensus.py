from __future__ import annotations

from typing import Any

from ..eps import eps_interval, eps_label_from_forecast
from ..retrieve import IndexedCorpus
from ..taskio import Task
from .common import ModelOutput, number


def solve(
    task: Task,
    entity: dict[str, Any],
    signals: dict[str, int],
    parameters: dict[str, float | None],
    corpus: IndexedCorpus,
    row_index: int,
    row_count: int,
) -> ModelOutput:
    consensus = number(entity.get("consensus_eps")) or 0.0
    threshold = number(entity.get("threshold_pct")) or 0.05
    signal = signals.get("target_period_earnings_signal", 0)
    if signal >= 2:
        point = consensus * (1.0 + 1.25 * threshold)
    elif signal <= -2:
        point = consensus * (1.0 - 1.25 * threshold)
    else:
        point = consensus
    label = eps_label_from_forecast(point, consensus, threshold)
    return ModelOutput(point, label, eps_interval(point, entity, task.interval_level), "consensus_strong_signal")
