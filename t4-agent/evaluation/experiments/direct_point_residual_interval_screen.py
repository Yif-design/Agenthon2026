#!/usr/bin/env python3
"""Reuse locked direct points while assigning cutoff-safe residual intervals.

The candidate never calls a model and never reads the current outcome while
constructing an answer.  It extracts complete pre-cutoff target-history
columns from the supplied corpus, computes target-kind baseline residuals,
and replaces only intervals when history is sufficient.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
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

from evaluation.experiments.quantity_unit_canonicalization_audit import (  # noqa: E402
    DATE,
    NUMBER,
    convert_once,
    semantic_role,
    source_unit,
    target_kind,
    target_unit,
    tokens,
)
from evaluation.rolling_origin import quantile  # noqa: E402
from score_proxy import score  # noqa: E402
from t4agent.retrieve import build_index  # noqa: E402
from t4agent.taskio import load_task  # noqa: E402
from t4agent.validate import validate_answer  # noqa: E402


LOCKED_REPORT = ROOT / "evaluation/reports/direct-forecast-reference-screen-v1.json"
REPORT = ROOT / "evaluation/reports/direct-point-residual-interval-screen-v1.json"
RUN_ROOT = ROOT / "evaluation/runs/direct-point-residual-interval-screen-v1"
MIN_RESIDUALS = 8
MIN_ORIGINS = 3
RESIDUAL_QUANTILE = 0.90


def locked_results() -> list[dict[str, Any]]:
    report = json.loads(LOCKED_REPORT.read_text(encoding="utf-8"))
    rows = report.get("results")
    if not isinstance(rows, list) or len(rows) != 8:
        raise ValueError("locked direct report must contain exactly eight units")
    return rows


def desired_roles(kind: str) -> set[str]:
    if kind == "change":
        return {"change", "recent_change"}
    if kind == "ratio_or_metric":
        return {"metric", "recent_metric", "baseline_metric"}
    return {"level", "recent_level", "baseline_level"}


def interval_target_kind(target: dict[str, Any]) -> str:
    """Recognize ratio semantics that survive opaque target-name rewrites."""
    kind = target_kind(target)
    text = " ".join(str(target.get(key) or "") for key in ("name", "definition")).lower()
    target_tokens = tokens(text)
    if (
        kind != "change"
        and (
            target_tokens & {"ratio", "share", "fraction", "margin", "intensity"}
            or "divided by" in text
            or "_to_" in str(target.get("name") or "").lower()
        )
    ):
        return "ratio_or_metric"
    return kind


def _target_terms(target: dict[str, Any]) -> set[str]:
    text = " ".join(str(target.get(key) or "") for key in ("name", "definition"))
    return tokens(text) - {
        "future", "next", "forecast", "target", "announced", "result", "week", "weekly",
        "million", "billion", "barrels", "cubic", "feet", "pct", "percent",
    }


def _parse_table_series(
    text: str,
    cutoff: str,
    target: dict[str, Any],
) -> list[dict[str, Any]]:
    canonical_unit = target_unit(target)
    kind = interval_target_kind(target)
    if canonical_unit is None:
        return []
    lines = text.splitlines()
    candidates: list[dict[str, Any]] = []
    target_terms = _target_terms(target)
    for index, header_line in enumerate(lines):
        if "|" not in header_line:
            continue
        headers = [cell.strip() for cell in header_line.split("|")]
        if len(headers) < 2:
            continue
        for column, header in enumerate(headers[1:], 1):
            original_unit = source_unit(header)
            role = semantic_role(header)
            if original_unit is None or role not in desired_roles(kind):
                continue
            if convert_once(1.0, original_unit, canonical_unit) is None:
                continue
            values = []
            for line in lines[index + 1:]:
                cells = [cell.strip() for cell in line.split("|")]
                if len(cells) != len(headers) or not DATE.fullmatch(cells[0]):
                    if values:
                        break
                    continue
                if cells[0] > cutoff:
                    continue
                raw = cells[column].replace(",", "")
                if not NUMBER.fullmatch(raw):
                    continue
                converted = convert_once(float(raw), original_unit, canonical_unit)
                if converted is not None:
                    values.append((cells[0], converted))
            if len(values) >= 2:
                candidates.append({
                    "header": header,
                    "role": role,
                    "canonical_unit": canonical_unit,
                    "overlap": len(tokens(header) & target_terms),
                    "values": sorted(dict(values).items()),
                })
        if candidates:
            break
    return sorted(candidates, key=lambda row: (-row["overlap"], row["header"]))


def extract_history(unit: Path) -> dict[str, Any]:
    task = json.loads((unit / "task.json").read_text(encoding="utf-8"))
    kind = interval_target_kind(task["target"])
    series = {}
    for entity in task["entities"]:
        entity_id = str(entity["entity_id"])
        corpus_ref = entity.get("corpus_ref")
        if not isinstance(corpus_ref, str):
            continue
        path = unit / corpus_ref
        document = json.loads(path.read_text(encoding="utf-8"))
        if entity_id not in {str(value) for value in document.get("entities", [])}:
            raise ValueError(f"{entity_id} does not own {path.name}")
        candidates = _parse_table_series(
            str(document.get("text") or ""), str(task["cutoff_date"]), task["target"]
        )
        if candidates:
            chosen = candidates[0]
            series[entity_id] = {
                "doc_id": str(document.get("doc_id")),
                "header": chosen["header"],
                "role": chosen["role"],
                "canonical_unit": chosen["canonical_unit"],
                "values": chosen["values"],
            }
    normalized = {
        "target_kind": kind,
        "target_unit": target_unit(task["target"]),
        "series": {key: series[key] for key in sorted(series)},
    }
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    normalized["history_sha256"] = hashlib.sha256(encoded).hexdigest()
    return normalized


def residual_policy(history: dict[str, Any]) -> dict[str, Any]:
    kind = str(history["target_kind"])
    residual_rows = []
    current_priors = {}
    for entity_id, item in history["series"].items():
        values = [(str(day), float(value)) for day, value in item["values"]]
        if kind == "change":
            current_priors[entity_id] = 0.0
            for day, value in values[1:]:
                residual_rows.append((day, entity_id, abs(value)))
        else:
            current_priors[entity_id] = values[-1][1]
            for (_, previous), (day, value) in zip(values, values[1:]):
                residual_rows.append((day, entity_id, abs(value - previous)))
    residual_rows.sort()
    residuals = [row[2] for row in residual_rows]
    origins = len({row[0] for row in residual_rows})
    eligible = len(residuals) >= MIN_RESIDUALS and origins >= MIN_ORIGINS
    q90 = quantile(residuals, RESIDUAL_QUANTILE) if eligible else None
    residual_payload = {
        "target_kind": kind,
        "rows": residual_rows,
        "current_priors": current_priors,
    }
    residual_hash = hashlib.sha256(
        json.dumps(residual_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "eligible": eligible,
        "residual_observations": len(residuals),
        "residual_origins": origins,
        "absolute_residual_q90": q90,
        "current_priors": current_priors,
        "residual_sha256": residual_hash,
    }


def without_intervals(answer: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(answer)
    for row in result["entity_predictions"]:
        row.pop("interval", None)
    return result


def build_candidate(
    locked_answer: dict[str, Any],
    history: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    candidate = copy.deepcopy(locked_answer)
    if not policy["eligible"]:
        return candidate, 0
    q90 = float(policy["absolute_residual_q90"])
    changed = 0
    for row in candidate["entity_predictions"]:
        entity_id = str(row["entity_id"])
        prior = policy["current_priors"].get(entity_id)
        if prior is None:
            continue
        point = float(row["point_forecast"])
        half = q90 + abs(point - float(prior))
        replacement = {"level": float(row["interval"]["level"]), "lo": point - half, "hi": point + half}
        if replacement != row["interval"]:
            changed += 1
            row["interval"] = replacement
    if without_intervals(candidate) != without_intervals(locked_answer):
        raise ValueError("candidate changed a field outside intervals")
    return candidate, changed


def run_screen() -> dict[str, Any]:
    rows = []
    histories = {}
    for locked in locked_results():
        unit = PROXY / "units" / locked["unit"]
        history = extract_history(unit)
        policy = residual_policy(history)
        locked_answer = locked["candidate_answer"]
        candidate, changed = build_candidate(locked_answer, history, policy)
        task = load_task(unit / "task.json")
        corpus = build_index(unit / "corpus", task.cutoff_date)
        errors = validate_answer(candidate, task, corpus)
        destination = RUN_ROOT / unit.name / "answer.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        production_path = PROXY / "baselines/control-v1" / unit.name / "answer.json"
        production_score = score(unit, production_path)
        candidate_score = score(unit, destination)
        direct_score = locked["candidate"]
        key = "composite_before_claim_penalty"
        event = unit.name.rsplit("-", 1)[0]
        histories.setdefault(event, {})[locked["variant"]] = {
            "history_sha256": history["history_sha256"],
            "residual_sha256": policy["residual_sha256"],
        }
        rows.append({
            "unit": unit.name,
            "event": event,
            "variant": locked["variant"],
            "rows": len(candidate["entity_predictions"]),
            "changed_interval_rows": changed,
            "history": history,
            "policy": policy,
            "validation_errors": errors,
            "outside_intervals_identical": without_intervals(candidate) == without_intervals(locked_answer),
            "answer_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "production": production_score,
            "direct": direct_score,
            "candidate": candidate_score,
            "candidate_minus_direct": candidate_score[key] - direct_score[key],
            "candidate_minus_production": candidate_score[key] - production_score[key],
        })

    pair_invariance = {
        event: {
            "history_equal": variants.get("explicit", {}).get("history_sha256") == variants.get("transformed", {}).get("history_sha256"),
            "residual_equal": variants.get("explicit", {}).get("residual_sha256") == variants.get("transformed", {}).get("residual_sha256"),
            "variants": variants,
        }
        for event, variants in sorted(histories.items())
    }
    key = "composite_before_claim_penalty"
    direct_mean = statistics.fmean(row["direct"][key] for row in rows)
    candidate_mean = statistics.fmean(row["candidate"][key] for row in rows)
    production_mean = statistics.fmean(row["production"][key] for row in rows)
    transformed = [row for row in rows if row["variant"] == "transformed"]
    transformed_candidate_mean = statistics.fmean(row["candidate"][key] for row in transformed)
    transformed_production_mean = statistics.fmean(row["production"][key] for row in transformed)
    gates = {
        "all_8_candidate_answers_valid": len(rows) == 8 and all(not row["validation_errors"] for row in rows),
        "point_claims_roster_identical": all(row["outside_intervals_identical"] for row in rows),
        "schema_pair_history_and_residual_hash_equal": all(
            value["history_equal"] and value["residual_equal"] for value in pair_invariance.values()
        ),
        "candidate_mean_beats_direct_by_0_02": candidate_mean - direct_mean >= 0.02,
        "candidate_mean_beats_production_by_0_10": candidate_mean - production_mean >= 0.10,
        "candidate_transformed_mean_beats_production_by_0_15": transformed_candidate_mean - transformed_production_mean >= 0.15,
        "candidate_noninferior_to_direct_on_6_of_8": sum(
            row["candidate_minus_direct"] >= -1e-12 for row in rows
        ) >= 6,
        "candidate_worst_production_delta_at_least_minus_0_10": min(
            row["candidate_minus_production"] for row in rows
        ) >= -0.10,
    }
    return {
        "schema_version": 1,
        "experiment": "direct_point_residual_interval_screen_v1",
        "scope": "evaluation_only_locked_direct_outputs_no_model_calls_no_production_change",
        "hypothesis": (
            "Target-kind pre-cutoff rolling residual intervals with a House-versus-prior guard improve "
            "locked direct forecasts and remove severe worst-unit degradation."
        ),
        "reference": {
            "repository": "https://github.com/wangzgui/agenthon-t4-baseline-2026",
            "active_version": "s1.6",
            "mechanism": "out-of-origin residual interval ownership with House correction guard",
        },
        "model_api_calls": 0,
        "locked_report": str(LOCKED_REPORT.relative_to(ROOT)),
        "policy": {
            "level_or_metric_baseline": "one-period persistence",
            "change_baseline": "zero",
            "minimum_residual_observations": MIN_RESIDUALS,
            "minimum_origins": MIN_ORIGINS,
            "absolute_residual_quantile": RESIDUAL_QUANTILE,
            "half_width": "absolute_residual_q90 + abs(locked_house_point - current_statistical_prior)",
            "insufficient_history": "preserve locked direct interval",
        },
        "production_mean_composite": production_mean,
        "direct_mean_composite": direct_mean,
        "candidate_mean_composite": candidate_mean,
        "candidate_minus_direct_mean": candidate_mean - direct_mean,
        "candidate_minus_production_mean": candidate_mean - production_mean,
        "candidate_transformed_minus_production_mean": transformed_candidate_mean - transformed_production_mean,
        "candidate_noninferior_units": sum(row["candidate_minus_direct"] >= -1e-12 for row in rows),
        "candidate_worst_production_delta": min(row["candidate_minus_production"] for row in rows),
        "pair_invariance": pair_invariance,
        "gates": gates,
        "decision": "advance_to_independent_confirmation" if all(gates.values()) else "reject_no_production_change",
        "results": rows,
        "limitations": [
            "This is a development screen over previously inspected direct outputs.",
            "Residuals belong to a target-kind statistical baseline, not to historical House forecasts.",
            "Capex has no complete pre-cutoff target-history table and therefore retains its locked direct interval.",
        ],
    }


def main() -> None:
    report = run_screen()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "decision": report["decision"],
        "candidate_minus_direct_mean": report["candidate_minus_direct_mean"],
        "candidate_minus_production_mean": report["candidate_minus_production_mean"],
        "candidate_transformed_minus_production_mean": report["candidate_transformed_minus_production_mean"],
        "candidate_noninferior_units": report["candidate_noninferior_units"],
        "candidate_worst_production_delta": report["candidate_worst_production_delta"],
        "gates": report["gates"],
        "report": str(REPORT),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
