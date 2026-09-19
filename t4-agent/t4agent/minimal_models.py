from __future__ import annotations

from typing import Any

from .calculators import solve as solve_calculator
from .calculators.common import ModelOutput, number
from .family_specs import FamilySpec
from .retrieve import IndexedCorpus
from .taskio import Task


def normalize_signals(parsed: dict[str, Any] | None, spec: FamilySpec) -> dict[str, int]:
    raw = parsed.get("signals") if isinstance(parsed, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    out: dict[str, int] = {}
    for signal_spec in spec.signals:
        value = raw.get(signal_spec.name)
        if isinstance(value, dict):
            value = value.get("level")
        out[signal_spec.name] = _signal_level(value)
    return out


def normalize_parameters(parsed: dict[str, Any] | None, spec: FamilySpec) -> dict[str, float | None]:
    raw = parsed.get("parameters") if isinstance(parsed, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    out: dict[str, float | None] = {}
    for parameter_spec in spec.numeric_parameters:
        value = raw.get(parameter_spec.name)
        if isinstance(value, dict):
            value = value.get("value")
        out[parameter_spec.name] = number(value)
    return out


def model_evidence(parsed: dict[str, Any] | None, spec: FamilySpec) -> list[dict[str, Any]]:
    if not isinstance(parsed, dict):
        return []
    evidence: list[dict[str, Any]] = []
    raw_signals = parsed.get("signals") if isinstance(parsed.get("signals"), dict) else {}
    for signal_spec in spec.signals:
        item = raw_signals.get(signal_spec.name)
        if not isinstance(item, dict) or _signal_level(item.get("level")) == 0:
            continue
        evidence.append(_evidence_item(item))
    raw_parameters = parsed.get("parameters") if isinstance(parsed.get("parameters"), dict) else {}
    for parameter_spec in spec.numeric_parameters:
        item = raw_parameters.get(parameter_spec.name)
        if not isinstance(item, dict) or number(item.get("value")) is None:
            continue
        evidence.append(_evidence_item(item))
    return [item for item in evidence if item.get("doc_id") and item.get("claim")]


def solve_minimal(
    task: Task,
    entity: dict[str, Any],
    spec: FamilySpec,
    signals: dict[str, int],
    corpus: IndexedCorpus,
    row_index: int,
    row_count: int,
    parameters: dict[str, float | None] | None = None,
) -> ModelOutput:
    return solve_calculator(task, entity, spec, signals, parameters or {}, corpus, row_index, row_count)


def _evidence_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_id": item.get("doc_id"),
        "quote": item.get("quote"),
        "claim": item.get("claim") or item.get("reason"),
    }


def _signal_level(value: object) -> int:
    names = {
        "strong_negative": -2,
        "negative": -1,
        "neutral": 0,
        "neutral_or_unknown": 0,
        "unknown": 0,
        "positive": 1,
        "strong_positive": 2,
    }
    if isinstance(value, bool):
        return 2 if value else 0
    if isinstance(value, (int, float)):
        return max(-2, min(2, round(float(value))))
    return names.get(str(value).strip().lower(), 0)
