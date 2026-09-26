from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelOutput:
    point: float
    label: str | None
    interval: dict[str, float]
    method: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    derivation: dict[str, Any] = field(default_factory=dict)


def number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "").replace("%", ""))
        except ValueError:
            return None
    return None


def clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def interval(point: float, level: float, half: float) -> dict[str, float]:
    return {"level": float(level), "lo": float(point - half), "hi": float(point + half)}
