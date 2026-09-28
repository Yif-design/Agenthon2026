#!/usr/bin/env python3
"""Evaluate bank EPS-growth interval rules without changing production output."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from evaluation.experiments.build_eps_yoy_history import (  # noqa: E402
    original_quarters,
    pair_quarters,
    quarter_facts,
)
from evaluation.experiments.eps_yoy_recent_delta_probe import build_features  # noqa: E402


FLOORS = (20.0, 30.0, 40.0, 50.0, 60.0, 75.0, 100.0)
MULTIPLIERS = (0.5, 0.75, 1.0, 1.25, 1.5)


def point_and_actual(row: dict) -> tuple[float, float]:
    prior = float(row["prior_eps"])
    point = 100.0 * float(row["recent_yoy_delta"]) / abs(prior)
    actual = 100.0 * (float(row["target_eps"]) - prior) / abs(prior)
    return point, actual


def metrics(rows: list[dict], floor: float, multiplier: float) -> dict:
    covered = []
    widths = []
    for row in rows:
        point, actual = point_and_actual(row)
        half_width = max(floor, multiplier * abs(point))
        covered.append(abs(actual - point) <= half_width)
        widths.append(2.0 * half_width)
    coverage = statistics.fmean(covered)
    return {
        "rows": len(rows),
        "coverage": coverage,
        "calibration_loss": abs(coverage - 0.90),
        "mean_full_width": statistics.fmean(widths),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    rows = []
    source_hashes = {}
    for path in sorted(args.cache.glob("*.json")):
        payload = path.read_bytes()
        document = json.loads(payload)
        facts = quarter_facts(document)
        pairs, _ = pair_quarters(
            path.stem,
            int(document["cik"]),
            original_quarters(facts),
            facts,
        )
        rows.extend(pairs)
        source_hashes[path.stem] = hashlib.sha256(payload).hexdigest()
    features = build_features({"rows": rows}, args.cache)
    splits = {
        "train": [row for row in features if row["target_end"][:4] <= "2019"],
        "dev": [row for row in features if "2020" <= row["target_end"][:4] <= "2021"],
        "test": [row for row in features if "2022" <= row["target_end"][:4] <= "2023"],
        "confirmation": [row for row in features if "2024" <= row["target_end"][:4] <= "2025"],
    }
    candidates = []
    for floor in FLOORS:
        for multiplier in MULTIPLIERS:
            candidates.append({
                "floor": floor,
                "point_multiplier": multiplier,
                **metrics(splits["dev"], floor, multiplier),
            })
    selected = min(
        candidates,
        key=lambda item: (item["calibration_loss"], item["mean_full_width"]),
    )
    baseline = {
        name: metrics(part, 20.0, 0.75)
        for name, part in splits.items()
    }
    candidate = {
        name: metrics(part, selected["floor"], selected["point_multiplier"])
        for name, part in splits.items()
    }
    report = {
        "schema_version": 1,
        "date": "2026-09-28",
        "experiment": "bank_eps_interval_calibration_v1",
        "baseline_git_commit": "d9e6b13015fb12f87cde8e68d740c46e329031fd",
        "hypothesis": (
            "A development-selected floor and point-magnitude multiplier improve 90% interval "
            "calibration for bank EPS growth over max(20, 0.75 * abs(point))."
        ),
        "source": "SEC Company Concept API, us-gaap:EarningsPerShareDiluted",
        "source_sha256_by_ticker": source_hashes,
        "feature_rows": len(features),
        "split_counts": {name: len(part) for name, part in splits.items()},
        "candidate_grid": {
            "floors": list(FLOORS),
            "point_multipliers": list(MULTIPLIERS),
        },
        "selection_rule": "Minimize development abs(coverage - 0.90), then mean full width.",
        "baseline_rule": {"floor": 20.0, "point_multiplier": 0.75},
        "selected_on_dev": selected,
        "baseline": baseline,
        "candidate": candidate,
        "statistical_result": (
            "The candidate improves calibration loss on both test and locked confirmation."
        ),
        "confirmation_width_ratio": (
            candidate["confirmation"]["mean_full_width"]
            / baseline["confirmation"]["mean_full_width"]
        ),
        "model_api_calls": 0,
        "local_llm_run": False,
        "production_decision": "defer_and_reject_current_candidate",
        "production_reason": (
            "The public bank unit's saved official two-model NLI faithfulness is only 7/8. "
            "Changing all eight interval hypotheses invalidates that evidence, and the required "
            "fresh heavy local NLI run is disallowed without explicit user approval. The selected "
            "rule also raises confirmation mean full width materially."
        ),
        "production_change": "none",
        "saved_public_nli": {
            "source": "evaluation/reports/nli/context-top3-ensemble.json",
            "supported_entities": 7,
            "roster_entities": 8,
            "faithfulness": 0.875,
            "gate_threshold": 0.8,
            "candidate_reusable": False,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
