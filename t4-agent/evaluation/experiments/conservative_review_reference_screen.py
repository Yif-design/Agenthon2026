#!/usr/bin/env python3
"""Evaluation-only conservative review of saved checked direct forecasts.

The reviewer sees the target contract, production baseline, saved direct draft
and the same cutoff-safe evidence.  It never sees outcomes, paired variants or
scores.  A valid review can retain the baseline, accept the draft, or provide a
revised point and interval grounded by an exact evidence quote.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
    admit_prediction,
    build_request,
    git_revision,
    pair_gap,
    selected_units,
)
from score_proxy import score  # noqa: E402
from t4agent.retrieve import build_index  # noqa: E402
from t4agent.taskio import load_task  # noqa: E402
from t4agent.validate import validate_answer  # noqa: E402


DIRECT_REPORT = ROOT / "evaluation/reports/direct-forecast-reference-screen-v1.json"
REPORT = ROOT / "evaluation/reports/conservative-review-reference-screen-v1.json"
RUN_ROOT = ROOT / "evaluation/runs/conservative-review-reference-screen-v1"

SYSTEM = """You independently review a financial forecast using only the supplied cutoff-safe evidence.
Return one strict JSON object and no prose. You never know the future outcome.
Check the requested quantity, unit, denominator, horizon and whether the target is a level, change, growth rate or ratio.
Check whether the draft's magnitude and interval are numerically compatible with the cited history and entity fields.
For each entity choose exactly one action: baseline, draft, or revised.
Use revised only when the supplied evidence supports a specific correction; otherwise prefer the safer of baseline and draft.
Every decision must cite one evidence_id and copy one exact evidence_quote substring from that evidence.
Do not use outside knowledge, paired variants, entity-specific rules or claims that the unknown outcome is known."""


def load_direct_answers(path: Path = DIRECT_REPORT) -> dict[str, dict[str, Any]]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("decision") != "reject_no_production_change":
        raise ValueError("expected the locked rejected direct-forecast report")
    answers: dict[str, dict[str, Any]] = {}
    for row in report.get("results", []):
        if not isinstance(row, dict) or not isinstance(row.get("unit"), str):
            continue
        answer = row.get("candidate_answer")
        if isinstance(answer, dict):
            answers[row["unit"]] = answer
    expected = {unit.name for unit in selected_units()}
    if set(answers) != expected:
        raise ValueError("direct report does not contain the complete locked unit set")
    return answers


def build_review_request(
    unit: Path,
    baseline: dict[str, Any],
    draft: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    direct_request, evidence_by_id = build_request(unit, baseline)
    drafts = {str(row["entity_id"]): row for row in draft["entity_predictions"]}
    for row in direct_request["rows"]:
        entity_id = str(row["entity_id"])
        candidate = drafts[entity_id]
        row["direct_draft"] = {
            "point_forecast": candidate.get("point_forecast"),
            "interval": candidate.get("interval"),
        }
    direct_request.pop("task_id", None)
    direct_request["instruction"] = (
        "Return {reviews:[{entity_id,action,evidence_id,evidence_quote,"
        "point_forecast,interval:{lo,hi}}]} exactly once per entity. "
        "action must be baseline, draft, or revised. point_forecast and interval are required only for revised. "
        "The interval is a 90% interval in the target unit and must contain the point."
    )
    return direct_request, evidence_by_id


def review_prediction(
    raw: object,
    baseline_row: dict[str, Any],
    draft_row: dict[str, Any],
    evidence: list[dict[str, Any]],
    interval_level: float,
) -> tuple[dict[str, Any], str]:
    """Apply a grounded review decision or fall back exactly to production."""
    if not isinstance(raw, dict):
        return dict(baseline_row), "malformed_review"
    evidence_id = raw.get("evidence_id")
    quote = raw.get("evidence_quote")
    item = {entry["evidence_id"]: entry for entry in evidence}.get(evidence_id)
    if item is None or not isinstance(quote, str) or not 12 <= len(quote) <= 380 or quote not in item["text"]:
        return dict(baseline_row), "unverified_review_quote"
    action = raw.get("action")
    if action == "baseline":
        return dict(baseline_row), "selected_baseline"
    if action == "draft":
        return dict(draft_row), "selected_draft"
    if action == "revised":
        revised, reason = admit_prediction(raw, baseline_row, evidence, interval_level)
        return revised, "selected_revised" if reason == "admitted" else f"revised_{reason}"
    return dict(baseline_row), "invalid_action"


def reviewed_answer(
    unit: Path,
    baseline: dict[str, Any],
    draft: dict[str, Any],
    parsed: dict[str, Any] | None,
    evidence_by_id: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, int]]:
    task = load_task(unit / "task.json")
    raw_rows = parsed.get("reviews") if isinstance(parsed, dict) else None
    raw_rows = raw_rows if isinstance(raw_rows, list) else []
    by_id: dict[str, dict[str, Any]] = {}
    duplicate_ids: set[str] = set()
    for row in raw_rows:
        if not isinstance(row, dict) or not isinstance(row.get("entity_id"), str):
            continue
        entity_id = str(row["entity_id"])
        if entity_id in by_id:
            duplicate_ids.add(entity_id)
        else:
            by_id[entity_id] = row
    baseline_by_id = {str(row["entity_id"]): row for row in baseline["entity_predictions"]}
    draft_by_id = {str(row["entity_id"]): row for row in draft["entity_predictions"]}
    counts: dict[str, int] = {}
    predictions = []
    for entity in task.entities:
        entity_id = str(entity["entity_id"])
        raw = None if entity_id in duplicate_ids else by_id.get(entity_id)
        prediction, reason = review_prediction(
            raw,
            baseline_by_id[entity_id],
            draft_by_id[entity_id],
            evidence_by_id.get(entity_id, []),
            task.interval_level,
        )
        counts[reason] = counts.get(reason, 0) + 1
        predictions.append(prediction)
    answer = {
        "task_id": task.task_id,
        "schema_version": "3",
        "target_type": task.target_type,
        "entity_predictions": predictions,
        "notes": {
            "experiment": "conservative_review_reference_screen_v1",
            "fallback_rows": sum(
                value for key, value in counts.items()
                if key not in {"selected_draft", "selected_revised"}
            ),
        },
    }
    return answer, counts


def run_screen(client: GeminiClient) -> dict[str, Any]:
    direct_answers = load_direct_answers()
    results = []
    for unit in selected_units():
        baseline_path = PROXY / "baselines/control-v1" / unit.name / "answer.json"
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        draft = direct_answers[unit.name]
        request, evidence_by_id = build_review_request(unit, baseline, draft)
        parsed = client.chat_json(SYSTEM, json.dumps(request, ensure_ascii=False, separators=(",", ":")), 4000)
        answer, admission = reviewed_answer(unit, baseline, draft, parsed, evidence_by_id)
        task = load_task(unit / "task.json")
        corpus = build_index(unit / "corpus", task.cutoff_date)
        validation_errors = validate_answer(answer, task, corpus)
        destination = RUN_ROOT / unit.name / "answer.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(answer, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        baseline_score = score(unit, baseline_path)
        candidate_score = score(unit, destination)
        results.append({
            "unit": unit.name,
            "variant": unit.name.rsplit("-", 1)[-1],
            "rows": len(task.entities),
            "admission": admission,
            "review_output": parsed,
            "validation_errors": validation_errors,
            "baseline_answer_sha256": hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
            "candidate_answer_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "candidate_answer": answer,
            "baseline": baseline_score,
            "candidate": candidate_score,
            "composite_delta": (
                candidate_score["composite_before_claim_penalty"]
                - baseline_score["composite_before_claim_penalty"]
            ),
        })
    baseline_mean = statistics.fmean(row["baseline"]["composite_before_claim_penalty"] for row in results)
    candidate_mean = statistics.fmean(row["candidate"]["composite_before_claim_penalty"] for row in results)
    transformed = [row for row in results if row["variant"] == "transformed"]
    transformed_delta = statistics.fmean(row["composite_delta"] for row in transformed)
    baseline_gap = pair_gap(
        [{"unit": row["unit"], "score": row["baseline"]["composite_before_claim_penalty"]} for row in results],
        "score",
    )
    candidate_gap = pair_gap(
        [{"unit": row["unit"], "score": row["candidate"]["composite_before_claim_penalty"]} for row in results],
        "score",
    )
    gates = {
        "mean_composite_improves_at_least_0_10": candidate_mean - baseline_mean >= 0.10,
        "transformed_mean_improves_at_least_0_15": transformed_delta >= 0.15,
        "no_unit_worse_by_more_than_0_10": min(row["composite_delta"] for row in results) >= -0.10,
        "all_answers_locally_valid": all(not row["validation_errors"] for row in results),
        "schema_gap_reduced_at_least_25pct": candidate_gap <= 0.75 * baseline_gap,
    }
    return {
        "schema_version": 1,
        "experiment": "conservative_review_reference_screen_v1",
        "scope": "evaluation_only_development_screen_no_production_change",
        "baseline_git_commit": git_revision(),
        "control": "proxy-benchmark/baselines/control-v1",
        "direct_candidate_report": str(DIRECT_REPORT.relative_to(ROOT)),
        "hypothesis": (
            "An outcome-blind conservative review of the production baseline and checked direct draft "
            "prevents severe regression while retaining most schema-robustness gains."
        ),
        "reference": {
            "repository": "https://github.com/wangzgui/agenthon-t4-baseline-2026",
            "active_version": "s1.6",
            "reported_score": 0.4793,
            "mechanism": "review the first draft for quantity, unit, period and omitted-driver errors, then admit only grounded review rows",
        },
        "provider": "Google Gemini Developer API",
        "model": client.model,
        "temperature": 0,
        "thinking": "disabled",
        "usage": asdict(client.usage),
        "units": len(results),
        "economic_events": len(results) // 2,
        "baseline_mean_composite": baseline_mean,
        "candidate_mean_composite": candidate_mean,
        "mean_composite_delta": candidate_mean - baseline_mean,
        "transformed_mean_delta": transformed_delta,
        "worst_unit_delta": min(row["composite_delta"] for row in results),
        "baseline_mean_schema_gap": baseline_gap,
        "candidate_mean_schema_gap": candidate_gap,
        "schema_gap_reduction": baseline_gap - candidate_gap,
        "gates": gates,
        "decision": "advance_to_independent_confirmation" if all(gates.values()) else "reject_no_production_change",
        "results": results,
        "limitations": [
            "The same development events exposed the preceding direct-forecast failure and cannot confirm generalization.",
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
    client = GeminiClient(args.model, key)
    report = run_screen(client)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "decision": report["decision"],
        "usage": report["usage"],
        "mean_composite_delta": report["mean_composite_delta"],
        "transformed_mean_delta": report["transformed_mean_delta"],
        "worst_unit_delta": report["worst_unit_delta"],
        "schema_gap_reduction": report["schema_gap_reduction"],
        "gates": report["gates"],
        "report": str(args.out),
    }, indent=2))


if __name__ == "__main__":
    main()
