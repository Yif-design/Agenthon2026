#!/usr/bin/env python3
"""Test cutoff-day yield reaction and momentum as FOMC point predictors."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from datetime import date, datetime
from pathlib import Path
from typing import Callable

TENORS = {
    "UST2Y": "2 Yr",
    "UST3Y": "3 Yr",
    "UST5Y": "5 Yr",
    "UST7Y": "7 Yr",
    "UST10Y": "10 Yr",
    "UST30Y": "30 Yr",
}
SENSITIVITY = {"UST2Y": 1.0, "UST3Y": 0.8, "UST5Y": 0.8, "UST7Y": 0.6, "UST10Y": 0.6, "UST30Y": 0.4}
Predictor = Callable[[dict, dict[str, dict[str, float]], str], float]


def load_rates(folder: Path) -> dict[date, dict[str, float]]:
    rates: dict[date, dict[str, float]] = {}
    for path in sorted(folder.glob("*.csv")):
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                try:
                    day = datetime.strptime(row["Date"], "%m/%d/%Y").date()
                    rates[day] = {tenor: float(row[column]) for tenor, column in TENORS.items()}
                except (KeyError, TypeError, ValueError):
                    continue
    return rates


def add_features(events: list[dict], rates: dict[date, dict[str, float]]) -> list[tuple[dict, dict]]:
    days = sorted(rates)
    positions = {day: index for index, day in enumerate(days)}
    featured = []
    for event in events:
        start = date.fromisoformat(event["start_date"])
        position = positions.get(start)
        if position is None or position < 20:
            continue
        features: dict[str, dict[str, float]] = {}
        for tenor in TENORS:
            features[tenor] = {
                "cutoff_reaction": 100.0 * (rates[start][tenor] - rates[days[position - 1]][tenor]),
                "momentum_10d": 100.0 * (rates[start][tenor] - rates[days[position - 10]][tenor]),
                "momentum_20d": 100.0 * (rates[start][tenor] - rates[days[position - 20]][tenor]),
            }
        featured.append((event, features))
    return featured


def score(rows: list[tuple[dict, dict]], predictor: Predictor) -> dict[str, float | int]:
    absolute_errors = []
    squared_errors = []
    directions = []
    for event, features in rows:
        for tenor in TENORS:
            prediction = float(predictor(event, features, tenor))
            truth = float(event["yield_changes_bps"][tenor])
            absolute_errors.append(abs(prediction - truth))
            squared_errors.append((prediction - truth) ** 2)
            directions.append((prediction > 0) == (truth > 0) if prediction and truth else prediction == truth)
    return {
        "observations": len(absolute_errors),
        "mae_bps": statistics.fmean(absolute_errors),
        "rmse_bps": math.sqrt(statistics.fmean(squared_errors)),
        "direction_accuracy": statistics.fmean(directions),
    }


def predictors() -> dict[str, Predictor]:
    result: dict[str, Predictor] = {
        "zero_change": lambda event, features, tenor: 0.0,
        "policy_decay": lambda event, features, tenor: 15.0
        * event["policy_direction"]
        * SENSITIVITY[tenor],
    }
    for feature in ("cutoff_reaction", "momentum_10d", "momentum_20d"):
        for coefficient in (-1.0, -0.5, 0.5, 1.0, 1.5, 2.0):
            name = f"{feature}_x{coefficient:g}"
            result[name] = lambda event, features, tenor, feature=feature, coefficient=coefficient: (
                coefficient * features[tenor][feature]
            )
    for momentum in ("momentum_10d", "momentum_20d"):
        for reaction_weight, momentum_weight in ((0.5, 0.5), (-0.5, 0.5), (0.5, -0.5), (1.0, 0.5), (0.5, 1.0)):
            name = f"cutoff_reaction_x{reaction_weight:g}_{momentum}_x{momentum_weight:g}"
            result[name] = (
                lambda event,
                features,
                tenor,
                reaction_weight=reaction_weight,
                momentum_weight=momentum_weight,
                momentum=momentum: reaction_weight * features[tenor]["cutoff_reaction"]
                + momentum_weight * features[tenor][momentum]
            )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--treasury", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    document = json.loads(args.dataset.read_text())
    rows = add_features(document["events"], load_rates(args.treasury))
    splits = {
        "train": [row for row in rows if row[0]["decision_date"][:4] <= "2015"],
        "dev": [row for row in rows if "2016" <= row[0]["decision_date"][:4] <= "2018"],
        "test": [row for row in rows if "2019" <= row[0]["decision_date"][:4] <= "2021"],
    }
    candidates = predictors()
    dev_scores = {name: score(splits["dev"], predictor) for name, predictor in candidates.items()}
    selected = min(dev_scores, key=lambda name: dev_scores[name]["mae_bps"])
    test_scores = {name: score(splits["test"], predictor) for name, predictor in candidates.items()}
    best_baseline_mae = min(test_scores[name]["mae_bps"] for name in ("zero_change", "policy_decay"))
    improvement = 100.0 * (best_baseline_mae - test_scores[selected]["mae_bps"]) / best_baseline_mae
    direction_floor = max(test_scores[name]["direction_accuracy"] for name in ("zero_change", "policy_decay"))
    decision = (
        "consider"
        if improvement >= 2.0 and test_scores[selected]["direction_accuracy"] > direction_floor
        else "reject"
    )
    result = {
        "dataset": str(args.dataset),
        "treasury_data": str(args.treasury),
        "source": document["source"],
        "feature_availability": "All features end at the first complete Treasury close after the decision, matching the public task's next-day cutoff pattern.",
        "split_event_counts": {name: len(items) for name, items in splits.items()},
        "selection_metric": "dev aggregate MAE in basis points",
        "candidate_count_including_baselines": len(candidates),
        "selected_on_dev": selected,
        "dev_scores": {name: dev_scores[name] for name in ("zero_change", "policy_decay", selected)},
        "test_scores": {name: test_scores[name] for name in ("zero_change", "policy_decay", selected)},
        "selected_test_improvement_vs_best_baseline_pct": improvement,
        "decision_rule": "Consider production only if the dev-selected model improves held-out test MAE over both baselines by at least 2 percent and improves direction accuracy.",
        "decision": decision,
        "production_change": "none" if decision == "reject" else "requires independent confirmation",
        "research_context": [
            "https://www.federalreserve.gov/econres/notes/feds-notes/how-do-principal-trading-firms-and-dealers-trade-around-fomc-statement-releases-20201231.html",
            "https://www.newyorkfed.org/research/staff_reports/sr773.html",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
