#!/usr/bin/env python3
"""Test semantic schema terms against the broad generic retrieval rubric."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from evaluation.experiments.generic_schema_query_expansion import CASES, _legacy_query, _task  # noqa: E402
from t4agent.retrieve import BM25, Chunk, query_for, tokenize  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for case_id, target_name, entity, phrase in CASES:
        distractor = "results outlook growth risk change forecast target evidence"
        chunks = [
            Chunk("DISTRACTOR", "2026-01-01", 0, len(distractor), distractor),
            Chunk("MATCH", "2026-01-01", 0, len(phrase), phrase),
        ]
        task = _task(target_name)
        legacy_query = _legacy_query(task, entity)
        candidate_query = query_for(task, entity, include_all_scalar_fields=True)
        index = BM25(chunks)
        exact_schema_tokens = [
            token
            for value in (target_name, *(key for key in entity if key != "entity_id"))
            for token in tokenize(value)
        ]
        rows.append({
            "case_id": case_id,
            "legacy_top1": index.search(legacy_query, top_k=1)[0].chunk.doc_id,
            "candidate_top1": index.search(candidate_query, top_k=1)[0].chunk.doc_id,
            "exact_schema_tokens_preserved": all(token in tokenize(candidate_query) for token in exact_schema_tokens),
        })
    opaque_task = _task("opaqueTarget")
    opaque_entity = {"entity_id": "A", "x1": 7}
    opaque_legacy = _legacy_query(opaque_task, opaque_entity)
    opaque_candidate = query_for(opaque_task, opaque_entity, include_all_scalar_fields=True)
    known_task = _task("futureMetric")
    known_task.family = "known_family"
    known_entity = {"entity_id": "A", "operatingMarginTrend": 1.0}
    known_legacy = "A futureMetric known_family results outlook growth risk change forecast target evidence"
    known_candidate = query_for(known_task, known_entity, include_all_scalar_fields=False)
    budget_entity = {"entity_id": "A", **{f"featureGroup{i}_latestValue": i for i in range(64)}}
    budget_task = _task("futureCompositeMetric")
    legacy_budget = len(tokenize(_legacy_query(budget_task, budget_entity)))
    candidate_budget = len(tokenize(query_for(budget_task, budget_entity, include_all_scalar_fields=True)))
    report = {
        "schema_version": 1,
        "experiment": "generic_schema_query_priority_v1",
        "layer": "L2 unknown-family retrieval",
        "hypothesis": "When semantic schema components exist, suppressing only the broad generic fallback rubric lets those bounded components retrieve natural-language evidence while opaque and known schemas preserve legacy behavior.",
        "baseline_git_commit": "64fe8e05d35f233d695bebe0e53f31cb02e55a99",
        "cases": rows,
        "opaque_query": {"legacy": opaque_legacy, "candidate": opaque_candidate, "identical": opaque_legacy == opaque_candidate},
        "known_query": {"legacy": known_legacy, "candidate": known_candidate, "identical": known_legacy == known_candidate},
        "results": {
            "legacy_correct": sum(row["legacy_top1"] == "MATCH" for row in rows),
            "candidate_correct": sum(row["candidate_top1"] == "MATCH" for row in rows),
            "total": len(rows),
            "exact_schema_token_cases": sum(row["exact_schema_tokens_preserved"] for row in rows),
            "opaque_query_identical": opaque_legacy == opaque_candidate,
            "known_query_identical": known_legacy == known_candidate,
            "budget_legacy_tokens": legacy_budget,
            "budget_candidate_tokens": candidate_budget,
            "budget_expansion_ratio": candidate_budget / legacy_budget,
        },
        "decision_rule": "Require candidate 4/4 top-1 versus legacy below 4/4, exact schema tokens in 4/4, byte-identical opaque and known-family queries, <=4x 64-field growth, byte-identical public outputs, 11/11 schema/smoke and no model calls.",
        "model_api": {"provider": None, "model": None, "requests": 0, "input_tokens": 0, "output_tokens": 0},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["results"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
