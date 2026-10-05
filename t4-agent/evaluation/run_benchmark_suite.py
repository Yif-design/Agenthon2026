#!/usr/bin/env python3
"""Run and score the unified 11-public + 40-proxy Track 4 evaluation suite."""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
PROXY_TOOLS = PROJECT / "proxy-benchmark"
if str(PROXY_TOOLS) not in sys.path:
    sys.path.insert(0, str(PROXY_TOOLS))

from score_proxy import score as score_proxy  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=PROJECT / "evaluation/benchmark_suite.json")
    parser.add_argument("--scope", choices=("all", "public", "proxy"), default="all")
    parser.add_argument("--name", default="current")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--public-units", type=Path)
    parser.add_argument(
        "--public-truth",
        type=Path,
        default=PROJECT / "evaluation/realized/public_all_realized.json",
    )
    parser.add_argument("--reuse", action="store_true", help="Score existing answers instead of running analyze.")
    return parser.parse_args()


def average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        rank = (cursor + 1 + end) / 2.0
        for index in order[cursor:end]:
            result[index] = rank
        cursor = end
    return result


def spearman(left: list[float], right: list[float]) -> float:
    a, b = average_ranks(left), average_ranks(right)
    am, bm = statistics.fmean(a), statistics.fmean(b)
    numerator = sum((x - am) * (y - bm) for x, y in zip(a, b))
    denominator = math.sqrt(sum((x - am) ** 2 for x in a) * sum((y - bm) ** 2 for y in b))
    return numerator / denominator if denominator else 0.0


def public_predictive_quality(target_type: str, rows: list[dict[str, Any]], truth: list[dict[str, Any]]) -> float:
    if target_type == "classification":
        return statistics.fmean(row.get("label") == actual.get("label") for row, actual in zip(rows, truth))
    predicted = [float(row["point_forecast"]) for row in rows]
    actual = [float(row["value"]) for row in truth]
    if target_type == "ranking":
        return 0.5 if len(actual) < 2 else (spearman(predicted, actual) + 1.0) / 2.0
    mean_actual = statistics.fmean(actual)
    baseline_mae = statistics.fmean(abs(value - mean_actual) for value in actual)
    mae = statistics.fmean(abs(value - point) for value, point in zip(actual, predicted))
    if baseline_mae <= 0:
        return 1.0 if mae <= 1e-12 else 0.0
    return max(0.0, min(1.0, 1.0 - mae / baseline_mae))


def score_public(unit: Path, answer_path: Path, truth_task: dict[str, Any]) -> dict[str, Any]:
    task = json.loads((unit / "task.json").read_text())
    answer = json.loads(answer_path.read_text())
    roster = [str(row["entity_id"]) for row in task["entities"]]
    predicted = {str(row["entity_id"]): row for row in answer["entity_predictions"]}
    actual = {str(row["entity_id"]): row for row in truth_task["outcomes"]}
    if set(roster) != set(predicted) or set(roster) != set(actual):
        raise ValueError(f"answer/outcome roster differs from task roster: {unit.name}")
    rows = [predicted[entity_id] for entity_id in roster]
    truth = [actual[entity_id] for entity_id in roster]
    quality = public_predictive_quality(str(truth_task["target_type"]), rows, truth)
    coverage = statistics.fmean(
        float(row["interval"]["lo"]) <= float(actual_row["value"]) <= float(row["interval"]["hi"])
        for row, actual_row in zip(rows, truth)
    )
    composite = 0.7 * quality - 0.3 * abs(coverage - float(task["interval_level"]))
    return {
        "unit": unit.name,
        "entities": len(roster),
        "predictive_quality": quality,
        "interval_coverage": coverage,
        "composite_before_claim_penalty": composite,
    }


def discover_public_units() -> Path | None:
    candidates = (
        PROJECT.parent / "starter-repos/track4-analysis-public/units",
        PROJECT.parent.parent / "Agenthon2026/track4-analysis-public/units",
        Path.home() / "PycharmProject/Agenthon2026/track4-analysis-public/units",
    )
    return next((path for path in candidates if path.is_dir()), None)


def run_agent(unit: Path, answer: Path) -> None:
    answer.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["T4_MODEL_MAX_CALLS"] = "0"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "t4agent.cli",
            "analyze",
            "--task",
            str(unit / "task.json"),
            "--corpus",
            str(unit / "corpus"),
            "--out",
            str(answer),
        ],
        cwd=PROJECT,
        env=environment,
        check=True,
    )


def mean(rows: list[dict[str, Any]], key: str) -> float:
    return statistics.fmean(float(row[key]) for row in rows)


def optional_mean(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return statistics.fmean(values) if values else None


def main() -> None:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text())
    out = args.out or PROJECT / "evaluation/runs" / f"benchmark-suite-{args.name}"
    report_path = args.report or PROJECT / "evaluation/reports" / f"benchmark-suite-{args.name}.json"
    public_units = args.public_units or discover_public_units()
    truth = json.loads(args.public_truth.read_text()) if args.scope in ("all", "public") else None
    if args.scope in ("all", "public") and public_units is None:
        raise SystemExit("public units not found; pass --public-units")

    results: list[dict[str, Any]] = []
    for entry in manifest["units"]:
        cohort = str(entry["cohort"])
        if args.scope != "all" and cohort != args.scope:
            continue
        unit = (
            PROJECT / str(entry["path"])
            if cohort == "proxy"
            else public_units / str(entry["unit_id"])
        )
        answer = out / cohort / str(entry["unit_id"]) / "answer.json"
        if not args.reuse:
            run_agent(unit, answer)
        elif not answer.is_file():
            raise SystemExit(f"missing reusable answer: {answer}")
        metrics = (
            score_proxy(unit, answer)
            if cohort == "proxy"
            else score_public(unit, answer, truth["tasks"][entry["unit_id"]])
        )
        results.append({**entry, **metrics})

    event_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        event_rows[str(row["event_id"])].append(row)
    events = []
    for event_id, rows in sorted(event_rows.items()):
        events.append(
            {
                "event_id": event_id,
                "cohort": rows[0]["cohort"],
                "family": rows[0]["family"],
                "target_type": rows[0]["target_type"],
                "split": rows[0]["split"],
                "variants": len(rows),
                "predictive_quality": mean(rows, "predictive_quality"),
                "interval_coverage": optional_mean(rows, "interval_coverage"),
                "composite_before_claim_penalty": mean(rows, "composite_before_claim_penalty"),
                "schema_gap": (
                    abs(float(rows[0]["composite_before_claim_penalty"]) - float(rows[1]["composite_before_claim_penalty"]))
                    if len(rows) == 2
                    else None
                ),
            }
        )

    def summarize(selected: list[dict[str, Any]]) -> dict[str, Any]:
        coverage_rows = [row for row in selected if row.get("interval_coverage") is not None]
        return {
            "events": len(selected),
            "runnable_units": sum(int(row["variants"]) for row in selected),
            "mean_predictive_quality": mean(selected, "predictive_quality"),
            "mean_interval_coverage": optional_mean(selected, "interval_coverage"),
            "interval_coverage_events": len(coverage_rows),
            "mean_composite_before_claim_penalty": mean(selected, "composite_before_claim_penalty"),
        }

    cohorts = {
        cohort: summarize([row for row in events if row["cohort"] == cohort])
        for cohort in ("public", "proxy")
        if any(row["cohort"] == cohort for row in events)
    }
    slices = {
        target: summarize([row for row in events if row["target_type"] == target])
        for target in ("classification", "regression", "ranking")
        if any(row["target_type"] == target for row in events)
    }
    schema_gaps = [float(row["schema_gap"]) for row in events if row["schema_gap"] is not None]
    report = {
        "suite_version": manifest["suite_version"],
        "name": args.name,
        "scope": args.scope,
        "model_api_calls": 0,
        "weighting": "macro average by economic event; explicit/transformed variants share one event weight",
        "score_limit": "predictive and interval composite before official citation-faithfulness gate",
        "overall": summarize(events),
        "cohorts": cohorts,
        "target_type_slices": slices,
        "schema_robustness": {
            "paired_events": len(schema_gaps),
            "mean_absolute_composite_gap": statistics.fmean(schema_gaps) if schema_gaps else None,
            "max_absolute_composite_gap": max(schema_gaps) if schema_gaps else None,
        },
        "events": events,
        "units": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"report": str(report_path), **report["overall"], "cohorts": cohorts}, indent=2))


if __name__ == "__main__":
    main()
