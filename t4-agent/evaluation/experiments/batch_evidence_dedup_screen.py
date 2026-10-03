#!/usr/bin/env python3
"""Measure exact evidence duplication inside public multi-entity prompts."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from t4agent.predict import predict_rows
from t4agent.retrieve import BM25, build_index
from t4agent.taskio import load_task


class PromptRecorder:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.last_failure_kind: str | None = None

    def chat_json(self, system: str, user: str, max_tokens: int) -> dict:
        self.prompts.append(user)
        marker = "REQUEST_JSON:\n"
        if marker not in user:
            return {}
        request = json.loads(user.split(marker, 1)[1].split("\nOUTPUT_SCHEMA_JSON:", 1)[0])
        return {
            "entities": [
                {"item_id": item["item_id"], "entity_id": item["entity_id"], "signals": {}}
                for item in request["items"]
            ]
        }


def request_from_prompt(prompt: str) -> dict | None:
    marker = "REQUEST_JSON:\n"
    if marker not in prompt:
        return None
    return json.loads(prompt.split(marker, 1)[1].split("\nOUTPUT_SCHEMA_JSON:", 1)[0])


def evidence_key(evidence: dict) -> str:
    # The ordinal is item-local presentation metadata, not evidence content.
    normalized = {key: value for key, value in evidence.items() if key != "n"}
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline-commit", required=True)
    args = parser.parse_args()

    old_batch_size = os.environ.get("T4_MODEL_BATCH_SIZE")
    os.environ["T4_MODEL_BATCH_SIZE"] = "3"
    batches: list[dict] = []
    try:
        for task_path in sorted(args.units_dir.glob("*/task.json")):
            task = load_task(task_path)
            corpus = build_index(task_path.parent / "corpus", task.cutoff_date)
            recorder = PromptRecorder()
            predict_rows(task, BM25(corpus.chunks), corpus, recorder, 8)
            for call_index, prompt in enumerate(recorder.prompts):
                request = request_from_prompt(prompt)
                if request is None or len(request.get("items") or []) < 2:
                    continue
                flattened = [
                    evidence_key(evidence)
                    for item in request["items"]
                    for evidence in item.get("evidence", [])
                ]
                counts = Counter(flattened)
                evidence_chars = sum(map(len, flattened))
                duplicate_chars = sum((count - 1) * len(key) for key, count in counts.items() if count > 1)
                batches.append(
                    {
                        "task_id": task.task_id,
                        "family": task.family,
                        "call_index": call_index,
                        "items": len(request["items"]),
                        "prompt_chars": len(prompt),
                        "evidence_occurrences": len(flattened),
                        "unique_evidence": len(counts),
                        "duplicate_occurrences": len(flattened) - len(counts),
                        "evidence_chars": evidence_chars,
                        "duplicate_chars": duplicate_chars,
                        "duplicate_evidence_pct": 100 * duplicate_chars / evidence_chars if evidence_chars else 0.0,
                    }
                )
    finally:
        if old_batch_size is None:
            os.environ.pop("T4_MODEL_BATCH_SIZE", None)
        else:
            os.environ["T4_MODEL_BATCH_SIZE"] = old_batch_size

    families_with_savings = sorted({row["family"] for row in batches if row["duplicate_chars"] > 0})
    total_evidence_chars = sum(row["evidence_chars"] for row in batches)
    total_duplicate_chars = sum(row["duplicate_chars"] for row in batches)
    savings_pct = 100 * total_duplicate_chars / total_evidence_chars if total_evidence_chars else 0.0
    qualifies = len(families_with_savings) >= 2 and savings_pct >= 10.0
    report = {
        "schema_version": 1,
        "experiment": "batch_evidence_dedup_screen_v1",
        "baseline_git_commit": args.baseline_commit,
        "hypothesis": "Public multi-entity prompts repeat enough exact evidence to justify a shared evidence catalog.",
        "decision_rule": "Proceed only if exact deduplication saves at least 10% of evidence characters across at least two families.",
        "batches": batches,
        "totals": {
            "batch_count": len(batches),
            "batches_with_duplicates": sum(row["duplicate_occurrences"] > 0 for row in batches),
            "evidence_occurrences": sum(row["evidence_occurrences"] for row in batches),
            "duplicate_occurrences": sum(row["duplicate_occurrences"] for row in batches),
            "evidence_chars": total_evidence_chars,
            "duplicate_chars": total_duplicate_chars,
            "duplicate_evidence_pct": savings_pct,
            "families_with_savings": families_with_savings,
        },
        "decision": "proceed_to_remote_ab" if qualifies else "reject_before_code",
        "production_change": "none",
        "model_api": {"requests": 0, "input_tokens": 0, "output_tokens": 0},
        "local_llm_run": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"decision": report["decision"], "totals": report["totals"]}, indent=2))


if __name__ == "__main__":
    main()
