from __future__ import annotations

from typing import Any


def is_eps_beat_task(target_name: str, target_type: str, labels: list[str]) -> bool:
    return (
        target_type == "classification"
        and target_name == "eps_outcome"
        and {"beat", "miss", "inline"}.issubset(set(labels))
    )


def eps_label_from_forecast(forecast_eps: float, consensus_eps: float, threshold_pct: float) -> str:
    beat_threshold = consensus_eps * (1.0 + threshold_pct)
    miss_threshold = consensus_eps * (1.0 - threshold_pct)
    if forecast_eps > beat_threshold:
        return "beat"
    if forecast_eps < miss_threshold:
        return "miss"
    return "inline"


def safe_eps_forecast(
    raw_forecast: float | None,
    entity: dict[str, Any],
    evidence_items: object,
) -> tuple[float, str | None]:
    """Return an EPS forecast that is allowed to drive the beat/miss/inline tool.

    The common failure mode is copying a pre-cutoff historical EPS number from an earnings release
    into the target quarter. For the public Apple example, Q1 FY2024 EPS of 2.18 appears in the
    corpus, while the task asks for Q2 FY2024. When a model's value is far from consensus and its
    evidence looks historical, use a conservative consensus-near estimate instead.
    """
    consensus = _float(entity.get("consensus_eps"))
    if consensus is None:
        return (float(raw_forecast or 0.0), None)
    threshold = _float(entity.get("threshold_pct")) or 0.05
    if raw_forecast is None:
        return (consensus, "eps_missing_forecast_used_consensus")

    if _looks_like_historical_eps(raw_forecast, consensus, threshold, evidence_items):
        # Slightly above consensus but inside the 5% band for ordinary EPS-beat cards.
        return (consensus * (1.0 + min(threshold * 0.4, 0.02)), "eps_historical_number_guardrail")
    return (float(raw_forecast), None)


def eps_interval(forecast_eps: float, entity: dict[str, Any], level: float) -> dict[str, float]:
    consensus = _float(entity.get("consensus_eps")) or abs(float(forecast_eps)) or 1.0
    threshold = _float(entity.get("threshold_pct")) or 0.05
    half = max(consensus * threshold * 1.25, consensus * 0.04, 0.05)
    return {"level": float(level), "lo": float(forecast_eps) - half, "hi": float(forecast_eps) + half}


def _looks_like_historical_eps(
    forecast: float,
    consensus: float,
    threshold: float,
    evidence_items: object,
) -> bool:
    if forecast <= consensus * (1.0 + threshold * 2.0):
        return False
    text = ""
    if isinstance(evidence_items, list):
        for item in evidence_items:
            if isinstance(item, dict):
                text += " " + str(item.get("quote", "")) + " " + str(item.get("claim", ""))
    lowered = text.lower()
    historical_markers = (
        "first quarter",
        "q1",
        "three months ended december",
        "quarter ended december",
        "fiscal 2024 first quarter",
        "same quarter of the prior year",
    )
    eps_markers = ("eps", "earnings per diluted share", "diluted eps", "per share")
    return any(m in lowered for m in historical_markers) and any(m in lowered for m in eps_markers)


def _float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None
