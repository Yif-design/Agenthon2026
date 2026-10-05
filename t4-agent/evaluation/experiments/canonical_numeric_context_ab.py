#!/usr/bin/env python3
"""Controlled remote A/B for raw versus canonical numeric context.

Both arms share target, evidence, deterministic prior, prompt, model and
admission.  Only each row's numeric_context changes.  The candidate uses the
accepted evaluation-only canonicalizer; no paired schema or outcome is visible
to either model request.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import statistics
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PROXY = ROOT / "proxy-benchmark"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(PROXY) not in sys.path:
    sys.path.insert(0, str(PROXY))

from evaluation.experiments.direct_forecast_reference_screen import (  # noqa: E402
    GeminiClient,
    SYSTEM,
    build_request,
    candidate_answer,
    git_revision,
)
from evaluation.experiments.quantity_unit_canonicalization_audit import (  # noqa: E402
    canonicalize_entity,
    canonicalize_unit,
    semantic_role,
    source_unit,
)
from score_proxy import score  # noqa: E402
from t4agent.retrieve import build_index  # noqa: E402
from t4agent.taskio import load_task  # noqa: E402
from t4agent.validate import validate_answer  # noqa: E402


UNIT_NAMES = (
    "proxy-04-capex-intensity-20230331-transformed",
    "proxy-15-auction-indirect-bidder-share-20230802-transformed",
    "proxy-16-crude-inventory-change-20260923-transformed",
    "proxy-17-natural-gas-storage-change-20260924-transformed",
)
REPORT = ROOT / "evaluation/reports/canonical-numeric-context-ab-v1.json"
RUN_ROOT = ROOT / "evaluation/runs/canonical-numeric-context-ab-v1"
CANONICAL_AUDIT_REPORT = ROOT / "evaluation/reports/quantity-unit-canonicalization-audit-v1.json"
FORBIDDEN_REQUEST_KEYS = {
    "task_id", "reference_answer", "answer", "score", "scores", "composite_delta",
    "known_outcome", "paired_variant", "worst_unit", "failure_marker",
}


def selected_units() -> list[Path]:
    units = [PROXY / "units" / name for name in UNIT_NAMES]
    missing = [path.name for path in units if not (path / "task.json").is_file()]
    if missing:
        raise ValueError(f"missing units: {missing}")
    return units


def raw_numeric_context(fields: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for field in sorted(fields):
        value = fields[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            continue
        unit = source_unit(field) or "unknown"
        rows.append({
            "source_kind": "entity_field",
            "source_field": field,
            "original_value": float(value),
            "original_unit": unit,
            "value": float(value),
            "unit": unit,
            "semantic_role": semantic_role(field),
            "status": "raw_unconverted",
            "provenance": {"source_field": field},
        })
    return rows


def canonical_numeric_context(row: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for fact in row["quantities"] + row["corpus_quantities"]:
        provenance = {"source_field": fact["source_field"]}
        if fact["source_kind"] == "corpus_table":
            provenance.update({
                "doc_id": fact["doc_id"],
                "span_start": fact["span_start"],
                "span_end": fact["span_end"],
                "period": fact["period"],
            })
        result.append({
            "source_kind": fact["source_kind"],
            "source_field": fact["source_field"],
            "original_value": fact["original_value"],
            "original_unit": fact["original_unit"],
            "value": fact["canonical_value"],
            "unit": fact["canonical_unit"],
            "semantic_role": fact["semantic_role"],
            "status": "canonical_once",
            "provenance": provenance,
        })
    return sorted(
        result,
        key=lambda item: (
            item["source_kind"], item["source_field"],
            str(item["provenance"].get("doc_id", "")), str(item["provenance"].get("period", "")),
        ),
    )


def arm_request(
    unit: Path,
    baseline: dict[str, Any],
    arm: str,
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    request, evidence_by_id = build_request(unit, baseline)
    request.pop("task_id", None)
    canonical = canonicalize_unit(unit)
    canonical_by_id = {row["entity_id"]: row for row in canonical["rows"]}
    for row in request["rows"]:
        fields = row.pop("fields")
        entity_id = str(row["entity_id"])
        row["identity_fields"] = {
            key: value for key, value in fields.items()
            if isinstance(value, bool) or not isinstance(value, (int, float))
        }
        if arm == "control":
            row["numeric_context"] = raw_numeric_context(fields)
            row["abstentions"] = []
        elif arm == "candidate":
            item = canonical_by_id[entity_id]
            row["numeric_context"] = canonical_numeric_context(item)
            row["abstentions"] = [
                {"source_field": value["source_field"], "reason": value["reason"]}
                for value in item["abstentions"]
            ]
        else:
            raise ValueError(f"unknown arm {arm}")
    return request, evidence_by_id


def without_numeric_context(request: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(request)
    for row in result["rows"]:
        row["numeric_context"] = "<ARM>"
        row["abstentions"] = "<ARM>"
    return result


def forbidden_request_paths(value: object, path: str = "$") -> list[str]:
    """Locate keys that would leak experiment identity, outcomes, or scores."""
    result: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_REQUEST_KEYS:
                result.append(f"{path}.{key}")
            result.extend(forbidden_request_paths(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(forbidden_request_paths(child, f"{path}[{index}]"))
    return result


def accepted_canonical_unit(unit: Path) -> dict[str, Any]:
    report = json.loads(CANONICAL_AUDIT_REPORT.read_text(encoding="utf-8"))
    matches = [
        row["canonical_units"]["transformed"]
        for row in report["results"]
        if row["transformed_unit"] == unit.name
    ]
    if len(matches) != 1:
        raise ValueError(f"accepted canonical audit has {len(matches)} matches for {unit.name}")
    return matches[0]


def request_pair_audit(unit: Path, baseline: dict[str, Any]) -> dict[str, Any]:
    control, control_evidence = arm_request(unit, baseline, "control")
    candidate, candidate_evidence = arm_request(unit, baseline, "candidate")
    task = load_task(unit / "task.json")
    serialized = json.dumps(
        {"control": control, "candidate": candidate}, ensure_ascii=False, sort_keys=True,
    )
    forbidden_identifiers = [
        value for value in (unit.name, task.task_id)
        if value and value in serialized
    ]
    return {
        "unit": unit.name,
        "equal_outside_numeric_context": without_numeric_context(control) == without_numeric_context(candidate),
        "evidence_equal": control_evidence == candidate_evidence,
        "control_rows": len(control["rows"]),
        "candidate_rows": len(candidate["rows"]),
        "control_numeric_facts": sum(len(row["numeric_context"]) for row in control["rows"]),
        "candidate_numeric_facts": sum(len(row["numeric_context"]) for row in candidate["rows"]),
        "candidate_abstentions": sum(len(row["abstentions"]) for row in candidate["rows"]),
        "control_chars": len(json.dumps(control, ensure_ascii=False, separators=(",", ":"))),
        "candidate_chars": len(json.dumps(candidate, ensure_ascii=False, separators=(",", ":"))),
        "accepted_canonical_report_exact": canonicalize_unit(unit) == accepted_canonical_unit(unit),
        "forbidden_request_paths": forbidden_request_paths(control) + forbidden_request_paths(candidate),
        "forbidden_identifier_leaks": forbidden_identifiers,
        "control_request_sha256": hashlib.sha256(
            json.dumps(control, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "candidate_request_sha256": hashlib.sha256(
            json.dumps(candidate, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
    }


def usage_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        "calls": after["calls"] - before["calls"],
        "prompt_tokens": after["prompt_tokens"] - before["prompt_tokens"],
        "completion_tokens": after["completion_tokens"] - before["completion_tokens"],
        "new_errors": after["errors"][len(before["errors"]):],
    }


def run_screen(client: GeminiClient) -> dict[str, Any]:
    audits = []
    prepared: dict[str, dict[str, Any]] = {}
    for unit in selected_units():
        baseline_path = PROXY / "baselines/control-v1" / unit.name / "answer.json"
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        audit = request_pair_audit(unit, baseline)
        audits.append(audit)
        if not all((
            audit["equal_outside_numeric_context"],
            audit["evidence_equal"],
            audit["accepted_canonical_report_exact"],
            not audit["forbidden_request_paths"],
            not audit["forbidden_identifier_leaks"],
        )):
            raise ValueError(f"request-pair audit failed for {unit.name}")
        prepared[unit.name] = {"unit": unit, "baseline_path": baseline_path, "baseline": baseline}

    calls: dict[tuple[str, str], dict[str, Any]] = {}
    for index, unit in enumerate(selected_units()):
        order = ("control", "candidate") if index % 2 == 0 else ("candidate", "control")
        for arm in order:
            baseline = prepared[unit.name]["baseline"]
            request, evidence_by_id = arm_request(unit, baseline, arm)
            before = asdict(client.usage)
            parsed = client.chat_json(
                SYSTEM,
                json.dumps(request, ensure_ascii=False, separators=(",", ":")),
                4000,
            )
            after = asdict(client.usage)
            answer, admission = candidate_answer(unit, baseline, parsed, evidence_by_id)
            task = load_task(unit / "task.json")
            corpus = build_index(unit / "corpus", task.cutoff_date)
            validation_errors = validate_answer(answer, task, corpus)
            destination = RUN_ROOT / arm / unit.name / "answer.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(answer, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            calls[(unit.name, arm)] = {
                "arm": arm,
                "call_order": len(calls) + 1,
                "usage": usage_delta(before, after),
                "model_output": parsed,
                "admission": admission,
                "validation_errors": validation_errors,
                "answer_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "answer": answer,
                "score": score(unit, destination),
            }

    results = []
    for unit in selected_units():
        baseline_path = prepared[unit.name]["baseline_path"]
        baseline_score = score(unit, baseline_path)
        control = calls[(unit.name, "control")]
        candidate = calls[(unit.name, "candidate")]
        key = "composite_before_claim_penalty"
        results.append({
            "unit": unit.name,
            "rows": len(prepared[unit.name]["baseline"]["entity_predictions"]),
            "baseline": baseline_score,
            "control": control,
            "candidate": candidate,
            "candidate_minus_control": candidate["score"][key] - control["score"][key],
            "candidate_minus_production": candidate["score"][key] - baseline_score[key],
        })

    key = "composite_before_claim_penalty"
    control_mean = statistics.fmean(row["control"]["score"][key] for row in results)
    candidate_mean = statistics.fmean(row["candidate"]["score"][key] for row in results)
    production_mean = statistics.fmean(row["baseline"][key] for row in results)
    api_errors = list(client.usage.errors)
    gates = {
        "all_8_api_calls_succeeded": client.usage.calls == 8 and not api_errors,
        "all_8_answers_locally_valid": all(
            not row[arm]["validation_errors"] for row in results for arm in ("control", "candidate")
        ),
        "candidate_mean_beats_control_by_0_05": candidate_mean - control_mean >= 0.05,
        "candidate_mean_beats_production_by_0_15": candidate_mean - production_mean >= 0.15,
        "candidate_noninferior_to_control_on_3_of_4": sum(
            row["candidate_minus_control"] >= -1e-12 for row in results
        ) >= 3,
        "candidate_worst_production_delta_at_least_minus_0_10": min(
            row["candidate_minus_production"] for row in results
        ) >= -0.10,
    }
    return {
        "schema_version": 1,
        "experiment": "canonical_numeric_context_ab_v1",
        "scope": "evaluation_only_transformed_development_screen_no_production_change",
        "baseline_git_commit": git_revision(),
        "hypothesis": (
            "Replacing raw numeric fields with once-converted canonical quantities and explicit abstentions "
            "improves small-model forecasts on transformed schemas while preventing severe scale regressions."
        ),
        "reference": {
            "repository": "https://github.com/wangzgui/agenthon-t4-baseline-2026",
            "active_version": "s1.6",
            "mechanisms": ["canonical quantity contract", "checked numerical facts"],
        },
        "provider": "Google Gemini Developer API",
        "model": client.model,
        "temperature": 0,
        "seed": 1234,
        "thinking": "disabled",
        "max_output_tokens_per_call": 4000,
        "usage": asdict(client.usage),
        "request_pair_audits": audits,
        "request_pair_audit_passed": True,
        "production_mean_composite": production_mean,
        "control_mean_composite": control_mean,
        "candidate_mean_composite": candidate_mean,
        "candidate_minus_control_mean": candidate_mean - control_mean,
        "candidate_minus_production_mean": candidate_mean - production_mean,
        "candidate_worst_production_delta": min(row["candidate_minus_production"] for row in results),
        "candidate_noninferior_units": sum(row["candidate_minus_control"] >= -1e-12 for row in results),
        "gates": gates,
        "decision": "advance_to_independent_confirmation" if all(gates.values()) else "reject_no_production_change",
        "results": results,
        "limitations": [
            "These four transformed development units were used to design the representation mechanism.",
            "Gemini Flash-Lite is an architecture proxy, not the official House model.",
            "The local composite excludes the official contradiction penalty and Final reasoning bonus.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", type=Path, default=ROOT / ".secrets/gemini_api_key.txt")
    parser.add_argument("--model", default="gemini-2.5-flash-lite")
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()
    key = args.key_file.read_text(encoding="utf-8").strip()
    if not key:
        raise SystemExit("Gemini key file is empty")
    report = run_screen(GeminiClient(args.model, key))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "decision": report["decision"],
        "usage": report["usage"],
        "candidate_minus_control_mean": report["candidate_minus_control_mean"],
        "candidate_minus_production_mean": report["candidate_minus_production_mean"],
        "candidate_worst_production_delta": report["candidate_worst_production_delta"],
        "candidate_noninferior_units": report["candidate_noninferior_units"],
        "gates": report["gates"],
        "report": str(args.out),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
