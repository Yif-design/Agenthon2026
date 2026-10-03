#!/usr/bin/env python3
"""Compare legacy substring routing with anchored known-family signatures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from t4agent.family_specs import family_spec  # noqa: E402


PUBLIC = (
    ("eps_beat_consensus", "eps_outcome", "eps_consensus"),
    ("auction_demand", "bid_to_cover_ratio", "auction"),
    ("positioning_shift", "net_positioning_change_pct_oi_rank", "positioning"),
    ("cpi_component_nowcast", "cpi_component_mom_first_print", "cpi"),
    ("credit_event", "credit_event_12m", "credit"),
    ("eps_growth_regression", "eps_yoy_growth_pct", "bank_eps"),
    ("eps_yoy_direction", "eps_yoy_direction", "eps_yoy"),
    ("rate_curve_cross_section", "yield_change_bps_intermeeting", "rates"),
    ("macro_revision_direction", "next_estimate_revision_direction", "macro_revision"),
    ("post_earnings_reaction", "earnings_reaction", "reaction"),
)

VARIANTS = (
    ("eps_beat_consensus_v2", "future_eps_class", "eps_consensus"),
    ("", "eps_beat_consensus_probability", "eps_consensus"),
    ("credit_event_cross_section", "event_probability", "credit"),
    ("post_earnings_reaction_v2", "abnormal_return_class", "reaction"),
    ("rate_curve_scenario", "tenor_move", "rates"),
    ("cpi_component_forecast", "first_print", "cpi"),
    ("macro_revision_panel", "direction", "macro_revision"),
    ("auction_demand_panel", "ratio", "auction"),
    ("positioning_shift_panel", "rank", "positioning"),
    ("cftc_positioning_panel", "rank", "positioning"),
)

COLLISIONS = (
    ("inventory_forecast", "inventory_position_rank"),
    ("housing", "auction_price_change"),
    ("equity_research", "analyst_revision_probability"),
    ("agriculture", "cotton_yield_rank"),
    ("marketing", "credit_eventual_return"),
    ("sports", "rate_curveball_score"),
    ("supply_chain", "positioning_of_inventory"),
)


def legacy_route(family: str, target: str) -> str:
    text = f"{family} {target}".lower()
    if target == "eps_outcome" or "eps_beat_consensus" in text:
        return "eps_consensus"
    if target == "eps_yoy_direction":
        return "eps_yoy"
    if target == "eps_yoy_growth_pct":
        return "bank_eps"
    if "credit_event" in text:
        return "credit"
    if "earnings_reaction" in text or "post_earnings_reaction" in text:
        return "reaction"
    if "yield_change_bps" in text or "rate_curve" in text:
        return "rates"
    if "cpi_component" in text:
        return "cpi"
    if "revision" in text:
        return "macro_revision"
    if "bid_to_cover" in text or "auction" in text:
        return "auction"
    if "position" in text or "cot" in text:
        return "positioning"
    return "generic"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    known = []
    for source, cases in (("public", PUBLIC), ("variant", VARIANTS)):
        for family, target, expected in cases:
            actual = family_spec(family, target).key
            known.append({"source": source, "family": family, "target": target, "expected": expected, "actual": actual, "correct": actual == expected})
    collisions = []
    for family, target in COLLISIONS:
        before = legacy_route(family, target)
        after = family_spec(family, target).key
        collisions.append({"family": family, "target": target, "legacy": before, "candidate": after, "candidate_generic": after == "generic"})
    report = {
        "schema_version": 1,
        "experiment": "router_signature_collision_v1",
        "baseline_git_commit": "6d5d731c1505e62e56737541927c87b32b631d99",
        "hypothesis": "Complete target/family token signatures retain known tools while preventing incidental substrings in unseen targets from bypassing the generic path.",
        "known_cases": known,
        "collision_cases": collisions,
        "results": {
            "known_correct": sum(row["correct"] for row in known),
            "known_total": len(known),
            "public_correct": sum(row["correct"] for row in known if row["source"] == "public"),
            "public_total": sum(row["source"] == "public" for row in known),
            "variant_correct": sum(row["correct"] for row in known if row["source"] == "variant"),
            "variant_total": sum(row["source"] == "variant" for row in known),
            "legacy_collision_misroutes": sum(row["legacy"] != "generic" for row in collisions),
            "candidate_collisions_to_generic": sum(row["candidate_generic"] for row in collisions),
            "collision_total": len(collisions),
        },
        "decision_rule": "Require every public and anchored-variant route to remain correct, all seven incidental-substring cases to route generic, byte-identical public outputs and no added model calls.",
        "not_measured": "Predictive quality for organizer-hidden family names; variants and collisions are synthetic routing tests.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["results"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
