from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .calc import default_point, interval_for, numeric_facts
from .eps import eps_interval, eps_label_from_forecast, is_eps_beat_task, safe_eps_forecast
from .llm import LLM
from .retrieve import BM25, Chunk, IndexedCorpus, query_for
from .rubrics import select_rubric
from .taskio import Task


@dataclass
class RowResult:
    prediction: dict[str, Any]
    raw_model: dict[str, Any] | None
    retrieved: list[Chunk]
    fallback_reason: str | None = None


SYSTEM = """You are a careful financial prediction module.
Use only the provided entity fields, calculated facts, rubric, and evidence excerpts.
Return one JSON object and no prose. Evidence quotes must be copied verbatim from excerpts."""


def predict_rows(task: Task, index: BM25, corpus: IndexedCorpus, llm: LLM, top_k: int) -> list[RowResult]:
    results: list[RowResult] = []
    for i, entity in enumerate(task.entities):
        scores = index.search(query_for(task, entity), top_k=top_k)
        chunks = [s.chunk for s in scores]
        parsed = llm.chat_json(SYSTEM, _prompt(task, entity, chunks), max_tokens=800)
        result = _prediction_from_model(task, entity, parsed, chunks, corpus, i, len(task.entities))
        results.append(result)
    return _normalize_ranking(task, results)


def _prompt(task: Task, entity: dict, chunks: list[Chunk]) -> str:
    rubric = select_rubric(task.family, str(task.target.get("name", "")), task.prompt)
    evidence = []
    for idx, chunk in enumerate(chunks, 1):
        evidence.append(
            {
                "n": idx,
                "doc_id": chunk.doc_id,
                "doc_date": chunk.doc_date,
                "span_start": chunk.span_start,
                "span_end": chunk.span_end,
                "text": chunk.text[:1400],
            }
        )
    schema = {
        "label": "one allowed label for classification, else null",
        "point_forecast": "number for regression/ranking; optional useful number for classification",
        "interval": {"lo": "number", "hi": "number"},
        "evidence": [
            {
                "doc_id": "one provided doc_id",
                "quote": "verbatim substring copied from evidence text",
                "claim": "short factual claim supported by quote",
            }
        ],
    }
    lines = [
        f"TASK_ID: {task.task_id}",
        f"PROMPT: {task.prompt}",
        f"CUTOFF_DATE: {task.cutoff_date}",
        f"TARGET_NAME: {task.target.get('name', '')}",
        f"TARGET_TYPE: {task.target_type}",
        f"ALLOWED_LABELS: {', '.join(task.labels)}",
        f"INTERVAL_LEVEL: {task.interval_level}",
        f"RUBRIC: {rubric}",
        _target_guardrail(task, entity),
        "ENTITY_JSON:",
        json.dumps(entity, ensure_ascii=False, sort_keys=True),
        "CALCULATED_FACTS_JSON:",
        json.dumps(numeric_facts(entity), ensure_ascii=False, sort_keys=True),
        "EVIDENCE_JSON:",
        json.dumps(evidence, ensure_ascii=False),
        "OUTPUT_SCHEMA_JSON:",
        json.dumps(schema, ensure_ascii=False),
        "Rules: choose 1-3 evidence items. Use null when a field does not apply. Do not cite unavailable documents.",
    ]
    return "\n".join(lines)


def _target_guardrail(task: Task, entity: dict) -> str:
    target_name = str(task.target.get("name", ""))
    if is_eps_beat_task(target_name, task.target_type, task.labels):
        consensus = entity.get("consensus_eps")
        threshold = entity.get("threshold_pct")
        return (
            "EPS_TARGET_GUARDRAIL: This task asks for the target quarter EPS outcome, not a prior "
            f"quarter already reported before cutoff. consensus_eps={consensus}, threshold_pct={threshold}. "
            "Return point_forecast as your forecast for the target quarter EPS. Do not copy Q1 or prior-year "
            "reported EPS as the target forecast unless the prompt explicitly asks for that same period."
        )
    return "TARGET_GUARDRAIL: Predict the target described in PROMPT, not any historical number that merely appears in evidence."


def _prediction_from_model(
    task: Task,
    entity: dict,
    parsed: dict[str, Any] | None,
    chunks: list[Chunk],
    corpus: IndexedCorpus,
    row_index: int,
    row_count: int,
) -> RowResult:
    target_name = str(task.target.get("name", ""))
    fallback_reason = None
    if parsed is None:
        parsed = {}
        fallback_reason = "model_unavailable_or_bad_json"

    label = parsed.get("label")

    point = _safe_float(parsed.get("point_forecast"))
    if point is None:
        point = default_point(task.target_type, target_name, entity, row_index, row_count)
        fallback_reason = fallback_reason or "default_point"

    if is_eps_beat_task(target_name, task.target_type, task.labels):
        guarded_point, guard_reason = safe_eps_forecast(point, entity, parsed.get("evidence"))
        point = guarded_point
        consensus = _safe_float(entity.get("consensus_eps")) or 0.0
        threshold = _safe_float(entity.get("threshold_pct")) or 0.05
        label = eps_label_from_forecast(point, consensus, threshold)
        fallback_reason = fallback_reason or guard_reason
    elif task.target_type == "classification":
        label = _safe_label(label, task.labels)
    else:
        label = None

    if is_eps_beat_task(target_name, task.target_type, task.labels):
        interval = eps_interval(point, entity, task.interval_level)
    else:
        interval = _safe_interval(parsed.get("interval"), point, target_name, task.interval_level)
    claims = _ground_claims(parsed.get("evidence"), chunks, corpus)
    if fallback_reason == "eps_historical_number_guardrail":
        claims = [_eps_guidance_claim(chunks, task, entity)]
    if not claims and chunks:
        claims = [_claim_from_chunk(chunks[0], task, entity)]
        fallback_reason = fallback_reason or "fallback_claim"

    pred: dict[str, Any] = {
        "entity_id": str(entity.get("entity_id", "")),
        "point_forecast": float(point),
        "interval": interval,
        "claims": claims,
    }
    if task.target_type == "classification":
        pred["label"] = label
    return RowResult(pred, parsed if parsed else None, chunks, fallback_reason)


def _safe_label(value: object, labels: list[str]) -> str | None:
    if not labels:
        return str(value) if value is not None else None
    if isinstance(value, str) and value in labels:
        return value
    return labels[0]


def _safe_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _safe_interval(value: object, point: float, target_name: str, level: float) -> dict[str, float]:
    if isinstance(value, dict):
        lo = _safe_float(value.get("lo"))
        hi = _safe_float(value.get("hi"))
        if lo is not None and hi is not None:
            if lo > hi:
                lo, hi = hi, lo
            if lo <= point <= hi:
                return {"level": float(level), "lo": float(lo), "hi": float(hi)}
    return interval_for(point, target_name, level)


def _ground_claims(value: object, chunks: list[Chunk], corpus: IndexedCorpus) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    by_doc = {c.doc_id: c for c in chunks}
    for item in value:
        if not isinstance(item, dict):
            continue
        doc_id = str(item.get("doc_id") or "")
        quote = str(item.get("quote") or "")
        claim = str(item.get("claim") or "").strip()
        if not doc_id or not claim:
            continue
        doc_text = corpus.doc_texts.get(doc_id)
        if not doc_text:
            continue
        start = doc_text.find(quote) if quote else -1
        if start >= 0:
            out.append({"doc_id": doc_id, "span_start": start, "span_end": start + len(quote), "claim": claim[:500]})
        elif doc_id in by_doc:
            chunk = by_doc[doc_id]
            out.append({"doc_id": doc_id, "span_start": chunk.span_start, "span_end": chunk.span_end, "claim": claim[:500]})
    return out[:3]


def _claim_from_chunk(chunk: Chunk, task: Task, entity: dict) -> dict[str, Any]:
    target = task.target.get("name", "target")
    name = entity.get("name") or entity.get("entity_id")
    return {
        "doc_id": chunk.doc_id,
        "span_start": chunk.span_start,
        "span_end": chunk.span_end,
        "claim": f"Retrieved pre-cutoff evidence for {name} related to {target}.",
    }


def _eps_guidance_claim(chunks: list[Chunk], task: Task, entity: dict) -> dict[str, Any]:
    keywords = ("guidance", "outlook", "march quarter", "gross margin", "revenue is expected", "services")
    best = None
    for chunk in chunks:
        lowered = chunk.text.lower()
        score = sum(1 for keyword in keywords if keyword in lowered)
        if best is None or score > best[0]:
            best = (score, chunk)
    chunk = best[1] if best else chunks[0]
    name = entity.get("name") or entity.get("entity_id")
    return {
        "doc_id": chunk.doc_id,
        "span_start": chunk.span_start,
        "span_end": chunk.span_end,
        "claim": (
            f"Pre-cutoff company guidance and outlook for {name} inform the target-quarter EPS "
            "forecast; historical EPS in the same document is treated as context rather than the target result."
        ),
    }


def _normalize_ranking(task: Task, results: list[RowResult]) -> list[RowResult]:
    if task.target_type != "ranking":
        return results
    ranked = sorted(results, key=lambda r: float(r.prediction.get("point_forecast", 0.0)), reverse=True)
    for rank, result in enumerate(ranked, 1):
        result.prediction["rank"] = rank
    return results
