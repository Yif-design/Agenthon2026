#!/usr/bin/env python3
"""Compare simple cutoff-safe CPI component forecasts and interval rules."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path


def point(name: str, history: list[float]) -> float:
    latest = history[-1]
    median3 = statistics.median(history[-3:])
    mean3 = statistics.fmean(history[-3:])
    if name == "zero":
        return 0.0
    if name == "latest":
        return latest
    if name == "current_mix":
        return 0.7 * latest + 0.3 * median3
    if name == "median3":
        return median3
    if name == "mean3":
        return mean3
    if name == "half_latest_half_mean3":
        return 0.5 * latest + 0.5 * mean3
    if name == "trend_damped":
        return latest + 0.25 * (latest - history[-2])
    raise KeyError(name)


def metrics(rows: list[dict], name: str) -> dict:
    errors = [point(name, row["known_mom_pct"]) - row["target_mom_pct"] for row in rows]
    return {
        "rows": len(rows),
        "mae": statistics.fmean(abs(value) for value in errors),
        "rmse": math.sqrt(statistics.fmean(value * value for value in errors)),
        "direction_accuracy": statistics.fmean(
            (point(name, row["known_mom_pct"]) >= 0) == (row["target_mom_pct"] >= 0) for row in rows
        ),
    }


def coverage(rows: list[dict], name: str, floor: float, multiplier: float) -> tuple[float, float]:
    hits, widths = [], []
    for row in rows:
        history = row["known_mom_pct"][-9:]
        half = max(floor, multiplier * statistics.pstdev(history))
        hits.append(abs(point(name, row["known_mom_pct"]) - row["target_mom_pct"]) <= half)
        widths.append(2.0 * half)
    return statistics.fmean(hits), statistics.fmean(widths)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.dataset.read_text())["rows"]
    splits = {
        "train": [row for row in rows if row["ref_month"][:4] <= "2020"],
        "dev": [row for row in rows if row["ref_month"][:4] == "2021"],
        "test": [row for row in rows if "2022" <= row["ref_month"][:4] <= "2023"],
    }
    names = ("zero", "latest", "current_mix", "median3", "mean3", "half_latest_half_mean3", "trend_damped")
    dev_scores = {name: metrics(splits["dev"], name) for name in names}
    selected = min(names, key=lambda name: (dev_scores[name]["mae"], dev_scores[name]["rmse"]))
    test_scores = {name: metrics(splits["test"], name) for name in names}

    interval_candidates = []
    for floor in (0.2, 0.35, 0.5, 0.75):
        for multiplier in (1.0, 1.25, 1.5, 1.65, 2.0, 2.5):
            dev_coverage, dev_width = coverage(splits["dev"], "current_mix", floor, multiplier)
            interval_candidates.append({
                "floor": floor,
                "multiplier": multiplier,
                "dev_coverage": dev_coverage,
                "dev_mean_width": dev_width,
            })
    selected_interval = min(
        interval_candidates,
        key=lambda item: (abs(item["dev_coverage"] - 0.90), item["dev_mean_width"]),
    )
    current_test_coverage, current_test_width = coverage(splits["test"], "current_mix", 0.35, 1.65)
    candidate_test_coverage, candidate_test_width = coverage(
        splits["test"], "current_mix", selected_interval["floor"], selected_interval["multiplier"]
    )
    result = {
        "dataset": str(args.dataset),
        "split_row_counts": {name: len(items) for name, items in splits.items()},
        "dev_scores": dev_scores,
        "point_selected_on_dev": selected,
        "test_scores": test_scores,
        "point_decision": "consider" if test_scores[selected]["mae"] < test_scores["current_mix"]["mae"] else "reject",
        "interval_selected_on_dev": selected_interval,
        "test_interval": {
            "current_coverage": current_test_coverage,
            "current_mean_width": current_test_width,
            "candidate_coverage": candidate_test_coverage,
            "candidate_mean_width": candidate_test_width,
            "current_calibration_loss": abs(current_test_coverage - 0.90),
            "candidate_calibration_loss": abs(candidate_test_coverage - 0.90),
        },
    }
    result["interval_decision"] = (
        "consider"
        if result["test_interval"]["candidate_calibration_loss"] < result["test_interval"]["current_calibration_loss"]
        else "reject"
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
