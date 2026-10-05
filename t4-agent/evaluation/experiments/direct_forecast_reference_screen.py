#!/usr/bin/env python3
"""Evaluation-only direct-forecast screen inspired by scored T4 references.

The candidate gives one remote small model a complete quantity contract, the
current deterministic forecast as a prior, and entity-scoped cutoff-safe
evidence.  A model row is admitted only when its cited quote is an exact
substring of the selected evidence.  Production code is never imported into a
different execution path by this experiment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import subprocess
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

from evaluation.experiments.evidence_id_remote_ab import GeminiClient  # noqa: E402
from score_proxy import score  # noqa: E402
from t4agent.retrieve import BM25, allowed_document_ids, build_index, query_for  # noqa: E402
from t4agent.taskio import load_task  # noqa: E402
from t4agent.validate import validate_answer  # noqa: E402


EVENT_PREFIXES = (
    "proxy-04-capex-intensity-20230331-",
    "proxy-15-auction-indirect-bidder-share-20230802-",
    "proxy-16-crude-inventory-change-20260923-",
    "proxy-17-natural-gas-storage-change-20260924-",
)
REPORT = ROOT / "evaluation/reports/direct-forecast-reference-screen-v1.json"
RUN_ROOT = ROOT / "evaluation/runs/direct-forecast-reference-screen-v1"

SYSTEM = """You are a conservative financial forecasting component operating only on the supplied cutoff-safe evidence.
Return one strict JSON object and no prose. Forecast the requested future target, not an observed historical value.
Respect the target quantity, unit, denominator and horizon exactly. Distinguish level, change, growth, ratio and rank.
The deterministic forecast is a prior, not a known outcome. Change it only when the supplied evidence supports a better estimate.
Every prediction must cite one evidence_id and copy one exact evidence_quote substring from that evidence.
Never use outside knowledge or claim that the unknown outcome is already known."""


def git_revision() -> str | None:
    """Return the evaluated repository revision without making the run depend on Git."""
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT.parent,
        check=False,
        capture_output=True,
        text=True,
    )
    revision = completed.stdout.strip()
    return revision if completed.returncode == 0 and revision else None


def _finite(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def selected_units() -> list[Path]:
    units = []
    for prefix in EVENT_PREFIXES:
        matched = sorted(path for path in (PROXY / "units").iterdir() if path.name.startswith(prefix))
        if len(matched) != 2:
            raise ValueError(f"expected explicit/transformed pair for {prefix}, found {len(matched)}")
        units.extend(matched)
    return units


def build_request(unit: Path, baseline: dict[str, Any]) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    task = load_task(unit / "task.json")
    corpus = build_index(unit / "corpus", task.cutoff_date)
    index = BM25(corpus.chunks)
    baseline_by_id = {str(row["entity_id"]): row for row in baseline["entity_predictions"]}
    evidence_by_id: dict[str, list[dict[str, Any]]] = {}
    rows = []
    for entity in task.entities:
        entity_id = str(entity["entity_id"])
        allowed = allowed_document_ids(task, entity, corpus)
        ranked = index.search(
            query_for(task, entity, include_all_scalar_fields=True),
            top_k=6,
            allowed_doc_ids=allowed,
        )
        evidence = [
            {
                "evidence_id": f"E{number}",
                "doc_id": item.chunk.doc_id,
                "doc_date": item.chunk.doc_date,
                "span_start": item.chunk.span_start,
                "span_end": item.chunk.span_end,
                "text": item.chunk.text[:1800],
            }
            for number, item in enumerate(ranked)
        ]
        evidence_by_id[entity_id] = evidence
        prior = baseline_by_id[entity_id]
        rows.append({
            "entity_id": entity_id,
            "fields": entity,
            "deterministic_prior": {
                "point_forecast": prior.get("point_forecast"),
                "interval": prior.get("interval"),
            },
            "evidence": [
                {"evidence_id": item["evidence_id"], "doc_date": item["doc_date"], "text": item["text"]}
                for item in evidence
            ],
        })
    request = {
        "instruction": (
            "Return predictions exactly once per entity as "
            "{predictions:[{entity_id,point_forecast,interval:{lo,hi},evidence_id,evidence_quote}]}. "
            "Use finite numbers. The interval is a 90% interval in the target unit and must contain the point."
        ),
        "task_id": task.task_id,
        "cutoff_date": task.cutoff_date,
        "prompt": task.prompt,
        "target_contract": task.target,
        "target_type": task.target_type,
        "interval_level": task.interval_level,
        "rows": rows,
    }
    return request, evidence_by_id


def admit_prediction(
    raw: object,
    baseline_row: dict[str, Any],
    evidence: list[dict[str, Any]],
    interval_level: float,
) -> tuple[dict[str, Any], str]:
    """Admit a direct forecast only with finite values and an exact scoped quote."""
    if not isinstance(raw, dict):
        return dict(baseline_row), "malformed_prediction"
    point = _finite(raw.get("point_forecast"))
    interval = raw.get("interval")
    lo = _finite(interval.get("lo")) if isinstance(interval, dict) else None
    hi = _finite(interval.get("hi")) if isinstance(interval, dict) else None
    evidence_id = raw.get("evidence_id")
    quote = raw.get("evidence_quote")
    by_id = {item["evidence_id"]: item for item in evidence}
    item = by_id.get(evidence_id) if isinstance(evidence_id, str) else None
    if point is None or lo is None or hi is None or lo > point or point > hi:
        return dict(baseline_row), "invalid_numeric_contract"
    if item is None or not isinstance(quote, str) or not 12 <= len(quote) <= 380 or quote not in item["text"]:
        return dict(baseline_row), "unverified_quote"
    relative = item["text"].index(quote)
    start = int(item["span_start"]) + relative
    prediction = {
        "entity_id": baseline_row["entity_id"],
        "point_forecast": point,
        "interval": {"level": interval_level, "lo": lo, "hi": hi},
        "claims": [{
            "claim": quote,
            "doc_id": item["doc_id"],
            "span_start": start,
            "span_end": start + len(quote),
        }],
    }
    return prediction, "admitted"


def candidate_answer(
    unit: Path,
    baseline: dict[str, Any],
    parsed: dict[str, Any] | None,
    evidence_by_id: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, int]]:
    task = load_task(unit / "task.json")
    raw_rows = parsed.get("predictions") if isinstance(parsed, dict) else None
    raw_rows = raw_rows if isinstance(raw_rows, list) else []
    by_id = {
        str(row.get("entity_id")): row
        for row in raw_rows
        if isinstance(row, dict) and isinstance(row.get("entity_id"), str)
    }
    counts: dict[str, int] = {}
    predictions = []
    for baseline_row in baseline["entity_predictions"]:
        entity_id = str(baseline_row["entity_id"])
        prediction, reason = admit_prediction(
            by_id.get(entity_id), baseline_row, evidence_by_id.get(entity_id, []), task.interval_level
        )
        counts[reason] = counts.get(reason, 0) + 1
        predictions.append(prediction)
    answer = {
        "task_id": task.task_id,
        "schema_version": "3",
        "target_type": task.target_type,
        "entity_predictions": predictions,
        "notes": {
            "experiment": "direct_forecast_reference_screen_v1",
            "fallback_rows": len(predictions) - counts.get("admitted", 0),
        },
    }
    return answer, counts


def pair_gap(results: list[dict[str, Any]], key: str) -> float:
    grouped: dict[str, list[float]] = {}
    for row in results:
        event = row["unit"].rsplit("-", 1)[0]
        grouped.setdefault(event, []).append(float(row[key]))
    gaps = [abs(values[0] - values[1]) for values in grouped.values() if len(values) == 2]
    return statistics.fmean(gaps)


def run_screen(client: GeminiClient) -> dict[str, Any]:
    results = []
    for unit in selected_units():
        baseline_path = PROXY / "baselines/control-v1" / unit.name / "answer.json"
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        request, evidence_by_id = build_request(unit, baseline)
        parsed = client.chat_json(SYSTEM, json.dumps(request, ensure_ascii=False, separators=(",", ":")), 4000)
        answer, admission = candidate_answer(unit, baseline, parsed, evidence_by_id)
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
        "mean_composite_improves_at_least_0_05": candidate_mean - baseline_mean >= 0.05,
        "transformed_mean_improves_at_least_0_05": transformed_delta >= 0.05,
        "no_unit_worse_by_more_than_0_10": min(row["composite_delta"] for row in results) >= -0.10,
        "all_answers_locally_valid": all(not row["validation_errors"] for row in results),
        "schema_gap_reduced_at_least_25pct": candidate_gap <= 0.75 * baseline_gap,
    }
    return {
        "schema_version": 2,
        "experiment": "direct_forecast_reference_screen_v1",
        "scope": "evaluation_only_no_production_change",
        "baseline_git_commit": git_revision(),
        "control": "proxy-benchmark/baselines/control-v1",
        "hypothesis": (
            "A checked direct forecast using the complete target contract, deterministic prior and exact "
            "cutoff-safe evidence improves weak unknown-family regression events and reduces schema dependence."
        ),
        "references": {
            "wang": {
                "repository": "https://github.com/wangzgui/agenthon-t4-baseline-2026",
                "active_version": "s1.6",
                "reported_score": 0.4793,
                "mechanisms": ["quantity contract", "verified facts", "direct forecast", "conservative admission"],
            },
            "optivex": {
                "repository": "https://github.com/dungcao06/optivex-t4-agent",
                "snapshot": "b897309bb591d98cf6aabb3cf04f71770e969af5",
                "leaderboard_score_seen": 0.4118,
                "score_mapping_caveat": "the public repository does not bind this exact HEAD to the displayed score",
                "mechanisms": ["complete target specification", "target-aware retrieval", "compact tables", "direct forecast"],
            },
        },
        "provider": "Google Gemini Developer API",
        "model": client.model,
        "temperature": 0,
        "thinking": "disabled",
        "usage": asdict(client.usage),
        "units": len(results),
        "economic_events": len(EVENT_PREFIXES),
        "baseline_mean_composite": baseline_mean,
        "candidate_mean_composite": candidate_mean,
        "mean_composite_delta": candidate_mean - baseline_mean,
        "transformed_mean_delta": transformed_delta,
        "worst_unit_delta": min(row["composite_delta"] for row in results),
        "baseline_mean_schema_gap": baseline_gap,
        "candidate_mean_schema_gap": candidate_gap,
        "schema_gap_reduction": baseline_gap - candidate_gap,
        "gates": gates,
        "decision": "advance_to_full_regression_screen" if all(gates.values()) else "reject_no_production_change",
        "results": results,
        "limitations": [
            "The proxy outcomes have influenced prior development and are not untouched confirmation.",
            "Gemini Flash-Lite is a quota-conscious architecture proxy, not the official House model.",
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
