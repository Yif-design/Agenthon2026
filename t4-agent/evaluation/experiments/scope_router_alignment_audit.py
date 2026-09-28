#!/usr/bin/env python3
"""Verify that specialist document scopes use the same anchored family route as calculators."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from evaluation.experiments.router_collision_audit import COLLISIONS, PUBLIC, VARIANTS  # noqa: E402
from t4agent.family_specs import family_spec  # noqa: E402
from t4agent.retrieve import IndexedCorpus, allowed_document_ids  # noqa: E402
from t4agent.taskio import Task  # noqa: E402


def _task(family: str, target: str, entity: dict) -> Task:
    return Task(
        raw={},
        task_id="scope-router-audit",
        schema_version="3",
        target={"name": target, "type": "regression"},
        target_type="regression",
        labels=[],
        entities=[entity],
        cutoff_date="2024-01-01",
        interval_level=0.9,
        prompt="",
        family=family,
    )


def _collision_rows() -> list[dict]:
    corpus = IndexedCorpus(
        [],
        {"ENTITY_A_LOCAL": "local evidence", "GLOBAL_SHARED": "shared evidence"},
        {"ENTITY_A_LOCAL": "2023-01-01", "GLOBAL_SHARED": "2023-01-01"},
        {"ENTITY_A_LOCAL": "local.json", "GLOBAL_SHARED": "shared.json"},
    )
    entity = {"entity_id": "ENTITY_A", "corpus_ref": "corpus/"}
    rows = []
    for family, target in COLLISIONS:
        allowed = allowed_document_ids(_task(family, target, entity), entity, corpus)
        family_text = f"{family} {target}".lower()
        baseline_allowed = set(corpus.doc_texts)
        if "position" in family_text or "cot" in family_text:
            scoped = {doc_id for doc_id in baseline_allowed if entity["entity_id"] in doc_id}
            baseline_allowed = scoped or baseline_allowed
        rows.append(
            {
                "family": family,
                "target": target,
                "route": family_spec(family, target).key,
                "allowed_doc_ids": sorted(allowed),
                "baseline_allowed_doc_ids": sorted(baseline_allowed),
                "baseline_shared_document_preserved": "GLOBAL_SHARED" in baseline_allowed,
                "shared_document_preserved": "GLOBAL_SHARED" in allowed,
            }
        )
    return rows


def _known_rows() -> list[dict]:
    rows = []
    for source, cases in (("public", PUBLIC), ("variant", VARIANTS)):
        for family, target, expected in cases:
            actual = family_spec(family, target).key
            rows.append(
                {
                    "source": source,
                    "family": family,
                    "target": target,
                    "expected": expected,
                    "actual": actual,
                    "correct": actual == expected,
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    collisions = _collision_rows()
    known = _known_rows()
    report = {
        "schema_version": 1,
        "experiment_id": "scope_router_alignment_v1",
        "baseline_git_commit": "87704b0729c96237a5518d32aef397b20fce7ae8",
        "layer": "L2 shared retrieval scope and unknown-family isolation",
        "hypothesis": "Dispatching specialist document scopes from the anchored family router preserves shared evidence for incidental-substring unknown tasks while retaining every known family route.",
        "collision_cases": collisions,
        "known_cases": known,
        "results": {
            "baseline_collision_shared_preserved": sum(
                row["baseline_shared_document_preserved"] for row in collisions
            ),
            "collision_shared_preserved": sum(row["shared_document_preserved"] for row in collisions),
            "collision_total": len(collisions),
            "known_routes_correct": sum(row["correct"] for row in known),
            "known_routes_total": len(known),
        },
        "decision_rule": "Require 7/7 unknown collision scopes to preserve shared corpus_ref documents, 20/20 known routes to remain correct, byte-identical public answers, 11/11 schema and smoke, and no extra model calls.",
        "model_api": {"provider": None, "model": None, "requests": 0, "input_tokens": 0, "output_tokens": 0},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["results"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
