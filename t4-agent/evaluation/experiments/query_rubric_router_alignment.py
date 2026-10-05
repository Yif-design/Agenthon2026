#!/usr/bin/env python3
"""Audit query rubric dispatch against the shared strict task router."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from evaluation.experiments.router_collision_audit import COLLISIONS, PUBLIC, VARIANTS  # noqa: E402
from evaluation.experiments.structural_router_fallback import POSITIVE_CASES  # noqa: E402
from t4agent.family_specs import task_family_spec  # noqa: E402
from t4agent.retrieve import GENERIC_RUBRIC, RUBRIC_BY_FAMILY, query_for, rubric_keywords  # noqa: E402
from t4agent.taskio import Task  # noqa: E402


def _task(family: str, target: str, target_type: str, entities: list[dict]) -> Task:
    return Task({}, "rubric-audit", "3", {"name": target, "type": target_type}, target_type, [], entities, "2026-01-01", 0.9, "", family)


def _legacy_known_query(family: str, target: str) -> str:
    return f"A {target} {family} {rubric_keywords(family, target)}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    collisions = []
    for family, target in COLLISIONS:
        entity = {"entity_id": "A", "opaqueValue": 1}
        task = _task(family, target, "classification", [entity])
        route = task_family_spec(family, target, task.target_type, task.entities).key
        legacy_rubric = rubric_keywords(family, target)
        candidate_rubric = rubric_keywords(family, target, routed_family=route)
        query = query_for(task, entity, include_all_scalar_fields=True)
        collisions.append({
            "family": family,
            "target": target,
            "route": route,
            "legacy_rubric": legacy_rubric,
            "candidate_rubric": candidate_rubric,
            "legacy_specialist_injection": legacy_rubric != GENERIC_RUBRIC,
            "candidate_specialist_injection": any(value in query for key, value in RUBRIC_BY_FAMILY.items() if key != "generic"),
        })
    known = []
    for source, cases in (("public", PUBLIC), ("variant", VARIANTS)):
        for family, target, expected in cases:
            task = _task(family, target, "classification", [{"entity_id": "A"}])
            candidate = query_for(task, task.entities[0], include_all_scalar_fields=False)
            legacy = _legacy_known_query(family, target)
            known.append({"source": source, "family": family, "target": target, "expected": expected, "byte_identical": candidate == legacy})
    structural = []
    for expected, target_type, entity in POSITIVE_CASES:
        task = _task("unseen_finance", "opaque_target", target_type, [dict(entity)])
        query = query_for(task, task.entities[0], include_all_scalar_fields=False)
        rubric = RUBRIC_BY_FAMILY[expected]
        structural.append({"expected": expected, "route": task_family_spec(task.family, "opaque_target", target_type, task.entities).key, "rubric_present": rubric in query})
    report = {
        "schema_version": 1,
        "experiment": "query_rubric_router_alignment_v1",
        "layer": "L2 shared task routing and retrieval",
        "hypothesis": "Dispatching retrieval rubrics from the same strict task route as calculators and document scopes removes incidental-substring domain bias while preserving known and structurally recovered tasks.",
        "baseline_git_commit": "3a37e44e73b411466308a0d8c0d6baaddc41fe45",
        "collision_cases": collisions,
        "known_cases": known,
        "structural_cases": structural,
        "results": {
            "legacy_collision_injections": sum(row["legacy_specialist_injection"] for row in collisions),
            "candidate_collision_injections": sum(row["candidate_specialist_injection"] for row in collisions),
            "collision_total": len(collisions),
            "known_queries_identical": sum(row["byte_identical"] for row in known),
            "known_total": len(known),
            "structural_rubrics_correct": sum(row["route"] == row["expected"] and row["rubric_present"] for row in structural),
            "structural_total": len(structural),
        },
        "decision_rule": "Require collision specialist injections 7/7 to 0/7, 20/20 known queries byte-identical, 9/9 structural rubrics correct, byte-identical public outputs, 11/11 schema/smoke and no model calls.",
        "model_api": {"provider": None, "model": None, "requests": 0, "input_tokens": 0, "output_tokens": 0},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["results"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
