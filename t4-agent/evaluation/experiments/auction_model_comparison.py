#!/usr/bin/env python3
"""Time-forward comparison of simple same-tenor bid-to-cover forecasts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
INTERVAL_MULTIPLIERS = (1.65, 1.75, 1.85, 2.0, 2.2, 2.5, 3.0)
INTERVAL_LEVEL = 0.9


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        type=Path,
        default=PROJECT / "evaluation/datasets/auction/nominal_coupon_2010_2024-10-31.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT / "evaluation/reports/auction-model-comparison-v1.json",
    )
    return parser.parse_args()


def mean(values: list[float]) -> float:
    return statistics.fmean(values)


def clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def candidates(history: list[dict], target: dict) -> dict[str, float]:
    values = [float(row["bid_to_cover_ratio"]) for row in history]
    last6 = values[-6:]
    same_regime = [
        float(row["bid_to_cover_ratio"])
        for row in history
        if bool(row["reopening"]) == bool(target["reopening"])
    ][-6:]
    current_trend = clip((values[-1] - values[-3]) / 2.0, -0.08, 0.08)
    linear_weights = list(range(1, len(last6) + 1))
    weighted = sum(w * x for w, x in zip(linear_weights, last6, strict=True)) / sum(linear_weights)
    return {
        "last": values[-1],
        "mean3": mean(values[-3:]),
        "mean6": mean(last6),
        "median6": statistics.median(last6),
        "linear_weighted6": weighted,
        "same_regime_mean6": mean(same_regime) if same_regime else mean(last6),
        "production_mean6_trend": mean(last6) + current_trend,
    }


def metrics(rows: list[dict], model: str, interval_multiplier: float = 1.65) -> dict:
    errors = [float(row["predictions"][model]) - float(row["actual"]) for row in rows]
    halves = [max(0.15, interval_multiplier * float(row["recent_pstdev"])) for row in rows]
    covered = [
        abs(float(row["predictions"][model]) - float(row["actual"])) <= half
        for row, half in zip(rows, halves, strict=True)
    ]
    coverage = mean([float(value) for value in covered])
    return {
        "n": len(rows),
        "mae": mean([abs(value) for value in errors]),
        "rmse": math.sqrt(mean([value * value for value in errors])),
        "bias": mean(errors),
        "interval_multiplier": interval_multiplier,
        "interval_coverage": coverage,
        "interval_calibration_error": abs(coverage - INTERVAL_LEVEL),
        "mean_interval_width": mean([2.0 * half for half in halves]),
    }


def paired_test(rows: list[dict], baseline: str, candidate: str) -> dict:
    improvements = [
        abs(float(row["predictions"][baseline]) - float(row["actual"]))
        - abs(float(row["predictions"][candidate]) - float(row["actual"]))
        for row in rows
    ]
    rng = random.Random(20260927)
    boot = []
    for _ in range(10_000):
        boot.append(mean([improvements[rng.randrange(len(improvements))] for _ in improvements]))
    boot.sort()
    return {
        "mean_absolute_error_improvement": mean(improvements),
        "candidate_better_fraction": mean([float(value > 0.0) for value in improvements]),
        "candidate_equal_fraction": mean([float(value == 0.0) for value in improvements]),
        "paired_bootstrap_mean_improvement_95pct": [boot[249], boot[9749]],
        "bootstrap_seed": 20260927,
        "bootstrap_samples": 10_000,
    }


def split_for(year: int) -> str:
    if year <= 2019:
        return "train"
    if year <= 2021:
        return "dev"
    if year <= 2023:
        return "test"
    return "confirmation"


def main() -> None:
    args = parse_args()
    source = json.loads(args.data.read_text(encoding="utf-8"))
    by_tenor: dict[str, list[dict]] = defaultdict(list)
    for row in source["data"]:
        by_tenor[row["tenor"]].append(row)
    samples = []
    for tenor, rows in sorted(by_tenor.items()):
        rows.sort(key=lambda row: row["auction_date"])
        for index, target in enumerate(rows):
            history = rows[:index]
            if len(history) < 6:
                continue
            year = int(target["auction_date"][:4])
            recent = [float(row["bid_to_cover_ratio"]) for row in history[-6:]]
            samples.append(
                {
                    "auction_date": target["auction_date"],
                    "tenor": tenor,
                    "reopening": target["reopening"],
                    "offering_amount_usd_bn": target["offering_amount_usd_bn"],
                    "split": split_for(year),
                    "actual": target["bid_to_cover_ratio"],
                    "recent_pstdev": statistics.pstdev(recent),
                    "predictions": candidates(history, target),
                }
            )
    models = sorted(samples[0]["predictions"])
    split_rows = {
        name: [row for row in samples if row["split"] == name]
        for name in ("train", "dev", "test", "confirmation")
    }
    results = {
        split: {model: metrics(rows, model) for model in models}
        for split, rows in split_rows.items()
    }
    selected = min(models, key=lambda model: (results["dev"][model]["mae"], model))
    baseline = "production_mean6_trend"
    interval_multiplier = min(
        INTERVAL_MULTIPLIERS,
        key=lambda value: (
            metrics(split_rows["dev"], selected, value)["interval_calibration_error"],
            value,
        ),
    )
    selected_metrics = {
        split: metrics(rows, selected, interval_multiplier)
        for split, rows in split_rows.items()
    }
    by_tenor_test = {}
    for tenor in sorted(by_tenor):
        rows = [row for row in split_rows["test"] if row["tenor"] == tenor]
        by_tenor_test[tenor] = {
            baseline: metrics(rows, baseline),
            selected: metrics(rows, selected, interval_multiplier),
        }
    result = {
        "experiment": "auction_point_models_v1",
        "source_dataset": str(args.data.relative_to(PROJECT)),
        "source_dataset_sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(),
        "source_rows": source["rows"],
        "feature_policy": "Only prior same-tenor results and current pre-auction reopening flag are used.",
        "splits": {
            "train": "2010-2019",
            "dev": "2020-2021",
            "test": "2022-2023; read once after development selection",
            "confirmation": "2024-01-01 through 2024-10-31; combined point/interval candidate frozen before first read",
        },
        "sample_counts": {key: len(value) for key, value in split_rows.items()},
        "candidate_definitions": {
            "last": "last same-tenor bid-to-cover",
            "mean3": "mean of last 3",
            "mean6": "mean of last 6",
            "median6": "median of last 6",
            "linear_weighted6": "last 6 with linear recency weights 1..6",
            "same_regime_mean6": "last 6 with matching new/reopening status, falling back to mean6",
            "production_mean6_trend": "current mean6 plus clipped (last minus third-last)/2 trend",
        },
        "metrics": results,
        "development_selected": selected,
        "development_selected_interval_multiplier": interval_multiplier,
        "interval_level": INTERVAL_LEVEL,
        "interval_multiplier_candidates": list(INTERVAL_MULTIPLIERS),
        "production_baseline": baseline,
        "holdout_protocol_caveat": (
            "The 2022-2023 point-forecast test was inspected before interval calibration was added. "
            "The combined point/interval candidate is therefore confirmed separately on untouched 2024 data."
        ),
        "development_comparison": {
            "baseline": results["dev"][baseline],
            "selected": selected_metrics["dev"],
            "relative_mae_change": (
                selected_metrics["dev"]["mae"] / results["dev"][baseline]["mae"] - 1.0
            ),
        },
        "test_comparison": {
            "baseline": results["test"][baseline],
            "selected": selected_metrics["test"],
            "relative_mae_change": results["test"][selected]["mae"] / results["test"][baseline]["mae"] - 1.0,
            "paired": paired_test(split_rows["test"], baseline, selected),
        },
        "confirmation_comparison": {
            "baseline": results["confirmation"][baseline],
            "selected": selected_metrics["confirmation"],
            "relative_mae_change": (
                selected_metrics["confirmation"]["mae"]
                / results["confirmation"][baseline]["mae"]
                - 1.0
            ),
            "paired": paired_test(split_rows["confirmation"], baseline, selected),
        },
        "test_by_tenor": by_tenor_test,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"selected": selected, "sample_counts": result["sample_counts"], "test": result["test_comparison"]}, indent=2))


if __name__ == "__main__":
    main()
