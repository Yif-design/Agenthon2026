#!/usr/bin/env python3
"""Screen explicit scalar-unit compatibility for unknown-schema baselines."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Callable

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from t4agent.calc import select_default_point  # noqa: E402


def baseline_point(
    target_type: str,
    target_name: str,
    entity: dict[str, Any],
    row_index: int,
    row_count: int,
) -> tuple[float, str | None, str]:
    return select_default_point(
        target_type,
        target_name,
        entity,
        row_index,
        row_count,
        enforce_unit_compatibility=False,
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regression_metrics(rows: list[tuple[float, float]]) -> dict[str, float | int]:
    errors = [prediction - outcome for prediction, outcome in rows]
    return {
        "rows": len(rows),
        "mae": statistics.fmean(abs(error) for error in errors),
        "rmse": math.sqrt(statistics.fmean(error * error for error in errors)),
    }


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
    left_mean, right_mean = statistics.fmean(left), statistics.fmean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    denominator = math.sqrt(
        sum((value - left_mean) ** 2 for value in left)
        * sum((value - right_mean) ** 2 for value in right)
    )
    return numerator / denominator if denominator else 0.0


def evaluate_cpi(document: dict[str, Any], choose: Callable[..., tuple[float, str | None, str]]) -> dict[str, Any]:
    pairs = []
    selections: dict[str, int] = defaultdict(int)
    for row in document["rows"]:
        if not ("2022" <= row["ref_month"][:4] <= "2023"):
            continue
        entity = {"current_component_movement_pct": float(row["known_mom_pct"][-1])}
        prediction, _, reason = choose("regression", "next_component_response_pct", entity, 0, 1)
        pairs.append((prediction, float(row["target_mom_pct"])))
        selections[reason] += 1
    return {**regression_metrics(pairs), "selection_reasons": dict(sorted(selections.items()))}


def evaluate_cot(document: dict[str, Any], choose: Callable[..., tuple[float, str | None, str]]) -> dict[str, Any]:
    correlations = []
    errors = []
    reasons: dict[str, int] = defaultdict(int)
    for group in document["groups"]:
        if not ("2022" <= group["start_date"][:4] <= "2023"):
            continue
        predicted, actual = [], []
        for index, row in enumerate(group["rows"]):
            entity = {"trailing_net_position_response_pct": float(row["trailing_4wk_net_change_pct_oi"])}
            point, _, reason = choose(
                "ranking", "future_net_position_response_pct", entity, index, len(group["rows"])
            )
            predicted.append(point)
            actual.append(float(row["target_5wk_change_pct_start_oi"]))
            errors.append(abs(point - actual[-1]))
            reasons[reason] += 1
        correlations.append(correlation(ranks(predicted), ranks(actual)))
    return {
        "groups": len(correlations),
        "rows": len(errors),
        "mean_spearman": statistics.fmean(correlations),
        "mae": statistics.fmean(errors),
        "selection_reasons": dict(sorted(reasons.items())),
    }


def evaluate_auction(document: dict[str, Any], choose: Callable[..., tuple[float, str | None, str]]) -> dict[str, Any]:
    history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=6))
    pairs = []
    reasons: dict[str, int] = defaultdict(int)
    for row in sorted(document["data"], key=lambda item: (item["auction_date"], item["tenor"])):
        prior = history[row["tenor"]]
        if row["auction_date"][:4] == "2024" and prior:
            entity = {"recent_demand_coverage_ratio": statistics.fmean(prior)}
            point, _, reason = choose("regression", "next_demand_coverage_ratio", entity, 0, 1)
            pairs.append((point, float(row["bid_to_cover_ratio"])))
            reasons[reason] += 1
        prior.append(float(row["bid_to_cover_ratio"]))
    return {**regression_metrics(pairs), "selection_reasons": dict(sorted(reasons.items()))}


def evaluate_macro(document: dict[str, Any], choose: Callable[..., tuple[float, str | None, str]]) -> dict[str, Any]:
    pairs = []
    reasons: dict[str, int] = defaultdict(int)
    for row in document["rows"]:
        if not ("2021" <= row["cutoff_vintage"][:4] <= "2022") or not row["all_history_changes"]:
            continue
        entity = {"historical_revision_delta": statistics.median(row["all_history_changes"])}
        point, _, reason = choose("regression", "next_revision_delta", entity, 0, 1)
        pairs.append((point, float(row["target_change"])))
        reasons[reason] += 1
    return {**regression_metrics(pairs), "selection_reasons": dict(sorted(reasons.items()))}


def evaluate_fomc(document: dict[str, Any], choose: Callable[..., tuple[float, str | None, str]]) -> dict[str, Any]:
    pairs = []
    reasons: dict[str, int] = defaultdict(int)
    for event in document["events"]:
        if not ("2019" <= event["decision_date"][:4] <= "2021"):
            continue
        for tenor, current_yield in event["start_yields_pct"].items():
            entity = {"current_curve_response_pct": float(current_yield)}
            point, _, reason = choose("regression", "future_curve_response_bps", entity, 0, 1)
            pairs.append((point, float(event["yield_changes_bps"][tenor])))
            reasons[reason] += 1
    return {**regression_metrics(pairs), "selection_reasons": dict(sorted(reasons.items()))}


def synthetic_checks(choose: Callable[..., tuple[float, str | None, str]]) -> dict[str, bool]:
    cases = {
        "reject_pct_for_bps": (
            "regression", "future_curve_response_bps", {"current_curve_response_pct": 4.5}, 0.0
        ),
        "reject_bps_for_pct": (
            "regression", "future_margin_response_pct", {"current_margin_response_bps": 45.0}, 0.0
        ),
        "preserve_matching_pct": (
            "regression", "future_margin_response_pct", {"current_margin_response_pct": 4.5}, 4.5
        ),
        "preserve_matching_bps": (
            "ranking", "future_spread_response_bps", {"current_spread_response_bps": 45.0}, 45.0
        ),
        "preserve_unspecified_unit": (
            "regression", "future_margin_response", {"current_margin_response": 4.5}, 4.5
        ),
    }
    return {
        name: math.isclose(choose(target_type, target, entity, 0, 1)[0], expected)
        for name, (target_type, target, entity, expected) in cases.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, default=PROJECT / "evaluation" / "datasets")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    paths = {
        "cpi": args.dataset_root / "cpi" / "components_2015_2023.json",
        "cot": args.dataset_root / "cot" / "legacy10_2015_2023.json",
        "auction": args.dataset_root / "auction" / "nominal_coupon_2010_2024-10-31.json",
        "macro_revision": args.dataset_root / "macro_revision" / "alfred_monthend_2014_2024.json",
        "fomc": args.dataset_root / "fomc" / "events_2000_2021.json",
    }
    documents = {name: json.loads(path.read_text()) for name, path in paths.items()}
    evaluators = {
        "cpi": evaluate_cpi,
        "cot": evaluate_cot,
        "auction": evaluate_auction,
        "macro_revision": evaluate_macro,
        "fomc": evaluate_fomc,
    }
    systems = {"baseline": baseline_point, "candidate": select_default_point}
    results = {
        system: {name: evaluators[name](documents[name], choose) for name in evaluators}
        for system, choose in systems.items()
    }
    unchanged_domains = []
    for name in ("cpi", "cot", "auction", "macro_revision"):
        baseline = {key: value for key, value in results["baseline"][name].items() if key != "selection_reasons"}
        candidate = {key: value for key, value in results["candidate"][name].items() if key != "selection_reasons"}
        if baseline == candidate:
            unchanged_domains.append(name)
    fomc_before = float(results["baseline"]["fomc"]["mae"])
    fomc_after = float(results["candidate"]["fomc"]["mae"])
    checks = synthetic_checks(select_default_point)
    decision = (
        "pass_to_production_gates"
        if fomc_after < fomc_before and len(unchanged_domains) == 4 and all(checks.values())
        else "reject"
    )
    report = {
        "schema_version": 1,
        "experiment": "generic_explicit_unit_compatibility_v1",
        "baseline_git_commit": "9ad1b7a7712b42aad0bb70de1e78acd32535c5a2",
        "hypothesis": (
            "For unknown schemas, rejecting a numeric field only when both the target and field declare "
            "incompatible explicit units prevents scale errors without changing compatible or unspecified fields."
        ),
        "scope": "L2 unknown-family scalar selection across regression and ranking.",
        "dataset_sha256": {name: sha256(path) for name, path in paths.items()},
        "time_splits": {
            "cpi": "2022-2023 test rows",
            "cot": "2022-2023 test groups",
            "auction": "2024 confirmation rows using prior same-tenor observations only",
            "macro_revision": "2021-2022 test rows",
            "fomc": "2019-2021 test events",
        },
        "schema_transform": (
            "Cutoff-safe real features and outcomes are retained, while family-specific target/field identifiers "
            "are rewritten as generic names. FOMC deliberately exposes percent inputs against basis-point outcomes."
        ),
        "systems": {
            "baseline": "current select_default_point",
            "candidate": "baseline after removing fields with explicit units incompatible with explicit target units",
        },
        "results": results,
        "synthetic_checks": checks,
        "unchanged_control_domains": unchanged_domains,
        "fomc_mae_improvement": fomc_before - fomc_after,
        "decision_rule": (
            "Advance only if FOMC MAE improves, CPI/COT/auction/macro results are exactly unchanged, "
            "and all five unit controls pass."
        ),
        "decision": decision,
        "model_api_calls": 0,
        "local_llm_run": False,
        "limitations": [
            "This evaluates point selection, not citation entailment.",
            "The transformed identifiers proxy unknown schemas; they are not hidden competition units.",
            "No parameter is tuned on the reported test periods.",
        ],
    }
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload)
    print(payload, end="")


if __name__ == "__main__":
    main()
