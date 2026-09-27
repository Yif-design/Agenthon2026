#!/usr/bin/env python3
"""Select and test a simple EPS YoY interval rule on forward time splits."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path


TARGET_COVERAGE = 0.90


def point(row: dict, mode: str) -> float:
    prior = float(row["prior_eps"])
    step = max(0.05 * abs(prior), 0.01)
    if mode == "resolved_direction":
        return prior + step if float(row["target_eps"]) > prior else prior - step
    if mode == "no_signal_fallback":
        return prior - step
    raise KeyError(mode)


def metrics(rows: list[dict], scale: float, floor: float, mode: str) -> dict:
    halves = [max(floor, scale * abs(float(row["prior_eps"]))) for row in rows]
    errors = [abs(float(row["target_eps"]) - point(row, mode)) for row in rows]
    coverage = statistics.fmean(error <= half for error, half in zip(errors, halves, strict=True))
    return {
        "rows": len(rows),
        "coverage": coverage,
        "calibration_loss": abs(coverage - TARGET_COVERAGE),
        "mean_full_width": 2.0 * statistics.fmean(halves),
        "mae": statistics.fmean(errors),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.dataset.read_text())
    rows = document["rows"]
    splits = {
        "train": [row for row in rows if row["target_end"][:4] <= "2019"],
        "dev": [row for row in rows if "2020" <= row["target_end"][:4] <= "2021"],
        "test": [row for row in rows if "2022" <= row["target_end"][:4] <= "2023"],
        "confirmation": [row for row in rows if "2024" <= row["target_end"][:4] <= "2025"],
    }

    candidates = []
    for scale_index in range(81):
        for floor_index in range(81):
            scale = scale_index / 20.0
            floor = floor_index / 20.0
            score = metrics(splits["dev"], scale, floor, "no_signal_fallback")
            candidates.append({"scale": scale, "floor": floor, **score})
    selected = min(
        candidates,
        key=lambda item: (
            item["calibration_loss"],
            item["mean_full_width"],
            item["scale"],
            item["floor"],
        ),
    )
    scale, floor = selected["scale"], selected["floor"]
    current = {name: metrics(part, 0.15, 0.03, "no_signal_fallback") for name, part in splits.items()}
    candidate = {name: metrics(part, scale, floor, "no_signal_fallback") for name, part in splits.items()}
    resolved_direction_check = {
        name: metrics(part, scale, floor, "resolved_direction") for name, part in splits.items()
    }
    result = {
        "experiment": "eps_yoy_interval_calibration_v1",
        "dataset": str(args.dataset),
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "split": {
            "train": "2015-2019",
            "dev": "2020-2021",
            "test": "2022-2023 (inspected before the comparability audit)",
            "confirmation": "2024-2025 (read once after locking extraction and candidate)",
        },
        "split_row_counts": {name: len(part) for name, part in splits.items()},
        "selection_point_mode": (
            "no_signal_fallback: prior EPS minus max(5% of abs(prior), 0.01); this is the current "
            "runtime point when no positive model signal is accepted"
        ),
        "current_rule": {"scale": 0.15, "floor": 0.03, "metrics": current},
        "selected_on_dev": selected,
        "candidate_rule": {"scale": scale, "floor": floor, "metrics": candidate},
        "resolved_direction_sensitivity": resolved_direction_check,
        "test_read_policy": (
            "Candidate fixed on dev before 2022-2023 metrics, but the comparability audit was added "
            "after inspecting that test. Extraction and candidate were then locked before the "
            "one-time 2024-2025 confirmation read."
        ),
        "decision": (
            "accept"
            if candidate["test"]["calibration_loss"] < current["test"]["calibration_loss"]
            and candidate["confirmation"]["calibration_loss"]
            < current["confirmation"]["calibration_loss"]
            else "reject"
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
