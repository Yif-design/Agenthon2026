#!/usr/bin/env python3
"""Confirm the locked post-earnings label prior on a new classification holdout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from postearn_ticker_prior import baseline, evaluate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--locked-report", type=Path, required=True)
    parser.add_argument("--confirmation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    history_doc = json.loads(args.history.read_text())
    locked = json.loads(args.locked_report.read_text())
    confirmation_doc = json.loads(args.confirmation.read_text())
    selected = locked["selection"]["selected"]
    if (selected["method"], selected["strength"]) != ("ticker_recent4", 0):
        raise ValueError("unexpected locked candidate")
    events = confirmation_doc["events"]
    before = baseline(events)
    after = evaluate(
        history_doc["events"], events, selected["method"], selected["strength"]
    )
    coverage_equal = after["coverage_fixed_interval"] == before["coverage_fixed_interval"]
    quality_pass = after["accuracy"] > before["accuracy"] and coverage_equal
    report = {
        "experiment_id": "postearn_classification_holdout_v2",
        "date": "2026-09-28",
        "baseline_git_commit": "0f92f1041b047554d429ea5bb43a96f45567d4ab",
        "hypothesis": "For a classification unit, the locked ticker_recent4 label prior improves the scored accuracy while a fixed interval preserves calibration; point MAE is diagnostic rather than an acceptance gate.",
        "official_scoring": {
            "classification_metric": "label accuracy",
            "interval_metric": "absolute coverage gap from interval_level",
            "source": "https://github.com/Agenthon-2026/track4-analysis-public/blob/main/README.md#scoring-formula"
        },
        "locked_candidate_source": str(args.locked_report),
        "locked_candidate": {"method": selected["method"], "strength": selected["strength"]},
        "fit_data": "2018-2023 only",
        "confirmation_dataset": str(args.confirmation),
        "confirmation_range": confirmation_doc["requested_event_range"],
        "baseline": before,
        "candidate": after,
        "accuracy_delta": after["accuracy"] - before["accuracy"],
        "mae_delta_diagnostic_only": after["mae_pct"] - before["mae_pct"],
        "coverage_equal": coverage_equal,
        "outcome_quality_gate": "pass" if quality_pass else "fail",
        "faithfulness_gate": "not_run_remote_official_models_unavailable",
        "decision": "defer_pending_official_nli" if quality_pass else "reject",
        "production_change": "none",
        "model_api_calls": 0,
        "local_llm_run": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
