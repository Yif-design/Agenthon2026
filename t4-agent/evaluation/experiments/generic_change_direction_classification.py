#!/usr/bin/env python3
"""Screen explicit generic change fields as no-model classification directions."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from t4agent.calc import CHANGE_TOKENS, _field_tokens, select_default_point  # noqa: E402
from t4agent.calculators.generic import _label, infer_label_roles  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def direction(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def predict_candidate(target: str, entity: dict[str, float], labels: list[str]) -> str:
    point, field, reason = select_default_point("classification", target, entity, 0, 1)
    roles = infer_label_roles(labels, "", target)
    explicit_change = bool(_field_tokens(target) & CHANGE_TOKENS)
    matched_change = field is not None and bool(_field_tokens(field) & CHANGE_TOKENS)
    if reason == "target_token_match" and explicit_change and matched_change and {"positive", "negative"} <= roles.keys():
        return _label(direction(point), labels, "", target) or labels[0]
    return _label(0, labels, "", target) or labels[0]


def score_pairs(pairs: list[tuple[float, float]], target: str, field: str) -> dict[str, Any]:
    labels = ["up", "down"]
    baseline_correct = candidate_correct = reversed_correct = 0
    for feature, outcome in pairs:
        expected = "up" if outcome > 0 else "down"
        baseline_correct += (_label(0, labels, "", target) == expected)
        candidate_correct += (predict_candidate(target, {field: feature}, labels) == expected)
        reversed_correct += (predict_candidate(target, {field: feature}, list(reversed(labels))) == expected)
    total = len(pairs)
    return {
        "rows": total,
        "baseline_accuracy": baseline_correct / total,
        "candidate_accuracy": candidate_correct / total,
        "reversed_label_accuracy": reversed_correct / total,
        "label_order_invariant": candidate_correct == reversed_correct,
    }


def cpi_pairs(document: dict[str, Any], years: set[str]) -> list[tuple[float, float]]:
    return [
        (float(row["known_mom_pct"][-1]), float(row["target_mom_pct"]))
        for row in document["rows"] if row["ref_month"][:4] in years
    ]


def cot_pairs(document: dict[str, Any], years: set[str]) -> list[tuple[float, float]]:
    return [
        (float(row["trailing_4wk_net_change_pct_oi"]), float(row["target_5wk_change_pct_start_oi"]))
        for group in document["groups"] if group["start_date"][:4] in years for row in group["rows"]
    ]


def macro_pairs(document: dict[str, Any], years: set[str]) -> list[tuple[float, float]]:
    return [
        (statistics.median(row["all_history_changes"]), float(row["target_change"]))
        for row in document["rows"]
        if row["cutoff_vintage"][:4] in years and row["all_history_changes"]
    ]


def evaluate(
    documents: dict[str, dict[str, Any]], split: dict[str, set[str]]
) -> dict[str, dict[str, Any]]:
    return {
        "cpi": score_pairs(
            cpi_pairs(documents["cpi"], split["cpi"]),
            "future_component_change_pct", "latest_component_change_pct",
        ),
        "cot": score_pairs(
            cot_pairs(documents["cot"], split["cot"]),
            "future_position_change_pct", "trailing_position_change_pct",
        ),
        "macro_revision": score_pairs(
            macro_pairs(documents["macro_revision"], split["macro_revision"]),
            "next_revision_delta", "historical_revision_delta",
        ),
    }


def split_gate(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    baseline_mean = statistics.fmean(row["baseline_accuracy"] for row in results.values())
    candidate_mean = statistics.fmean(row["candidate_accuracy"] for row in results.values())
    return {
        "baseline_mean_accuracy": baseline_mean,
        "candidate_mean_accuracy": candidate_mean,
        "mean_accuracy_improved": candidate_mean > baseline_mean,
        "no_domain_worsened": all(row["candidate_accuracy"] >= row["baseline_accuracy"] for row in results.values()),
        "label_order_invariant": all(row["label_order_invariant"] for row in results.values()),
    }


def safety_checks() -> dict[str, bool]:
    labels = ["up", "down"]
    return {
        "positive_change": predict_candidate(
            "future_margin_change_pct", {"latest_margin_change_pct": 2.0}, labels
        ) == "up",
        "negative_change": predict_candidate(
            "future_margin_change_pct", {"latest_margin_change_pct": -2.0}, labels
        ) == "down",
        "zero_keeps_baseline": predict_candidate(
            "future_margin_change_pct", {"latest_margin_change_pct": 0.0}, labels
        ) == _label(0, labels, "", "future_margin_change_pct"),
        "level_keeps_baseline": predict_candidate(
            "future_margin_pct", {"current_margin_pct": -2.0}, labels
        ) == _label(0, labels, "", "future_margin_pct"),
        "unmatched_change_keeps_baseline": predict_candidate(
            "future_margin_change_pct", {"current_margin_pct": -2.0}, labels
        ) == _label(0, labels, "", "future_margin_change_pct"),
        "opaque_labels_keep_baseline": predict_candidate(
            "future_margin_change_pct", {"latest_margin_change_pct": -2.0}, ["class_a", "class_b"]
        ) == _label(0, ["class_a", "class_b"], "", "future_margin_change_pct"),
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
    }
    loaded = {name: json.loads(path.read_text()) for name, path in paths.items()}
    base_documents = {name: loaded[name] for name in ("cpi", "cot", "macro_revision")}
    splits = {
        "development": {"cpi": {"2021"}, "cot": {"2021"}, "macro_revision": {"2020"}},
        "test": {"cpi": {"2022"}, "cot": {"2022"}, "macro_revision": {"2021", "2022"}},
        "confirmation": {"cpi": {"2024", "2025"}, "cot": {"2023"}, "macro_revision": {"2023"}},
    }
    results = {}
    gates = {}
    for name, split in splits.items():
        documents = dict(base_documents)
        if name == "confirmation":
            documents["cpi"] = loaded["cpi_confirmation"]
        results[name] = evaluate(documents, split)
        gates[name] = split_gate(results[name])
    checks = safety_checks()
    passed = (
        gates["development"]["mean_accuracy_improved"]
        and gates["test"]["mean_accuracy_improved"]
        and gates["test"]["no_domain_worsened"]
        and gates["confirmation"]["mean_accuracy_improved"]
        and gates["confirmation"]["no_domain_worsened"]
        and all(gate["label_order_invariant"] for gate in gates.values())
        and all(checks.values())
    )
    report = {
        "schema_version": 1,
        "experiment": "generic_change_direction_classification_v1",
        "baseline_git_commit": "f74fe4713080f9446a65a169a1a68573bf288cd2",
        "hypothesis": (
            "For unknown binary direction classifications, use the sign of a numeric field only when "
            "the target and selected field explicitly describe change and both label roles are unambiguous."
        ),
        "scope": "L2/L3 unknown-family no-model classification fallback",
        "dataset_sha256": {name: sha256(path) for name, path in paths.items()},
        "time_splits": {name: {domain: sorted(years) for domain, years in split.items()} for name, split in splits.items()},
        "results": results,
        "gates": gates,
        "safety_checks": checks,
        "decision_rule": (
            "Advance only if cross-domain mean accuracy improves on development, test and confirmation; "
            "no test or confirmation domain worsens; label order is invariant; and every safety check passes."
        ),
        "decision": "pass_to_production_gates" if passed else "reject",
        "model_api_calls": 0,
        "local_llm_run": False,
        "limitations": [
            "The transformed binary labels proxy unknown direction tasks and are not hidden competition labels.",
            "Rows with exactly zero outcomes are treated as down because the screen is binary.",
            "No task prompt or corpus evidence is used by this no-model candidate.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"gates": gates, "safety_checks": checks, "decision": report["decision"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
