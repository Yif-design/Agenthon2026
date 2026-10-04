#!/usr/bin/env python3
"""Screen full target-contract semantics for generic scalar selection on all proxies."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
PROXY = PROJECT / "proxy-benchmark"
if str(PROXY) not in sys.path:
    sys.path.insert(0, str(PROXY))

import score_proxy  # type: ignore  # noqa: E402
from t4agent.calc import (  # noqa: E402
    CHANGE_BASELINE_SHRINKAGE,
    CHANGE_TOKENS,
    CURRENT_BASELINE_TOKENS,
    METADATA_TOKENS,
    REFERENCE_BASELINE_TOKENS,
    TARGET_NOISE_TOKENS,
    _field_tokens,
    interval_for,
    numeric_facts,
)


PERCENT_LIKE = {
    "pct", "percent", "percentage", "ratio", "fraction", "decimal", "share",
    "growth", "return", "volatility", "sigma", "margin", "intensity",
}
ABSOLUTE_SCALE = {
    "usd", "dollar", "dollars", "person", "persons", "month", "months", "year", "years",
    "day", "days", "million", "millions", "billion", "billions", "thousand", "thousands",
    "barrel", "barrels", "volume", "count", "index",
}


def target_contract(task: dict[str, Any]) -> str:
    target = task["target"]
    parts = [str(target.get(key, "")) for key in ("name", "unit", "definition", "horizon")]
    parts.append(str(task.get("prompt", ""))[:1200])
    return " ".join(parts)


def select_contract_point(
    target_type: str, target_name: str, contract: str, entity: dict[str, Any]
) -> tuple[float, str | None, str]:
    """Candidate selector; it never infers a conversion from value magnitude."""
    nums = numeric_facts(entity)
    semantic_tokens = _field_tokens(contract)
    target_tokens = semantic_tokens - TARGET_NOISE_TOKENS
    percent_like = bool(semantic_tokens & PERCENT_LIKE)
    requires_change = target_type in {"regression", "ranking"} and bool(
        semantic_tokens & CHANGE_TOKENS
    )
    candidates: list[tuple[int, str, float]] = []
    eligible: list[tuple[str, float]] = []
    for key, value in nums.items():
        field_tokens = _field_tokens(key)
        if percent_like and field_tokens & ABSOLUTE_SCALE and not field_tokens & PERCENT_LIKE:
            continue
        overlap = target_tokens & field_tokens
        if requires_change and not field_tokens & CHANGE_TOKENS:
            continue
        if not field_tokens & METADATA_TOKENS or overlap:
            eligible.append((key, value))
        score = 10 * len(overlap)
        score += 2 if field_tokens & CURRENT_BASELINE_TOKENS else 0
        score += 1 if field_tokens & REFERENCE_BASELINE_TOKENS else 0
        score -= 8 if field_tokens & METADATA_TOKENS and not overlap else 0
        if overlap and score > 0:
            candidates.append((score, key, value))
    if candidates:
        _, key, value = sorted(candidates, key=lambda item: (-item[0], item[1]))[0]
        if requires_change and _field_tokens(key) & CHANGE_TOKENS:
            return CHANGE_BASELINE_SHRINKAGE * value, key, "contract_damped_change_match"
        return value, key, "contract_token_match"
    if requires_change:
        if len(eligible) == 1:
            key, value = eligible[0]
            return CHANGE_BASELINE_SHRINKAGE * value, key, "contract_single_change_fallback"
        return 0.0, None, "contract_change_without_baseline"
    if len(eligible) == 1:
        key, value = eligible[0]
        return value, key, "contract_single_numeric_fallback"
    return 0.0, None, "contract_no_unambiguous_baseline"


def generic_units(catalog: dict[str, Any]) -> set[str]:
    units = set()
    for item in catalog["materialized_questions"]:
        report = json.loads((PROJECT / item["control_report"]).read_text())
        for row in report["results"]:
            if row["methods"] == ["generic_baseline"]:
                units.add(row["unit"])
    return units


def candidate_answer(unit: Path, baseline_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    task = json.loads((unit / "task.json").read_text())
    answer = json.loads(baseline_path.read_text())
    entities = {row["entity_id"]: row for row in task["entities"]}
    details = []
    points = {}
    contract = target_contract(task)
    for prediction in answer["entity_predictions"]:
        entity_id = prediction["entity_id"]
        point, field, reason = select_contract_point(
            task["target"]["type"], task["target"]["name"], contract, entities[entity_id]
        )
        interval = interval_for(point, task["target"]["name"], task["interval_level"])
        half = (interval["hi"] - interval["lo"]) / 2.0
        prediction["point_forecast"] = point
        prediction["interval"] = {
            "level": interval["level"], "lo": point - 2.0 * half, "hi": point + 2.0 * half
        }
        points[entity_id] = point
        details.append({"entity_id": entity_id, "field": field, "reason": reason, "point": point})
    if task["target"]["type"] == "ranking":
        ordered = sorted(points, key=lambda entity_id: (-points[entity_id], entity_id))
        ranks = {entity_id: index + 1 for index, entity_id in enumerate(ordered)}
        for prediction in answer["entity_predictions"]:
            prediction["rank"] = ranks[prediction["entity_id"]]
    return answer, details


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, default=PROJECT / "evaluation/runs/target-contract-scalar-screen-v1")
    args = parser.parse_args()
    catalog = json.loads((PROJECT / "proxy-benchmark/question_catalog.json").read_text())
    eligible = generic_units(catalog)
    rows = []
    for unit in sorted(path for path in (PROJECT / "proxy-benchmark/units").iterdir() if path.is_dir()):
        baseline_dir = PROJECT / "proxy-benchmark/baselines/control-v1" / unit.name
        baseline_score = json.loads((baseline_dir / "score.json").read_text())
        variant = unit.name.rsplit("-", 1)[-1]
        if unit.name in eligible:
            answer, details = candidate_answer(unit, baseline_dir / "answer.json")
            output = args.run_dir / unit.name / "answer.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(answer, indent=2) + "\n")
            candidate_score = score_proxy.score(unit, output)
        else:
            details = []
            candidate_score = baseline_score
        rows.append({
            "unit": unit.name, "question": unit.name.rsplit("-", 2)[0], "variant": variant,
            "eligible_generic_baseline": unit.name in eligible,
            "baseline_composite": baseline_score["composite_before_claim_penalty"],
            "candidate_composite": candidate_score["composite_before_claim_penalty"],
            "delta": candidate_score["composite_before_claim_penalty"] - baseline_score["composite_before_claim_penalty"],
            "selection_details": details,
        })
    by_variant = {}
    for variant in ("explicit", "transformed"):
        selected = [row for row in rows if row["variant"] == variant]
        by_variant[variant] = {
            "units": len(selected),
            "baseline_mean": statistics.fmean(row["baseline_composite"] for row in selected),
            "candidate_mean": statistics.fmean(row["candidate_composite"] for row in selected),
            "mean_delta": statistics.fmean(row["delta"] for row in selected),
            "minimum_delta": min(row["delta"] for row in selected),
            "improved": sum(row["delta"] > 1e-12 for row in selected),
            "worsened": sum(row["delta"] < -1e-12 for row in selected),
        }
    gates = {
        "transformed_mean_improves_at_least_0_05": by_variant["transformed"]["mean_delta"] >= 0.05,
        "explicit_mean_noninferior": by_variant["explicit"]["mean_delta"] >= -1e-12,
        "no_unit_worse_by_more_than_0_02": min(row["delta"] for row in rows) >= -0.02,
        "at_least_four_units_improve": sum(row["delta"] > 1e-12 for row in rows) >= 4,
        "all_points_finite": all(math.isfinite(detail["point"]) for row in rows for detail in row["selection_details"]),
    }
    report = {
        "schema_version": 1, "experiment": "target_contract_scalar_screen_v1",
        "baseline_git_commit": "cc01e90ba3403c2e0c1847fe29e245dd60e9660c",
        "hypothesis": "Full target-contract semantics plus explicit absolute-scale rejection improves generic scalar selection across transformed schemas without family-specific rules or magnitude inference.",
        "scope": "L2/L3 generic unknown-family scalar selection on the complete 40-unit proxy catalog",
        "candidate": "Use target name, unit, definition, horizon and bounded prompt; for ratio-like targets reject explicit absolute-scale fields; never rescale values.",
        "by_variant": by_variant, "gates": gates, "rows": rows,
        "decision_rule": "Advance only when every gate passes; production and public-output gates are separate.",
        "decision": "pass_to_production_gates" if all(gates.values()) else "reject",
        "model_api_calls": 0, "local_llm_run": False, "local_nli_run": False,
        "limitations": ["One historical event per proxy family.", "Fraction values remain unscaled by design.", "This screen does not test citations or model-assisted signals."],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"by_variant": by_variant, "gates": gates, "decision": report["decision"], "changed": [(r["unit"], round(r["delta"], 6)) for r in rows if abs(r["delta"]) > 1e-12]}, indent=2))


if __name__ == "__main__":
    main()
