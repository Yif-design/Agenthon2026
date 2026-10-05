#!/usr/bin/env python3
"""Audit deterministic mapping from generic direction signals to arbitrary labels."""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from t4agent.calculators.generic import _label, _legacy_label  # noqa: E402


GROUPS: tuple[dict[str, Any], ...] = (
    {
        "id": "demand_tier",
        "prompt": "Label high when demand rises strongly, medium when stable, and low when it falls.",
        "target": "future_demand_direction",
        "labels": ["high", "medium", "low"],
        "rows": [(2, "high"), (0, "medium"), (-2, "low")],
    },
    {
        "id": "credit_action",
        "prompt": "Choose upgrade for improving credit quality, unchanged for stable credit quality, or downgrade for deterioration.",
        "target": "future_credit_quality",
        "labels": ["upgrade", "unchanged", "downgrade"],
        "rows": [(2, "upgrade"), (0, "unchanged"), (-2, "downgrade")],
    },
    {
        "id": "capacity_action",
        "prompt": "Label expand if capacity will rise, hold if unchanged, or contract if it will fall.",
        "target": "future_capacity_direction",
        "labels": ["expand", "hold", "contract"],
        "rows": [(2, "expand"), (0, "hold"), (-2, "contract")],
    },
    {
        "id": "covenant_risk",
        "prompt": "Label at_risk if covenant failure is likely, otherwise not_at_risk.",
        "target": "covenant_risk",
        "labels": ["at_risk", "not_at_risk"],
        "rows": [(2, "at_risk"), (-2, "not_at_risk")],
    },
    {
        "id": "quality_gate",
        "prompt": "Label pass when every quality requirement is met, otherwise fail.",
        "target": "quality_gate",
        "labels": ["pass", "fail"],
        "rows": [(2, "pass"), (-2, "fail")],
    },
)

CONFIRMATION: tuple[dict[str, Any], ...] = (
    {
        "id": "opaque_throughput",
        "prompt": "Use zeta when throughput climbs, eta when throughput stays unchanged, and theta when throughput drops.",
        "target": "throughput_direction",
        "labels": ["zeta", "eta", "theta"],
        "rows": [(1, "zeta"), (0, "eta"), (-1, "theta")],
    },
    {
        "id": "opaque_conditions",
        "prompt": "Assign red for worsening conditions; amber for steady conditions; green for improving conditions.",
        "target": "condition_direction",
        "labels": ["red", "amber", "green"],
        "rows": [(1, "green"), (0, "amber"), (-1, "red")],
    },
    {
        "id": "opaque_metric",
        "prompt": "class_a means the metric is higher; class_b means the metric is lower.",
        "target": "metric_direction",
        "labels": ["class_a", "class_b"],
        "rows": [(1, "class_a"), (-1, "class_b")],
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def score(groups: tuple[dict[str, Any], ...], use_schema: bool) -> tuple[int, int, list[dict[str, Any]]]:
    correct = 0
    total = 0
    rows = []
    for group in groups:
        for signal, expected in group["rows"]:
            predicted = (
                _label(signal, group["labels"], group["prompt"], group["target"])
                if use_schema
                else _legacy_label(signal, group["labels"])
            )
            total += 1
            correct += predicted == expected
            rows.append({"group": group["id"], "signal": signal, "expected": expected, "predicted": predicted})
    return correct, total, rows


def main() -> None:
    args = parse_args()
    baseline_correct, baseline_total, _ = score(GROUPS, False)
    candidate_correct, candidate_total, candidate_rows = score(GROUPS, True)
    confirmation_correct, confirmation_total, confirmation_rows = score(CONFIRMATION, True)
    permutation_checks = 0
    permutation_passed = 0
    for group in GROUPS + CONFIRMATION:
        for labels in itertools.permutations(group["labels"]):
            for signal, expected in group["rows"]:
                permutation_checks += 1
                permutation_passed += _label(signal, list(labels), group["prompt"], group["target"]) == expected
    ambiguous_labels = ["class_x", "class_y"]
    ambiguous = _label(1, ambiguous_labels, "Choose the appropriate class.", "unknown_target")
    report = {
        "schema_version": 1,
        "experiment": "generic_label_role_mapping_v1",
        "baseline_git_commit": "2b3422b483fd056c0e15c6ab816c4f5bdd6c8171",
        "hypothesis": "A bounded deterministic parser can map the existing validated generic direction signal to arbitrary allowed labels from task-schema wording more reliably than a fixed label-token list, without another model request.",
        "development_dataset": "The 13-row five-schema set retained from the two rejected direct-label experiments.",
        "confirmation_dataset": "Eight new rows across three opaque label schemas whose role is stated only in the task prompt.",
        "results": {
            "development_baseline_correct": baseline_correct,
            "development_candidate_correct": candidate_correct,
            "development_total": candidate_total,
            "confirmation_correct": confirmation_correct,
            "confirmation_total": confirmation_total,
            "permutation_checks_passed": permutation_passed,
            "permutation_checks_total": permutation_checks,
            "ambiguous_fallback": ambiguous,
            "ambiguous_fallback_allowed": ambiguous in ambiguous_labels,
        },
        "development_rows": candidate_rows,
        "confirmation_rows": confirmation_rows,
        "decision_rule": "Require 13/13 development, 8/8 confirmation, all label-order permutations, an allowed deterministic fallback for ambiguous prompts, unchanged public outputs and no added model calls.",
        "not_measured": "Real hidden-outcome accuracy or generic direction-signal extraction accuracy.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["results"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
