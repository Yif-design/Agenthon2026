#!/usr/bin/env python3
"""Compare immediate versus deferred single-row recovery under the 25-call cap."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def simulate(rows: int, context_batches: set[int], *, deferred: bool, max_calls: int = 25) -> dict:
    widths = [min(3, rows - start) for start in range(0, rows, 3)]
    calls = 0
    enhanced = 0
    failed_widths: list[int] = []
    for index, width in enumerate(widths):
        if calls >= max_calls:
            break
        calls += 1
        if index not in context_batches:
            enhanced += width
            continue
        if deferred:
            failed_widths.append(width)
            continue
        for _ in range(width):
            if calls >= max_calls:
                break
            calls += 1
            enhanced += 1
    if deferred:
        for width in failed_widths:
            for _ in range(width):
                if calls >= max_calls:
                    break
                calls += 1
                enhanced += 1
    return {"rows": rows, "batches": math.ceil(rows / 3), "calls": calls, "enhanced_rows": enhanced}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cases = {
        "large_first_batch_context": (78, {0}),
        "small_first_batch_context": (9, {0}),
        "small_all_batches_context": (9, {0, 1, 2}),
        "large_clean": (78, set()),
    }
    results = {
        name: {
            "immediate": simulate(rows, failures, deferred=False),
            "deferred": simulate(rows, failures, deferred=True),
        }
        for name, (rows, failures) in cases.items()
    }
    proceed = (
        results["large_first_batch_context"]["deferred"]["enhanced_rows"] >= 72
        and results["large_first_batch_context"]["deferred"]["enhanced_rows"]
        > results["large_first_batch_context"]["immediate"]["enhanced_rows"]
        and results["small_first_batch_context"]["deferred"]["enhanced_rows"] == 9
        and results["small_all_batches_context"]["deferred"]["enhanced_rows"]
        >= results["small_all_batches_context"]["immediate"]["enhanced_rows"]
        and results["large_clean"]["deferred"] == results["large_clean"]["immediate"]
    )
    report = {
        "schema_version": 1,
        "experiment": "context_recovery_scheduling_screen_v1",
        "baseline_git_commit": "848f18df6ec57cd9e1c7ed409591eb01441ff38a",
        "hypothesis": "Deferring single-row recovery until normal batches have used their efficient call opportunities increases enhanced-row coverage under the fixed 25-call budget.",
        "decision_rule": "Require >=72 enhanced rows on the 78-row first-failure case, 9/9 on both small cases, no loss when every small batch fails, and identical clean behavior.",
        "results": results,
        "decision": "proceed_to_implementation" if proceed else "reject_before_code",
        "model_api": {"requests": 0, "input_tokens": 0, "output_tokens": 0},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
