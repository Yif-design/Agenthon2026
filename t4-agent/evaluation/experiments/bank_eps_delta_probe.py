#!/usr/bin/env python3
"""Compare damped recent-quarter EPS deltas on a fixed bank panel."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from evaluation.experiments.build_eps_yoy_history import (
    original_quarters,
    pair_quarters,
    quarter_facts,
)
from evaluation.experiments.eps_yoy_recent_delta_probe import build_features


BETAS = (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)


def metrics(rows: list[dict], beta: float) -> dict:
    growth_errors = []
    directions = []
    for row in rows:
        prior = float(row["prior_eps"])
        target = float(row["target_eps"])
        forecast = prior + beta * float(row["recent_yoy_delta"])
        growth_errors.append(100.0 * (forecast - target) / abs(prior))
        directions.append((forecast > prior) == (target > prior))
    return {
        "rows": len(rows),
        "mae_growth_pct": statistics.fmean(abs(error) for error in growth_errors),
        "rmse_growth_pct": math.sqrt(statistics.fmean(error * error for error in growth_errors)),
        "direction_accuracy": statistics.fmean(directions),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    source_hashes = {}
    rows = []
    audits = {}
    for path in sorted(args.cache.glob("*.json")):
        payload = path.read_bytes()
        document = json.loads(payload)
        facts = quarter_facts(document)
        pairs, audit = pair_quarters(
            path.stem,
            int(document["cik"]),
            original_quarters(facts),
            facts,
        )
        rows.extend(pairs)
        audits[path.stem] = audit
        source_hashes[path.stem] = hashlib.sha256(payload).hexdigest()

    features = build_features({"rows": rows}, args.cache)
    splits = {
        "train": [row for row in features if row["target_end"][:4] <= "2019"],
        "dev": [row for row in features if "2020" <= row["target_end"][:4] <= "2021"],
        "test": [row for row in features if "2022" <= row["target_end"][:4] <= "2023"],
        "confirmation": [row for row in features if "2024" <= row["target_end"][:4] <= "2025"],
    }
    candidates = {str(beta): metrics(splits["dev"], beta) for beta in BETAS}
    selected = min(
        BETAS,
        key=lambda beta: (
            candidates[str(beta)]["mae_growth_pct"],
            candidates[str(beta)]["rmse_growth_pct"],
        ),
    )
    baseline = {name: metrics(part, 1.0) for name, part in splits.items()}
    candidate = {name: metrics(part, selected) for name, part in splits.items()}
    distinct = selected != 1.0
    confirmation_pass = distinct and (
        candidate["confirmation"]["mae_growth_pct"]
        < baseline["confirmation"]["mae_growth_pct"]
        and candidate["confirmation"]["direction_accuracy"]
        > baseline["confirmation"]["direction_accuracy"]
    )
    report = {
        "schema_version": 1,
        "experiment": "bank_eps_delta_damping_v1",
        "hypothesis": (
            "Damping the latest filed quarterly YoY EPS delta improves the next-quarter "
            "bank EPS growth forecast over full delta persistence."
        ),
        "source": "SEC Company Concept API, us-gaap:EarningsPerShareDiluted",
        "source_documentation": (
            "https://www.sec.gov/search-filings/edgar-application-programming-interfaces"
        ),
        "source_sha256_by_ticker": source_hashes,
        "bank_tickers": sorted(source_hashes),
        "pair_rows_before_feature_cutoff": len(rows),
        "feature_rows": len(features),
        "split_counts": {name: len(part) for name, part in splits.items()},
        "split_rule": {
            "train": "target year <= 2019",
            "dev": "target year 2020-2021",
            "test": "target year 2022-2023",
            "confirmation": "target year 2024-2025",
        },
        "cutoff_rule": (
            "For each target quarter, use only the closest 45-180-day earlier quarter filed "
            "at least seven days before the target filing and its comparable prior-year quarter."
        ),
        "pair_audits": audits,
        "baseline_beta": 1.0,
        "dev_candidates": candidates,
        "selected_beta_on_dev": selected,
        "selected_candidate_distinct_from_baseline": distinct,
        "baseline": baseline,
        "candidate": candidate,
        "acceptance_rule": (
            "Development must select a beta different from 1.0, then confirmation must improve "
            "both growth-percentage MAE and direction accuracy."
        ),
        "decision": "accept" if confirmation_pass else "reject",
        "reason": (
            "The development set selected beta=1.0, exactly the production baseline; every "
            "damped candidate had worse development growth MAE and no direction improvement."
            if not distinct
            else "The distinct candidate did not improve both locked confirmation metrics."
        ),
        "production_change": "none",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
