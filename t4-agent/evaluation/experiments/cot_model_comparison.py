#!/usr/bin/env python3
"""Time-forward COT point/ranking and interval model comparison."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path


def ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index], reverse=True)
    result = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        average = ((cursor + 1) + end) / 2.0
        for index in order[cursor:end]:
            result[index] = average
        cursor = end
    return result


def correlation(left: list[float], right: list[float]) -> float:
    lmean, rmean = statistics.fmean(left), statistics.fmean(right)
    numerator = sum((a - lmean) * (b - rmean) for a, b in zip(left, right))
    denominator = math.sqrt(sum((a - lmean) ** 2 for a in left) * sum((b - rmean) ** 2 for b in right))
    return numerator / denominator if denominator else 0.0


def point(name: str, row: dict) -> float:
    trend = row["trailing_4wk_net_change_pct_oi"]
    if name == "zero":
        return 0.0
    if name == "trend":
        return trend
    if name == "half_trend":
        return 0.5 * trend
    if name == "crowding_cap":
        return 0.5 * trend if row["crowded"] else trend
    if name == "mean_reversion":
        return -0.2 * row["current_net_pct_oi"]
    raise KeyError(name)


def score(groups: list[dict], name: str) -> dict:
    correlations, errors = [], []
    for group in groups:
        predicted = [point(name, row) for row in group["rows"]]
        actual = [row["target_5wk_change_pct_start_oi"] for row in group["rows"]]
        correlations.append(correlation(ranks(predicted), ranks(actual)))
        errors.extend(abs(a - b) for a, b in zip(predicted, actual))
    return {"groups": len(groups), "mean_spearman": statistics.fmean(correlations), "mae_pct_oi": statistics.fmean(errors)}


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def interval_coverage(groups: list[dict], name: str, half_width: float | None = None) -> float:
    hits = []
    for group in groups:
        for row in group["rows"]:
            width = half_width if half_width is not None else max(4.0, 1.65 * row["history_pstdev_pct_oi"])
            hits.append(abs(row["target_5wk_change_pct_start_oi"] - point(name, row)) <= width)
    return statistics.fmean(hits)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.dataset.read_text())
    groups = document["groups"]
    splits = {
        "train": [group for group in groups if group["start_date"][:4] <= "2020"],
        "dev": [group for group in groups if group["start_date"][:4] == "2021"],
        "test": [group for group in groups if "2022" <= group["start_date"][:4] <= "2023"],
    }
    names = ("zero", "trend", "half_trend", "crowding_cap", "mean_reversion")
    dev_scores = {name: score(splits["dev"], name) for name in names}
    selected = max(names, key=lambda name: (dev_scores[name]["mean_spearman"], -dev_scores[name]["mae_pct_oi"]))
    test_scores = {name: score(splits["test"], name) for name in names}

    train_errors = [
        abs(row["target_5wk_change_pct_start_oi"] - point(selected, row))
        for group in splits["train"] for row in group["rows"]
    ]
    candidates = []
    for probability in (0.80, 0.85, 0.90, 0.925, 0.95, 0.975):
        width = quantile(train_errors, probability)
        candidates.append({"train_quantile": probability, "half_width_pct_oi": width, "dev_coverage": interval_coverage(splits["dev"], selected, width)})
    interval_selected = min(candidates, key=lambda item: (abs(item["dev_coverage"] - 0.90), item["half_width_pct_oi"]))
    current_test_coverage = interval_coverage(splits["test"], "crowding_cap")
    candidate_test_coverage = interval_coverage(splits["test"], selected, interval_selected["half_width_pct_oi"])
    result = {
        "dataset": str(args.dataset),
        "split_group_counts": {name: len(items) for name, items in splits.items()},
        "dev_scores": dev_scores,
        "point_selected_on_dev": selected,
        "test_scores": test_scores,
        "point_decision": "consider" if test_scores[selected]["mean_spearman"] > test_scores["crowding_cap"]["mean_spearman"] else "reject",
        "interval_candidates": candidates,
        "interval_selected_on_dev": interval_selected,
        "test_interval": {
            "current_coverage": current_test_coverage,
            "candidate_coverage": candidate_test_coverage,
            "current_calibration_loss": abs(current_test_coverage - 0.90),
            "candidate_calibration_loss": abs(candidate_test_coverage - 0.90),
        },
    }
    result["interval_decision"] = "consider" if result["test_interval"]["candidate_calibration_loss"] < result["test_interval"]["current_calibration_loss"] else "reject"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
