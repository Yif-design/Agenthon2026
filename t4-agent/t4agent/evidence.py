from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .family_specs import FamilySpec
from .retrieve import IndexedCorpus


@dataclass(frozen=True)
class EvidenceFact:
    fact_id: str
    entity_id: str
    name: str
    kind: str
    value: Any
    doc_id: str
    span_start: int
    span_end: int
    quote: str
    claim: str
    extractor: str

    def as_claim(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "claim": self.claim[:500],
        }

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RejectedFact:
    entity_id: str
    name: str
    reason: str
    raw: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def locate_exact_quote(corpus: IndexedCorpus, doc_id: str, quote: str) -> tuple[int, int] | None:
    text = corpus.doc_texts.get(doc_id)
    if not text or not quote:
        return None
    start = text.find(quote)
    if start >= 0:
        return start, start + len(quote)
    # Tables and SEC HTML extraction often turn runs of spaces / NBSP into a single space in the
    # model response. Match only that normalization, then map the match back to the original text.
    normalized_text, offsets = _collapse_whitespace_with_offsets(text)
    normalized_quote = " ".join(quote.split())
    normalized_start = normalized_text.find(normalized_quote)
    if normalized_start < 0 or not normalized_quote:
        return None
    normalized_end = normalized_start + len(normalized_quote)
    return offsets[normalized_start], offsets[normalized_end - 1] + 1


def _collapse_whitespace_with_offsets(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    offsets: list[int] = []
    in_space = False
    for index, char in enumerate(text):
        if char.isspace():
            if not in_space:
                chars.append(" ")
                offsets.append(index)
            in_space = True
        else:
            chars.append(char)
            offsets.append(index)
            in_space = False
    return "".join(chars), offsets


def fact_from_quote(
    *,
    entity_id: str,
    name: str,
    kind: str,
    value: float | int | str,
    doc_id: str,
    quote: str,
    claim: str,
    extractor: str,
    corpus: IndexedCorpus,
) -> EvidenceFact | None:
    span = locate_exact_quote(corpus, doc_id, quote)
    if span is None:
        return None
    return EvidenceFact(
        fact_id=f"{entity_id}.{name}.{doc_id}.{span[0]}",
        entity_id=entity_id,
        name=name,
        kind=kind,
        value=value,
        doc_id=doc_id,
        span_start=span[0],
        span_end=span[1],
        quote=quote,
        claim=claim,
        extractor=extractor,
    )


def validate_model_output(
    parsed: dict[str, Any] | None,
    spec: FamilySpec,
    entity_id: str,
    corpus: IndexedCorpus,
    allowed_doc_ids: set[str],
) -> tuple[dict[str, int], dict[str, float | None], list[EvidenceFact], list[RejectedFact]]:
    signals: dict[str, int] = {}
    parameters: dict[str, float | None] = {}
    facts: list[EvidenceFact] = []
    rejected: list[RejectedFact] = []
    raw_signals = parsed.get("signals") if isinstance(parsed, dict) else None
    raw_signals = raw_signals if isinstance(raw_signals, dict) else {}
    for signal_spec in spec.signals:
        raw = raw_signals.get(signal_spec.name)
        item = raw if isinstance(raw, dict) else {}
        level = _signal_level(item.get("level") if item else raw)
        if level == 0:
            signals[signal_spec.name] = 0
            continue
        fact, reason = _validated_item(
            item,
            entity_id=entity_id,
            name=signal_spec.name,
            kind="text_signal",
            value=level,
            corpus=corpus,
            allowed_doc_ids=allowed_doc_ids,
            require_number=False,
        )
        if fact is None:
            signals[signal_spec.name] = 0
            rejected.append(RejectedFact(entity_id, signal_spec.name, reason, item))
        else:
            signals[signal_spec.name] = level
            facts.append(fact)

    raw_parameters = parsed.get("parameters") if isinstance(parsed, dict) else None
    raw_parameters = raw_parameters if isinstance(raw_parameters, dict) else {}
    for parameter_spec in spec.numeric_parameters:
        raw = raw_parameters.get(parameter_spec.name)
        item = raw if isinstance(raw, dict) else {}
        value = _number(item.get("value") if item else raw)
        if value is None:
            parameters[parameter_spec.name] = None
            continue
        fact, reason = _validated_item(
            item,
            entity_id=entity_id,
            name=parameter_spec.name,
            kind="extracted_number",
            value=value,
            corpus=corpus,
            allowed_doc_ids=allowed_doc_ids,
            require_number=True,
        )
        if fact is None:
            parameters[parameter_spec.name] = None
            rejected.append(RejectedFact(entity_id, parameter_spec.name, reason, item))
        else:
            parameters[parameter_spec.name] = value
            facts.append(fact)
    return signals, parameters, facts, rejected


def validated_context_fact(
    parsed: dict[str, Any] | None,
    entity_id: str,
    corpus: IndexedCorpus,
    allowed_doc_ids: set[str],
) -> tuple[EvidenceFact | None, RejectedFact | None]:
    item = parsed.get("context") if isinstance(parsed, dict) else None
    if not isinstance(item, dict):
        return None, None
    fact, reason = _validated_item(
        item,
        entity_id=entity_id,
        name="context",
        kind="context",
        value="context",
        corpus=corpus,
        allowed_doc_ids=allowed_doc_ids,
        require_number=False,
    )
    if fact is None:
        return None, RejectedFact(entity_id, "context", reason, item)
    return fact, None


def _validated_item(
    item: dict[str, Any],
    *,
    entity_id: str,
    name: str,
    kind: str,
    value: float | int | str,
    corpus: IndexedCorpus,
    allowed_doc_ids: set[str],
    require_number: bool,
) -> tuple[EvidenceFact | None, str]:
    doc_id = str(item.get("doc_id") or "")
    quote = str(item.get("quote") or "")
    claim = str(item.get("claim") or item.get("reason") or "").strip()
    if not doc_id or doc_id not in allowed_doc_ids:
        return None, "doc_not_in_entity_scope"
    if not quote:
        return None, "missing_quote"
    if not claim:
        return None, "missing_claim"
    if require_number and not _quote_contains_number(quote, float(value)):
        return None, "numeric_value_not_in_quote"
    fact = fact_from_quote(
        entity_id=entity_id,
        name=name,
        kind=kind,
        value=value,
        doc_id=doc_id,
        quote=quote,
        claim=claim,
        extractor="qwen",
        corpus=corpus,
    )
    return (fact, "") if fact is not None else (None, "quote_not_exact_substring")


def _quote_contains_number(quote: str, value: float) -> bool:
    candidates = {f"{value:g}", f"{value:.2f}", f"{value:,.0f}", f"{value:,.2f}"}
    compact = quote.replace("$", "").replace("%", "")
    return any(candidate in compact for candidate in candidates)


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "").replace("%", ""))
        except ValueError:
            return None
    return None


def _signal_level(value: object) -> int:
    names = {
        "strong_negative": -2,
        "negative": -1,
        "neutral": 0,
        "neutral_or_unknown": 0,
        "unknown": 0,
        "positive": 1,
        "strong_positive": 2,
    }
    if isinstance(value, bool):
        return 2 if value else 0
    if isinstance(value, (int, float)):
        return max(-2, min(2, round(float(value))))
    return names.get(str(value).strip().lower(), 0)
