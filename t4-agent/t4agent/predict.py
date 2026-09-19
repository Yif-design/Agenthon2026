from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .calc import numeric_facts
from .calculators import extract_parameters as extract_calculator_parameters
from .evidence import (
    EvidenceFact,
    RejectedFact,
    fact_from_quote,
    validate_model_output,
    validated_context_fact,
)
from .family_specs import FamilySpec, family_spec, project_entity
from .llm import LLM
from .minimal_models import solve_minimal
from .retrieve import BM25, Chunk, IndexedCorpus, allowed_document_ids, query_for, scoped_corpus
from .taskio import Task


@dataclass
class RowResult:
    prediction: dict[str, Any]
    raw_model: dict[str, Any] | None
    retrieved: list[Chunk]
    fallback_reason: str | None = None
    method: str = ""
    allowed_doc_ids: tuple[str, ...] = ()
    facts: tuple[EvidenceFact, ...] = ()
    used_fact_ids: tuple[str, ...] = ()
    rejected_facts: tuple[RejectedFact, ...] = ()
    derivation: dict[str, Any] | None = None
    calculator_inputs: dict[str, Any] | None = None
    model_prompt: str | None = None


SYSTEM = """You extract a few coarse evidence signals and explicitly reported numbers for a deterministic financial prediction workflow.
Use only the provided entity fields and evidence excerpts. Never invent missing numbers or facts.
Return one JSON object and no prose. Every non-neutral signal and every reported number must include one verbatim quote from the excerpts.
Use level -2, -1, 0, 1, or 2. Use 0 when evidence is missing, ambiguous, historical-only, or not comparable."""


def predict_rows(task: Task, index: BM25, corpus: IndexedCorpus, llm: LLM, top_k: int) -> list[RowResult]:
    results: list[RowResult] = []
    spec = family_spec(task.family, str(task.target.get("name", "")))
    shared_model_output: dict[str, Any] | None = None
    shared_model_prompt: str | None = None
    for i, entity in enumerate(task.entities):
        allowed = allowed_document_ids(task, entity, corpus)
        entity_corpus = scoped_corpus(corpus, allowed)
        scores = index.search(query_for(task, entity), top_k=top_k, allowed_doc_ids=allowed)
        chunks = [s.chunk for s in scores]
        extracted, extracted_evidence = extract_calculator_parameters(project_entity(entity, spec), spec, entity_corpus)
        extracted_facts, extracted_rejected = _facts_from_items(
            extracted_evidence, str(entity.get("entity_id", "")), entity_corpus, allowed, "deterministic_extractor"
        )
        if extracted and not extracted_facts:
            extracted = {}
        needs_model = spec.model_required and (
            bool(spec.signals) or any(parameter.name not in extracted for parameter in spec.numeric_parameters)
        )
        if needs_model and spec.key == "rates" and shared_model_output is not None:
            parsed = shared_model_output
            prompt_text = shared_model_prompt
        else:
            prompt_text = _prompt(task, entity, chunks, spec) if needs_model else None
            parsed = llm.chat_json(SYSTEM, prompt_text, max_tokens=600) if prompt_text is not None else None
            if needs_model and spec.key == "rates":
                shared_model_output = parsed
                shared_model_prompt = prompt_text
        result = _prediction_from_model(
            task,
            entity,
            parsed,
            chunks,
            entity_corpus,
            spec,
            i,
            len(task.entities),
            extracted,
            extracted_facts,
            extracted_rejected,
            allowed,
            prompt_text,
        )
        results.append(result)
    return _normalize_ranking(task, results)


def _prompt(task: Task, entity: dict, chunks: list[Chunk], spec: FamilySpec) -> str:
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
    schema: dict[str, Any] = {
        "context": {
            "doc_id": "provided entity-scoped doc_id",
            "quote": "one verbatim factual passage relevant to this entity and target",
            "claim": "short factual statement supported by the quote",
        },
        "signals": {
            signal.name: {
                "level": "integer -2, -1, 0, 1, or 2",
                "doc_id": "provided doc_id or null when level is 0",
                "quote": "verbatim evidence substring or empty when level is 0",
                "claim": "short fact supported by quote or empty when level is 0",
            }
            for signal in spec.signals
        }
    }
    if spec.numeric_parameters:
        schema["parameters"] = {
            parameter.name: {
                "value": "number copied from evidence, or null",
                "doc_id": "provided doc_id or null",
                "quote": "verbatim table text containing the value, or empty",
                "claim": "identify the period and GAAP diluted EPS value, or empty",
            }
            for parameter in spec.numeric_parameters
        }
    signal_rules = [{"name": signal.name, "meaning": signal.description} for signal in spec.signals]
    parameter_rules = [
        {"name": parameter.name, "meaning": parameter.description} for parameter in spec.numeric_parameters
    ]
    lines = [
        f"TASK_ID: {task.task_id}",
        f"PROMPT: {task.prompt}",
        f"CUTOFF_DATE: {task.cutoff_date}",
        f"TARGET_NAME: {task.target.get('name', '')}",
        f"TARGET_TYPE: {task.target_type}",
        f"FAMILY_MODEL: {spec.key}",
        "SIGNAL_RULES_JSON:",
        json.dumps(signal_rules, ensure_ascii=False),
        "NUMERIC_PARAMETER_RULES_JSON:",
        json.dumps(parameter_rules, ensure_ascii=False),
        "ENTITY_JSON:",
        json.dumps(project_entity(entity, spec), ensure_ascii=False, sort_keys=True),
        "CALCULATED_FACTS_JSON:",
        json.dumps(numeric_facts(project_entity(entity, spec)), ensure_ascii=False, sort_keys=True),
        "EVIDENCE_JSON:",
        json.dumps(evidence, ensure_ascii=False),
        "OUTPUT_SCHEMA_JSON:",
        json.dumps(schema, ensure_ascii=False),
        "Rules: return one entity-specific context passage, every named signal, and every numeric parameter. Level 0 needs no signal citation. Non-zero signals and non-null numeric parameters require a provided doc_id and an exact quote. Numeric parameters must be copied from evidence, never estimated. Do not output a label, forecast, probability, interval, beta, or confidence.",
    ]
    return "\n".join(lines)


def _prediction_from_model(
    task: Task,
    entity: dict,
    parsed: dict[str, Any] | None,
    chunks: list[Chunk],
    corpus: IndexedCorpus,
    spec: FamilySpec,
    row_index: int,
    row_count: int,
    extracted_parameters: dict[str, float] | None = None,
    extracted_facts: list[EvidenceFact] | None = None,
    extracted_rejected: list[RejectedFact] | None = None,
    allowed_doc_ids: set[str] | None = None,
    model_prompt: str | None = None,
) -> RowResult:
    fallback_reason = None
    entity_id = str(entity.get("entity_id", ""))
    allowed_doc_ids = allowed_doc_ids or set(corpus.doc_texts)
    signals, parameters, model_facts, rejected = validate_model_output(
        parsed, spec, entity_id, corpus, allowed_doc_ids
    )
    parameters.update(extracted_parameters or {})
    still_needs_model = bool(spec.signals) or any(value is None for value in parameters.values())
    if parsed is None and spec.model_required and still_needs_model:
        fallback_reason = "model_unavailable_or_bad_json"
    solver_entity = project_entity(entity, spec)
    output = solve_minimal(task, solver_entity, spec, signals, corpus, row_index, row_count, parameters)
    replay = solve_minimal(task, solver_entity, spec, signals, corpus, row_index, row_count, parameters)
    if (replay.point, replay.label, replay.interval, replay.method) != (
        output.point,
        output.label,
        output.interval,
        output.method,
    ):
        raise RuntimeError(f"non-deterministic calculator result for {entity_id}")
    has_model_value = any(signals.values()) or any(value is not None for value in parameters.values())
    if spec.model_required and not has_model_value:
        fallback_reason = fallback_reason or "neutral_or_missing_signals"

    output_facts, output_rejected = _facts_from_items(
        output.evidence, entity_id, corpus, allowed_doc_ids, "deterministic_calculator"
    )
    if output_rejected:
        reasons = ", ".join(item.reason for item in output_rejected)
        raise RuntimeError(f"calculator emitted ungrounded evidence for {entity_id}: {reasons}")
    facts = list(extracted_facts or []) + model_facts + output_facts
    used_fact_ids = tuple(fact.fact_id for fact in facts)
    context_fact, context_rejected = validated_context_fact(parsed, entity_id, corpus, allowed_doc_ids)
    if context_fact is not None:
        facts.append(context_fact)
    elif not facts:
        context_fact = _context_fact_from_chunks(chunks, entity_id, corpus)
        if context_fact is not None:
            facts.append(context_fact)
            fallback_reason = fallback_reason or "scoped_context_only"
    all_rejected = list(extracted_rejected or []) + rejected + output_rejected
    if context_rejected is not None:
        all_rejected.append(context_rejected)
    claims = _claims_from_facts(facts)

    pred: dict[str, Any] = {
        "entity_id": entity_id,
        "point_forecast": float(output.point),
        "interval": output.interval,
        "claims": claims,
    }
    if task.target_type == "classification":
        pred["label"] = _safe_label(output.label, task.labels)
    return RowResult(
        prediction=pred,
        raw_model=parsed if parsed else None,
        retrieved=chunks,
        fallback_reason=fallback_reason,
        method=output.method,
        allowed_doc_ids=tuple(sorted(allowed_doc_ids)),
        facts=tuple(facts),
        used_fact_ids=used_fact_ids,
        rejected_facts=tuple(all_rejected),
        derivation={**output.derivation, "replay_verified": True},
        calculator_inputs={"entity": solver_entity, "signals": signals, "parameters": parameters},
        model_prompt=model_prompt,
    )


def _safe_label(value: object, labels: list[str]) -> str | None:
    if not labels:
        return str(value) if value is not None else None
    if isinstance(value, str) and value in labels:
        return value
    return labels[0]


def _facts_from_items(
    value: object,
    entity_id: str,
    corpus: IndexedCorpus,
    allowed_doc_ids: set[str],
    extractor: str,
) -> tuple[list[EvidenceFact], list[RejectedFact]]:
    if not isinstance(value, list):
        return [], []
    facts: list[EvidenceFact] = []
    rejected: list[RejectedFact] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        doc_id = str(item.get("doc_id") or "")
        quote = str(item.get("quote") or "")
        claim = str(item.get("claim") or "").strip()
        name = str(item.get("name") or f"extracted_{index}")
        if doc_id not in allowed_doc_ids:
            rejected.append(RejectedFact(entity_id, name, "doc_not_in_entity_scope", item))
            continue
        fact = fact_from_quote(
            entity_id=entity_id,
            name=name,
            kind="computed_input",
            value=item.get("value", "computed"),
            doc_id=doc_id,
            quote=quote,
            claim=claim,
            extractor=extractor,
            corpus=corpus,
        )
        if fact is None:
            rejected.append(RejectedFact(entity_id, name, "quote_not_exact_substring", item))
        else:
            facts.append(fact)
    return facts, rejected


def _claims_from_facts(facts: list[EvidenceFact]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for fact in facts:
        key = (fact.doc_id, fact.span_start, fact.span_end)
        if key in seen:
            continue
        seen.add(key)
        out.append(fact.as_claim())
    return out[:3]


def _context_fact_from_chunks(
    chunks: list[Chunk], entity_id: str, corpus: IndexedCorpus
) -> EvidenceFact | None:
    if not chunks:
        return None
    chunk = chunks[0]
    quote = chunk.text.strip()
    if len(quote) > 500:
        boundary = max(quote.rfind(". ", 0, 500), quote.rfind("\n", 0, 500))
        quote = quote[: boundary + 1 if boundary > 80 else 500].strip()
    return fact_from_quote(
        entity_id=entity_id,
        name="scoped_context",
        kind="context",
        value="context",
        doc_id=chunk.doc_id,
        quote=quote,
        claim=quote,
        extractor="deterministic_context",
        corpus=corpus,
    )


def _normalize_ranking(task: Task, results: list[RowResult]) -> list[RowResult]:
    if task.target_type != "ranking":
        return results
    ranked = sorted(results, key=lambda r: float(r.prediction.get("point_forecast", 0.0)), reverse=True)
    for rank, result in enumerate(ranked, 1):
        result.prediction["rank"] = rank
    return results
