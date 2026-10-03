#!/usr/bin/env python3
"""Evaluate fixed-role multi-query reciprocal-rank fusion on validated fact spans."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from t4agent.family_specs import project_entity, task_family_spec  # noqa: E402
from t4agent.retrieve import BM25, ScoredChunk, allowed_document_ids, build_index, query_for  # noqa: E402
from t4agent.taskio import load_task  # noqa: E402

RRF_K = 60
QUERY_DEPTH = 30
TOP_K = 8


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def chunk_key(item: ScoredChunk) -> tuple[str, int, int]:
    chunk = item.chunk
    return chunk.doc_id, chunk.span_start, chunk.span_end


def role_queries(task: Any, entity: dict[str, Any], base: str) -> list[str]:
    identity = " ".join(
        str(entity.get(key)) for key in ("entity_id", "name", "series_id", "tenor") if entity.get(key) is not None
    )
    target = str((task.target or {}).get("name", ""))
    return [
        base,
        f"{identity} {target} reported actual value result",
        f"{identity} {target} historical previous prior year change",
        f"{identity} {target} consensus expectation estimate",
        f"{identity} {target} guidance outlook risk forecast",
    ]


def rrf(index: BM25, queries: list[str], allowed: set[str]) -> list[ScoredChunk]:
    by_key: dict[tuple[str, int, int], ScoredChunk] = {}
    scores: dict[tuple[str, int, int], float] = defaultdict(float)
    for query in queries:
        for rank, item in enumerate(index.search(query, top_k=QUERY_DEPTH, allowed_doc_ids=allowed), 1):
            # BM25.search deliberately returns recency-ordered zero-score chunks when a
            # query has no lexical match. That is a useful single-query runtime fallback,
            # but it must not become an RRF vote from an empty role query.
            if item.score <= 0:
                continue
            key = chunk_key(item)
            by_key[key] = item
            scores[key] += 1.0 / (RRF_K + rank)
    ordered = sorted(scores, key=lambda key: (-scores[key], key[0], key[1], key[2]))
    return [ScoredChunk(by_key[key].chunk, scores[key]) for key in ordered[:TOP_K]]


def relevant_rank(items: list[ScoredChunk], fact: dict[str, Any]) -> int | None:
    quote = str(fact.get("quote") or "")
    doc_id = str(fact.get("doc_id") or "")
    start, end = int(fact.get("span_start") or -1), int(fact.get("span_end") or -1)
    for rank, item in enumerate(items, 1):
        chunk = item.chunk
        if chunk.doc_id != doc_id:
            continue
        if quote and quote in chunk.text:
            return rank
        if start >= chunk.span_start and end <= chunk.span_end:
            return rank
    return None


def metrics(rows: list[dict[str, Any]], key: str) -> dict[str, float | int]:
    ranks = [row[key] for row in rows]
    return {
        "facts": len(rows),
        "hit_at_1": sum(rank == 1 for rank in ranks) / len(rows),
        "hit_at_3": sum(rank is not None and rank <= 3 for rank in ranks) / len(rows),
        "hit_at_8": sum(rank is not None and rank <= 8 for rank in ranks) / len(rows),
        "mrr": statistics.fmean(1.0 / rank if rank is not None else 0.0 for rank in ranks),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-root", type=Path, required=True)
    parser.add_argument("--units-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows: list[dict[str, Any]] = []
    query_cases: dict[tuple[str, str], dict[str, Any]] = {}
    for rows_path in sorted(args.trace_root.glob("*/trace/rows.json")):
        task_id = rows_path.parent.parent.name
        unit = args.units_dir / task_id
        if not (unit / "task.json").exists():
            continue
        task = load_task(unit / "task.json")
        corpus = build_index(unit / "corpus", task.cutoff_date)
        index = BM25(corpus.chunks)
        spec = task_family_spec(task.family, str(task.target.get("name", "")), task.target_type, task.entities)
        route_path = rows_path.parent / "route.json"
        route = json.loads(route_path.read_text()) if route_path.exists() else {}
        family = str(route.get("family") or spec.key)
        entities = {str(entity.get("entity_id")): entity for entity in task.entities}
        for trace_row in json.loads(rows_path.read_text()):
            entity_id = str(trace_row.get("entity_id"))
            facts = [
                fact for fact in trace_row.get("validated_facts") or []
                if fact.get("extractor") == "qwen" and fact.get("kind") != "context"
            ]
            if not facts or entity_id not in entities:
                continue
            case_key = (task_id, entity_id)
            if case_key not in query_cases:
                entity = entities[entity_id]
                allowed = allowed_document_ids(task, entity, corpus)
                query_entity = project_entity(entity, spec) if spec.key == "generic" else entity
                base_query = query_for(task, query_entity, include_all_scalar_fields=spec.key == "generic")
                baseline = index.search(base_query, top_k=TOP_K, allowed_doc_ids=allowed)
                candidate = rrf(index, role_queries(task, query_entity, base_query), allowed)
                query_cases[case_key] = {
                    "baseline": baseline,
                    "candidate": candidate,
                    "baseline_chars": sum(len(item.chunk.text) for item in baseline),
                    "candidate_chars": sum(len(item.chunk.text) for item in candidate),
                    "churn": len(set(map(chunk_key, baseline)) ^ set(map(chunk_key, candidate))),
                }
            case = query_cases[case_key]
            for fact in facts:
                rows.append({
                    "task_id": task_id,
                    "family": family,
                    "entity_id": entity_id,
                    "fact_name": fact.get("name"),
                    "baseline_rank": relevant_rank(case["baseline"], fact),
                    "candidate_rank": relevant_rank(case["candidate"], fact),
                })
    if not rows:
        raise SystemExit("no validated qwen facts")
    overall = {"baseline": metrics(rows, "baseline_rank"), "candidate": metrics(rows, "candidate_rank")}
    by_family = {}
    for family in sorted({row["family"] for row in rows}):
        subset = [row for row in rows if row["family"] == family]
        by_family[family] = {"baseline": metrics(subset, "baseline_rank"), "candidate": metrics(subset, "candidate_rank")}
    improved_families = [
        family for family, value in by_family.items()
        if value["candidate"]["mrr"] > value["baseline"]["mrr"] + 1e-12
    ]
    family_hit8_noninferior = all(
        value["candidate"]["hit_at_8"] >= value["baseline"]["hit_at_8"]
        for value in by_family.values()
    )
    baseline_chars = sum(case["baseline_chars"] for case in query_cases.values())
    candidate_chars = sum(case["candidate_chars"] for case in query_cases.values())
    char_growth = (candidate_chars - baseline_chars) / baseline_chars if baseline_chars else 0.0
    pass_gate = (
        overall["candidate"]["mrr"] > overall["baseline"]["mrr"]
        and overall["candidate"]["hit_at_3"] > overall["baseline"]["hit_at_3"]
        and len(improved_families) >= 2
        and family_hit8_noninferior
        and char_growth <= 0.10
    )
    report = {
        "schema_version": 1,
        "experiment": "multi_query_rrf_screen_v1",
        "date": "2026-09-30",
        "baseline_git_commit": "ded7edcb26de06280ca8324832bb39c41089d98a",
        "hypothesis": "Fixed-role target, historical, expectations and outlook queries fused with RRF recover independently validated exact facts more reliably than one broad BM25 query.",
        "scope": "L2 multi-query lexical retrieval",
        "source_trace_root": str(args.trace_root),
        "source_trace_rows_sha256": {
            path.parent.parent.name: sha256(path) for path in sorted(args.trace_root.glob("*/trace/rows.json"))
        },
        "configuration": {"rrf_k": RRF_K, "query_depth": QUERY_DEPTH, "top_k": TOP_K, "query_roles": 5},
        "facts": rows,
        "overall": overall,
        "by_family": by_family,
        "improved_families": improved_families,
        "family_hit8_noninferior": family_hit8_noninferior,
        "query_cases": len(query_cases),
        "retrieved_chars": {"baseline": baseline_chars, "candidate": candidate_chars, "growth_fraction": char_growth},
        "chunk_set_symmetric_difference_total": sum(case["churn"] for case in query_cases.values()),
        "decision_rule": "Advance only if overall MRR and hit@3 strictly improve, MRR improves in at least two families, no family's hit@8 falls, and top-eight retrieved characters grow by at most 10%.",
        "decision": "advance_to_flagged_candidate" if pass_gate else "reject_before_production",
        "model_api_calls": 0,
        "local_llm_run": False,
        "limitations": [
            "Validated weak-model facts are independent exact spans but come from retired public practice units.",
            "Retrieval relevance does not by itself prove predictive-quality or NLI improvement."
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: report[key] for key in ("overall", "by_family", "improved_families", "family_hit8_noninferior", "retrieved_chars", "chunk_set_symmetric_difference_total", "decision")}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
