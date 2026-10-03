#!/usr/bin/env python3
"""Compare legacy and expanded generic schema-name retrieval queries."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from t4agent.retrieve import BM25, Chunk, query_for, rubric_keywords, tokenize  # noqa: E402


CASES = (
    ("camel_field", "opaqueTarget", {"entity_id": "A", "operatingMarginTrend": 1.0}, "operating margin trend"),
    ("snake_field", "opaqueTarget", {"entity_id": "A", "liquidity_risk_score": 1.0}, "liquidity risk score"),
    ("hyphen_field", "opaqueTarget", {"entity_id": "A", "forward-looking-demand": 1.0}, "forward looking demand"),
    ("camel_target", "futureCashFlowDelta", {"entity_id": "A"}, "future cash flow delta"),
)


def _task(target_name: str) -> SimpleNamespace:
    return SimpleNamespace(target={"name": target_name}, family="unseen_family")


def _legacy_query(task: SimpleNamespace, entity: dict) -> str:
    parts = [str(entity.get("entity_id", ""))]
    for key, value in entity.items():
        if key == "entity_id" or value is None or isinstance(value, (dict, list, tuple, set)):
            continue
        if isinstance(value, float) and not math.isfinite(value):
            continue
        parts.extend((str(key), str(value)))
    target_name = str(task.target.get("name", ""))
    parts.extend((target_name, task.family, rubric_keywords(task.family, target_name)))
    return " ".join(parts)


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
        rows.append({
            "case_id": case_id,
            "legacy_top1": index.search(legacy_query, top_k=1)[0].chunk.doc_id,
            "candidate_top1": index.search(candidate_query, top_k=1)[0].chunk.doc_id,
            "legacy_tokens": len(tokenize(legacy_query)),
            "candidate_tokens": len(tokenize(candidate_query)),
            "exact_schema_tokens_preserved": all(token in tokenize(candidate_query) for token in tokenize(legacy_query)),
        })
    budget_entity = {"entity_id": "A", **{f"featureGroup{i}_latestValue": i for i in range(64)}}
    budget_task = _task("futureCompositeMetric")
    legacy_budget = len(tokenize(_legacy_query(budget_task, budget_entity)))
    candidate_budget = len(tokenize(query_for(budget_task, budget_entity, include_all_scalar_fields=True)))
    report = {
        "schema_version": 1,
        "experiment": "generic_schema_query_expansion_v1",
        "layer": "L2 unknown-family retrieval",
        "hypothesis": "Keeping exact schema tokens while adding bounded identifier components improves natural-language evidence retrieval for unseen schemas without changing known-family queries or model usage.",
        "baseline_git_commit": "64fe8e05d35f233d695bebe0e53f31cb02e55a99",
        "cases": rows,
        "results": {
            "legacy_correct": sum(row["legacy_top1"] == "MATCH" for row in rows),
            "candidate_correct": sum(row["candidate_top1"] == "MATCH" for row in rows),
            "total": len(rows),
            "exact_schema_token_cases": sum(row["exact_schema_tokens_preserved"] for row in rows),
            "budget_legacy_tokens": legacy_budget,
            "budget_candidate_tokens": candidate_budget,
            "budget_expansion_ratio": candidate_budget / legacy_budget,
        },
        "decision_rule": "Require candidate 4/4 top-1 versus legacy below 4/4, exact legacy schema tokens in 4/4, <=4x 64-field query growth, unchanged known-family query behavior, byte-identical public outputs, 11/11 schema/smoke and no model calls.",
        "model_api": {"provider": None, "model": None, "requests": 0, "input_tokens": 0, "output_tokens": 0},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["results"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
