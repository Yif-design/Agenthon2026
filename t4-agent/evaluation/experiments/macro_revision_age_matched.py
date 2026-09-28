#!/usr/bin/env python3
"""Compare pooled and revision-age-matched ALFRED revision baselines."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import median


def sign(value: float) -> str:
    return "up" if value > 0 else "down"


def metrics(rows: list[dict[str, object]], method: str) -> dict[str, object]:
    correct = 0
    absolute_errors: list[float] = []
    by_series: dict[str, list[bool]] = defaultdict(list)
    usable = 0
    for row in rows:
        history = row[f"{method}_history_changes"]
        if not history:
            continue
        prediction = median(float(value) for value in history)
        target = float(row["target_change"])
        hit = sign(prediction) == sign(target)
        usable += 1
        correct += int(hit)
        absolute_errors.append(abs(prediction - target))
        by_series[str(row["series_id"])].append(hit)
    return {
        "rows": usable,
        "accuracy": correct / usable if usable else None,
        "mae_change": sum(absolute_errors) / len(absolute_errors) if absolute_errors else None,
        "series_accuracy": {
            series_id: sum(values) / len(values) for series_id, values in sorted(by_series.items())
        },
        "series_rows": {series_id: len(values) for series_id, values in sorted(by_series.items())},
    }


def split(row: dict[str, object]) -> str | None:
    year = int(str(row["cutoff_vintage"])[:4])
    if 2015 <= year <= 2019:
        return "train"
    if year == 2020:
        return "dev"
    if 2021 <= year <= 2022:
        return "test"
    if year == 2023:
        return "confirmation"
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text())
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in dataset["rows"]:
        group = split(row)
        if group:
            groups[group].append(row)

    results = {}
    for group in ("train", "dev", "test", "confirmation"):
        # Compare on an identical roster: the production fallback would use
        # pooled history when no age-matched transition exists.
        rows = [row for row in groups[group] if row["age_history_changes"]]
        results[group] = {
            "pooled": metrics(rows, "all"),
            "age_matched": metrics(rows, "age"),
        }
        baseline = results[group]["pooled"]["accuracy"]
        candidate = results[group]["age_matched"]["accuracy"]
        results[group]["accuracy_delta"] = (
            candidate - baseline if baseline is not None and candidate is not None else None
        )

    required = ("dev", "test", "confirmation")
    noninferior = all(
        results[group]["age_matched"]["accuracy"] >= results[group]["pooled"]["accuracy"]
        for group in required
    )
    improved_series = set()
    for group in required:
        pooled = results[group]["pooled"]["series_accuracy"]
        candidate = results[group]["age_matched"]["series_accuracy"]
        improved_series.update(
            series_id
            for series_id in candidate.keys() & pooled.keys()
            if candidate[series_id] > pooled[series_id]
        )
    decision = "pass_to_public_confirmation" if noninferior and len(improved_series) >= 2 else "reject"
    report = {
        "baseline_git_commit": "193a06a3bcfc668ec9fdf2fcc5449b37e40bd67f",
        "hypothesis": "Matching historical changes by revision age improves next-revision direction over pooling all revision stages.",
        "dataset": str(args.dataset),
        "dataset_raw_cache_sha256": dataset["raw_cache_sha256"],
        "dataset_method": dataset["method"],
        "dataset_caveat": dataset["caveat"],
        "splits": {
            "train": "2015-2019",
            "dev": "2020",
            "test": "2021-2022",
            "confirmation": "2023",
        },
        "results": results,
        "noninferior_on_dev_test_confirmation": noninferior,
        "improved_series": sorted(improved_series),
        "decision": decision,
        "acceptance_rule": "Direction accuracy must be non-inferior on dev, test, and confirmation, and improve for at least two series.",
        "notes": [
            "Rows with no age-matched history are excluded from candidate metrics and require a pooled fallback in production.",
            "Direction accuracy is the preregistered primary metric; change MAE is diagnostic.",
            "No model API or post-cutoff runtime data is used.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"decision": decision, "improved_series": sorted(improved_series), "results": results}, indent=2))


if __name__ == "__main__":
    main()
