#!/usr/bin/env python3
"""Audit that structural fallback requires usable values, not only field names."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from evaluation.experiments.structural_router_fallback import POSITIVE_CASES  # noqa: E402
from t4agent.family_specs import task_family_spec  # noqa: E402


UNUSABLE_CASES = (
    ("eps_consensus_null", "classification", {"consensus_eps": None, "threshold_pct": 0.05}),
    (
        "eps_yoy_nan",
        "classification",
        {"prior_year_q_eps": math.nan, "prior_year_quarter": "Q2", "quarter_reported": "Q2"},
    ),
    (
        "reaction_blank",
        "classification",
        {"report_datetime": " ", "event_window": "next_day", "benchmark": "SPY", "flat_threshold_abn_pct": 1.0},
    ),
    (
        "macro_revision_null",
        "classification",
        {"latest_precutoff_estimate": None, "latest_precutoff_vintage": "2026-01-01", "resolving_release_date": "2026-02-01"},
    ),
    (
        "bank_eps_blank",
        "regression",
        {"cik": "", "prior_year_q_eps": 1.0, "prior_year_quarter": "Q2", "quarter_reported": "Q2"},
    ),
    ("rates_infinite", "regression", {"maturity_years": 2, "start_yield_pct": math.inf, "as_of": "2026-01-01"}),
    (
        "cpi_null",
        "regression",
        {"series_fred": "CPI", "ref_month": "2026-01", "latest_published_mom_pct": None, "latest_published_ref_month": "2025-12"},
    ),
    (
        "auction_blank",
        "regression",
        {"tenor": "10Y", "auction_date": "2026-01-01", "new_or_reopening": " ", "offering_amount_usd_bn": 40},
    ),
    (
        "positioning_null_prefix",
        "ranking",
        {"asset_class": "rates", "net_noncommercial_20260901": 1, "open_interest_20260901": None, "net_pct_oi_20260901": 0.5},
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    positives = [
        {
            "expected": expected,
            "candidate": task_family_spec("unseen_finance", "opaque_target", target_type, [dict(entity)]).key,
        }
        for expected, target_type, entity in POSITIVE_CASES
    ]
    unusable = [
        {
            "case_id": case_id,
            "candidate": task_family_spec("unseen_finance", "opaque_target", target_type, [dict(entity)]).key,
        }
        for case_id, target_type, entity in UNUSABLE_CASES
    ]
    report = {
        "schema_version": 1,
        "experiment": "structural_router_value_guard_v1",
        "layer": "L2 cross-family task routing",
        "hypothesis": "Requiring usable roster-wide values for a structural signature prevents incomplete hidden tasks from entering specialists without losing complete renamed tasks.",
        "baseline_git_commit": "cde29508690543825dd09e255776d51dc3898d46",
        "positive_cases": positives,
        "unusable_cases": unusable,
        "results": {
            "complete_recovered": sum(row["candidate"] == row["expected"] for row in positives),
            "complete_total": len(positives),
            "unusable_kept_generic": sum(row["candidate"] == "generic" for row in unusable),
            "unusable_total": len(unusable),
        },
        "decision_rule": "Require 9/9 complete structures to recover, 9/9 null/blank/non-finite structures to remain generic, byte-identical public outputs, 11/11 schema and smoke, and no extra model calls.",
        "model_api": {"provider": None, "model": None, "requests": 0, "input_tokens": 0, "output_tokens": 0},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report["results"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
