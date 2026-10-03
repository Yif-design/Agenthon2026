#!/usr/bin/env python3
"""Compare the legacy generic median/order fallback with target-aware selection."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from statistics import median
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from t4agent.calc import numeric_facts, select_default_point  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    return parser.parse_args()


def legacy_default_point(
    target_type: str,
    target_name: str,
    entity: dict[str, Any],
    row_index: int,
    row_count: int,
) -> float:
    nums = numeric_facts(entity)
    name = target_name.lower()
    if "eps_yoy_growth_pct" in name or "yield_change_bps" in name:
        return 0.0
    if "cpi_component_mom" in name:
        return float(entity.get("latest_published_mom_pct") or 0.0)
    if "bid_to_cover" in name:
        return 2.5
    if "position" in name or target_type == "ranking":
        return float(
            entity.get("trailing_4wk_net_change_pct_oi")
            or entity.get("net_pct_oi_20241022")
            or (row_count - row_index)
        )
    return float(median(nums.values())) if nums else 0.0


def candidate_point(
    target_type: str,
    target_name: str,
    entity: dict[str, Any],
    row_index: int,
    row_count: int,
) -> float:
    return select_default_point(target_type, target_name, entity, row_index, row_count)[0]


def build_report() -> dict[str, Any]:
    regression = {
        "latest_revenue_growth_pct": 8.0,
        "market_cap_bn": 200.0,
        "fiscal_year": 2024,
    }
    regression_noise = {**regression, "internal_row_id": 999999}
    change = {"start_yield_pct": 4.5, "maturity_years": 2, "fiscal_year": 2024}
    rank_entities = {
        "A": {"recent_net_flow_change_pct_oi": -3.0, "market_size_bn": 100.0},
        "B": {"recent_net_flow_change_pct_oi": 4.0, "market_size_bn": 200.0},
    }

    systems = {"baseline": legacy_default_point, "candidate": candidate_point}
    results: dict[str, Any] = {}
    for system, choose in systems.items():
        base = choose("regression", "revenue_growth_next_q_pct", regression, 0, 1)
        noisy = choose("regression", "revenue_growth_next_q_pct", regression_noise, 0, 1)
        change_point = choose("regression", "yield_delta_bps", change, 0, 1)
        order_ab = {
            entity_id: choose("ranking", "five_week_net_flow_change_pct_oi", rank_entities[entity_id], index, 2)
            for index, entity_id in enumerate(("A", "B"))
        }
        order_ba = {
            entity_id: choose("ranking", "five_week_net_flow_change_pct_oi", rank_entities[entity_id], index, 2)
            for index, entity_id in enumerate(("B", "A"))
        }
        single = choose("regression", "unknown_metric", {"latest_value": 12.0}, 0, 1)
        checks = {
            "target_related_level_selected": math.isclose(base, 8.0),
            "irrelevant_numeric_noise_invariant": math.isclose(base, noisy),
            "change_target_does_not_reuse_level": math.isclose(change_point, 0.0),
            "ranking_is_row_order_invariant": order_ab == order_ba,
            "single_numeric_fallback_preserved": math.isclose(single, 12.0),
        }
        results[system] = {
            "values": {
                "regression_base": base,
                "regression_with_noise": noisy,
                "change_without_delta_feature": change_point,
                "ranking_order_ab": order_ab,
                "ranking_order_ba": order_ba,
                "single_numeric": single,
            },
            "checks": checks,
            "checks_passed": sum(checks.values()),
            "checks_total": len(checks),
        }
    return {
        "schema_version": 1,
        "experiment": "generic_target_aware_baseline_v1",
        "baseline_git_commit": "bb81ce7a1c7c3423ec6987d1da960bd583e2f075",
        "scope": "Synthetic robustness checks for unknown regression and ranking targets.",
        "not_measured": "Predictive accuracy; these checks test invariants and target-field alignment only.",
        "results": results,
        "decision_rule": "Accept only if candidate passes 5/5, preserves the single-field fallback, and public known-family predictions do not change.",
    }


def main() -> None:
    args = parse_args()
    report = build_report()
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
