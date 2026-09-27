from __future__ import annotations

import math
import re


FIELD_TOKEN_RE = re.compile(r"[A-Za-z]+|[0-9]+")
CHANGE_TOKENS = {"change", "delta", "growth", "return", "revision", "shift", "move"}
CURRENT_BASELINE_TOKENS = {"latest", "current", "recent", "trailing", "precutoff"}
REFERENCE_BASELINE_TOKENS = {"start", "baseline"}
METADATA_TOKENS = {
    "id",
    "cik",
    "year",
    "month",
    "day",
    "date",
    "count",
    "index",
    "code",
    "threshold",
    "maturity",
    "amount",
    "cap",
    "size",
}
TARGET_NOISE_TOKENS = {
    "forecast",
    "prediction",
    "predicted",
    "target",
    "next",
    "future",
    "rank",
    "ranking",
    "pct",
    "percent",
    "bps",
    "value",
    "metric",
}


def numeric_facts(entity: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in entity.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            out[key] = float(value)
    return out


def default_point(target_type: str, target_name: str, entity: dict, row_index: int, row_count: int) -> float:
    return select_default_point(target_type, target_name, entity, row_index, row_count)[0]


def select_default_point(
    target_type: str,
    target_name: str,
    entity: dict,
    row_index: int,
    row_count: int,
) -> tuple[float, str | None, str]:
    """Choose a generic baseline without mixing unrelated numeric metadata."""
    nums = numeric_facts(entity)
    name = target_name.lower()
    if "eps_yoy_growth_pct" in name:
        return 0.0, None, "known_change_neutral"
    if "yield_change_bps" in name:
        return 0.0, None, "known_change_neutral"
    if "cpi_component_mom" in name:
        return float(entity.get("latest_published_mom_pct") or 0.0), "latest_published_mom_pct", "known_latest"
    if "bid_to_cover" in name:
        return 2.5, None, "known_constant"

    target_tokens = _field_tokens(target_name) - TARGET_NOISE_TOKENS
    requires_change = target_type in {"regression", "ranking"} and bool(target_tokens & CHANGE_TOKENS)
    candidates: list[tuple[int, str, float]] = []
    eligible: list[tuple[str, float]] = []
    for key, value in nums.items():
        field_tokens = _field_tokens(key)
        overlap = target_tokens & field_tokens
        if requires_change and not field_tokens & CHANGE_TOKENS:
            continue
        if not field_tokens & METADATA_TOKENS or overlap:
            eligible.append((key, value))
        score = 10 * len(overlap)
        score += 2 if field_tokens & CURRENT_BASELINE_TOKENS else 0
        score += 1 if field_tokens & REFERENCE_BASELINE_TOKENS else 0
        score -= 8 if field_tokens & METADATA_TOKENS and not overlap else 0
        if overlap and score > 0:
            candidates.append((score, key, value))
    if candidates:
        _, key, value = sorted(candidates, key=lambda item: (-item[0], item[1]))[0]
        return float(value), key, "target_token_match"
    if requires_change:
        return 0.0, None, "change_without_matching_baseline"
    if len(eligible) == 1:
        key, value = eligible[0]
        return float(value), key, "single_numeric_fallback"
    return 0.0, None, "no_unambiguous_baseline"


def _field_tokens(value: str) -> set[str]:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).replace("_", " ")
    return {token.lower() for token in FIELD_TOKEN_RE.findall(separated)}


def interval_for(point: float | None, target_name: str, level: float) -> dict[str, float]:
    center = float(point or 0.0)
    name = target_name.lower()
    if "yield_change_bps" in name:
        half = 75.0
    elif "eps_yoy_growth_pct" in name:
        half = 60.0
    elif "cpi_component_mom" in name:
        half = 0.6
    elif "bid_to_cover" in name:
        half = 0.8
    elif "position" in name:
        half = 8.0
    else:
        half = max(abs(center) * 0.5, 1.0)
    return {"level": float(level), "lo": center - half, "hi": center + half}
