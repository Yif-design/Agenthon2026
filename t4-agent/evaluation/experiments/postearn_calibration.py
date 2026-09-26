#!/usr/bin/env python3
"""Time-forward calibration for after-close earnings reaction intervals and labels."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def coverage(events: list[dict], half_width: float) -> float:
    return statistics.fmean(abs(event["abnormal_return_pct"]) <= half_width for event in events)


def accuracy(events: list[dict], label: str) -> float:
    return statistics.fmean(event["label"] == label for event in events)


def prior_reaction_accuracy(events: list[dict], history: list[dict]) -> float:
    last = {}
    for event in sorted(history + events, key=lambda item: item["announcement_date"]):
        if event in events:
            event["prior_prediction"] = last.get(event["ticker"], "flat")
        last[event["ticker"]] = event["label"]
    return statistics.fmean(event["prior_prediction"] == event["label"] for event in events)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.dataset.read_text())
    events = document["events"]
    train = [event for event in events if event["announcement_date"] <= "2020-12-31"]
    dev = [event for event in events if "2021-01-01" <= event["announcement_date"] <= "2021-12-31"]
    test = [event for event in events if "2022-01-01" <= event["announcement_date"] <= "2023-12-31"]

    candidates = []
    absolute_train = [abs(event["abnormal_return_pct"]) for event in train]
    for probability in (0.80, 0.85, 0.90, 0.925, 0.95, 0.975):
        half = quantile(absolute_train, probability)
        candidates.append({"train_quantile": probability, "half_width_pct": half, "dev_coverage": coverage(dev, half)})
    selected = min(candidates, key=lambda item: (abs(item["dev_coverage"] - 0.90), item["half_width_pct"]))

    train_counts = {label: sum(event["label"] == label for event in train) for label in ("negative_reaction", "flat", "positive_reaction")}
    majority = max(train_counts, key=train_counts.get)
    result = {
        "dataset": str(args.dataset),
        "split_counts": {"train": len(train), "dev": len(dev), "test": len(test)},
        "interval_candidates": candidates,
        "selected_on_dev": selected,
        "test_interval": {
            "current_half_width_pct": 2.5,
            "current_coverage": coverage(test, 2.5),
            "candidate_half_width_pct": selected["half_width_pct"],
            "candidate_coverage": coverage(test, selected["half_width_pct"]),
            "candidate_calibration_loss": abs(coverage(test, selected["half_width_pct"]) - 0.90),
        },
        "label_baselines": {
            "train_counts": train_counts,
            "train_majority_label": majority,
            "dev_flat_accuracy": accuracy(dev, "flat"),
            "dev_majority_accuracy": accuracy(dev, majority),
            "dev_prior_reaction_accuracy": prior_reaction_accuracy(dev, train),
            "test_flat_accuracy": accuracy(test, "flat"),
            "test_majority_accuracy": accuracy(test, majority),
            "test_prior_reaction_accuracy": prior_reaction_accuracy(test, train + dev),
        },
    }
    result["interval_decision"] = "consider" if result["test_interval"]["candidate_calibration_loss"] < abs(result["test_interval"]["current_coverage"] - 0.90) else "reject"
    result["label_decision"] = "keep_flat" if result["label_baselines"]["test_flat_accuracy"] >= max(result["label_baselines"]["test_majority_accuracy"], result["label_baselines"]["test_prior_reaction_accuracy"]) else "research_further"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
