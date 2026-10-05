#!/usr/bin/env python3
"""Audit strict entity-shape fallback routing for renamed known task structures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from evaluation.experiments.router_collision_audit import COLLISIONS  # noqa: E402
from t4agent.family_specs import family_spec, task_family_spec  # noqa: E402


POSITIVE_CASES = (
    ("eps_consensus", "classification", {"consensus_eps": 1.2, "threshold_pct": 0.05}),
    ("eps_yoy", "classification", {"prior_year_q_eps": 1.0, "prior_year_quarter": "Q2", "quarter_reported": "Q2"}),
    (
        "reaction",
        "classification",
        {"report_datetime": "2026-01-01", "event_window": "next_day", "benchmark": "SPY", "flat_threshold_abn_pct": 1.0},
    ),
    (
        "macro_revision",
        "classification",
        {"latest_precutoff_estimate": 1.0, "latest_precutoff_vintage": "2026-01-01", "resolving_release_date": "2026-02-01"},
    ),
    (
        "bank_eps",
        "regression",
        {"cik": "1", "prior_year_q_eps": 1.0, "prior_year_quarter": "Q2", "quarter_reported": "Q2"},
    ),
    ("rates", "regression", {"maturity_years": 2, "start_yield_pct": 4.0, "as_of": "2026-01-01"}),
    (
        "cpi",
        "regression",
        {"series_fred": "CPI", "ref_month": "2026-01", "latest_published_mom_pct": 0.2, "latest_published_ref_month": "2025-12"},
    ),
    (
        "auction",
        "regression",
        {"tenor": "10Y", "auction_date": "2026-01-01", "new_or_reopening": "new", "offering_amount_usd_bn": 40},
    ),
    (
        "positioning",
        "ranking",
        {"asset_class": "rates", "net_noncommercial_20260901": 1, "open_interest_20260901": 2, "net_pct_oi_20260901": 0.5},
    ),
)


def _negative_cases() -> list[tuple[str, str, str, list[dict]]]:
    rows = []
    for expected, target_type, entity in POSITIVE_CASES:
        partial = dict(entity)
        partial.pop(next(reversed(partial)))
        rows.append((f"partial_{expected}", target_type, "opaque_target", [partial]))
        wrong_type = "ranking" if target_type != "ranking" else "classification"
        rows.append((f"wrong_type_{expected}", wrong_type, "opaque_target", [dict(entity)]))
    rates = dict(POSITIVE_CASES[5][2])
    cpi = dict(POSITIVE_CASES[6][2])
    rows.append(("ambiguous_regression", "regression", "opaque_target", [{**rates, **cpi}]))
    partial_roster = dict(rates)
    partial_roster.pop("as_of")
    rows.append(("inconsistent_roster", "regression", "opaque_target", [rates, partial_roster]))
    for family, target in COLLISIONS:
        rows.append((f"collision_{family}", "classification", target, [{"entity_id": "A", "name": "A"}]))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    positives = []
    for expected, target_type, entity in POSITIVE_CASES:
        legacy = family_spec("unseen_finance", "opaque_target").key
        candidate = task_family_spec("unseen_finance", "opaque_target", target_type, [dict(entity)]).key
        positives.append({"expected": expected, "target_type": target_type, "legacy": legacy, "candidate": candidate, "correct": candidate == expected})
    negatives = []
    for case_id, target_type, target_name, entities in _negative_cases():
        candidate = task_family_spec("unseen_finance", target_name, target_type, entities).key
        negatives.append({"case_id": case_id, "target_type": target_type, "candidate": candidate, "generic": candidate == "generic"})
    report = {
        "schema_version": 1,
        "experiment": "structural_router_fallback_v1",
        "layer": "L2 cross-family task routing",
        "hypothesis": "A unique roster-wide entity-field signature can recover a known specialist after name routing fails without reintroducing substring collisions or partial-shape guesses.",
        "baseline_git_commit": "ae1e6312e0e6bdec49e2e697794a16e630589998",
        "positive_cases": positives,
        "negative_cases": negatives,
        "results": {
            "legacy_positive_recovered": sum(row["legacy"] == row["expected"] for row in positives),
            "candidate_positive_recovered": sum(row["correct"] for row in positives),
            "positive_total": len(positives),
            "candidate_negative_generic": sum(row["generic"] for row in negatives),
            "negative_total": len(negatives),
        },
        "decision_rule": "Require 9/9 renamed complete structures to recover, every partial/wrong-type/ambiguous/collision case to remain generic, public outputs to be byte-identical, 11/11 schema and smoke, and no extra model calls.",
        "model_api": {"provider": None, "model": None, "requests": 0, "input_tokens": 0, "output_tokens": 0},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["results"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
