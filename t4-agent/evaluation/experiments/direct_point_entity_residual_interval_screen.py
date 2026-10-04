#!/usr/bin/env python3
"""Screen entity-matched residual intervals on locked direct forecasts."""

from __future__ import annotations

import copy
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PROXY = ROOT / "proxy-benchmark"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(PROXY) not in sys.path:
    sys.path.insert(0, str(PROXY))

from evaluation.experiments.direct_point_residual_interval_screen import (  # noqa: E402
    LOCKED_REPORT,
    MIN_ORIGINS,
    MIN_RESIDUALS,
    RESIDUAL_QUANTILE,
    extract_history,
    locked_results,
    without_intervals,
)
from evaluation.rolling_origin import quantile  # noqa: E402
from score_proxy import score  # noqa: E402
from t4agent.retrieve import build_index  # noqa: E402
from t4agent.taskio import load_task  # noqa: E402
from t4agent.validate import validate_answer  # noqa: E402


REPORT = ROOT / "evaluation/reports/direct-point-entity-residual-interval-screen-v1.json"
RUN_ROOT = ROOT / "evaluation/runs/direct-point-entity-residual-interval-screen-v1"


def entity_residual_policy(history: dict[str, Any]) -> dict[str, Any]:
    policies = {}
    kind = str(history["target_kind"])
    for entity_id, item in sorted(history["series"].items()):
        values = [(str(day), float(value)) for day, value in item["values"]]
        if kind == "change":
            prior = 0.0
            residual_rows = [(day, abs(value)) for day, value in values[1:]]
        else:
            prior = values[-1][1]
            residual_rows = [
                (day, abs(value - previous))
                for (_, previous), (day, value) in zip(values, values[1:])
            ]
        origins = len({day for day, _ in residual_rows})
        residuals = [value for _, value in residual_rows]
        eligible = len(residuals) >= MIN_RESIDUALS and origins >= MIN_ORIGINS
        payload = {"target_kind": kind, "entity_id": entity_id, "prior": prior, "rows": residual_rows}
        policies[entity_id] = {
            "eligible": eligible,
            "residual_observations": len(residuals),
            "residual_origins": origins,
            "absolute_residual_q90": quantile(residuals, RESIDUAL_QUANTILE) if eligible else None,
            "current_prior": prior,
            "residual_sha256": hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        }
    policy_hash = hashlib.sha256(
        json.dumps(policies, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {"entities": policies, "entity_policy_sha256": policy_hash}


def build_candidate(
    locked_answer: dict[str, Any], policy: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    candidate = copy.deepcopy(locked_answer)
    changed = 0
    for row in candidate["entity_predictions"]:
        item = policy["entities"].get(str(row["entity_id"]))
        if not item or not item["eligible"]:
            continue
        point = float(row["point_forecast"])
        half = float(item["absolute_residual_q90"]) + abs(point - float(item["current_prior"]))
        replacement = {"level": float(row["interval"]["level"]), "lo": point - half, "hi": point + half}
        if replacement != row["interval"]:
            row["interval"] = replacement
            changed += 1
    if without_intervals(candidate) != without_intervals(locked_answer):
        raise ValueError("candidate changed a field outside intervals")
    return candidate, changed


def run_screen() -> dict[str, Any]:
    results = []
    pair_material: dict[str, dict[str, dict[str, str]]] = {}
    for locked in locked_results():
        unit = PROXY / "units" / locked["unit"]
        history = extract_history(unit)
        policy = entity_residual_policy(history)
        candidate, changed = build_candidate(locked["candidate_answer"], policy)
        task = load_task(unit / "task.json")
        corpus = build_index(unit / "corpus", task.cutoff_date)
        validation_errors = validate_answer(candidate, task, corpus)
        destination = RUN_ROOT / unit.name / "answer.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        production_path = PROXY / "baselines/control-v1" / unit.name / "answer.json"
        production = score(unit, production_path)
        direct = locked["candidate"]
        scored = score(unit, destination)
        key = "composite_before_claim_penalty"
        event = unit.name.rsplit("-", 1)[0]
        pair_material.setdefault(event, {})[locked["variant"]] = {
            "history_sha256": history["history_sha256"],
            "entity_policy_sha256": policy["entity_policy_sha256"],
        }
        results.append({
            "unit": unit.name,
            "event": event,
            "variant": locked["variant"],
            "rows": len(candidate["entity_predictions"]),
            "changed_interval_rows": changed,
            "history_sha256": history["history_sha256"],
            "policy": policy,
            "outside_intervals_identical": without_intervals(candidate) == without_intervals(locked["candidate_answer"]),
            "validation_errors": validation_errors,
            "answer_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "production": production,
            "direct": direct,
            "candidate": scored,
            "candidate_minus_direct": scored[key] - direct[key],
            "candidate_minus_production": scored[key] - production[key],
        })
    pair_invariance = {
        event: {
            "history_equal": variants.get("explicit", {}).get("history_sha256") == variants.get("transformed", {}).get("history_sha256"),
            "entity_policy_equal": variants.get("explicit", {}).get("entity_policy_sha256") == variants.get("transformed", {}).get("entity_policy_sha256"),
            "variants": variants,
        }
        for event, variants in sorted(pair_material.items())
    }
    key = "composite_before_claim_penalty"
    production_mean = statistics.fmean(row["production"][key] for row in results)
    direct_mean = statistics.fmean(row["direct"][key] for row in results)
    candidate_mean = statistics.fmean(row["candidate"][key] for row in results)
    transformed = [row for row in results if row["variant"] == "transformed"]
    transformed_delta = statistics.fmean(row["candidate"][key] for row in transformed) - statistics.fmean(
        row["production"][key] for row in transformed
    )
    noninferior = sum(row["candidate_minus_direct"] >= -1e-12 for row in results)
    worst = min(row["candidate_minus_production"] for row in results)
    gates = {
        "all_8_candidate_answers_valid": len(results) == 8 and all(not row["validation_errors"] for row in results),
        "point_claims_roster_identical": all(row["outside_intervals_identical"] for row in results),
        "schema_pair_entity_history_and_residual_hash_equal": all(
            row["history_equal"] and row["entity_policy_equal"] for row in pair_invariance.values()
        ),
        "candidate_mean_beats_direct_by_0_02": candidate_mean - direct_mean >= 0.02,
        "candidate_mean_beats_production_by_0_10": candidate_mean - production_mean >= 0.10,
        "candidate_transformed_mean_beats_production_by_0_15": transformed_delta >= 0.15,
        "candidate_noninferior_to_direct_on_6_of_8": noninferior >= 6,
        "candidate_worst_production_delta_at_least_minus_0_10": worst >= -0.10,
    }
    return {
        "schema_version": 1,
        "experiment": "direct_point_entity_residual_interval_screen_v1",
        "scope": "evaluation_only_locked_direct_outputs_no_model_calls_no_production_change",
        "hypothesis": (
            "Entity-matched pre-cutoff residual intervals preserve useful direct points while avoiding "
            "cross-entity scale contamination."
        ),
        "reference": {
            "repository": "https://github.com/wangzgui/agenthon-t4-baseline-2026",
            "active_version": "s1.6",
            "mechanism": "entity-matched residuals_for_entity interval ownership",
        },
        "model_api_calls": 0,
        "locked_report": str(LOCKED_REPORT.relative_to(ROOT)),
        "policy": {
            "residual_scope": "one entity series only",
            "level_or_metric_baseline": "one-period persistence",
            "change_baseline": "zero",
            "minimum_residual_observations": MIN_RESIDUALS,
            "minimum_origins": MIN_ORIGINS,
            "absolute_residual_quantile": RESIDUAL_QUANTILE,
            "half_width": "entity absolute_residual_q90 + abs(locked_house_point - current_entity_prior)",
            "insufficient_history": "preserve locked direct interval",
        },
        "production_mean_composite": production_mean,
        "direct_mean_composite": direct_mean,
        "candidate_mean_composite": candidate_mean,
        "candidate_minus_direct_mean": candidate_mean - direct_mean,
        "candidate_minus_production_mean": candidate_mean - production_mean,
        "candidate_transformed_minus_production_mean": transformed_delta,
        "candidate_noninferior_units": noninferior,
        "candidate_worst_production_delta": worst,
        "pair_invariance": pair_invariance,
        "gates": gates,
        "decision": "advance_to_independent_confirmation" if all(gates.values()) else "reject_no_production_change",
        "results": results,
        "limitations": [
            "This is a development screen over previously inspected direct outputs.",
            "Residuals belong to target-kind statistical baselines, not historical House forecasts.",
            "Capex lacks complete target-history tables and retains locked direct intervals.",
        ],
    }


def main() -> None:
    report = run_screen()
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "decision", "candidate_minus_direct_mean", "candidate_minus_production_mean",
        "candidate_transformed_minus_production_mean", "candidate_noninferior_units",
        "candidate_worst_production_delta", "gates",
    )}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
