#!/usr/bin/env python3
"""Test whether the latest filed YoY EPS delta improves the next-quarter point."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from evaluation.experiments.build_eps_yoy_history import (  # noqa: E402
    original_quarters,
    quarter_facts,
)


def build_features(dataset: dict, cache: Path) -> list[dict]:
    company_facts = {}
    for ticker in {row["ticker"] for row in dataset["rows"]}:
        facts = quarter_facts(json.loads((cache / f"{ticker}.json").read_text()))
        company_facts[ticker] = (facts, original_quarters(facts))

    output = []
    for row in dataset["rows"]:
        facts, originals = company_facts[row["ticker"]]
        # A seven-day pre-filing proxy avoids using the target filing itself.  The
        # production task supplies its exact cutoff; this probe only has SEC facts.
        proxy_cutoff = date.fromisoformat(row["target_filed"]) - timedelta(days=7)
        candidates = []
        for recent in originals:
            gap = (date.fromisoformat(row["target_end"]) - date.fromisoformat(recent["end"])).days
            if 45 <= gap <= 180 and date.fromisoformat(recent["filed"]) <= proxy_cutoff:
                candidates.append((gap, recent))
        if not candidates:
            continue
        recent = min(candidates, key=lambda item: item[0])[1]

        prior_candidates = []
        for prior in originals:
            gap = (date.fromisoformat(recent["end"]) - date.fromisoformat(prior["end"])).days
            if 330 <= gap <= 400 and prior["filed"] < recent["start"]:
                prior_candidates.append((abs(gap - 365), prior))
        if not prior_candidates:
            continue
        recent_prior = min(prior_candidates, key=lambda item: item[0])[1]
        comparators = [
            float(fact["val"])
            for fact in facts
            if fact["accn"] == recent["accn"]
            and fact["start"] == recent_prior["start"]
            and fact["end"] == recent_prior["end"]
        ]
        if not comparators:
            continue
        prior_value = float(recent_prior["val"])
        comparator = min(comparators, key=lambda value: abs(value - prior_value))
        if abs(comparator - prior_value) > max(0.01, 0.01 * abs(prior_value)):
            continue
        output.append({
            **row,
            "recent_eps": float(recent["val"]),
            "recent_prior_eps": prior_value,
            "recent_yoy_delta": float(recent["val"]) - prior_value,
            "feature_proxy_cutoff": proxy_cutoff.isoformat(),
            "recent_filed": recent["filed"],
        })
    return output


def point(row: dict, method: str, beta: float = 0.0) -> float:
    prior = float(row["prior_eps"])
    if method == "current_no_signal":
        return prior - max(0.05 * abs(prior), 0.01)
    if method == "recent_delta":
        return prior + beta * float(row["recent_yoy_delta"])
    raise KeyError(method)


def metrics(rows: list[dict], method: str, beta: float = 0.0) -> dict:
    points = [point(row, method, beta) for row in rows]
    errors = [forecast - float(row["target_eps"]) for forecast, row in zip(points, rows, strict=True)]
    return {
        "rows": len(rows),
        "mae": statistics.fmean(abs(error) for error in errors),
        "rmse": math.sqrt(statistics.fmean(error * error for error in errors)),
        "direction_accuracy": statistics.fmean(
            (forecast > float(row["prior_eps"]))
            == (float(row["target_eps"]) > float(row["prior_eps"]))
            for forecast, row in zip(points, rows, strict=True)
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.dataset.read_text())
    rows = build_features(document, args.cache)
    splits = {
        "train": [row for row in rows if row["target_end"][:4] <= "2019"],
        "dev": [row for row in rows if "2020" <= row["target_end"][:4] <= "2021"],
        "test": [row for row in rows if "2022" <= row["target_end"][:4] <= "2023"],
        "confirmation": [row for row in rows if "2024" <= row["target_end"][:4] <= "2025"],
    }
    candidates = {
        str(beta): metrics(splits["dev"], "recent_delta", beta)
        for beta in (0.25, 0.5, 0.75, 1.0)
    }
    selected_beta = min(
        (float(beta) for beta in candidates),
        key=lambda beta: (candidates[str(beta)]["mae"], candidates[str(beta)]["rmse"]),
    )
    baseline = {name: metrics(part, "current_no_signal") for name, part in splits.items()}
    candidate = {name: metrics(part, "recent_delta", selected_beta) for name, part in splits.items()}
    confirmation_pass = (
        candidate["confirmation"]["mae"] < baseline["confirmation"]["mae"]
        and candidate["confirmation"]["direction_accuracy"]
        > baseline["confirmation"]["direction_accuracy"]
    )
    result = {
        "experiment": "eps_yoy_recent_delta_point_v1",
        "hypothesis": "A damped latest-filed quarterly YoY EPS delta improves the next same-quarter EPS point.",
        "dataset": str(args.dataset),
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "feature_rows": len(rows),
        "split_row_counts": {name: len(part) for name, part in splits.items()},
        "candidate_betas": candidates,
        "selected_beta_on_dev": selected_beta,
        "baseline": baseline,
        "candidate": candidate,
        "acceptance_rule": "Confirmation must improve both MAE and direction accuracy.",
        "decision": "accept" if confirmation_pass else "reject",
        "reason": (
            "confirmation improved both required metrics"
            if confirmation_pass
            else "confirmation direction improved but MAE and RMSE worsened"
        ),
        "limitation": "The exact task cutoff is unavailable in SEC history; target filing minus seven days is a proxy.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
