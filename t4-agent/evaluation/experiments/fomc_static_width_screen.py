#!/usr/bin/env python3
"""Time-split screen for one wider static FOMC interval half-width."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


TENORS = ("UST2Y", "UST3Y", "UST5Y", "UST7Y", "UST10Y", "UST30Y")
SENSITIVITY = {"UST2Y": 1.0, "UST3Y": 0.8, "UST5Y": 0.8, "UST7Y": 0.6, "UST10Y": 0.6, "UST30Y": 0.4}
PUBLIC_DIAGNOSTIC_DATES = {"2022-07-27", "2024-09-18"}
BASELINE_HALF_WIDTH = 50.0
CANDIDATE_HALF_WIDTHS = tuple(float(value) for value in range(50, 101, 5))


def score(events: list[dict], half_width: float) -> dict[str, float | int]:
    hits = []
    for event in events:
        for tenor in TENORS:
            point = 15.0 * event["policy_direction"] * SENSITIVITY[tenor]
            truth = event["yield_changes_bps"][tenor]
            hits.append(abs(truth - point) <= half_width)
    coverage = sum(hits) / len(hits)
    return {
        "events": len(events),
        "observations": len(hits),
        "coverage": coverage,
        "calibration_loss": abs(coverage - 0.90),
        "full_width_bps": 2.0 * half_width,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline-commit", required=True)
    args = parser.parse_args()

    document = json.loads(args.dataset.read_text())
    events = document["events"]
    development = [
        event
        for event in events
        if event["decision_date"][:4] in {"2022", "2023"}
        and event["decision_date"] not in PUBLIC_DIAGNOSTIC_DATES
    ]
    test = [
        event
        for event in events
        if event["decision_date"][:4] in {"2024", "2025"}
        and event["decision_date"] not in PUBLIC_DIAGNOSTIC_DATES
    ]
    confirmation = [event for event in events if event["decision_date"].startswith("2026-")]
    public_diagnostic = [event for event in events if event["decision_date"] in PUBLIC_DIAGNOSTIC_DATES]

    development_battery = [
        {"half_width_bps": width, **score(development, width)} for width in CANDIDATE_HALF_WIDTHS
    ]
    selected = min(development_battery, key=lambda item: (item["calibration_loss"], item["half_width_bps"]))
    selected_width = float(selected["half_width_bps"])
    periods = {
        name: {
            "baseline": score(values, BASELINE_HALF_WIDTH),
            "candidate": score(values, selected_width),
        }
        for name, values in (
            ("test", test),
            ("confirmation", confirmation),
            ("public_diagnostic_after_lock", public_diagnostic),
        )
    }
    passes = (
        periods["test"]["candidate"]["calibration_loss"]
        <= periods["test"]["baseline"]["calibration_loss"]
        and periods["confirmation"]["candidate"]["calibration_loss"]
        <= periods["confirmation"]["baseline"]["calibration_loss"]
    )
    report = {
        "schema_version": 1,
        "experiment": "fomc_static_width_screen_v1",
        "baseline_git_commit": args.baseline_commit,
        "dataset": str(args.dataset),
        "source": document["source"],
        "hypothesis": "A recent-regime-selected static half-width improves FOMC interval calibration without changing points or evidence.",
        "development_period": "2022-01-01/2023-12-31",
        "test_period": "2024-01-01/2025-12-31",
        "confirmation_period": "2026-01-01/2026-09-15",
        "excluded_from_selection_test_confirmation": sorted(PUBLIC_DIAGNOSTIC_DATES),
        "development_battery": development_battery,
        "selected_half_width_bps": selected_width,
        "periods": periods,
        "decision_rule": "Proceed only if the development-selected width is non-inferior to the 50 bps baseline on both test and confirmation calibration loss.",
        "decision": "proceed_to_production_validation" if passes else "reject",
        "production_change": "none" if not passes else "requires reliability validation",
        "model_api": {"requests": 0, "input_tokens": 0, "output_tokens": 0},
        "local_llm_run": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"selected_half_width_bps": selected_width, "periods": periods, "decision": report["decision"]}, indent=2))


if __name__ == "__main__":
    main()
