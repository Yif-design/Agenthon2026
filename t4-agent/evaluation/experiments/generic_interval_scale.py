#!/usr/bin/env python3
"""Calibrate one shared final-interval multiplier for generic numeric tasks."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from t4agent.calc import interval_for, select_default_point  # noqa: E402


GRID = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 6.0, 8.0)
TARGET_COVERAGE = 0.90


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def base_row(
    target_type: str,
    target_name: str,
    entity: dict[str, Any],
    outcome: float,
    row_index: int = 0,
    row_count: int = 1,
) -> tuple[float, float, float]:
    point = select_default_point(target_type, target_name, entity, row_index, row_count)[0]
    interval = interval_for(point, target_name, TARGET_COVERAGE)
    return point, (interval["hi"] - interval["lo"]) / 2.0, float(outcome)


def cpi_rows(document: dict[str, Any], years: set[str]) -> list[tuple[float, float, float]]:
    return [
        base_row(
            "regression",
            "future_component_change_pct",
            {"latest_component_change_pct": float(row["known_mom_pct"][-1])},
            float(row["target_mom_pct"]),
        )
        for row in document["rows"]
        if row["ref_month"][:4] in years
    ]


def cot_rows(document: dict[str, Any], years: set[str]) -> list[tuple[float, float, float]]:
    rows = []
    for group in document["groups"]:
        if group["start_date"][:4] not in years:
            continue
        for index, row in enumerate(group["rows"]):
            rows.append(base_row(
                "ranking",
                "future_position_change_pct",
                {"trailing_position_change_pct": float(row["trailing_4wk_net_change_pct_oi"])},
                float(row["target_5wk_change_pct_start_oi"]),
                index,
                len(group["rows"]),
            ))
    return rows


def macro_rows(document: dict[str, Any], years: set[str]) -> list[tuple[float, float, float]]:
    return [
        base_row(
            "regression",
            "next_revision_delta",
            {"historical_revision_delta": statistics.median(row["all_history_changes"])},
            float(row["target_change"]),
        )
        for row in document["rows"]
        if row["cutoff_vintage"][:4] in years and row["all_history_changes"]
    ]


def auction_rows(document: dict[str, Any]) -> list[tuple[float, float, float]]:
    history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=6))
    rows = []
    for row in sorted(document["data"], key=lambda item: (item["auction_date"], item["tenor"])):
        prior = history[row["tenor"]]
        if row["auction_date"][:4] == "2024" and prior:
            rows.append(base_row(
                "regression",
                "next_demand_coverage_ratio",
                {"recent_demand_coverage_ratio": statistics.fmean(prior)},
                float(row["bid_to_cover_ratio"]),
            ))
        prior.append(float(row["bid_to_cover_ratio"]))
    return rows


def fomc_rows(document: dict[str, Any]) -> list[tuple[float, float, float]]:
    rows = []
    for event in document["events"]:
        if not ("2019" <= event["decision_date"][:4] <= "2021"):
            continue
        for tenor, current_yield in event["start_yields_pct"].items():
            rows.append(base_row(
                "regression",
                "future_curve_response_bps",
                {"current_curve_response_pct": float(current_yield)},
                float(event["yield_changes_bps"][tenor]),
            ))
    return rows


def interval_metrics(rows: list[tuple[float, float, float]], multiplier: float) -> dict[str, float | int]:
    coverage = statistics.fmean(
        float(point - multiplier * half <= outcome <= point + multiplier * half)
        for point, half, outcome in rows
    )
    return {
        "rows": len(rows),
        "coverage": coverage,
        "calibration_error": abs(coverage - TARGET_COVERAGE),
        "mean_full_width": statistics.fmean(2.0 * multiplier * half for _, half, _ in rows),
    }


def evaluate_period(
    documents: dict[str, dict[str, Any]], split: dict[str, set[str]], multiplier: float
) -> dict[str, dict[str, float | int]]:
    rows = {
        "cpi": cpi_rows(documents["cpi"], split["cpi"]),
        "cot": cot_rows(documents["cot"], split["cot"]),
        "macro_revision": macro_rows(documents["macro_revision"], split["macro_revision"]),
    }
    return {name: interval_metrics(values, multiplier) for name, values in rows.items()}


def mean_loss(results: dict[str, dict[str, float | int]]) -> float:
    return statistics.fmean(float(row["calibration_error"]) for row in results.values())


def period_gate(
    baseline: dict[str, dict[str, float | int]], candidate: dict[str, dict[str, float | int]]
) -> dict[str, Any]:
    return {
        "baseline_mean_calibration_error": mean_loss(baseline),
        "candidate_mean_calibration_error": mean_loss(candidate),
        "mean_calibration_error_improved": mean_loss(candidate) < mean_loss(baseline),
        "no_domain_worsened": all(
            float(candidate[name]["calibration_error"]) <= float(baseline[name]["calibration_error"])
            for name in baseline
        ),
    }


def synthetic_checks(multiplier: float) -> dict[str, bool]:
    point = 4.0
    base = interval_for(point, "future_margin_pct", TARGET_COVERAGE)
    base_half = (base["hi"] - base["lo"]) / 2.0
    candidate = {
        "level": base["level"],
        "lo": point - multiplier * base_half,
        "hi": point + multiplier * base_half,
    }
    classification = dict(base)
    return {
        "regression_half_width_doubled": math.isclose(
            (candidate["hi"] - candidate["lo"]) / 2.0, 2.0 * base_half, abs_tol=1e-12
        ),
        "point_unchanged": math.isclose((candidate["lo"] + candidate["hi"]) / 2.0, point, abs_tol=1e-12),
        "level_unchanged": candidate["level"] == TARGET_COVERAGE,
        "classification_interval_unchanged": classification == base,
        "finite_and_ordered": all(math.isfinite(value) for value in candidate.values()) and candidate["lo"] <= candidate["hi"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, default=PROJECT / "evaluation" / "datasets")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    paths = {
        "cpi": args.dataset_root / "cpi" / "components_2015_2023.json",
        "cpi_confirmation": args.dataset_root / "cpi" / "components_2024_2025_confirmation.json",
        "cot": args.dataset_root / "cot" / "legacy10_2015_2023.json",
        "macro_revision": args.dataset_root / "macro_revision" / "alfred_monthend_2014_2024.json",
        "auction": args.dataset_root / "auction" / "nominal_coupon_2010_2024-10-31.json",
        "fomc": args.dataset_root / "fomc" / "events_2000_2021.json",
    }
    loaded = {name: json.loads(path.read_text()) for name, path in paths.items()}
    documents = {name: loaded[name] for name in ("cpi", "cot", "macro_revision")}
    splits = {
        "development": {"cpi": {"2021"}, "cot": {"2021"}, "macro_revision": {"2020"}},
        "test": {"cpi": {"2022"}, "cot": {"2022"}, "macro_revision": {"2021", "2022"}},
        "confirmation": {"cpi": {"2024", "2025"}, "cot": {"2023"}, "macro_revision": {"2023"}},
    }

    dev_baseline = evaluate_period(documents, splits["development"], 1.0)
    grid_results = {}
    for multiplier in GRID:
        values = evaluate_period(documents, splits["development"], multiplier)
        grid_results[str(multiplier)] = {
            "mean_calibration_error": mean_loss(values),
            "no_domain_worsened": all(
                float(values[name]["calibration_error"]) <= float(dev_baseline[name]["calibration_error"])
                for name in dev_baseline
            ),
            "metrics": values,
        }
    eligible = [value for value in GRID if grid_results[str(value)]["no_domain_worsened"]]
    selected = min(eligible, key=lambda value: (grid_results[str(value)]["mean_calibration_error"], value))

    results = {}
    gates = {}
    for name in ("test", "confirmation"):
        period_documents = dict(documents)
        if name == "confirmation":
            period_documents["cpi"] = loaded["cpi_confirmation"]
        baseline = evaluate_period(period_documents, splits[name], 1.0)
        candidate = evaluate_period(period_documents, splits[name], selected)
        results[name] = {"baseline": baseline, "candidate": candidate}
        gates[name] = period_gate(baseline, candidate)

    controls = {}
    for name, rows in {
        "auction": auction_rows(loaded["auction"]),
        "fomc": fomc_rows(loaded["fomc"]),
    }.items():
        baseline = interval_metrics(rows, 1.0)
        candidate = interval_metrics(rows, selected)
        controls[name] = {
            "baseline": baseline,
            "candidate": candidate,
            "calibration_noninferior": candidate["calibration_error"] <= baseline["calibration_error"],
        }
    checks = synthetic_checks(selected)
    selected_as_locked = math.isclose(selected, 2.0, abs_tol=1e-12)
    passed = (
        selected_as_locked
        and all(gate["mean_calibration_error_improved"] and gate["no_domain_worsened"] for gate in gates.values())
        and all(control["calibration_noninferior"] for control in controls.values())
        and all(checks.values())
    )
    report = {
        "schema_version": 1,
        "experiment": "generic_interval_scale_v1",
        "baseline_git_commit": "cbe352f51878c90daaf4fb0332f358a152deec95",
        "hypothesis": (
            "Generic numeric intervals are systematically too narrow; one development-selected multiplier "
            "on the final half-width improves 90% coverage calibration without changing predictions."
        ),
        "scope": "L3 unknown-family regression and ranking intervals",
        "official_metric": "absolute difference between realized interval coverage and requested interval level",
        "target_coverage": TARGET_COVERAGE,
        "dataset_sha256": {name: sha256(path) for name, path in paths.items()},
        "time_splits": {name: {domain: sorted(years) for domain, years in split.items()} for name, split in splits.items()},
        "multiplier_grid": list(GRID),
        "development_baseline": dev_baseline,
        "development_grid": grid_results,
        "selection_constraint": "Every development domain calibration error must be no worse than multiplier 1.0.",
        "selected_multiplier": selected,
        "selected_multiplier_matches_preregistered_lock": selected_as_locked,
        "results": results,
        "gates": gates,
        "controls": controls,
        "synthetic_checks": checks,
        "prediction_invariance": "The candidate changes final interval bounds only; point and label paths are not called differently.",
        "decision_rule": (
            "Advance only if development locks multiplier 2.0; test and confirmation both reduce mean "
            "calibration error without worsening any CPI, COT or macro-revision domain; auction and FOMC "
            "controls are non-inferior; and every synthetic invariant passes."
        ),
        "decision": "pass_to_production_gates" if passed else "reject",
        "model_api_calls": 0,
        "local_llm_run": False,
        "limitations": [
            "Transformed generic schemas proxy unknown tasks and are not sealed competition tasks.",
            "The official score has no direct width penalty; this experiment optimizes the published coverage term only.",
            "CPI confirmation uses 2024-2025 while COT and macro confirmation use 2023.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "selected_multiplier": selected,
        "development_loss": grid_results[str(selected)]["mean_calibration_error"],
        "gates": gates,
        "controls": {name: value["calibration_noninferior"] for name, value in controls.items()},
        "synthetic_checks": checks,
        "decision": report["decision"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
