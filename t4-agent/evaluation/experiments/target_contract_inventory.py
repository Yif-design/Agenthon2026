#!/usr/bin/env python3
"""Inventory authoritative target quantity metadata before adding a central TargetSpec."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

QUANTITY_KEYS = ("unit", "units", "minimum", "maximum", "min", "max", "domain")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    units: list[dict[str, Any]] = []
    type_totals: dict[str, int] = {}
    type_with_units: dict[str, int] = {}
    for task_path in sorted(args.units_dir.glob("*/task.json")):
        task = json.loads(task_path.read_text())
        target = task.get("target") or {}
        target_type = str(target.get("type") or task.get("target_type") or "")
        explicit = {key: target[key] for key in QUANTITY_KEYS if key in target}
        type_totals[target_type] = type_totals.get(target_type, 0) + 1
        if "unit" in explicit or "units" in explicit:
            type_with_units[target_type] = type_with_units.get(target_type, 0) + 1
        units.append({
            "task_id": task.get("task_id"),
            "target_name": target.get("name"),
            "target_type": target_type,
            "target_keys": sorted(target),
            "explicit_quantity_metadata": explicit,
            "task_sha256": sha256(task_path),
        })
    count = len(units)
    explicit_unit_count = sum(bool(set(row["explicit_quantity_metadata"]) & {"unit", "units"}) for row in units)
    explicit_domain_count = sum(bool(set(row["explicit_quantity_metadata"]) & {"minimum", "maximum", "min", "max", "domain"}) for row in units)
    types_with_unit_coverage = sum(type_with_units.get(name, 0) > 0 for name in type_totals)
    official_alignment = {
        "closed_target_types": True,
        "classification_label_required_and_vocabulary_checked": True,
        "regression_and_ranking_point_required": True,
        "supplied_point_must_be_finite": True,
        "interval_required_finite_ordered_and_exact_level": True,
        "optional_rank_must_be_complete_permutation": True,
        "point_inside_interval_required": False,
        "quantity_unit_checked": False,
        "quantity_domain_checked": False,
        "source": "starter-repos/track4-analysis-public/qfbench2_track_analysis/alignment.py"
    }
    production_validator = {
        "closed_target_types": False,
        "classification_label_required_and_vocabulary_checked": True,
        "regression_and_ranking_point_required": True,
        "supplied_point_must_be_finite": True,
        "interval_required_finite_ordered_and_exact_level": True,
        "optional_rank_must_be_complete_permutation": True,
        "point_inside_interval_required": True,
        "quantity_unit_checked": False,
        "quantity_domain_checked": False,
        "source": "t4agent/validate.py"
    }
    metadata_gate = (
        count > 0
        and explicit_unit_count / count >= 0.80
        and types_with_unit_coverage >= 2
        and explicit_domain_count == count
    )
    report = {
        "schema_version": 1,
        "experiment": "target_contract_inventory_v1",
        "date": "2026-09-30",
        "baseline_git_commit": "b6b1605bcb278ad3326a4e3a72a6f8a434fb0653",
        "hypothesis": "Official task targets expose enough machine-readable unit and domain metadata to support a shared TargetSpec without heuristic prompt interpretation.",
        "scope": "L2 target quantity contract preflight",
        "units": units,
        "summary": {
            "tasks": count,
            "target_types": type_totals,
            "tasks_with_explicit_unit": explicit_unit_count,
            "explicit_unit_rate": explicit_unit_count / count if count else 0.0,
            "tasks_with_explicit_domain_or_bounds": explicit_domain_count,
            "explicit_domain_or_bounds_rate": explicit_domain_count / count if count else 0.0,
            "target_types_with_any_explicit_unit": types_with_unit_coverage,
        },
        "contract_comparison": {"official_alignment": official_alignment, "production_validator": production_validator},
        "decision_rule": "Implement a central metadata-driven TargetSpec only if at least 80% of tasks expose an explicit unit across at least two target types and every domain-bound task exposes authoritative bounds; otherwise do not infer a global contract from free-form prompt text.",
        "decision": "advance_to_target_spec" if metadata_gate else "reject_metadata_driven_target_spec",
        "production_change": "none",
        "model_api_calls": 0,
        "local_llm_run": False,
        "follow_up": "Keep explicit field-name unit compatibility and family calculators. A future prompt parser requires a separately labeled paraphrase benchmark and cannot inherit this metadata gate."
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"summary": report["summary"], "decision": report["decision"], "contract_comparison": report["contract_comparison"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
