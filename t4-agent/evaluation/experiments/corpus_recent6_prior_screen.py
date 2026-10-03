#!/usr/bin/env python3
"""Screen one fixed corpus-derived prior across two resolved proxy families.

This experiment deliberately assumes that a separate TargetSpec stage has already
resolved the target history.  It tests only the forecasting prior; the source
adapters below are evaluation code and are never imported by the production agent.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import statistics
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
PROXY = ROOT / "proxy-benchmark"
EXPERIMENT = "corpus_recent6_prior_screen_v1"
WINDOW = 6
INTERVAL_MULTIPLIER = 1.65


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_scorer() -> Any:
    path = PROXY / "score_proxy.py"
    spec = importlib.util.spec_from_file_location("proxy_score", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load scorer from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def auction_histories() -> dict[str, list[float]]:
    source = load_json(PROXY / "sources/proxy-15-auctions-2023.json")
    task = load_json(
        PROXY / "units/proxy-15-auction-indirect-bidder-share-20230802-explicit/task.json"
    )
    cutoff = str(task["cutoff_date"])
    entity_by_term = {str(row["tenor"]): str(row["entity_id"]) for row in task["entities"]}
    rows: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in source["rows"]:
        term = str(row["original_security_term"])
        if term not in entity_by_term or str(row["auction_date"]) >= cutoff:
            continue
        accepted = float(row["total_accepted"])
        indirect = float(row["indirect_bidder_accepted"])
        if accepted <= 0.0 or not 0.0 <= indirect <= accepted:
            raise ValueError("invalid Treasury accepted amounts")
        rows[term].append((str(row["auction_date"]), 100.0 * indirect / accepted))
    result = {}
    for term, entity_id in entity_by_term.items():
        ordered = [value for _, value in sorted(rows[term])]
        if len(ordered) < WINDOW:
            raise ValueError(f"{term} has fewer than {WINDOW} cutoff-safe observations")
        result[entity_id] = ordered
    return result


def energy_histories() -> dict[str, list[float]]:
    source = load_json(PROXY / "sources/proxy-16-eia-crude-2026.json")
    cutoff_release = str(source["cutoff_release_date"])
    target_week = str(source["target_week_ending"])
    result = {}
    for row in source["rows"]:
        entity_id = f"EIA_CRUDE_{row['region_code']}_{target_week.replace('-', '')}"
        visible = [
            item
            for item in row["observations"]
            if str(item["release_date"]) <= cutoff_release and str(item["week_ending"]) < target_week
        ]
        ordered = [
            float(item["change_million_barrels"])
            for item in sorted(visible, key=lambda item: str(item["week_ending"]))
        ]
        if len(ordered) < WINDOW:
            raise ValueError(f"{entity_id} has fewer than {WINDOW} cutoff-safe observations")
        result[entity_id] = ordered
    return result


def recent6(values: list[float]) -> tuple[float, float]:
    window = values[-WINDOW:]
    point = statistics.fmean(window)
    half = INTERVAL_MULTIPLIER * statistics.pstdev(window)
    return point, max(1e-9, half)


def candidate_answer(unit: Path, histories: dict[str, list[float]]) -> dict[str, Any]:
    task = load_json(unit / "task.json")
    naive = load_json(unit / "reference/naive_answer.json")
    claims = {
        str(row["entity_id"]): row.get("claims", []) for row in naive["entity_predictions"]
    }
    predictions = []
    for entity in task["entities"]:
        entity_id = str(entity["entity_id"])
        point, half = recent6(histories[entity_id])
        predictions.append(
            {
                "entity_id": entity_id,
                "point_forecast": point,
                "interval": {"lo": point - half, "hi": point + half, "level": 0.9},
                "claims": claims[entity_id],
            }
        )
    return {
        "task_id": task["task_id"],
        "schema_version": "3",
        "target_type": "regression",
        "entity_predictions": predictions,
        "notes": {
            "experiment": EXPERIMENT,
            "prior": "mean_last_6_resolved_target_observations",
            "interval": "1.65_population_standard_deviations_last_6",
        },
    }


def keyed_forecasts(answer: dict[str, Any]) -> dict[str, tuple[float, float, float]]:
    return {
        str(row["entity_id"]): (
            float(row["point_forecast"]),
            float(row["interval"]["lo"]),
            float(row["interval"]["hi"]),
        )
        for row in answer["entity_predictions"]
    }


def mean_composite(rows: list[dict[str, Any]]) -> float:
    return statistics.fmean(float(row["composite_before_claim_penalty"]) for row in rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "evaluation/reports/corpus-recent6-prior-screen-v1.json",
    )
    parser.add_argument(
        "--answers-dir",
        type=Path,
        help="Optional directory for schema-validation artifacts; omitted by default.",
    )
    args = parser.parse_args()
    scorer = load_scorer()

    families: dict[str, tuple[Callable[[], dict[str, list[float]]], str, str]] = {
        "proxy-15": (
            auction_histories,
            "proxy-15-auction-indirect-bidder-share-20230802-",
            "evaluation/reports/proxy-15-auction-control-v1.json",
        ),
        "proxy-16": (
            energy_histories,
            "proxy-16-crude-inventory-change-20260923-",
            "evaluation/reports/proxy-16-energy-control-v1.json",
        ),
    }
    candidate_results = []
    baseline_results = []
    forecasts: dict[str, dict[str, tuple[float, float, float]]] = {}
    source_hashes = {}
    with tempfile.TemporaryDirectory(prefix="corpus-prior-screen-") as tmp:
        tmp_path = Path(tmp)
        for family, (history_builder, prefix, baseline_report_path) in families.items():
            histories = history_builder()
            report_path = ROOT / baseline_report_path
            baseline_report = load_json(report_path)
            source_hashes[family] = {
                "baseline_report": baseline_report_path,
                "baseline_report_sha256": sha256(report_path),
            }
            source_path = (
                PROXY / "sources/proxy-15-auctions-2023.json"
                if family == "proxy-15"
                else PROXY / "sources/proxy-16-eia-crude-2026.json"
            )
            source_hashes[family].update(
                {
                    "source_snapshot": str(source_path.relative_to(ROOT)),
                    "source_snapshot_sha256": sha256(source_path),
                }
            )
            for row in baseline_report["results"]:
                baseline_results.append({**row, "proxy_family": family})
            for variant in ("explicit", "transformed"):
                unit = PROXY / "units" / f"{prefix}{variant}"
                answer = candidate_answer(unit, histories)
                answer_path = tmp_path / f"{unit.name}.json"
                answer_path.write_text(json.dumps(answer, indent=2, sort_keys=True) + "\n")
                if args.answers_dir is not None:
                    args.answers_dir.mkdir(parents=True, exist_ok=True)
                    (args.answers_dir / answer_path.name).write_bytes(answer_path.read_bytes())
                result = scorer.score(unit, answer_path)
                candidate_results.append({**result, "proxy_family": family, "variant": variant})
                forecasts[unit.name] = keyed_forecasts(answer)

    candidate_by_family = {
        family: [row for row in candidate_results if row["proxy_family"] == family]
        for family in families
    }
    baseline_by_family = {
        family: [row for row in baseline_results if row["proxy_family"] == family]
        for family in families
    }
    pair_invariant = {}
    for family, (_builder, prefix, _report) in families.items():
        pair_invariant[family] = forecasts[f"{prefix}explicit"] == forecasts[f"{prefix}transformed"]

    candidate_mean = mean_composite(candidate_results)
    baseline_mean = mean_composite(baseline_results)
    family_improved = {
        family: mean_composite(candidate_by_family[family]) > mean_composite(baseline_by_family[family])
        for family in families
    }
    gates = {
        "mean_composite_improvement_at_least_0_05": candidate_mean - baseline_mean >= 0.05,
        "each_family_mean_strictly_improved": all(family_improved.values()),
        "every_case_composite_at_least_0_45": all(
            float(row["composite_before_claim_penalty"]) >= 0.45 for row in candidate_results
        ),
        "schema_pair_forecasts_identical": all(pair_invariant.values()),
        "candidate_generated_before_outcome_scoring": True,
        "model_api_calls_zero": True,
    }
    accepted = all(gates.values())
    report = {
        "experiment": EXPERIMENT,
        "date": "2026-10-03",
        "scope": "L1/L2 corpus-derived numerical prior screen after resolved target history",
        "hypothesis": (
            "A fixed recent-six mean with a 1.65 population-standard-deviation interval improves "
            "the current control across both resolved regression proxy families and remains invariant "
            "to equivalent schema transformations."
        ),
        "candidate": {
            "point": "mean of the six most recent cutoff-safe resolved-target observations",
            "interval": "point plus/minus 1.65 population standard deviations of the same six values",
            "window": WINDOW,
            "interval_multiplier": INTERVAL_MULTIPLIER,
            "target_resolution": "evaluation adapters; TargetSpec/runtime field resolution is out of scope",
            "outcome_used_for_selection": False,
        },
        "source_hashes": source_hashes,
        "baseline_results": baseline_results,
        "candidate_results": candidate_results,
        "aggregate": {
            "baseline_mean_composite": baseline_mean,
            "candidate_mean_composite": candidate_mean,
            "mean_composite_delta": candidate_mean - baseline_mean,
            "family_baseline_mean": {
                family: mean_composite(rows) for family, rows in baseline_by_family.items()
            },
            "family_candidate_mean": {
                family: mean_composite(rows) for family, rows in candidate_by_family.items()
            },
            "family_improved": family_improved,
            "schema_pair_forecasts_identical": pair_invariant,
        },
        "adoption_gates": gates,
        "decision": "accept_prior_evidence_only" if accepted else "reject_prior_candidate",
        "production_change": "none",
        "limitations": [
            "Only two regression events are runnable; this cannot satisfy the full cross-target-type production gate.",
            "Evaluation adapters provide the resolved target history and are not production TargetSpec logic.",
            "The screen tests one fixed prior and does not select among windows using target outcomes.",
            "Claim penalty and reasoning bonus are outside this metric-only screen.",
        ],
        "model_api_calls": 0,
        "local_llm_run": False,
        "local_nli_run": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
