#!/usr/bin/env python3
"""Confirm a fixed 12-month CPI mean on untouched 2024-2025 vintages."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path


TARGET_ENTITIES = {"CPI_CORE", "CPI_FOOD"}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def forecast(row: dict, method: str) -> float:
    history = row["known_mom_pct"]
    if method == "current_mix":
        return 0.7 * history[-1] + 0.3 * statistics.median(history[-3:])
    if method == "mean12":
        if len(history) != 12:
            raise ValueError("mean12 requires exactly 12 cutoff-safe monthly changes")
        return statistics.fmean(history)
    raise KeyError(method)


def metrics(rows: list[dict], method: str) -> dict:
    predictions = [forecast(row, method) for row in rows]
    targets = [row["target_mom_pct"] for row in rows]
    errors = [prediction - target for prediction, target in zip(predictions, targets)]
    return {
        "rows": len(rows),
        "mae": statistics.fmean(abs(error) for error in errors),
        "rmse": math.sqrt(statistics.fmean(error * error for error in errors)),
        "direction_accuracy": statistics.fmean(
            (prediction >= 0.0) == (target >= 0.0)
            for prediction, target in zip(predictions, targets)
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    document = json.loads(args.dataset.read_text())
    eligible = [
        row for row in document["rows"]
        if row["entity_id"] in TARGET_ENTITIES and len(row["known_mom_pct"]) == 12
    ]
    years = {}
    for year in ("2024", "2025"):
        rows = [row for row in eligible if row["ref_month"].startswith(year)]
        baseline = metrics(rows, "current_mix")
        candidate = metrics(rows, "mean12")
        passed = (
            candidate["mae"] < baseline["mae"]
            and candidate["rmse"] < baseline["rmse"]
            and candidate["direction_accuracy"] >= baseline["direction_accuracy"]
        )
        years[year] = {
            "baseline_current_mix": baseline,
            "candidate_mean12": candidate,
            "candidate_minus_baseline": {
                key: candidate[key] - baseline[key]
                for key in ("mae", "rmse", "direction_accuracy")
            },
            "passed": passed,
        }

    excluded = [
        {"ref_month": row["ref_month"], "entity_id": row["entity_id"], "history_length": len(row["known_mom_pct"])}
        for row in document["rows"]
        if row["entity_id"] in TARGET_ENTITIES and len(row["known_mom_pct"]) != 12
    ]
    accepted = all(result["passed"] for result in years.values())
    result = {
        "experiment": "cpi_core_food_mean12_confirmation_v1",
        "hypothesis": (
            "A fixed 12-month mean lowers MAE and RMSE without reducing direction accuracy "
            "versus the production current_mix in each untouched confirmation year."
        ),
        "scope": sorted(TARGET_ENTITIES),
        "dataset": str(args.dataset),
        "dataset_sha256": file_sha256(args.dataset),
        "dataset_raw_cache_sha256": document["raw_cache_sha256"],
        "source": document["source"],
        "selection_reference": "Cleveland Fed Inflation Nowcasting FAQ: core and food CPI use J=12 moving averages.",
        "acceptance_rule": (
            "Accept only if mean12 has strictly lower MAE and RMSE and non-inferior direction "
            "accuracy in 2024 and 2025 separately."
        ),
        "years": years,
        "excluded_incomplete_histories": excluded,
        "decision": "accept" if accepted else "reject",
        "model_api_calls": 0,
        "local_llm_run": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
