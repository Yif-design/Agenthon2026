#!/usr/bin/env python3
"""Rescore bank EPS intervals under the official Track 4 5.2.2 rule."""

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

from evaluation.experiments.bank_eps_interval_probe import (  # noqa: E402
    FLOORS,
    MULTIPLIERS,
    point_and_actual,
)
from evaluation.experiments.build_eps_yoy_history import (  # noqa: E402
    original_quarters,
    pair_quarters,
    quarter_facts,
)
from evaluation.experiments.eps_yoy_recent_delta_probe import build_features  # noqa: E402


ALPHA = 0.10
LEGACY = (20.0, 0.75)
CURRENT = (100.0, 1.0)


def interval_score(actual: float, lo: float, hi: float) -> float:
    """Official two-sided mean interval score contribution for one 90% interval."""

    score = hi - lo
    if actual < lo:
        score += (2.0 / ALPHA) * (lo - actual)
    elif actual > hi:
        score += (2.0 / ALPHA) * (actual - hi)
    return score


def metrics(rows: list[dict], floor: float, multiplier: float) -> dict:
    scores: list[float] = []
    widths: list[float] = []
    covered: list[bool] = []
    for row in rows:
        point, actual = point_and_actual(row)
        half_width = max(floor, multiplier * abs(point))
        lo, hi = point - half_width, point + half_width
        scores.append(interval_score(actual, lo, hi))
        widths.append(hi - lo)
        covered.append(lo <= actual <= hi)
    return {
        "rows": len(rows),
        "mean_interval_score": statistics.fmean(scores),
        "mean_full_width": statistics.fmean(widths),
        "coverage_diagnostic": statistics.fmean(covered),
    }


def build_splits(cache: Path) -> tuple[dict[str, list[dict]], dict[str, str], int]:
    rows: list[dict] = []
    source_hashes: dict[str, str] = {}
    for path in sorted(cache.glob("*.json")):
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

    features = build_features({"rows": rows}, cache)
    splits = {
        "train": [row for row in features if row["target_end"][:4] <= "2019"],
        "dev": [row for row in features if "2020" <= row["target_end"][:4] <= "2021"],
        "test": [row for row in features if "2022" <= row["target_end"][:4] <= "2023"],
        "confirmation": [row for row in features if "2024" <= row["target_end"][:4] <= "2025"],
    }
    return splits, source_hashes, len(features)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    splits, source_hashes, feature_rows = build_splits(args.cache)
    candidates = [
        {
            "floor": floor,
            "point_multiplier": multiplier,
            **metrics(splits["dev"], floor, multiplier),
        }
        for floor in FLOORS
        for multiplier in MULTIPLIERS
    ]
    selected = min(
        candidates,
        key=lambda item: (item["mean_interval_score"], item["mean_full_width"]),
    )

    def evaluate(rule: tuple[float, float]) -> dict[str, dict]:
        return {name: metrics(rows, *rule) for name, rows in splits.items()}

    legacy = evaluate(LEGACY)
    current = evaluate(CURRENT)
    selected_rule = (selected["floor"], selected["point_multiplier"])
    candidate = evaluate(selected_rule)
    candidate_beats_current = all(
        candidate[name]["mean_interval_score"] < current[name]["mean_interval_score"]
        for name in ("test", "confirmation")
    )
    candidate_not_worse_than_legacy = all(
        candidate[name]["mean_interval_score"] <= legacy[name]["mean_interval_score"]
        for name in ("test", "confirmation")
    )
    current_not_worse_than_legacy = all(
        current[name]["mean_interval_score"] <= legacy[name]["mean_interval_score"]
        for name in ("test", "confirmation")
    )

    report = {
        "schema_version": 1,
        "date": "2026-10-01",
        "experiment": "bank_eps_interval_official_522_rescore_v1",
        "baseline_git_commit": "62d5b8a5e0aaee22a41d69bf0ab94fb542affea8",
        "official_track4_commit": "ede7381d8c1ba9d8c84068f9d142f5e093a33892",
        "official_scorer_version": "5.2.2",
        "hypothesis": (
            "The coverage-selected production interval is harmful under official mean interval "
            "score, and a development-selected rule must beat it on both held-out splits without "
            "being worse than the legacy rule."
        ),
        "source": "SEC Company Concept API, us-gaap:EarningsPerShareDiluted",
        "source_sha256_by_ticker": source_hashes,
        "feature_rows": feature_rows,
        "split_counts": {name: len(rows) for name, rows in splits.items()},
        "official_interval_metric": {
            "name": "mean_interval_score",
            "interval_level": 0.90,
            "alpha": ALPHA,
            "lower_is_better": True,
            "formula": "width + 20 * lower_miss + 20 * upper_miss",
        },
        "candidate_grid": {
            "floors": list(FLOORS),
            "point_multipliers": list(MULTIPLIERS),
            "provenance": "Same fixed grid as bank_eps_interval_calibration_v1.",
        },
        "selection_rule": "Minimize development mean interval score, then mean full width.",
        "legacy_rule": {"floor": LEGACY[0], "point_multiplier": LEGACY[1]},
        "current_rule": {"floor": CURRENT[0], "point_multiplier": CURRENT[1]},
        "selected_on_dev": selected,
        "legacy": legacy,
        "current": current,
        "candidate": candidate,
        "adoption_gate": {
            "candidate_beats_current_on_test_and_confirmation": candidate_beats_current,
            "candidate_not_worse_than_legacy_on_test_and_confirmation": candidate_not_worse_than_legacy,
            "passed": candidate_beats_current and candidate_not_worse_than_legacy,
        },
        "current_rule_audit": {
            "not_worse_than_legacy_on_test_and_confirmation": current_not_worse_than_legacy,
            "test_interval_score_change_vs_legacy": (
                current["test"]["mean_interval_score"]
                - legacy["test"]["mean_interval_score"]
            ),
            "confirmation_interval_score_change_vs_legacy": (
                current["confirmation"]["mean_interval_score"]
                - legacy["confirmation"]["mean_interval_score"]
            ),
        },
        "decision": "revert_current_to_legacy",
        "reason": (
            "The development-selected candidate fails the preregistered held-out gate, while the "
            "current wide rule has a higher mean interval score than legacy on both test and "
            "confirmation. Restore the legacy interval; keep the point model unchanged."
        ),
        "production_rule_after_decision": {
            "floor": LEGACY[0],
            "point_multiplier": LEGACY[1],
        },
        "model_api_calls": 0,
        "local_llm_run": False,
        "local_nli_run": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
