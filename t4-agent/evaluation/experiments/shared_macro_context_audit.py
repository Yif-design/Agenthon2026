#!/usr/bin/env python3
"""Audit whether macro families can safely share retrieval or model context."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from t4agent.family_specs import project_entity, task_family_spec
from t4agent.predict import predict_rows
from t4agent.retrieve import BM25, allowed_document_ids, build_index, query_for
from t4agent.taskio import load_task


MACRO_KEYS = {"rates", "cpi", "macro_revision"}


class PromptRecorder:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.last_failure_kind: str | None = None

    def chat_json(self, system: str, user: str, max_tokens: int) -> dict:
        self.prompts.append(user)
        return {"signals": {"policy_direction": {"level": 0, "doc_id": "", "quote": ""}}}


def _chunk_key(chunk: object) -> tuple[str, int, int, str]:
    return (str(chunk.doc_id), int(chunk.span_start), int(chunk.span_end), str(chunk.text))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline-commit", required=True)
    parser.add_argument("--top-k", type=int, default=8)
    args = parser.parse_args()

    units: list[dict] = []
    for task_path in sorted(args.units_dir.glob("*/task.json")):
        task = load_task(task_path)
        spec = task_family_spec(task.family, str(task.target.get("name", "")), task.target_type, task.entities)
        if spec.key not in MACRO_KEYS:
            continue
        corpus = build_index(task_path.parent / "corpus", task.cutoff_date)
        index = BM25(corpus.chunks)
        query_counts: Counter[str] = Counter()
        doc_counts: Counter[str] = Counter()
        chunk_counts: Counter[tuple[str, int, int, str]] = Counter()
        retrieved_chars = 0
        for entity in task.entities:
            allowed = allowed_document_ids(task, entity, corpus)
            query_entity = project_entity(entity, spec) if spec.key == "generic" else entity
            query = query_for(task, query_entity, include_all_scalar_fields=spec.key == "generic")
            query_counts[query] += 1
            chunks = [
                item.chunk
                for item in index.search(query, top_k=args.top_k, allowed_doc_ids=allowed)
            ]
            for chunk in chunks:
                doc_counts[chunk.doc_id] += 1
                chunk_counts[_chunk_key(chunk)] += 1
                retrieved_chars += len(chunk.text)

        recorder = PromptRecorder()
        predict_rows(task, index, corpus, recorder, args.top_k)
        duplicate_chunk_chars = sum(
            (count - 1) * len(key[3]) for key, count in chunk_counts.items() if count > 1
        )
        units.append(
            {
                "task_id": task.task_id,
                "family": task.family,
                "family_model": spec.key,
                "entities": len(task.entities),
                "model_required": spec.model_required,
                "model_calls": len(recorder.prompts),
                "retrieval_calls": len(task.entities),
                "unique_queries": len(query_counts),
                "duplicate_query_calls": sum(count - 1 for count in query_counts.values()),
                "retrieved_chunk_occurrences": sum(chunk_counts.values()),
                "unique_retrieved_chunks": len(chunk_counts),
                "duplicate_chunk_occurrences": sum(count - 1 for count in chunk_counts.values()),
                "retrieved_chunk_chars": retrieved_chars,
                "duplicate_chunk_chars": duplicate_chunk_chars,
                "duplicate_chunk_pct": 100 * duplicate_chunk_chars / retrieved_chars if retrieved_chars else 0.0,
                "unique_retrieved_docs": len(doc_counts),
                "docs_seen_by_multiple_entities": sum(count > 1 for count in doc_counts.values()),
                "runtime_interpretation": (
                    "one task-level model prompt is already shared across every tenor"
                    if spec.key == "rates"
                    else "deterministic calculator; no model prompt or model context exists"
                ),
            }
        )

    eligible = [row for row in units if row["model_required"] and row["model_calls"] > 0]
    families_with_new_safe_savings = [
        row["family_model"]
        for row in eligible
        if row["model_calls"] > 1 and row["duplicate_chunk_pct"] >= 10.0
    ]
    report = {
        "schema_version": 1,
        "experiment": "shared_macro_context_audit_v1",
        "baseline_git_commit": args.baseline_commit,
        "hypothesis": (
            "At least two macro families repeat identical evidence in multiple model prompts, so a shared "
            "task-level context can reduce model-input evidence characters by at least 10% without changing citations."
        ),
        "decision_rule": (
            "Proceed only if at least two model-required macro families have multiple prompts and at least 10% "
            "exact duplicate evidence characters."
        ),
        "units": units,
        "families_with_new_safe_savings": sorted(set(families_with_new_safe_savings)),
        "decision": "proceed_to_candidate" if len(set(families_with_new_safe_savings)) >= 2 else "reject_as_already_shared_or_not_applicable",
        "production_change": "none",
        "model_api": {"requests": 0, "input_tokens": 0, "output_tokens": 0},
        "local_llm_run": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"decision": report["decision"], "units": units}, indent=2))


if __name__ == "__main__":
    main()
