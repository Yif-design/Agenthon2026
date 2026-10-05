#!/usr/bin/env python3
"""Test policy-change-scaled interval widths on recent FOMC events."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

TENORS = ("UST2Y", "UST3Y", "UST5Y", "UST7Y", "UST10Y", "UST30Y")
SENSITIVITY = {"UST2Y": 1.0, "UST3Y": 0.8, "UST5Y": 0.8, "UST7Y": 0.6, "UST10Y": 0.6, "UST30Y": 0.4}
PUBLIC_DIAGNOSTIC_DATES = {"2022-07-27", "2024-09-18"}
CANDIDATE_SCALES = (0.0, 0.25, 0.5, 0.75, 1.0)


def score(events: list[dict], scale: float) -> dict[str, float | int]:
    hits = 0
    widths = []
    for event in events:
        half_width = 50.0 + scale * abs(event["policy_change_bps"])
        for tenor in TENORS:
            point = 15.0 * event["policy_direction"] * SENSITIVITY[tenor]
            truth = event["yield_changes_bps"][tenor]
            hits += abs(truth - point) <= half_width
            widths.append(2.0 * half_width)
    coverage = hits / len(widths)
    return {
        "events": len(events),
        "observations": len(widths),
        "coverage": coverage,
        "calibration_loss": abs(coverage - 0.90),
        "mean_full_width_bps": statistics.fmean(widths),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.dataset.read_text())
    events = document["events"]
    development = [
        event
        for event in events
        if 2022 <= int(event["decision_date"][:4]) <= 2025
        and event["decision_date"] not in PUBLIC_DIAGNOSTIC_DATES
    ]
    confirmation = [event for event in events if event["decision_date"].startswith("2026-")]
    public_diagnostic = [event for event in events if event["decision_date"] in PUBLIC_DIAGNOSTIC_DATES]
    battery = [{"scale": scale, **score(development, scale)} for scale in CANDIDATE_SCALES]
    selected = min(battery, key=lambda item: (item["calibration_loss"], item["mean_full_width_bps"]))
    scale = float(selected["scale"])
    baseline_confirmation = score(confirmation, 0.0)
    candidate_confirmation = score(confirmation, scale)
    decision = (
        "consider"
        if candidate_confirmation["calibration_loss"] < baseline_confirmation["calibration_loss"]
        else "reject"
    )
    result = {
        "dataset": str(args.dataset),
        "source": document["source"],
        "hypothesis": "Scale the fixed 50 bps half-width by one quarter of the absolute FOMC target-rate change.",
        "development_period": "2022-01-01/2025-12-31",
        "confirmation_period": "2026-01-01/2026-09-15",
        "excluded_from_selection_and_confirmation": sorted(PUBLIC_DIAGNOSTIC_DATES),
        "candidate_battery": battery,
        "selected_scale": scale,
        "confirmation": {
            "baseline": baseline_confirmation,
            "candidate": candidate_confirmation,
        },
        "public_diagnostic_after_lock": {
            "baseline": score(public_diagnostic, 0.0),
            "candidate": score(public_diagnostic, scale),
        },
        "decision_rule": "Require strictly lower calibration loss on the one-time 2026 confirmation set.",
        "decision": decision,
        "decision_reason": (
            "The 2026 confirmation meetings all held the target range unchanged, so the candidate was identical to the baseline and supplied no independent evidence."
            if decision == "reject"
            else "The locked scale improved confirmation calibration."
        ),
        "production_change": "none" if decision == "reject" else "requires reliability validation",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
