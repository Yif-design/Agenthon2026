#!/usr/bin/env python3
"""Measure citation churn from deduplicating BM25 query terms before production changes."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from t4agent.family_specs import project_entity, task_family_spec  # noqa: E402
from t4agent.retrieve import BM25, allowed_document_ids, build_index, query_for  # noqa: E402
from t4agent.taskio import load_task  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for unit in sorted(path for path in args.units.iterdir() if path.is_dir()):
        task = load_task(unit / "task.json")
        corpus = build_index(unit / "corpus", task.cutoff_date)
        baseline = BM25(corpus.chunks)
        candidate = BM25(corpus.chunks, tokenizer=lambda text: list(dict.fromkeys(baseline.tokenizer(text))))
        spec = task_family_spec(task.family, str(task.target.get("name", "")), task.target_type, task.entities)
        for entity in task.entities:
            query_entity = project_entity(entity, spec) if spec.key == "generic" else entity
            query = query_for(task, query_entity, include_all_scalar_fields=spec.key == "generic")
            tokens = baseline.tokenizer(query)
            allowed = allowed_document_ids(task, entity, corpus)
            current = [(item.chunk.doc_id, item.chunk.span_start) for item in baseline.search(query, 3, allowed)]
            deduplicated = [(item.chunk.doc_id, item.chunk.span_start) for item in candidate.search(query, 3, allowed)]
            rows.append({
                "unit_id": unit.name,
                "entity_id": entity.get("entity_id"),
                "query_tokens": len(tokens),
                "unique_query_tokens": len(set(tokens)),
                "duplicate_terms": sum(count - 1 for count in Counter(tokens).values()),
                "top1_changed": current[:1] != deduplicated[:1],
                "top3_changed": current != deduplicated,
            })
    report = {
        "schema_version": 1,
        "experiment": "bm25_query_dedup_screen_v1",
        "layer": "L2 shared lexical retrieval",
        "baseline_git_commit": "08eaaafdb1dbce0241304c1db59e6b2eef1f7893",
        "hypothesis": "Counting each query term once, as in the public strong-RAG reference, may remove accidental weighting from repeated schema and rubric words without destabilizing existing citations.",
        "reference": "https://github.com/wangzgui/agenthon-t4-baseline-2026/blob/main/strong_rag/retriever.py",
        "rows": rows,
        "results": {
            "rows": len(rows),
            "rows_with_duplicates": sum(row["duplicate_terms"] > 0 for row in rows),
            "duplicate_terms_total": sum(row["duplicate_terms"] for row in rows),
            "top1_changed": sum(row["top1_changed"] for row in rows),
            "top3_changed": sum(row["top3_changed"] for row in rows),
        },
        "decision_rule": "Proceed only if citation churn is small enough to validate with existing evidence, or an independent relevance/NLI metric proves the changed retrieval is better. Reject before code when broad citation churn has no such quality signal.",
        "decision": "reject_before_code",
        "decision_reason": "Deduplication changes 27/78 top-one and 46/78 top-three retrievals. That invalidates broad citation evidence without a lightweight quality gain, while a fresh heavy local NLI run is prohibited.",
        "production_change": "none",
        "model_api": {"provider": None, "model": None, "requests": 0, "input_tokens": 0, "output_tokens": 0},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["results"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
