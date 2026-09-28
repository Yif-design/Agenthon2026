#!/usr/bin/env python3
"""Measure whether public batch prompts have single-row context recovery windows."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from t4agent.predict import predict_rows
from t4agent.retrieve import BM25, build_index
from t4agent.taskio import load_task


class PromptRecorder:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def chat_json(self, system: str, user: str, max_tokens: int) -> None:
        self.prompts.append(user)
        return None


def batch_width(prompt: str) -> int:
    marker = "REQUEST_JSON:\n"
    if marker not in prompt:
        return 1
    request_line = prompt.split(marker, 1)[1].splitlines()[0]
    request = json.loads(request_line)
    return len(request.get("items") or [])


def record_prompts(task_path: Path, batch_size: int) -> list[str]:
    task = load_task(task_path)
    corpus = build_index(task_path.parent / "corpus", task.cutoff_date)
    recorder = PromptRecorder()
    old = os.environ.get("T4_MODEL_BATCH_SIZE")
    os.environ["T4_MODEL_BATCH_SIZE"] = str(batch_size)
    try:
        predict_rows(task, BM25(corpus.chunks), corpus, recorder, 8)
    finally:
        if old is None:
            os.environ.pop("T4_MODEL_BATCH_SIZE", None)
        else:
            os.environ["T4_MODEL_BATCH_SIZE"] = old
    return recorder.prompts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    thresholds = (16_000, 24_000, 32_000)
    totals = {str(limit): {"oversized_batches": 0, "recoverable_entities": 0} for limit in thresholds}
    task_rows = []
    for task_path in sorted(args.units_dir.glob("*/task.json")):
        batched = record_prompts(task_path, 3)
        singles = record_prompts(task_path, 1)
        if not batched:
            continue
        cursor = 0
        groups = []
        for prompt in batched:
            width = batch_width(prompt)
            group_singles = singles[cursor : cursor + width]
            cursor += width
            group = {
                "batch_chars": len(prompt),
                "width": width,
                "single_chars": [len(item) for item in group_singles],
            }
            for limit in thresholds:
                if len(prompt) > limit:
                    totals[str(limit)]["oversized_batches"] += 1
                    totals[str(limit)]["recoverable_entities"] += sum(
                        len(item) <= limit for item in group_singles
                    )
            groups.append(group)
        task_rows.append(
            {
                "task_id": load_task(task_path).task_id,
                "batch_calls": len(batched),
                "single_calls": len(singles),
                "groups": groups,
            }
        )
    qualifying = sum(value["recoverable_entities"] > 0 for value in totals.values())
    report = {
        "schema_version": 1,
        "experiment": "context_batch_split_size_screen_v1",
        "baseline_git_commit": "f9489224e6fa44850dce15659de4a90406d01312",
        "hypothesis": "A batch-local context-limit failure can often be recovered by retrying its rows individually within the existing request and deadline caps.",
        "decision_rule": "Proceed to fault-injection implementation only if at least two of the 16k, 24k, and 32k character proxies contain one or more batch-oversized but individually recoverable entities.",
        "thresholds": totals,
        "qualifying_thresholds": qualifying,
        "tasks": task_rows,
        "decision": "proceed_to_fault_injection" if qualifying >= 2 else "reject_before_code",
        "model_api": {"requests": 0, "input_tokens": 0, "output_tokens": 0},
        "caveat": "Character limits are deterministic context proxies; no authoritative House token ceiling is published.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: report[key] for key in ("decision", "qualifying_thresholds", "thresholds")}, indent=2))


if __name__ == "__main__":
    main()
