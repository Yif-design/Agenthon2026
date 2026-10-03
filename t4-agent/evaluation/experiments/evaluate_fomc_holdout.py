#!/usr/bin/env python3
"""One-shot evaluation of a locked FOMC interval artifact on public holdouts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HOLDOUTS = ("t4-fomc-curve-20220728", "t4-fomc-curve-20240918")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifact_raw = args.artifact.read_bytes()
    artifact = json.loads(artifact_raw)
    widths = artifact["selected"]["widths_bps"]
    truth = json.loads(args.truth.read_text())["tasks"]
    tasks = []
    for task_id in HOLDOUTS:
        answer = json.loads((args.answers / task_id / "answer.json").read_text())
        actual = {row["entity_id"]: float(row["value"]) for row in truth[task_id]["outcomes"]}
        rows = []
        base_hits = candidate_hits = 0
        for row in answer["entity_predictions"]:
            entity = row["entity_id"]
            point = float(row["point_forecast"])
            value = actual[entity]
            interval = row["interval"]
            base_hit = float(interval["lo"]) <= value <= float(interval["hi"])
            width = float(widths[entity])
            candidate_hit = point - width <= value <= point + width
            base_hits += base_hit
            candidate_hits += candidate_hit
            rows.append({
                "entity_id": entity,
                "point_forecast": point,
                "truth": value,
                "base_hit": base_hit,
                "candidate_half_width_bps": width,
                "candidate_hit": candidate_hit,
            })
        count = len(rows)
        tasks.append({
            "task_id": task_id,
            "base_coverage": base_hits / count,
            "candidate_coverage": candidate_hits / count,
            "base_calibration_loss": abs(base_hits / count - 0.90),
            "candidate_calibration_loss": abs(candidate_hits / count - 0.90),
            "rows": rows,
        })
    report = {
        "artifact": str(args.artifact),
        "artifact_sha256": hashlib.sha256(artifact_raw).hexdigest(),
        "artifact_holdout_not_read_assertion": artifact["holdout_not_read"],
        "answer_configuration": "nemotron-free-nothink-signal",
        "tasks": tasks,
        "mean_base_calibration_loss": sum(x["base_calibration_loss"] for x in tasks) / len(tasks),
        "mean_candidate_calibration_loss": sum(x["candidate_calibration_loss"] for x in tasks) / len(tasks),
    }
    report["decision"] = (
        "accept"
        if report["mean_candidate_calibration_loss"] < report["mean_base_calibration_loss"]
        else "reject"
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
