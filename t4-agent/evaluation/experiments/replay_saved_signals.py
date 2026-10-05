#!/usr/bin/env python3
"""Replay saved, validated model signals through the current calculators.

This updates a comparison baseline after deterministic calculator changes without
spending another model request or changing the saved evidence signals.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from t4agent.family_specs import family_spec  # noqa: E402
from t4agent.minimal_models import solve_minimal  # noqa: E402
from t4agent.retrieve import build_index  # noqa: E402
from t4agent.taskio import load_task, write_json  # noqa: E402
from t4agent.validate import validate_answer  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--units",
        type=Path,
        default=Path("/Users/joezhou/PycharmProject/Agenthon2026/track4-analysis-public/units"),
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def normalize_ranks(target_type: str, rows: list[dict[str, Any]]) -> None:
    if target_type != "ranking":
        return
    ordered = sorted(rows, key=lambda row: (-float(row["point_forecast"]), str(row["entity_id"])))
    for rank, row in enumerate(ordered, 1):
        row["rank"] = rank


def main() -> None:
    args = parse_args()
    counts = {"tasks": 0, "rows": 0}
    for unit_dir in sorted(args.units.iterdir()):
        if not (unit_dir / "task.json").exists():
            continue
        task = load_task(unit_dir / "task.json")
        source_dir = args.source / task.task_id
        old_answer = json.loads((source_dir / "answer.json").read_text(encoding="utf-8"))
        traces = json.loads((source_dir / "trace/rows.json").read_text(encoding="utf-8"))
        trace_by_id = {str(row["entity_id"]): row for row in traces}
        old_by_id = {str(row["entity_id"]): row for row in old_answer["entity_predictions"]}
        corpus = build_index(unit_dir / "corpus", task.cutoff_date)
        spec = family_spec(task.family, str(task.target.get("name", "")))
        rows = []
        for index, entity in enumerate(task.entities):
            entity_id = str(entity["entity_id"])
            trace = trace_by_id[entity_id]
            inputs = trace["calculator_inputs"]
            output = solve_minimal(
                task,
                dict(inputs["entity"]),
                spec,
                dict(inputs["signals"]),
                corpus,
                index,
                len(task.entities),
                dict(inputs["parameters"]),
            )
            row: dict[str, Any] = {
                "entity_id": entity_id,
                "point_forecast": float(output.point),
                "interval": output.interval,
                "claims": list(old_by_id[entity_id].get("claims") or []),
            }
            if task.target_type == "classification":
                row["label"] = output.label if output.label in task.labels else task.labels[0]
            rows.append(row)
        normalize_ranks(task.target_type, rows)
        answer = {
            "task_id": task.task_id,
            "schema_version": task.schema_version,
            "target_type": task.target_type,
            "entity_predictions": rows,
            "evidence_trace": "Saved validated model signals replayed through current deterministic calculators.",
        }
        errors = validate_answer(answer, task, corpus)
        if errors:
            raise RuntimeError(f"{task.task_id}: {errors}")
        write_json(args.out / task.task_id / "answer.json", answer)
        counts["tasks"] += 1
        counts["rows"] += len(rows)
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
