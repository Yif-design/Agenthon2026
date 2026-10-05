#!/usr/bin/env python3
"""Test bounded task-prompt terms as a fallback for opaque generic schemas."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from t4agent.retrieve import BM25, Chunk, query_for, tokenize  # noqa: E402
from t4agent.taskio import Task  # noqa: E402


CASES = (
    ("classification", "Predict whether the issuer faces a covenant breach within 12 months.", "issuer covenant breach"),
    ("regression", "Forecast warehouse throughput measured in pallets per hour.", "warehouse throughput pallets hour"),
    ("ranking", "Rank suppliers by delivery delay and late shipments.", "suppliers delivery delay late shipments"),
)


def _task(target_type: str, prompt: str, entity: dict) -> Task:
    return Task({}, "prompt-query", "3", {"name": "opaqueTarget", "type": target_type}, target_type, [], [entity], "2026-01-01", 0.9, prompt, "unseen_family")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    entity = {"entity_id": "A", "x1": 7}
    for target_type, prompt, phrase in CASES:
        distractor = "results outlook growth risk change forecast target evidence"
        chunks = [
            Chunk("DISTRACTOR", "2026-01-01", 0, len(distractor), distractor),
            Chunk("MATCH", "2026-01-01", 0, len(phrase), phrase),
        ]
        baseline_task = _task(target_type, "", entity)
        candidate_task = _task(target_type, prompt, entity)
        baseline_query = query_for(baseline_task, entity, include_all_scalar_fields=True)
        candidate_query = query_for(candidate_task, entity, include_all_scalar_fields=True)
        index = BM25(chunks)
        rows.append({
            "target_type": target_type,
            "baseline_top1": index.search(baseline_query, 1)[0].chunk.doc_id,
            "candidate_top1": index.search(candidate_query, 1)[0].chunk.doc_id,
            "candidate_added_tokens": len(tokenize(candidate_query)) - len(tokenize(baseline_query)) + 8,
        })
    template = _task("regression", "Predict target value for each entity.", entity)
    empty = _task("regression", "", entity)
    template_identical = query_for(template, entity, True) == query_for(empty, entity, True)
    semantic_entity = {"entity_id": "A", "operatingMarginTrend": 1.0}
    semantic_with_prompt = _task("regression", CASES[1][1], semantic_entity)
    semantic_empty = _task("regression", "", semantic_entity)
    semantic_identical = query_for(semantic_with_prompt, semantic_entity, True) == query_for(semantic_empty, semantic_entity, True)
    long_prompt = " ".join(
        f"word{chr(97 + (index // 26) % 26)}{chr(97 + index % 26)}"
        for index in range(100)
    )
    bounded = _task("regression", long_prompt, entity)
    bounded_query = query_for(bounded, entity, True)
    base_query = query_for(empty, entity, True)
    # The candidate removes the eight generic rubric tokens when prompt terms are added.
    bounded_added = len(tokenize(bounded_query)) - len(tokenize(base_query)) + 8
    report = {
        "schema_version": 1,
        "experiment": "generic_prompt_query_priority_v1",
        "layer": "L2 unknown-family retrieval",
        "hypothesis": "For opaque generic schemas only, bounded non-template prompt terms can replace the broad fallback rubric and retrieve task-defined evidence across target types without changing semantic-schema or known-family paths.",
        "baseline_git_commit": "08eaaafdb1dbce0241304c1db59e6b2eef1f7893",
        "cases": rows,
        "results": {
            "baseline_correct": sum(row["baseline_top1"] == "MATCH" for row in rows),
            "candidate_correct": sum(row["candidate_top1"] == "MATCH" for row in rows),
            "total": len(rows),
            "template_query_identical": template_identical,
            "semantic_schema_query_identical": semantic_identical,
            "bounded_prompt_terms_added": bounded_added,
        },
        "decision_rule": "Require 3/3 target types to move from wrong to correct top-1, byte-identical template and semantic-schema queries, <=24 prompt terms, byte-identical public outputs, 11/11 schema/smoke and no model calls.",
        "model_api": {"provider": None, "model": None, "requests": 0, "input_tokens": 0, "output_tokens": 0},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["results"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
