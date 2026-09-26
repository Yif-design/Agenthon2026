from __future__ import annotations

from typing import Any

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
    default = signals.get("covenant_breach_or_payment_default", 0) > 0
    going = signals.get("going_concern_present", 0) > 0
    liquidity = signals.get("liquidity_explicitly_insufficient", 0) > 0
    maturity = signals.get("near_term_debt_without_stated_funding", 0) > 0
    if default:
        point = 0.85
    elif going and liquidity:
        point = 0.70
    elif going or liquidity:
        point = 0.40
    elif maturity:
        point = 0.20
    else:
        point = 0.05
    label = "credit_event" if point >= 0.5 else "no_event"
    # The target is a Bernoulli event probability, so its fixed mathematical
    # support is the most defensible interval when no calibrated probability
    # history is available for the entity population.
    interval = {"level": task.interval_level, "lo": 0.0, "hi": 1.0}
    return ModelOutput(point, label, interval, "explicit_credit_flags")
