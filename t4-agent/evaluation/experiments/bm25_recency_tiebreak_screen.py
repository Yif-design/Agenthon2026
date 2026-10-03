#!/usr/bin/env python3
"""Screen a recency tie-break for exactly equal BM25 scores."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from t4agent.retrieve import BM25, Chunk, ScoredChunk, allowed_document_ids, build_index, query_for
from t4agent.taskio import Task, load_task


def date_ordinal(value: str | None) -> int:
    try:
        return date.fromisoformat(str(value)[:10]).toordinal()
    except ValueError:
        return 0


def recency_tiebreak(results: list[ScoredChunk]) -> list[ScoredChunk]:
    return sorted(
        results,
        key=lambda item: (
            -item.score,
            -date_ordinal(item.chunk.doc_date),
            item.chunk.doc_id,
            item.chunk.span_start,
        ),
    )


def make_task(family: str, target_name: str, target_type: str, entity: dict) -> Task:
    return Task(
        raw={},
        task_id=f"screen-{family}",
        schema_version="3",
        target={"name": target_name, "type": target_type},
        target_type=target_type,
        labels=["up", "flat", "down"] if target_type == "classification" else [],
        entities=[entity],
        cutoff_date="2025-01-01",
        interval_level=0.9,
        prompt="",
        family=family,
    )


def synthetic_results() -> list[dict]:
    cases = [
        make_task("eps_beat_consensus", "eps_outcome", "classification", {"entity_id": "ACME", "name": "Acme"}),
        make_task("rate_curve", "yield_change_bps", "regression", {"entity_id": "US10Y", "name": "10-year", "tenor": "10Y"}),
        make_task("auction_demand", "bid_to_cover", "regression", {"entity_id": "US7Y", "name": "7-year", "tenor": "7Y"}),
    ]
    out = []
    for task in cases:
        entity = task.entities[0]
        text = f"{entity['name']} results outlook evidence"
        chunks = [
            Chunk("A_OLD", "2023-01-01", 0, len(text), text),
            Chunk("Z_NEW", "2024-12-01", 0, len(text), text),
        ]
        baseline = BM25(chunks).search(query_for(task, entity), top_k=2)
        candidate = recency_tiebreak(baseline)
        out.append(
            {
                "family": task.family,
                "baseline_top1": baseline[0].chunk.doc_id,
                "candidate_top1": candidate[0].chunk.doc_id,
                "scores_equal": baseline[0].score == baseline[1].score,
                "baseline_correct": baseline[0].chunk.doc_id == "Z_NEW",
                "candidate_correct": candidate[0].chunk.doc_id == "Z_NEW",
            }
        )
    return out


def public_results(units_dir: Path) -> dict:
    rows = 0
    top1_changed = 0
    top3_changed = 0
    changed_top1_all_exact_ties = True
    changes = []
    for task_path in sorted(units_dir.glob("*/task.json")):
        task = load_task(task_path)
        corpus = build_index(task_path.parent / "corpus", task.cutoff_date)
        engine = BM25(corpus.chunks)
        for entity in task.entities:
            rows += 1
            allowed = allowed_document_ids(task, entity, corpus)
            baseline = engine.search(query_for(task, entity), top_k=max(3, len(corpus.chunks)), allowed_doc_ids=allowed)
            candidate = recency_tiebreak(baseline)
            base_ids = [item.chunk.doc_id for item in baseline[:3]]
            candidate_ids = [item.chunk.doc_id for item in candidate[:3]]
            if base_ids[:1] != candidate_ids[:1]:
                top1_changed += 1
                tied = bool(baseline and candidate) and abs(baseline[0].score - candidate[0].score) <= 1e-12
                changed_top1_all_exact_ties &= tied
                changes.append(
                    {
                        "task_id": task.task_id,
                        "entity_id": str(entity.get("entity_id", "")),
                        "baseline_top1": base_ids[0] if base_ids else None,
                        "candidate_top1": candidate_ids[0] if candidate_ids else None,
                        "baseline_date": baseline[0].chunk.doc_date if baseline else None,
                        "candidate_date": candidate[0].chunk.doc_date if candidate else None,
                        "score": baseline[0].score if baseline else None,
                        "exact_tie": tied,
                    }
                )
            if base_ids != candidate_ids:
                top3_changed += 1
    return {
        "units": len(list(units_dir.glob("*/task.json"))),
        "rows": rows,
        "top1_changed": top1_changed,
        "top3_changed": top3_changed,
        "changed_top1_all_exact_ties": changed_top1_all_exact_ties,
        "top1_changes": changes,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    synthetic = synthetic_results()
    public = public_results(args.units_dir)
    before = sum(item["baseline_correct"] for item in synthetic)
    after = sum(item["candidate_correct"] for item in synthetic)
    proceed = (
        before == 0
        and after == 3
        and public["top1_changed"] <= 3
        and public["changed_top1_all_exact_ties"]
    )
    report = {
        "schema_version": 1,
        "experiment": "bm25_recency_tiebreak_screen_v1",
        "baseline_git_commit": "751d04db14b1d464e3e7ec6916913c6c5900f51a",
        "hypothesis": "For exactly equal BM25 scores, newer cutoff-safe documents are a safer cross-family tie-break than lexicographic doc_id order.",
        "decision_rule": "Proceed only if 3/3 families move from wrong to correct, public top-1 changes are <=3/78, and every public top-1 change is an exact score tie.",
        "synthetic": {"baseline_correct": before, "candidate_correct": after, "total": 3, "cases": synthetic},
        "public": public,
        "decision": "proceed_to_implementation" if proceed else "reject_before_code",
        "model_api": {"requests": 0, "input_tokens": 0, "output_tokens": 0},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
