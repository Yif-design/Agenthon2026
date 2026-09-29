#!/usr/bin/env python3
"""Screen a roster-aware batch width against the fixed width of three."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def width_for(rows: int, remaining_calls: int, *, adaptive: bool) -> int:
    if not adaptive or rows <= 3 * remaining_calls:
        return 3
    return min(6, max(3, math.ceil(rows / max(1, remaining_calls))))


def simulate(
    rows: int,
    *,
    adaptive: bool,
    max_calls: int = 25,
    transient_first: bool = False,
    context_batches: set[int] | None = None,
    persistent_failure: bool = False,
) -> dict:
    width = width_for(rows, max_calls, adaptive=adaptive)
    widths = [min(width, rows - start) for start in range(0, rows, width)]
    context_batches = context_batches or set()
    calls = 0
    enhanced = 0
    consecutive_failures = 0
    deferred: list[int] = []
    for index, batch_width in enumerate(widths):
        if calls >= max_calls or consecutive_failures >= 4:
            break
        calls += 1
        if persistent_failure:
            consecutive_failures += 1
            continue
        if transient_first and index == 0:
            if calls >= max_calls:
                break
            calls += 1
        if index in context_batches:
            consecutive_failures += 1
            deferred.append(batch_width)
            continue
        consecutive_failures = 0
        enhanced += batch_width
    for batch_width in deferred:
        for _ in range(batch_width):
            if calls >= max_calls or consecutive_failures >= 4:
                break
            calls += 1
            consecutive_failures = 0
            enhanced += 1
    return {
        "rows": rows,
        "batch_width": width,
        "normal_batches": len(widths),
        "calls": calls,
        "enhanced_rows": enhanced,
        "fallback_rows": rows - enhanced,
        "call_26_blocked": calls <= max_calls,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cases = {
        **{
            f"clean_{rows}": {
                "baseline": simulate(rows, adaptive=False),
                "candidate": simulate(rows, adaptive=True),
            }
            for rows in (60, 75, 78, 100, 150)
        },
        "transient_first_78": {
            "baseline": simulate(78, adaptive=False, transient_first=True),
            "candidate": simulate(78, adaptive=True, transient_first=True),
        },
        "context_first_78": {
            "baseline": simulate(78, adaptive=False, context_batches={0}),
            "candidate": simulate(78, adaptive=True, context_batches={0}),
        },
        "context_all_9": {
            "baseline": simulate(9, adaptive=False, context_batches={0, 1, 2}),
            "candidate": simulate(9, adaptive=True, context_batches={0, 1, 2}),
        },
        "persistent_78": {
            "baseline": simulate(78, adaptive=False, persistent_failure=True),
            "candidate": simulate(78, adaptive=True, persistent_failure=True),
        },
    }
    pass_gate = (
        cases["clean_78"]["baseline"]["enhanced_rows"] == 75
        and cases["clean_78"]["candidate"]["enhanced_rows"] == 78
        and cases["transient_first_78"]["candidate"]["enhanced_rows"] == 78
        and cases["context_first_78"]["candidate"]["enhanced_rows"] == 78
        and cases["context_all_9"]["candidate"] == cases["context_all_9"]["baseline"]
        and all(
            cases["persistent_78"]["candidate"][key] == cases["persistent_78"]["baseline"][key]
            for key in ("calls", "enhanced_rows", "fallback_rows", "call_26_blocked")
        )
        and all(value[variant]["call_26_blocked"] for value in cases.values() for variant in ("baseline", "candidate"))
    )
    report = {
        "schema_version": 1,
        "experiment": "adaptive_batch_screen_v1",
        "baseline_git_commit": "8f3ef1790f67d20890a615fa2c38f4c0d997d3ce",
        "layer": "L1/L2 cross-family House request scheduling",
        "hypothesis": "Increase batch width only when the remaining fixed-width schedule cannot cover all model-required rows within the remaining House request allowance.",
        "decision_rule": "Require 78/78 clean, transient and first-context coverage; preserve the nine-row all-context and persistent-failure behavior; never issue call 26.",
        "cases": cases,
        "decision": "proceed_to_fault_injection" if pass_gate else "reject_before_code",
        "model_api": {"requests": 0, "input_tokens": 0, "output_tokens": 0},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"decision": report["decision"], "cases": cases}, indent=2))
    if not pass_gate:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
