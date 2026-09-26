from __future__ import annotations

import math
from statistics import median


def numeric_facts(entity: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in entity.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            out[key] = float(value)
    return out


def default_point(target_type: str, target_name: str, entity: dict, row_index: int, row_count: int) -> float:
    nums = numeric_facts(entity)
    name = target_name.lower()
    if "eps_yoy_growth_pct" in name:
        return 0.0
    if "yield_change_bps" in name:
        return 0.0
    if "cpi_component_mom" in name:
        return float(entity.get("latest_published_mom_pct") or 0.0)
    if "bid_to_cover" in name:
        return 2.5
    if "position" in name or target_type == "ranking":
        return float(entity.get("trailing_4wk_net_change_pct_oi") or entity.get("net_pct_oi_20241022") or (row_count - row_index))
    if nums:
        vals = list(nums.values())
        return median(vals)
    return 0.0


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
