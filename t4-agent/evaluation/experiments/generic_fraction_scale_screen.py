#!/usr/bin/env python3
"""Screen explicit fraction/decimal to percent scaling for unknown schemas."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from evaluation.experiments.generic_unit_compatibility_screen import (  # noqa: E402
    evaluate_auction,
    evaluate_fomc,
    evaluate_macro,
    regression_metrics,
)
from t4agent.calc import _field_tokens, select_default_point  # noqa: E402


FRACTION_TOKENS = {"decimal", "fraction"}
PERCENT_TOKENS = {"pct", "percent", "percentage"}
OTHER_UNIT_TOKENS = {"bp", "bps", "basispoint", "basispoints", "usd", "dollar", "dollars"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def declared_scale(value: str) -> str | None:
    tokens = _field_tokens(value)
    if tokens & FRACTION_TOKENS:
        return "fraction"
    if tokens & PERCENT_TOKENS:
        return "percent"
    if tokens & OTHER_UNIT_TOKENS:
        return "other"
    return None


def candidate_point(
    target_type: str,
    target_name: str,
    entity: dict[str, Any],
    row_index: int,
    row_count: int,
) -> tuple[float, str | None, str]:
    target_scale = declared_scale(target_name)
    adjusted = dict(entity)
    for key, value in entity.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            continue
        field_scale = declared_scale(key)
        if target_scale == "percent" and field_scale == "fraction":
            adjusted[key] = float(value) * 100.0
        elif target_scale == "fraction" and field_scale == "percent":
            adjusted[key] = float(value) / 100.0
        elif target_scale in {"fraction", "other"} and field_scale in {"fraction", "percent", "other"}:
            if target_scale != field_scale:
                adjusted.pop(key)
    point, field, reason = select_default_point(target_type, target_name, adjusted, row_index, row_count)
    if field is not None and field in entity and adjusted.get(field) != entity.get(field):
        reason = f"scaled_{declared_scale(field)}_to_{target_scale}"
    return point, field, reason


def evaluate_cpi(
    document: dict[str, Any],
    choose: Callable[..., tuple[float, str | None, str]],
    *,
    fraction_encoded: bool,
) -> dict[str, Any]:
    pairs = []
    reasons: dict[str, int] = defaultdict(int)
    for row in document["rows"]:
        if not ("2022" <= row["ref_month"][:4] <= "2023"):
            continue
        value = float(row["known_mom_pct"][-1])
        field = "current_component_movement_fraction" if fraction_encoded else "current_component_movement_pct"
        entity = {field: value / 100.0 if fraction_encoded else value}
        point, _, reason = choose("regression", "next_component_response_pct", entity, 0, 1)
        pairs.append((point, float(row["target_mom_pct"])))
        reasons[reason] += 1
    return {**regression_metrics(pairs), "selection_reasons": dict(sorted(reasons.items()))}


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


def evaluate_cot(
    document: dict[str, Any],
    choose: Callable[..., tuple[float, str | None, str]],
    *,
    fraction_encoded: bool,
) -> dict[str, Any]:
    correlations, errors = [], []
    reasons: dict[str, int] = defaultdict(int)
    for group in document["groups"]:
        if not ("2022" <= group["start_date"][:4] <= "2023"):
            continue
        predicted, actual = [], []
        for index, row in enumerate(group["rows"]):
            value = float(row["trailing_4wk_net_change_pct_oi"])
            field = "trailing_net_position_response_fraction" if fraction_encoded else "trailing_net_position_response_pct"
            entity = {field: value / 100.0 if fraction_encoded else value}
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


def close_metrics(left: dict[str, Any], right: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(math.isclose(float(left[key]), float(right[key]), rel_tol=0.0, abs_tol=1e-12) for key in keys)


def synthetic_checks() -> dict[str, bool]:
    cases = {
        "fraction_to_pct": ("regression", "future_margin_pct", {"current_margin_fraction": 0.042}, 4.2),
        "decimal_to_percent": ("regression", "future_margin_percent", {"current_margin_decimal": 0.042}, 4.2),
        "pct_to_fraction": ("regression", "future_margin_fraction", {"current_margin_pct": 4.2}, 0.042),
        "percent_to_decimal": ("ranking", "future_margin_decimal", {"current_margin_percent": 4.2}, 0.042),
        "bare_ratio_unchanged": ("regression", "future_coverage_ratio", {"current_coverage_ratio": 2.5}, 2.5),
        "unspecified_unchanged": ("regression", "future_margin", {"current_margin": 4.2}, 4.2),
        "fraction_rejected_for_bps": ("regression", "future_margin_bps", {"current_margin_fraction": 0.042}, 0.0),
    }
    return {
        name: math.isclose(candidate_point(target_type, target, entity, 0, 1)[0], expected, abs_tol=1e-12)
        for name, (target_type, target, entity, expected) in cases.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, default=PROJECT / "evaluation" / "datasets")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    paths = {
        "cpi": args.dataset_root / "cpi" / "components_2015_2023.json",
        "cot": args.dataset_root / "cot" / "legacy10_2015_2023.json",
        "auction": args.dataset_root / "auction" / "nominal_coupon_2010_2024-10-31.json",
        "macro_revision": args.dataset_root / "macro_revision" / "alfred_monthend_2014_2024.json",
        "fomc": args.dataset_root / "fomc" / "events_2000_2021.json",
    }
    documents = {name: json.loads(path.read_text()) for name, path in paths.items()}
    results = {
        "native_reference": {
            "cpi": evaluate_cpi(documents["cpi"], select_default_point, fraction_encoded=False),
            "cot": evaluate_cot(documents["cot"], select_default_point, fraction_encoded=False),
        },
        "fraction_baseline": {
            "cpi": evaluate_cpi(documents["cpi"], select_default_point, fraction_encoded=True),
            "cot": evaluate_cot(documents["cot"], select_default_point, fraction_encoded=True),
        },
        "fraction_candidate": {
            "cpi": evaluate_cpi(documents["cpi"], candidate_point, fraction_encoded=True),
            "cot": evaluate_cot(documents["cot"], candidate_point, fraction_encoded=True),
        },
    }
    controls = {
        "auction": {
            "baseline": evaluate_auction(documents["auction"], select_default_point),
            "candidate": evaluate_auction(documents["auction"], candidate_point),
        },
        "macro_revision": {
            "baseline": evaluate_macro(documents["macro_revision"], select_default_point),
            "candidate": evaluate_macro(documents["macro_revision"], candidate_point),
        },
        "fomc": {
            "baseline": evaluate_fomc(documents["fomc"], select_default_point),
            "candidate": evaluate_fomc(documents["fomc"], candidate_point),
        },
    }
    reference_restored = {
        "cpi": close_metrics(results["native_reference"]["cpi"], results["fraction_candidate"]["cpi"], ("mae", "rmse")),
        "cot": close_metrics(results["native_reference"]["cot"], results["fraction_candidate"]["cot"], ("mae", "mean_spearman")),
    }
    strict_improvement = {
        "cpi_mae": results["fraction_candidate"]["cpi"]["mae"] < results["fraction_baseline"]["cpi"]["mae"],
        "cpi_rmse": results["fraction_candidate"]["cpi"]["rmse"] < results["fraction_baseline"]["cpi"]["rmse"],
        "cot_mae": results["fraction_candidate"]["cot"]["mae"] < results["fraction_baseline"]["cot"]["mae"],
        "cot_rank_noninferior": results["fraction_candidate"]["cot"]["mean_spearman"] >= results["fraction_baseline"]["cot"]["mean_spearman"],
    }
    controls_unchanged = {name: values["baseline"] == values["candidate"] for name, values in controls.items()}
    checks = synthetic_checks()
    passed = all(reference_restored.values()) and all(strict_improvement.values()) and all(controls_unchanged.values()) and all(checks.values())
    report = {
        "schema_version": 1,
        "experiment": "generic_fraction_percent_scale_v1",
        "baseline_git_commit": "b6d4542",
        "hypothesis": (
            "For unknown regression and ranking schemas, explicitly declared fraction/decimal fields "
            "must be scaled by 100 for percent targets, and explicit percent fields by 0.01 for fraction targets."
        ),
        "scope": "L2 unknown-family scalar selection across regression and ranking",
        "dataset_sha256": {name: sha256(path) for name, path in paths.items()},
        "time_splits": {
            "cpi": "2022-2023 test rows",
            "cot": "2022-2023 test groups",
            "auction": "2024 confirmation control",
            "macro_revision": "2021-2022 test control",
            "fomc": "2019-2021 test control",
        },
        "transform": "Only field identifiers and their numerical representation change; outcomes are untouched.",
        "results": results,
        "reference_restored": reference_restored,
        "strict_improvement": strict_improvement,
        "controls": controls,
        "controls_unchanged": controls_unchanged,
        "synthetic_checks": checks,
        "decision_rule": (
            "Advance only if candidate fraction encoding restores native CPI and COT metrics, strictly "
            "improves fraction-encoded CPI MAE/RMSE and COT MAE with non-inferior rank correlation, "
            "leaves auction/macro/FOMC exactly unchanged, and passes every synthetic control."
        ),
        "decision": "pass_to_production_gates" if passed else "reject",
        "model_api_calls": 0,
        "local_llm_run": False,
        "limitations": [
            "The transformed schemas proxy unknown tasks and are not hidden competition units.",
            "No scale is inferred from value magnitude; conversion requires explicit fraction/decimal and percent identifiers.",
            "This evaluates numeric selection and scaling, not citation entailment.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "reference_restored": reference_restored,
        "strict_improvement": strict_improvement,
        "controls_unchanged": controls_unchanged,
        "synthetic_checks": checks,
        "decision": report["decision"],
        "cpi_mae": {name: values["cpi"]["mae"] for name, values in results.items()},
        "cot_mae": {name: values["cot"]["mae"] for name, values in results.items()},
    }, indent=2))


if __name__ == "__main__":
    main()
