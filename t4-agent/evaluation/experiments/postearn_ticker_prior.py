#!/usr/bin/env python3
"""Select a ticker prior on development and confirm it on untouched years."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


CANDIDATES = (
    ("global_mean", 0),
    ("ticker_mean", 2),
    ("ticker_mean", 4),
    ("ticker_mean", 8),
    ("ticker_mean", 16),
    ("ticker_median", 0),
    ("ticker_recent4", 0),
)


def class_label(value: float) -> str:
    if value > 1.0:
        return "positive_reaction"
    if value < -1.0:
        return "negative_reaction"
    return "flat"


def raw_prior(history: list[dict], ticker: str, method: str, strength: int) -> float:
    global_mean = statistics.fmean(event["abnormal_return_pct"] for event in history)
    values = [event["abnormal_return_pct"] for event in history if event["ticker"] == ticker]
    if method == "global_mean" or not values:
        return global_mean
    if method == "ticker_mean":
        return (sum(values) + strength * global_mean) / (len(values) + strength)
    if method == "ticker_median":
        return statistics.median(values)
    if method == "ticker_recent4":
        return statistics.fmean(values[-4:])
    raise ValueError(method)


def predicted_point(value: float) -> float:
    label = class_label(value)
    return 1.25 if label == "positive_reaction" else -1.25 if label == "negative_reaction" else 0.0


def evaluate(history: list[dict], events: list[dict], method: str, strength: int) -> dict[str, float | int]:
    predictions = []
    for event in events:
        prior = raw_prior(history, event["ticker"], method, strength)
        point = predicted_point(prior)
        predictions.append((point, class_label(prior), event))
    count = len(predictions)
    return {
        "rows": count,
        "accuracy": sum(label == event["label"] for _, label, event in predictions) / count,
        "mae_pct": statistics.fmean(
            abs(point - event["abnormal_return_pct"]) for point, _, event in predictions
        ),
        # Keep the already calibrated zero-centered fallback interval unchanged.
        "coverage_fixed_interval": statistics.fmean(
            -8.3 <= event["abnormal_return_pct"] <= 8.3 for _, _, event in predictions
        ),
    }


def baseline(events: list[dict]) -> dict[str, float | int]:
    count = len(events)
    return {
        "rows": count,
        "accuracy": sum(event["label"] == "flat" for event in events) / count,
        "mae_pct": statistics.fmean(abs(event["abnormal_return_pct"]) for event in events),
        "coverage_fixed_interval": statistics.fmean(
            -8.3 <= event["abnormal_return_pct"] <= 8.3 for event in events
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--confirmation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    history_doc = json.loads(args.history.read_text())
    confirmation_doc = json.loads(args.confirmation.read_text())
    events = history_doc["events"]
    train = [event for event in events if event["announcement_date"] <= "2020-12-31"]
    dev = [event for event in events if event["announcement_date"].startswith("2021-")]
    diagnostics = [event for event in events if event["announcement_date"] >= "2022-01-01"]
    candidate_results = []
    for method, strength in CANDIDATES:
        result = evaluate(train, dev, method, strength)
        candidate_results.append({"method": method, "strength": strength, **result})
    selected = max(
        candidate_results,
        key=lambda item: (item["accuracy"], -item["mae_pct"], -item["strength"]),
    )

    diagnostic_result = evaluate(train + dev, diagnostics, selected["method"], selected["strength"])
    artifact_history = events
    confirmation = {}
    passes = []
    for year in (2024, 2025):
        rows = [
            event for event in confirmation_doc["events"] if event["announcement_date"].startswith(f"{year}-")
        ]
        before = baseline(rows)
        after = evaluate(artifact_history, rows, selected["method"], selected["strength"])
        confirmation[str(year)] = {"baseline": before, "candidate": after}
        passes.append(after["accuracy"] >= before["accuracy"] and after["mae_pct"] <= before["mae_pct"])

    strict = any(
        values["candidate"]["accuracy"] > values["baseline"]["accuracy"]
        or values["candidate"]["mae_pct"] < values["baseline"]["mae_pct"]
        for values in confirmation.values()
    )
    decision = "pass_to_runtime_and_nli_validation" if all(passes) and strict else "reject"
    report = {
        "experiment_id": "postearn_ticker_prior_v1",
        "date": "2026-09-28",
        "baseline_git_commit": "d252c2121e6236ed1bb2d96f53c2cf426ad69fdd",
        "hypothesis": "A same-ticker historical abnormal-return prior can improve the zero/flat fallback when emitted as a conservative threshold-crossing point.",
        "history_dataset": str(args.history),
        "confirmation_dataset": str(args.confirmation),
        "selection": {
            "train": "2018-2020",
            "development": "2021",
            "candidate_results": candidate_results,
            "selected": selected,
        },
        "previously_inspected_diagnostic_2022_2023": {
            "baseline": baseline(diagnostics),
            "candidate": diagnostic_result,
            "used_for_selection": False,
        },
        "untouched_confirmation": confirmation,
        "interval_policy": "Preserve the accepted zero-centered [-8.3, 8.3] fallback interval so point-model testing cannot borrow interval score.",
        "acceptance_rule": "For both 2024 and 2025, accuracy must not fall and MAE must not rise; at least one metric must improve strictly.",
        "decision": decision,
        "next_gate": (
            "Production and official-NLI A/B are required because labels and point forecasts change."
            if decision.startswith("pass")
            else None
        ),
        "model_api_calls": 0,
        "local_llm_run": False
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"selected": selected, "confirmation": confirmation, "decision": decision}, indent=2))


if __name__ == "__main__":
    main()
