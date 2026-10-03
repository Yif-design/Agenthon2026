#!/usr/bin/env python3
"""Test one locked shrinkage factor for explicit generic change baselines."""

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

from evaluation.experiments.generic_fraction_scale_screen import correlation, ranks  # noqa: E402
from evaluation.experiments.generic_unit_compatibility_screen import (  # noqa: E402
    evaluate_auction,
    evaluate_fomc,
    regression_metrics,
)
from t4agent.calc import (  # noqa: E402
    CHANGE_BASELINE_SHRINKAGE,
    CHANGE_TOKENS,
    _field_tokens,
    select_default_point,
)


GRID = (0.05, 0.1, 0.2, 0.25, 0.33, 0.5, 0.75, 1.0)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def baseline_point(
    target_type: str,
    target_name: str,
    entity: dict[str, Any],
    row_index: int,
    row_count: int,
) -> tuple[float, str | None, str]:
    """Reconstruct the pinned pre-change baseline when run after adoption."""
    point, field, reason = select_default_point(target_type, target_name, entity, row_index, row_count)
    if reason == "damped_change_match":
        return point / CHANGE_BASELINE_SHRINKAGE, field, "target_token_match"
    return point, field, reason


def shrunken_point(alpha: float) -> Callable[..., tuple[float, str | None, str]]:
    def choose(
        target_type: str,
        target_name: str,
        entity: dict[str, Any],
        row_index: int,
        row_count: int,
    ) -> tuple[float, str | None, str]:
        point, field, reason = baseline_point(target_type, target_name, entity, row_index, row_count)
        target_is_change = bool(_field_tokens(target_name) & CHANGE_TOKENS)
        field_is_change = field is not None and bool(_field_tokens(field) & CHANGE_TOKENS)
        if (
            target_type in {"regression", "ranking"}
            and reason == "target_token_match"
            and target_is_change
            and field_is_change
        ):
            return alpha * point, field, "damped_change_match"
        return point, field, reason

    return choose


def evaluate_cpi(
    document: dict[str, Any],
    choose: Callable[..., tuple[float, str | None, str]],
    years: set[str],
) -> dict[str, Any]:
    pairs: list[tuple[float, float]] = []
    reasons: dict[str, int] = defaultdict(int)
    for row in document["rows"]:
        if row["ref_month"][:4] not in years:
            continue
        entity = {"latest_component_change_pct": float(row["known_mom_pct"][-1])}
        point, _, reason = choose("regression", "future_component_change_pct", entity, 0, 1)
        pairs.append((point, float(row["target_mom_pct"])))
        reasons[reason] += 1
    return {**regression_metrics(pairs), "selection_reasons": dict(sorted(reasons.items()))}


def evaluate_cot(
    document: dict[str, Any],
    choose: Callable[..., tuple[float, str | None, str]],
    years: set[str],
) -> dict[str, Any]:
    correlations: list[float] = []
    errors: list[float] = []
    reasons: dict[str, int] = defaultdict(int)
    for group in document["groups"]:
        if group["start_date"][:4] not in years:
            continue
        predicted, actual = [], []
        for index, row in enumerate(group["rows"]):
            entity = {"trailing_position_change_pct": float(row["trailing_4wk_net_change_pct_oi"])}
            point, _, reason = choose(
                "ranking", "future_position_change_pct", entity, index, len(group["rows"])
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


def evaluate_macro(
    document: dict[str, Any],
    choose: Callable[..., tuple[float, str | None, str]],
    years: set[str],
) -> dict[str, Any]:
    pairs: list[tuple[float, float]] = []
    reasons: dict[str, int] = defaultdict(int)
    for row in document["rows"]:
        if row["cutoff_vintage"][:4] not in years or not row["all_history_changes"]:
            continue
        entity = {"historical_revision_delta": statistics.median(row["all_history_changes"])}
        point, _, reason = choose("regression", "next_revision_delta", entity, 0, 1)
        pairs.append((point, float(row["target_change"])))
        reasons[reason] += 1
    return {**regression_metrics(pairs), "selection_reasons": dict(sorted(reasons.items()))}


def evaluate_period(
    documents: dict[str, dict[str, Any]],
    choose: Callable[..., tuple[float, str | None, str]],
    split: dict[str, set[str]],
) -> dict[str, dict[str, Any]]:
    return {
        "cpi": evaluate_cpi(documents["cpi"], choose, split["cpi"]),
        "cot": evaluate_cot(documents["cot"], choose, split["cot"]),
        "macro_revision": evaluate_macro(documents["macro_revision"], choose, split["macro_revision"]),
    }


def normalized_mae(candidate: dict[str, dict[str, Any]], baseline: dict[str, dict[str, Any]]) -> float:
    return statistics.fmean(candidate[name]["mae"] / baseline[name]["mae"] for name in baseline)


def synthetic_checks(candidate: Callable[..., tuple[float, str | None, str]]) -> dict[str, bool]:
    cases = {
        "explicit_change_regression_damped": (
            "regression", "future_margin_change_pct", {"latest_margin_change_pct": 4.0}, 2.0
        ),
        "explicit_change_ranking_damped": (
            "ranking", "future_position_delta", {"trailing_position_delta": -6.0}, -3.0
        ),
        "level_regression_unchanged": (
            "regression", "future_margin_pct", {"current_margin_pct": 4.0}, 4.0
        ),
        "classification_unchanged": (
            "classification", "future_margin_change_pct", {"latest_margin_change_pct": 4.0}, 4.0
        ),
        "unmatched_change_stays_zero": (
            "regression", "future_margin_change_pct", {"current_margin_pct": 4.0}, 0.0
        ),
        "metadata_stays_excluded": (
            "regression", "future_margin_change_pct", {"year": 2026}, 0.0
        ),
        "incompatible_units_stay_excluded": (
            "regression", "future_yield_change_bps", {"latest_yield_change_pct": 0.2}, 0.0
        ),
    }
    return {
        name: math.isclose(candidate(target_type, target, entity, 0, 1)[0], expected, abs_tol=1e-12)
        for name, (target_type, target, entity, expected) in cases.items()
    }


def period_gate(candidate: dict[str, dict[str, Any]], baseline: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "mean_normalized_mae": normalized_mae(candidate, baseline),
        "mean_normalized_mae_improved": normalized_mae(candidate, baseline) < 1.0,
        "cpi_mae_noninferior": candidate["cpi"]["mae"] <= baseline["cpi"]["mae"],
        "macro_mae_noninferior": candidate["macro_revision"]["mae"] <= baseline["macro_revision"]["mae"],
        "cot_rank_noninferior": candidate["cot"]["mean_spearman"] >= baseline["cot"]["mean_spearman"],
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

    dev_split = {"cpi": {"2021"}, "cot": {"2021"}, "macro_revision": {"2020"}}
    test_split = {"cpi": {"2022"}, "cot": {"2022"}, "macro_revision": {"2021", "2022"}}
    confirmation_split = {"cpi": {"2024", "2025"}, "cot": {"2023"}, "macro_revision": {"2023"}}

    dev_baseline = evaluate_period(documents, baseline_point, dev_split)
    grid_results: dict[str, Any] = {}
    for alpha in GRID:
        candidate = evaluate_period(documents, shrunken_point(alpha), dev_split)
        grid_results[str(alpha)] = {
            "mean_normalized_mae": normalized_mae(candidate, dev_baseline),
            "metrics": candidate,
        }
    selected_alpha = min(GRID, key=lambda alpha: (grid_results[str(alpha)]["mean_normalized_mae"], alpha))
    candidate_point = shrunken_point(selected_alpha)

    test_baseline = evaluate_period(documents, baseline_point, test_split)
    test_candidate = evaluate_period(documents, candidate_point, test_split)
    confirmation_documents = dict(documents)
    confirmation_documents["cpi"] = loaded["cpi_confirmation"]
    confirmation_baseline = evaluate_period(confirmation_documents, baseline_point, confirmation_split)
    confirmation_candidate = evaluate_period(confirmation_documents, candidate_point, confirmation_split)
    test_gate = period_gate(test_candidate, test_baseline)
    confirmation_gate = period_gate(confirmation_candidate, confirmation_baseline)

    controls = {
        "auction": {
            "baseline": evaluate_auction(loaded["auction"], baseline_point),
            "candidate": evaluate_auction(loaded["auction"], candidate_point),
        },
        "fomc": {
            "baseline": evaluate_fomc(loaded["fomc"], baseline_point),
            "candidate": evaluate_fomc(loaded["fomc"], candidate_point),
        },
    }
    controls_unchanged = {name: values["baseline"] == values["candidate"] for name, values in controls.items()}
    checks = synthetic_checks(candidate_point)
    selected_as_locked = math.isclose(selected_alpha, 0.5, abs_tol=1e-12)
    passed = (
        selected_as_locked
        and all(value for key, value in test_gate.items() if key != "mean_normalized_mae")
        and all(value for key, value in confirmation_gate.items() if key != "mean_normalized_mae")
        and all(controls_unchanged.values())
        and all(checks.values())
    )
    report = {
        "schema_version": 1,
        "experiment": "generic_change_shrinkage_v1",
        "baseline_git_commit": "1b13a46fdecaf0853c37bf0762f2f4f4fcc7e211",
        "hypothesis": (
            "For unknown regression and ranking schemas with an explicit matched change field, shrinking "
            "the carried-forward change by one cross-domain development-selected factor reduces noisy over-persistence."
        ),
        "scope": "L2/L3 unknown-family scalar projection across regression and ranking",
        "dataset_sha256": {name: sha256(path) for name, path in paths.items()},
        "time_splits": {
            "development": {name: sorted(years) for name, years in dev_split.items()},
            "test": {name: sorted(years) for name, years in test_split.items()},
            "confirmation": {name: sorted(years) for name, years in confirmation_split.items()},
            "controls": {"auction": "2024", "fomc": "2019-2021"},
        },
        "alpha_grid": list(GRID),
        "development_baseline": dev_baseline,
        "development_grid": grid_results,
        "selected_alpha": selected_alpha,
        "selected_alpha_matches_preregistered_lock": selected_as_locked,
        "test": {"baseline": test_baseline, "candidate": test_candidate, "gate": test_gate},
        "confirmation": {
            "baseline": confirmation_baseline,
            "candidate": confirmation_candidate,
            "gate": confirmation_gate,
        },
        "controls": controls,
        "controls_unchanged": controls_unchanged,
        "synthetic_checks": checks,
        "decision_rule": (
            "Advance only if development selects the preregistered alpha 0.5; test and confirmation each "
            "improve mean normalized MAE, do not worsen CPI or macro MAE, and do not worsen COT Spearman; "
            "auction/FOMC controls remain exactly unchanged; and every synthetic guard passes."
        ),
        "decision": "pass_to_production_gates" if passed else "reject",
        "model_api_calls": 0,
        "local_llm_run": False,
        "persistent_virtual_environment": False,
        "limitations": [
            "Generic identifiers proxy unseen schemas and are not hidden competition tasks.",
            "COT Spearman is invariant to positive scalar shrinkage; COT MAE remains a diagnostic in the aggregate gate.",
            "The rule applies only to an explicit change target matched to an explicit change field.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "selected_alpha": selected_alpha,
        "development_normalized_mae": grid_results[str(selected_alpha)]["mean_normalized_mae"],
        "test_gate": test_gate,
        "confirmation_gate": confirmation_gate,
        "controls_unchanged": controls_unchanged,
        "synthetic_checks": checks,
        "decision": report["decision"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
