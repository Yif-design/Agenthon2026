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
    half = 0.15 if point in (0.05, 0.85) else 0.25
    interval = {"level": task.interval_level, "lo": max(0.0, point - half), "hi": min(1.0, point + half)}
    return ModelOutput(point, label, interval, "explicit_credit_flags")
