#!/usr/bin/env python3
"""Development-only direct/hybrid architecture comparison on public Track 4 units.

The public outcomes have influenced development, so this script is a feasibility
screen rather than a held-out acceptance test. It never changes the production
``analyze`` path. Outputs live under the ignored ``evaluation/runs`` tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from t4agent.llm import LLM  # noqa: E402
from t4agent.retrieve import BM25, allowed_document_ids, build_index, query_for  # noqa: E402
from t4agent.taskio import Task, load_task, write_json  # noqa: E402


SYSTEM = """You are a financial forecaster operating before the task cutoff.
Use only the supplied entity fields and evidence excerpts. Predict every entity independently.
Return one JSON object and no prose. Never use knowledge after the cutoff.
For each entity return entity_id, point_forecast, interval {lo, hi}, and one evidence object with
doc_id, an exact verbatim quote, and a short factual claim. For classification also return exactly
one allowed label. Use the target's stated units. Do not return ranks; ranking is derived from the
numeric point forecasts. If evidence is weak, make a conservative forecast rather than omitting a row."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--units",
        type=Path,
        default=Path("/Users/joezhou/PycharmProject/Agenthon2026/track4-analysis-public/units"),
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=PROJECT / "evaluation/runs/20260926-current/nemotron-free-nothink",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT / "evaluation/runs/architecture-ab-v1",
    )
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--max-excerpt-chars", type=int, default=1400)
    parser.add_argument("--max-output-tokens", type=int, default=4000)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--task-ids", help="Comma-separated task ids for a representative screen.")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=0,
        help="Entities per direct call; zero means one complete-roster call.",
    )
    parser.add_argument("--prompt-only", action="store_true")
    parser.add_argument(
        "--raw-input",
        type=Path,
        help="Reuse saved raw model JSON by task id; makes no model requests.",
    )
    return parser.parse_args()


def prompt_for(
    task: Task,
    corpus_dir: Path,
    top_k: int,
    max_chars: int,
    entities: list[dict[str, Any]] | None = None,
) -> tuple[str, Any]:
    corpus = build_index(corpus_dir, task.cutoff_date)
    index = BM25(corpus.chunks)
    items = []
    for entity in entities or task.entities:
        allowed = allowed_document_ids(task, entity, corpus)
        chunks = index.search(query_for(task, entity), top_k=top_k, allowed_doc_ids=allowed)
        items.append(
            {
                "entity_id": str(entity.get("entity_id", "")),
                "features": entity,
                "evidence": [
                    {
                        "doc_id": item.chunk.doc_id,
                        "doc_date": item.chunk.doc_date,
                        "text": item.chunk.text[:max_chars],
                    }
                    for item in chunks
                ],
            }
        )
    request = {
        "task_id": task.task_id,
        "cutoff_date": task.cutoff_date,
        "prompt": task.prompt,
        "family_hint": task.family,
        "target": task.target,
        "target_type": task.target_type,
        "interval_level": task.interval_level,
        "allowed_labels": task.labels,
        "items": items,
    }
    schema: dict[str, Any] = {
        "entities": [
            {
                "entity_id": "copy the entity_id",
                "point_forecast": "finite number in target units",
                "interval": {"lo": "finite number", "hi": "finite number"},
                "evidence": {
                    "doc_id": "one provided doc_id",
                    "quote": "exact verbatim substring from that document",
                    "claim": "short fact supported by the quote",
                },
            }
        ]
    }
    if task.target_type == "classification":
        schema["entities"][0]["label"] = "exactly one allowed label"
    text = "\n".join(
        [
            "FORECAST_REQUEST_JSON:",
            json.dumps(request, ensure_ascii=False, sort_keys=True),
            "OUTPUT_SCHEMA_JSON:",
            json.dumps(schema, ensure_ascii=False),
        ]
    )
    return text, corpus


def finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def exact_claim(
    task: Task,
    entity: dict[str, Any],
    raw: dict[str, Any],
    corpus: Any,
) -> dict[str, Any] | None:
    evidence = raw.get("evidence")
    if not isinstance(evidence, dict):
        return None
    doc_id = str(evidence.get("doc_id") or "")
    quote = str(evidence.get("quote") or "")
    allowed = allowed_document_ids(task, entity, corpus)
    text = corpus.doc_texts.get(doc_id, "")
    if doc_id not in allowed or not quote or quote not in text:
        return None
    start = text.index(quote)
    return {
        "doc_id": doc_id,
        "span_start": start,
        "span_end": start + len(quote),
        "claim": str(evidence.get("claim") or quote).strip() or quote,
    }


def validate_rows(
    task: Task,
    parsed: dict[str, Any] | None,
    corpus: Any,
    baseline: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    baseline_by_id = {row["entity_id"]: row for row in baseline["entity_predictions"]}
    raw_rows = parsed.get("entities") if isinstance(parsed, dict) else None
    raw_by_id = {
        str(row.get("entity_id")): row
        for row in raw_rows or []
        if isinstance(row, dict) and isinstance(row.get("entity_id"), str)
    }
    direct: list[dict[str, Any]] = []
    counters = {"valid": 0, "fallback": 0, "invalid_numeric": 0, "invalid_label": 0, "invalid_quote": 0}
    for entity in task.entities:
        entity_id = str(entity["entity_id"])
        raw = raw_by_id.get(entity_id)
        fallback = baseline_by_id[entity_id]
        if raw is None:
            direct.append(fallback)
            counters["fallback"] += 1
            continue
        point = finite_number(raw.get("point_forecast"))
        interval = raw.get("interval")
        lo = finite_number(interval.get("lo")) if isinstance(interval, dict) else None
        hi = finite_number(interval.get("hi")) if isinstance(interval, dict) else None
        if point is None or lo is None or hi is None or lo > point or point > hi:
            direct.append(fallback)
            counters["fallback"] += 1
            counters["invalid_numeric"] += 1
            continue
        label = raw.get("label")
        if task.target_type == "classification" and label not in task.labels:
            direct.append(fallback)
            counters["fallback"] += 1
            counters["invalid_label"] += 1
            continue
        claim = exact_claim(task, entity, raw, corpus)
        if claim is None:
            direct.append(fallback)
            counters["fallback"] += 1
            counters["invalid_quote"] += 1
            continue
        row: dict[str, Any] = {
            "entity_id": entity_id,
            "point_forecast": point,
            "interval": {"level": task.interval_level, "lo": lo, "hi": hi},
            "claims": [claim],
        }
        if task.target_type == "classification":
            row["label"] = label
        direct.append(row)
        counters["valid"] += 1
    normalize_ranks(task, direct)
    return direct, counters


def normalize_ranks(task: Task, rows: list[dict[str, Any]]) -> None:
    if task.target_type != "ranking":
        return
    ordered = sorted(rows, key=lambda row: (-float(row["point_forecast"]), str(row["entity_id"])))
    for rank, row in enumerate(ordered, 1):
        row["rank"] = rank


def hybrid_rows(
    task: Task,
    baseline: dict[str, Any],
    direct: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    baseline_by_id = {row["entity_id"]: row for row in baseline["entity_predictions"]}
    output = []
    for model_row in direct:
        base = baseline_by_id[model_row["entity_id"]]
        point = 0.5 * float(base["point_forecast"]) + 0.5 * float(model_row["point_forecast"])
        bounds = [
            float(base["interval"]["lo"]),
            float(base["interval"]["hi"]),
            float(model_row["interval"]["lo"]),
            float(model_row["interval"]["hi"]),
        ]
        half = max(abs(value - point) for value in bounds)
        claims = []
        seen = set()
        for claim in list(model_row.get("claims") or []) + list(base.get("claims") or []):
            key = (claim.get("doc_id"), claim.get("span_start"), claim.get("span_end"))
            if key not in seen:
                claims.append(claim)
                seen.add(key)
        row: dict[str, Any] = {
            "entity_id": model_row["entity_id"],
            "point_forecast": point,
            "interval": {"level": task.interval_level, "lo": point - half, "hi": point + half},
            "claims": claims[:3],
        }
        if task.target_type == "classification":
            row["label"] = model_row.get("label", base.get("label"))
        output.append(row)
    normalize_ranks(task, output)
    return output


def answer(task: Task, rows: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "schema_version": task.schema_version,
        "target_type": task.target_type,
        "entity_predictions": rows,
        "evidence_trace": f"Development architecture A/B mode={mode}; cutoff-scoped BM25 evidence.",
    }


def usage_delta(before: tuple[int, int, int, float], llm: LLM) -> dict[str, Any]:
    return {
        "calls": llm.usage.calls - before[0],
        "prompt_tokens": llm.usage.prompt_tokens - before[1],
        "completion_tokens": llm.usage.completion_tokens - before[2],
        "cost_usd": llm.usage.total_cost - before[3],
    }


def main() -> None:
    args = parse_args()
    unit_dirs = [path for path in sorted(args.units.iterdir()) if (path / "task.json").exists()]
    if args.task_ids:
        wanted = {value.strip() for value in args.task_ids.split(",") if value.strip()}
        unit_dirs = [path for path in unit_dirs if path.name in wanted]
        missing = wanted - {path.name for path in unit_dirs}
        if missing:
            raise SystemExit(f"unknown task ids: {sorted(missing)}")
    if args.limit is not None:
        unit_dirs = unit_dirs[: args.limit]
    llm = LLM(PROJECT)
    if not args.prompt_only and args.raw_input is None and not llm.enabled:
        raise SystemExit(f"model unavailable: {llm.usage.disabled_reason}")
    report: dict[str, Any] = {
        "experiment": "architecture_ab_v1",
        "role": "development feasibility; not held-out acceptance",
        "model": llm.model if args.raw_input is None else "saved direct outputs",
        "temperature": llm.temperature,
        "seed": llm.seed,
        "thinking": llm.enable_thinking,
        "top_k": args.top_k,
        "max_excerpt_chars": args.max_excerpt_chars,
        "batch_size": args.batch_size or "complete task roster",
        "hybrid_definition": "50/50 point blend; interval envelope around blend; direct label with baseline fallback",
        "tasks": [],
    }
    for unit_dir in unit_dirs:
        task = load_task(unit_dir / "task.json")
        baseline_path = args.baseline / task.task_id / "answer.json"
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        entity_batches = (
            [task.entities]
            if args.batch_size <= 0
            else [task.entities[i : i + args.batch_size] for i in range(0, len(task.entities), args.batch_size)]
        )
        prompts: list[str] = []
        corpus = None
        for entity_batch in entity_batches:
            prompt, corpus = prompt_for(
                task, unit_dir / "corpus", args.top_k, args.max_excerpt_chars, entity_batch
            )
            prompts.append(prompt)
        assert corpus is not None
        prompt_hashes = [hashlib.sha256(prompt.encode()).hexdigest() for prompt in prompts]
        prompt_sha = hashlib.sha256("".join(prompt_hashes).encode()).hexdigest()
        if args.prompt_only:
            report["tasks"].append(
                {
                    "task_id": task.task_id,
                    "batches": len(prompts),
                    "prompt_chars": sum(len(prompt) for prompt in prompts),
                    "prompt_sha256": prompt_sha,
                }
            )
            continue
        before = (
            llm.usage.calls,
            llm.usage.prompt_tokens,
            llm.usage.completion_tokens,
            llm.usage.total_cost,
        )
        started = time.monotonic()
        if args.raw_input is not None:
            parsed_path = args.raw_input / task.task_id / "model.json"
            parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
        else:
            combined_rows = []
            for prompt in prompts:
                batch_result = llm.chat_json(SYSTEM, prompt, max_tokens=args.max_output_tokens)
                if isinstance(batch_result, dict) and isinstance(batch_result.get("entities"), list):
                    combined_rows.extend(batch_result["entities"])
            parsed = {"entities": combined_rows} if combined_rows else None
        elapsed = time.monotonic() - started
        direct, validity = validate_rows(task, parsed, corpus, baseline)
        hybrid = hybrid_rows(task, baseline, direct)
        write_json(args.out / "direct" / task.task_id / "answer.json", answer(task, direct, "direct"))
        write_json(args.out / "hybrid" / task.task_id / "answer.json", answer(task, hybrid, "hybrid"))
        report["tasks"].append(
            {
                "task_id": task.task_id,
                "target_type": task.target_type,
                "entities": len(task.entities),
                "batches": len(prompts),
                "prompt_chars": sum(len(prompt) for prompt in prompts),
                "prompt_sha256": prompt_sha,
                "latency_s": elapsed,
                "validity": validity,
                "usage": usage_delta(before, llm),
                "parseable": parsed is not None,
            }
        )
        write_json(args.out / "raw" / task.task_id / "model.json", parsed or {})
    tasks = report["tasks"]
    if not args.prompt_only:
        report["summary"] = {
            "tasks": len(tasks),
            "entities": sum(item["entities"] for item in tasks),
            "valid_direct_rows": sum(item["validity"]["valid"] for item in tasks),
            "fallback_rows": sum(item["validity"]["fallback"] for item in tasks),
            "calls": sum(item["usage"]["calls"] for item in tasks),
            "prompt_tokens": sum(item["usage"]["prompt_tokens"] for item in tasks),
            "completion_tokens": sum(item["usage"]["completion_tokens"] for item in tasks),
            "cost_usd": sum(item["usage"]["cost_usd"] for item in tasks),
            "mean_latency_s": statistics.fmean(item["latency_s"] for item in tasks),
            "errors": llm.usage.errors,
        }
    write_json(args.out / "run.json", report)
    print(json.dumps(report.get("summary", {"tasks": len(tasks)}), indent=2))


if __name__ == "__main__":
    main()
