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
    baseline = default_point(task.target_type, name, entity, row_index, row_count)
    signal = signals.get("directional_signal", 0)
    point = baseline
    if task.target_type in {"regression", "ranking"} and signal:
        baseline_interval = interval_for(baseline, name, task.interval_level)
        scale = (baseline_interval["hi"] - baseline_interval["lo"]) / 6.0
        point = baseline + signal * scale
    label = _label(signal, task.labels)
    method = "generic_evidence_adjusted" if signal else "generic_baseline"
    return ModelOutput(point, label, interval_for(point, name, task.interval_level), method)


def _label(signal: int, labels: list[str]) -> str | None:
    if not labels:
        return None
    if signal == 0:
        for candidate in ("flat", "neutral", "unchanged", "inline", "no_change"):
            for label in labels:
                if candidate in label.lower():
                    return label
        return labels[0]
    positive = ("up", "positive", "yes", "beat", "credit_event")
    negative = ("down", "negative", "no", "miss", "no_event")
    candidates = positive if signal > 0 else negative
    for candidate in candidates:
        for label in labels:
            if candidate in label.lower():
                return label
    return labels[0]
