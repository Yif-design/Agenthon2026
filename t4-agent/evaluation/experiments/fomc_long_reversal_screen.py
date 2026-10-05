#!/usr/bin/env python3
"""Screen horizon-aligned pre-cutoff yield reversal for FOMC curve tasks."""

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
PUBLIC_DIAGNOSTIC_DATES = {"2022-07-27", "2024-09-18"}
WINDOWS = (35, 45, 60)
COEFFICIENTS = (-0.25, -0.5, -0.75, -1.0)
Predictor = Callable[[dict, dict[str, dict[str, float]], str], float]


def load_rates(folders: list[Path]) -> dict[date, dict[str, float]]:
    rates: dict[date, dict[str, float]] = {}
    for folder in folders:
        for path in sorted(folder.glob("*.csv")):
            with path.open(newline="") as handle:
                for row in csv.DictReader(handle):
                    try:
                        day = datetime.strptime(row["Date"], "%m/%d/%Y").date()
                        values = {tenor: float(row[column]) for tenor, column in TENORS.items()}
                    except (KeyError, TypeError, ValueError):
                        continue
                    rates[day] = values
    return rates


def add_features(events: list[dict], rates: dict[date, dict[str, float]]) -> list[tuple[dict, dict[str, dict[str, float]]]]:
    days = sorted(rates)
    positions = {day: index for index, day in enumerate(days)}
    featured = []
    for event in events:
        start = date.fromisoformat(event["start_date"])
        position = positions.get(start)
        if position is None or position < max(WINDOWS):
            continue
        features = {
            tenor: {
                f"move_{window}d": 100.0 * (rates[start][tenor] - rates[days[position - window]][tenor])
                for window in WINDOWS
            }
            for tenor in TENORS
        }
        featured.append((event, features))
    return featured


def score(rows: list[tuple[dict, dict[str, dict[str, float]]]], predictor: Predictor) -> dict:
    absolute: list[float] = []
    squared: list[float] = []
    directions: list[bool] = []
    by_tenor: dict[str, list[float]] = {tenor: [] for tenor in TENORS}
    for event, features in rows:
        for tenor in TENORS:
            prediction = float(predictor(event, features, tenor))
            truth = float(event["yield_changes_bps"][tenor])
            error = abs(prediction - truth)
            absolute.append(error)
            squared.append((prediction - truth) ** 2)
            directions.append((prediction > 0) == (truth > 0) if prediction and truth else prediction == truth)
            by_tenor[tenor].append(error)
    return {
        "events": len(rows),
        "observations": len(absolute),
        "mae_bps": statistics.fmean(absolute),
        "rmse_bps": math.sqrt(statistics.fmean(squared)),
        "direction_accuracy": statistics.fmean(directions),
        "mae_by_tenor": {tenor: statistics.fmean(values) for tenor, values in by_tenor.items()},
    }


def predictors() -> dict[str, Predictor]:
    output: dict[str, Predictor] = {
        "zero_change": lambda event, features, tenor: 0.0,
        "policy_decay": lambda event, features, tenor: 15.0 * event["policy_direction"] * SENSITIVITY[tenor],
    }
    for window in WINDOWS:
        for coefficient in COEFFICIENTS:
            output[f"reversal_{window}d_x{coefficient:g}"] = (
                lambda event, features, tenor, window=window, coefficient=coefficient:
                coefficient * features[tenor][f"move_{window}d"]
            )
    return output


def improvement(candidate: dict, baselines: list[dict]) -> float:
    best = min(row["mae_bps"] for row in baselines)
    return 100.0 * (best - candidate["mae_bps"]) / best


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--historical-events", type=Path, required=True)
    parser.add_argument("--recent-events", type=Path, required=True)
    parser.add_argument("--treasury", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline-commit", required=True)
    args = parser.parse_args()

    historical = json.loads(args.historical_events.read_text())
    recent = json.loads(args.recent_events.read_text())
    rows = add_features(historical["events"] + recent["events"], load_rates(args.treasury))
    splits = {
        "development": [row for row in rows if "2016" <= row[0]["decision_date"][:4] <= "2018"],
        "test": [row for row in rows if "2019" <= row[0]["decision_date"][:4] <= "2021"],
        "confirmation": [
            row for row in rows
            if "2022" <= row[0]["decision_date"][:4] <= "2026"
            and row[0]["decision_date"] not in PUBLIC_DIAGNOSTIC_DATES
        ],
        "public_diagnostic": [row for row in rows if row[0]["decision_date"] in PUBLIC_DIAGNOSTIC_DATES],
    }
    candidates = predictors()
    development_scores = {name: score(splits["development"], predictor) for name, predictor in candidates.items()}
    reversal_names = [name for name in candidates if name.startswith("reversal_")]
    selected = min(reversal_names, key=lambda name: development_scores[name]["mae_bps"])
    scores = {
        split: {name: score(values, candidates[name]) for name in ("zero_change", "policy_decay", selected)}
        for split, values in splits.items()
    }
    gates = {}
    for split in ("test", "confirmation"):
        candidate = scores[split][selected]
        baselines = [scores[split]["zero_change"], scores[split]["policy_decay"]]
        best_direction = max(row["direction_accuracy"] for row in baselines)
        worst_tenor_regression = max(
            candidate["mae_by_tenor"][tenor] - min(row["mae_by_tenor"][tenor] for row in baselines)
            for tenor in TENORS
        )
        gates[split] = {
            "mae_improvement_vs_best_baseline_pct": improvement(candidate, baselines),
            "direction_accuracy_improved": candidate["direction_accuracy"] > best_direction,
            "worst_tenor_mae_regression_bps": worst_tenor_regression,
            "passed": improvement(candidate, baselines) >= 2.0
            and candidate["direction_accuracy"] > best_direction
            and worst_tenor_regression <= 2.0,
        }
    passed = all(gate["passed"] for gate in gates.values())
    report = {
        "schema_version": 1,
        "experiment": "fomc_long_reversal_screen_v1",
        "baseline_git_commit": args.baseline_commit,
        "source": [historical["source"], recent["source"]],
        "hypothesis": "A development-selected reversal of the 35, 45, or 60 trading-day pre-cutoff yield move predicts the roughly 35-trading-day intermeeting move better than zero change and policy decay.",
        "candidate_grid": {"windows_trading_days": WINDOWS, "coefficients": COEFFICIENTS},
        "split_event_counts": {name: len(values) for name, values in splits.items()},
        "selected_on_development": selected,
        "development_scores": development_scores,
        "scores": scores,
        "gates": gates,
        "decision_rule": "Proceed only if the locked candidate improves MAE at least 2%, improves direction accuracy, and worsens no tenor MAE by more than 2 bps on both test and confirmation.",
        "decision": "advance_to_corpus_and_nli_gates" if passed else "reject",
        "production_change": "none",
        "model_api_calls": 0,
        "local_llm_run": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"selected": selected, "gates": gates, "decision": report["decision"]}, indent=2))


if __name__ == "__main__":
    main()
