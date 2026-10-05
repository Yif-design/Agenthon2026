#!/usr/bin/env python3
"""Compare simple, submission-compatible FOMC yield-change point models."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

TENORS = ("UST2Y", "UST3Y", "UST5Y", "UST7Y", "UST10Y", "UST30Y")
SENSITIVITY = {"UST2Y": 1.0, "UST3Y": 0.8, "UST5Y": 0.8, "UST7Y": 0.6, "UST10Y": 0.6, "UST30Y": 0.4}


def solve_linear(matrix: list[list[float]], values: list[float]) -> list[float]:
    augmented = [row[:] + [value] for row, value in zip(matrix, values)]
    size = len(values)
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        if abs(scale) < 1e-12:
            raise ValueError("singular matrix")
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [left - factor * right for left, right in zip(augmented[row], augmented[column])]
    return [augmented[row][-1] for row in range(size)]


def features(event: dict, tenor: str, include_policy: bool) -> list[float]:
    yields = event["start_yields_pct"]
    level = statistics.fmean(yields[item] for item in TENORS)
    slope = yields["UST10Y"] - yields["UST2Y"]
    curvature = 2.0 * yields["UST5Y"] - yields["UST2Y"] - yields["UST10Y"]
    result = [yields[tenor], level, slope, curvature]
    if include_policy:
        result.append(float(event["policy_direction"]))
    return result


def fit_ridge(events: list[dict], tenor: str, include_policy: bool, penalty: float = 1.0) -> dict:
    raw = [features(event, tenor, include_policy) for event in events]
    means = [statistics.fmean(row[column] for row in raw) for column in range(len(raw[0]))]
    scales = []
    for column, mean in enumerate(means):
        variance = statistics.fmean((row[column] - mean) ** 2 for row in raw)
        scales.append(math.sqrt(variance) or 1.0)
    design = [[1.0] + [(value - means[i]) / scales[i] for i, value in enumerate(row)] for row in raw]
    target = [event["yield_changes_bps"][tenor] for event in events]
    width = len(design[0])
    gram = [[sum(row[i] * row[j] for row in design) for j in range(width)] for i in range(width)]
    rhs = [sum(row[i] * value for row, value in zip(design, target)) for i in range(width)]
    for i in range(1, width):
        gram[i][i] += penalty
    return {"coefficients": solve_linear(gram, rhs), "means": means, "scales": scales}


def ridge_predict(model: dict, event: dict, tenor: str, include_policy: bool) -> float:
    raw = features(event, tenor, include_policy)
    row = [1.0] + [(value - model["means"][i]) / model["scales"][i] for i, value in enumerate(raw)]
    return sum(coefficient * value for coefficient, value in zip(model["coefficients"], row))


def score(events: list[dict], predictor) -> dict[str, float]:
    errors = []
    squared = []
    directions = []
    for event in events:
        for tenor in TENORS:
            prediction = float(predictor(event, tenor))
            truth = float(event["yield_changes_bps"][tenor])
            errors.append(abs(prediction - truth))
            squared.append((prediction - truth) ** 2)
            directions.append((prediction > 0) == (truth > 0) if prediction != 0 and truth != 0 else prediction == truth)
    return {
        "observations": len(errors),
        "mae_bps": statistics.fmean(errors),
        "rmse_bps": math.sqrt(statistics.fmean(squared)),
        "direction_accuracy": statistics.fmean(directions),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.dataset.read_text())
    events = document["events"]
    splits = {
        "train": [event for event in events if event["decision_date"][:4] <= "2015"],
        "dev": [event for event in events if "2016" <= event["decision_date"][:4] <= "2018"],
        "test": [event for event in events if "2019" <= event["decision_date"][:4] <= "2021"],
    }
    ridge = {
        name: {tenor: fit_ridge(splits["train"], tenor, include_policy) for tenor in TENORS}
        for name, include_policy in (("curve_ridge", False), ("curve_policy_ridge", True))
    }
    predictors = {
        "zero_change": lambda event, tenor: 0.0,
        "policy_decay": lambda event, tenor: 15.0 * event["policy_direction"] * SENSITIVITY[tenor],
        "curve_ridge": lambda event, tenor: ridge_predict(ridge["curve_ridge"][tenor], event, tenor, False),
        "curve_policy_ridge": lambda event, tenor: ridge_predict(ridge["curve_policy_ridge"][tenor], event, tenor, True),
    }
    dev_scores = {name: score(splits["dev"], predictor) for name, predictor in predictors.items()}
    selected = min(dev_scores, key=lambda name: dev_scores[name]["mae_bps"])
    test_scores = {name: score(splits["test"], predictor) for name, predictor in predictors.items()}
    best_test = min(test_scores, key=lambda name: test_scores[name]["mae_bps"])
    result = {
        "dataset": str(args.dataset),
        "source": document["source"],
        "split_event_counts": {name: len(items) for name, items in splits.items()},
        "selection_metric": "dev aggregate MAE in basis points",
        "models": {
            "zero_change": "Random-walk/no-change yield forecast",
            "policy_decay": "Current 15 bps policy direction shock with maturity decay",
            "curve_ridge": "Per-tenor ridge on cutoff curve level, slope and curvature",
            "curve_policy_ridge": "Curve ridge plus parsed policy direction",
        },
        "dev_scores": dev_scores,
        "selected_on_dev": selected,
        "test_scores": test_scores,
        "best_on_test_for_diagnostics_only": best_test,
        "selected_test_mae_bps": test_scores[selected]["mae_bps"],
        "decision_rule": "Consider production only if the dev-selected model improves test MAE over both zero_change and policy_decay by at least 2 percent",
    }
    baselines = min(test_scores["zero_change"]["mae_bps"], test_scores["policy_decay"]["mae_bps"])
    result["selected_test_improvement_vs_best_baseline_pct"] = 100.0 * (baselines - test_scores[selected]["mae_bps"]) / baselines
    result["decision"] = "consider" if result["selected_test_improvement_vs_best_baseline_pct"] >= 2.0 else "reject"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
