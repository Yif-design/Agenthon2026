#!/usr/bin/env python3
"""Cutoff-safe rolling-origin evaluation for normalized economic events.

This module is evaluation infrastructure.  It deliberately has no dependency on
the production agent and never reads a competition outcome while constructing a
forecast.  An observation becomes eligible training history only after its
``resolution_date`` is strictly earlier than the next ``origin_date``.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable


CANDIDATES = (
    "zero",
    "persistence",
    "recent_mean",
    "momentum",
    "anti_momentum",
    "mean_reversion",
    "seasonal",
    "ridge",
    "production_prior",
)


@dataclass(frozen=True)
class Observation:
    family: str
    event_id: str
    entity_id: str
    origin_date: date
    resolution_date: date
    target: float
    target_kind: str
    season_period: int
    features: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.target_kind not in {"level", "change"}:
            raise ValueError(f"unsupported target_kind: {self.target_kind}")
        if self.resolution_date < self.origin_date:
            raise ValueError("resolution_date precedes origin_date")
        if not math.isfinite(self.target):
            raise ValueError("target must be finite")


@dataclass(frozen=True)
class ForecastRow:
    family: str
    event_id: str
    entity_id: str
    origin_date: date
    resolution_date: date
    split: str
    actual: float
    history_count: int
    predictions: dict[str, float]
    intervals: dict[str, tuple[float, float]]
    interval_sources: dict[str, str]
    selected_model: str
    selector_validation_rows: int
    selector_validation_origins: int
    latest_training_resolution: date | None


def quantile(values: Iterable[float], q: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("empty quantile input")
    position = (len(ordered) - 1) * q
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def chronological_splits(observations: list[Observation]) -> dict[tuple[str, date], str]:
    """Assign whole event groups to 60/20/20 chronological partitions."""
    result: dict[tuple[str, date], str] = {}
    families = sorted({row.family for row in observations})
    for family in families:
        origins = sorted({row.origin_date for row in observations if row.family == family})
        if len(origins) < 5:
            raise ValueError(f"{family} needs at least five origins")
        test_start = max(1, min(len(origins) - 2, math.floor(0.60 * len(origins))))
        confirmation_start = max(test_start + 1, min(len(origins) - 1, math.floor(0.80 * len(origins))))
        for index, origin in enumerate(origins):
            split = "development" if index < test_start else "time_forward_test"
            if index >= confirmation_start:
                split = "confirmation"
            result[(family, origin)] = split
    return result


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def _ridge_delta(values: list[float]) -> float | None:
    """Fit Wang-style recent-change/deviation ridge features without tuning."""
    if len(values) < 7:
        return None
    samples: list[tuple[tuple[float, float], float]] = []
    for index in range(2, len(values)):
        prior = values[:index]
        recent = prior[-1] - prior[-2]
        anchor = _median(prior[-6:])
        features = (recent, prior[-1] - anchor)
        samples.append((features, values[index] - prior[-1]))
    a = sum(x[0] * x[0] for x, _ in samples)
    b = sum(x[0] * x[1] for x, _ in samples)
    d = sum(x[1] * x[1] for x, _ in samples)
    u = sum(x[0] * y for x, y in samples)
    v = sum(x[1] * y for x, y in samples)
    penalty = max(1e-8, 0.1 * (a + d) / len(samples))
    a += penalty
    d += penalty
    determinant = a * d - b * b
    if determinant <= 1e-12:
        return None
    beta0 = max(-1.5, min(1.5, (u * d - v * b) / determinant))
    beta1 = max(-1.5, min(1.5, (v * a - u * b) / determinant))
    recent = values[-1] - values[-2]
    deviation = values[-1] - _median(values[-6:])
    return beta0 * recent + beta1 * deviation


def _production_prior(observation: Observation, history: list[Observation]) -> float:
    values = [row.target for row in history]
    features = observation.features
    rule = str(features.get("production_rule", "fallback"))
    if rule == "auction_recent6":
        return statistics.fmean(values[-6:]) if values else 2.5
    if rule == "cpi_component":
        known = [float(value) for value in features.get("known_values", [])]
        latest = known[-1] if known else 0.0
        recent_median = _median(known[-3:]) if known else latest
        return 0.7 * latest + 0.3 * recent_median
    if rule == "eps_directionless":
        prior = float(features.get("prior_eps", 0.0))
        return prior - max(0.05 * abs(prior), 0.01)
    if rule == "cot_positioning":
        current = float(features.get("current", 0.0))
        if observation.origin_date >= date(2022, 1, 1):
            return -0.2 * current
        return float(features.get("trailing_change", 0.0))
    if rule == "macro_revision":
        changes = [float(value) for value in features.get("history_changes", [])]
        return _median(changes)
    if rule in {"zero", "fomc_no_signal", "reaction_no_signal"}:
        return 0.0
    return values[-1] if values and observation.target_kind == "level" else 0.0


def candidate_predictions(observation: Observation, history: list[Observation]) -> dict[str, float]:
    values = [row.target for row in history]
    fallback = values[-1] if values and observation.target_kind == "level" else 0.0
    persistence = values[-1] if values else fallback
    recent_mean = statistics.fmean(values[-6:]) if values else fallback
    if len(values) >= 2:
        change = values[-1] - values[-2]
        momentum = values[-1] + change
        anti_momentum = values[-1] - change
    else:
        momentum = anti_momentum = fallback
    mean_reversion = values[-1] - 0.5 * (values[-1] - _median(values[-12:])) if values else fallback
    seasonal = values[-observation.season_period] if len(values) >= observation.season_period else fallback
    ridge_delta = _ridge_delta(values)
    ridge = values[-1] + ridge_delta if values and ridge_delta is not None else fallback
    return {
        "zero": 0.0,
        "persistence": persistence,
        "recent_mean": recent_mean,
        "momentum": momentum,
        "anti_momentum": anti_momentum,
        "mean_reversion": mean_reversion,
        "seasonal": seasonal,
        "ridge": ridge,
        "production_prior": _production_prior(observation, history),
    }


def _eligible_rows(rows: list[ForecastRow], origin: date) -> list[ForecastRow]:
    return [row for row in rows if row.resolution_date < origin]


def select_wang_style(
    past_rows: list[ForecastRow], origin: date, target_kind: str
) -> tuple[str, int, int]:
    """Select on the latest 40% of earlier resolved origins with a 5% gain rail."""
    eligible = _eligible_rows(past_rows, origin)
    origins = sorted({row.origin_date for row in eligible})
    baseline = "persistence" if target_kind == "level" else "zero"
    if len(origins) < 3 or len(eligible) < 12:
        return baseline, len(eligible), len(origins)
    validation_start = origins[max(1, math.floor(0.60 * len(origins)))]
    validation = [row for row in eligible if row.origin_date >= validation_start]
    if len(validation) < 3:
        return baseline, len(validation), len({row.origin_date for row in validation})
    maes = {
        name: statistics.fmean(abs(row.actual - row.predictions[name]) for row in validation)
        for name in CANDIDATES
    }
    selected = min(CANDIDATES, key=lambda name: (maes[name], name))
    required = 0.05 * max(maes[baseline], 1e-8)
    if selected == baseline or maes[selected] + required >= maes[baseline]:
        selected = baseline
    return selected, len(validation), len({row.origin_date for row in validation})


def _interval_from_eligible(
    candidate: str,
    point: float,
    eligible: list[ForecastRow],
    history: list[Observation],
    residuals_by_candidate: dict[str, list[float]],
    residual_origins: int,
) -> tuple[tuple[float, float], str]:
    residuals = residuals_by_candidate[candidate]
    if len(residuals) >= 8 and residual_origins >= 3:
        half = max(1e-9, quantile(residuals, 0.90))
        source = "prior_origin_absolute_residual_q90"
    else:
        values = [row.target for row in history]
        if len(values) >= 2:
            center = _median(values)
            scale = _median([abs(value - center) for value in values])
            half = max(1e-9, 2.5 * scale)
        elif values:
            half = max(1e-9, abs(values[-1]) * 0.25)
        else:
            half = max(1.0, abs(point) * 0.5)
        source = "pre_origin_scale_fallback"
    return (point - half, point + half), source


def run_rolling_origin(observations: list[Observation]) -> list[ForecastRow]:
    if not observations:
        return []
    splits = chronological_splits(observations)
    grouped: dict[tuple[str, date], list[Observation]] = {}
    for observation in observations:
        grouped.setdefault((observation.family, observation.origin_date), []).append(observation)
    history_by_series: dict[tuple[str, str], list[Observation]] = {}
    past_rows_by_family: dict[str, list[ForecastRow]] = {}
    pending: list[Observation] = []
    results: list[ForecastRow] = []

    for family, origin in sorted(grouped, key=lambda item: (item[1], item[0])):
        # Release all outcomes that were public strictly before this origin.
        still_pending = []
        for item in pending:
            if item.resolution_date < origin:
                history_by_series.setdefault((item.family, item.entity_id), []).append(item)
            else:
                still_pending.append(item)
        pending = still_pending

        family_rows = past_rows_by_family.setdefault(family, [])
        eligible_family_rows = _eligible_rows(family_rows, origin)
        residual_origins = len({row.origin_date for row in eligible_family_rows})
        residuals_by_candidate = {
            candidate: [abs(row.actual - row.predictions[candidate]) for row in eligible_family_rows]
            for candidate in CANDIDATES
        }
        target_kind = grouped[(family, origin)][0].target_kind
        selected, validation_rows, validation_origins = select_wang_style(
            family_rows, origin, target_kind
        )
        new_rows: list[ForecastRow] = []
        for observation in sorted(grouped[(family, origin)], key=lambda row: (row.event_id, row.entity_id)):
            history = sorted(
                history_by_series.get((family, observation.entity_id), []),
                key=lambda row: (row.resolution_date, row.origin_date, row.event_id),
            )
            predictions = candidate_predictions(observation, history)
            predictions["wang_selector"] = predictions[selected]
            intervals: dict[str, tuple[float, float]] = {}
            sources: dict[str, str] = {}
            for candidate, point in predictions.items():
                residual_name = selected if candidate == "wang_selector" else candidate
                intervals[candidate], sources[candidate] = _interval_from_eligible(
                    residual_name,
                    point,
                    eligible_family_rows,
                    history,
                    residuals_by_candidate,
                    residual_origins,
                )
            latest = max((row.resolution_date for row in history), default=None)
            new_rows.append(ForecastRow(
                family=family,
                event_id=observation.event_id,
                entity_id=observation.entity_id,
                origin_date=origin,
                resolution_date=observation.resolution_date,
                split=splits[(family, origin)],
                actual=observation.target,
                history_count=len(history),
                predictions=predictions,
                intervals=intervals,
                interval_sources=sources,
                selected_model=selected,
                selector_validation_rows=validation_rows,
                selector_validation_origins=validation_origins,
                latest_training_resolution=latest,
            ))
        # Rows from this event become selector evidence only after their resolution.
        family_rows.extend(new_rows)
        results.extend(new_rows)
        pending.extend(grouped[(family, origin)])
    return sorted(results, key=lambda row: (row.origin_date, row.family, row.event_id, row.entity_id))


def interval_score(actual: float, interval: tuple[float, float], level: float = 0.90) -> float:
    lo, hi = interval
    alpha = 1.0 - level
    score = hi - lo
    if actual < lo:
        score += 2.0 / alpha * (lo - actual)
    elif actual > hi:
        score += 2.0 / alpha * (actual - hi)
    return score


def score_rows(rows: list[ForecastRow], candidate: str, naive: str) -> dict[str, float | int]:
    if not rows:
        return {"rows": 0, "origins": 0, "mae": 0.0, "naive_mae": 0.0,
                "predictive_quality": 0.0, "mean_interval_score": 0.0,
                "naive_mean_interval_score": 0.0, "interval_quality": 0.0,
                "composite": 0.0, "interval_coverage": 0.0}
    errors = [abs(row.actual - row.predictions[candidate]) for row in rows]
    naive_errors = [abs(row.actual - row.predictions[naive]) for row in rows]
    mae = statistics.fmean(errors)
    naive_mae = statistics.fmean(naive_errors)
    quality = naive_mae / (naive_mae + mae) if naive_mae + mae > 0 else 0.5
    scores = [interval_score(row.actual, row.intervals[candidate]) for row in rows]
    naive_scores = [interval_score(row.actual, row.intervals[naive]) for row in rows]
    mean_score = statistics.fmean(scores)
    naive_mean_score = statistics.fmean(naive_scores)
    raw_interval_quality = (
        naive_mean_score / (naive_mean_score + mean_score)
        if naive_mean_score + mean_score > 0 else 0.5
    )
    interval_quality = min(raw_interval_quality, max(0.5, quality))
    coverage = statistics.fmean(
        float(row.intervals[candidate][0] <= row.actual <= row.intervals[candidate][1])
        for row in rows
    )
    return {
        "rows": len(rows),
        "origins": len({row.origin_date for row in rows}),
        "mae": mae,
        "naive_mae": naive_mae,
        "predictive_quality": quality,
        "mean_interval_score": mean_score,
        "naive_mean_interval_score": naive_mean_score,
        "interval_quality": interval_quality,
        "composite": 0.70 * quality + 0.30 * interval_quality,
        "interval_coverage": coverage,
    }
