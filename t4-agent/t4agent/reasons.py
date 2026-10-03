from __future__ import annotations

import json
import os
import re
from typing import Any

from .retrieve import IndexedCorpus


MAX_REASONS = 3
MAX_ANSWER_BYTES = 3_000
MAX_REASON_BYTES = 6_500
MAX_EVIDENCE_BYTES = 46_500
MAX_CITATION_CHARS = 8_000

METHOD_ANCHORS: dict[str, tuple[str, ...]] = {
    "consensus_strong_signal": (
        "diluted earnings per share", "earnings per share", "eps", "earnings", "revenue", "guidance",
    ),
    "explicit_credit_flags": (
        "going concern", "default", "bankruptcy", "covenant", "credit rating", "rating", "outlook",
        "liquidity", "debt", "maturity", "cash",
    ),
    "seasonal_eps_delta_persistence": (
        "diluted earnings per share", "earnings per share", "eps", "diluted", "net income", "prior year",
    ),
    "prior_eps_direction_only": (
        "diluted earnings per share", "earnings per share", "eps", "diluted", "net income", "prior year",
    ),
    "policy_direction_maturity_decay": (
        "federal funds", "target range", "monetary policy", "raised", "lowered", "maintained",
        "inflation", "unemployment", "yield",
    ),
    "flat_unless_strong_outlook": (
        "guidance", "outlook", "gross margin", "operating margin", "operating income", "revenue", "earnings",
    ),
}
HIGH_VALUE_ANCHORS = {
    "diluted earnings per share", "earnings per share", "going concern", "default", "bankruptcy", "covenant",
    "federal funds", "target range", "monetary policy", "raised", "lowered", "maintained", "guidance", "outlook",
    "gross margin", "operating margin",
    "credit rating", "rating",
}
JUNK_PATTERNS = (
    "table of contents",
    "united states securities and exchange commission",
    "pursuant to section 13",
    "not applicable or is not present",
    "see accompanying notes",
    "exhibit number description",
    "actual results could differ materially",
    "excluded from the calculation",
    "antidilutive",
)
NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\$?\d[\d,.]*(?:%|\s+billion|\s+million)?", re.IGNORECASE)
BOUNDARY_RE = re.compile(r"(?:\n+|(?<=[.!?])\s+)")

MECHANISMS = {
    "consensus_strong_signal": "The cited earnings evidence is combined with the available consensus signal; a positive or negative signal moves the submitted earnings class away from the neutral threshold.",
    "same_tenor_recent_history": "Recent same-tenor bid-to-cover observations are averaged to estimate the next auction result, while their dispersion sets forecast uncertainty.",
    "net_position_mean_reversion": "Current net positioning is treated as a crowding signal: more extreme positioning implies a larger subsequent move in the opposite direction.",
    "component_history": "The component's pre-cutoff monthly history anchors its next monthly change; recent observations determine the point and historical variation sets uncertainty.",
    "component_history_mean12": "The complete pre-cutoff twelve-month component history is averaged to reduce sensitivity to one volatile monthly observation.",
    "explicit_credit_flags": "Explicit distress indicators in the cited filing raise estimated event risk; absent validated distress evidence leaves the forecast near the low-risk prior.",
    "seasonal_eps_delta_persistence": "The latest same-quarter EPS change is carried forward as a simple seasonal persistence estimate for next-quarter year-over-year EPS growth.",
    "prior_eps_direction_only": "The prior comparable EPS level anchors the forecast, and the validated directional signal applies only a bounded step rather than inventing a missing magnitude.",
    "policy_direction_maturity_decay": "The policy direction sets the sign of the curve response, with smaller sensitivity at longer maturities and a fixed uncertainty band.",
    "median_historical_revision": "The median of the series' pre-cutoff revision history is applied to the current vintage to estimate the next revised level.",
    "flat_unless_strong_outlook": "Without validated forward-looking evidence strong enough to choose a direction, the submitted reaction stays flat with an uncertainty band reflecting historical event volatility.",
    "generic_dated_table_baseline": "The latest cutoff-safe observation from the exact target-matched dated column is used as the persistence forecast.",
}


def build_submitted_reasons(results: list[Any], corpus: IndexedCorpus) -> list[dict[str, Any]]:
    """Build bounded reasons from validated facts and final normalized answers.

    The optional field is omitted whenever any unit-level cap cannot be proven locally.
    ``T4_ENABLE_SUBMITTED_REASONS=0`` is the immediate rollback.
    """
    if os.environ.get("T4_ENABLE_SUBMITTED_REASONS", "1") != "1":
        return []
    projected_answer = [_project_answer(row.prediction) for row in results]
    if _compact_bytes(projected_answer) > MAX_ANSWER_BYTES:
        return []
    reasons: list[dict[str, Any]] = []
    evidence_projection: list[dict[str, Any]] = []
    for row in results:
        mechanism = MECHANISMS.get(str(row.method or ""))
        if mechanism is None:
            continue
        citation = _best_citation(row, corpus)
        if citation is None:
            continue
        doc_id, start, end, premise = citation
        item = {
            "reason_id": f"r{len(reasons) + 1}",
            "premise": premise,
            "mechanism": mechanism,
            "answer_implication": _implication(row.prediction),
            "scope": {"entities": [str(row.prediction.get("entity_id") or "")]},
            "citations": [{"doc_id": doc_id, "span_start": start, "span_end": end}],
        }
        projected_reason = {key: item[key] for key in ("reason_id", "premise", "mechanism", "answer_implication")}
        projected_evidence = {
            "doc_id": doc_id,
            "span_start": start,
            "span_end": end,
            "trusted_text": premise,
            "reason_id": item["reason_id"],
        }
        if _compact_bytes([*[_project_reason(reason) for reason in reasons], projected_reason]) > MAX_REASON_BYTES:
            continue
        if _compact_bytes([*evidence_projection, projected_evidence]) > MAX_EVIDENCE_BYTES:
            continue
        reasons.append(item)
        evidence_projection.append(projected_evidence)
        if len(reasons) == MAX_REASONS:
            break
    return reasons


def _best_citation(row: Any, corpus: IndexedCorpus) -> tuple[str, int, int, str] | None:
    facts = sorted(row.facts, key=lambda fact: fact.kind == "context")
    candidates = [(fact.doc_id, fact.span_start, fact.span_end) for fact in facts]
    candidates.extend(
        (str(claim.get("doc_id") or ""), claim.get("span_start"), claim.get("span_end"))
        for claim in row.prediction.get("claims", [])
    )
    seen = set()
    valid: list[tuple[str, int, int, str]] = []
    for doc_id, start, end in candidates:
        key = (doc_id, start, end)
        if key in seen:
            continue
        seen.add(key)
        text = corpus.doc_texts.get(doc_id, "")
        if (
            doc_id != "task"
            and isinstance(start, int)
            and isinstance(end, int)
            and 0 <= start < end <= len(text)
            and end - start <= min(2_000, MAX_CITATION_CHARS)
        ):
            premise = text[start:end]
            if len(premise.split()) >= 3:
                valid.append((doc_id, start, end, premise))
    if not valid:
        return None
    baseline = valid[0]
    context_only = bool(row.facts) and all(fact.kind == "context" for fact in row.facts)
    if not context_only or os.environ.get("T4_ENABLE_REASON_RELEVANCE", "1") != "1":
        return baseline
    selected = _select_context_citation(row, corpus, baseline)
    return selected or baseline


def _select_context_citation(
    row: Any,
    corpus: IndexedCorpus,
    baseline: tuple[str, int, int, str],
) -> tuple[str, int, int, str] | None:
    method = str(row.method or "")
    if method not in METHOD_ANCHORS:
        return None
    baseline_item = _citation_item(*baseline, method)
    candidates = [baseline_item]
    for chunk in row.retrieved:
        for item in _context_windows(chunk, method):
            text = corpus.doc_texts.get(item["doc_id"], "")
            if text[item["span_start"] : item["span_end"]] == item["premise"]:
                candidates.append(item)
    selected = max(candidates, key=_choice_key)
    gain = selected["score"]["total"] - baseline_item["score"]["total"]
    if selected is baseline_item or gain < 4:
        return None
    return (
        str(selected["doc_id"]),
        int(selected["span_start"]),
        int(selected["span_end"]),
        str(selected["premise"]),
    )


def _citation_item(doc_id: str, start: int, end: int, premise: str, method: str) -> dict[str, Any]:
    return {
        "doc_id": doc_id,
        "span_start": start,
        "span_end": end,
        "premise": premise,
        "score": _relevance_score(method, premise),
    }


def _relevance_score(method: str, text: str) -> dict[str, int]:
    low = text.casefold()
    matched = [anchor for anchor in METHOD_ANCHORS.get(method, ()) if anchor in low]
    high_count = sum(anchor in HIGH_VALUE_ANCHORS for anchor in matched)
    junk_count = sum(pattern in low for pattern in JUNK_PATTERNS)
    number_count = min(3, len(NUMBER_RE.findall(text)))
    anchor_weight = sum(3 if anchor in HIGH_VALUE_ANCHORS else 1 for anchor in matched)
    return {
        "total": anchor_weight + number_count - 4 * junk_count,
        "anchor_count": len(matched),
        "high_value_count": high_count,
        "number_count_capped": number_count,
        "junk_count": junk_count,
    }


def _eligible(metric: dict[str, int]) -> bool:
    return metric["total"] > 0 and (metric["high_value_count"] >= 1 or metric["anchor_count"] >= 2)


def _context_windows(chunk: Any, method: str) -> list[dict[str, Any]]:
    text = str(chunk.text)
    starts: list[int] = []
    cursor = 0
    for match in BOUNDARY_RE.finditer(text):
        starts.append(cursor)
        cursor = match.end()
    starts.append(cursor)
    spans: list[tuple[int, int]] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        if start < end and text[start:end].strip():
            spans.append((start, end))
    output: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    anchors = METHOD_ANCHORS[method]
    for index, (start, end) in enumerate(spans):
        sentence = text[start:end]
        if not any(anchor in sentence.casefold() for anchor in anchors):
            continue
        left, right = index, index + 1
        while left > 0 and end - spans[left - 1][0] <= 700:
            left -= 1
        while right < len(spans) and spans[right][1] - spans[left][0] <= 700:
            right += 1
        local_start, local_end = spans[left][0], spans[right - 1][1]
        while local_end - local_start > 700 and left < index:
            left += 1
            local_start = spans[left][0]
        while local_end - local_start > 700 and right - 1 > index:
            right -= 1
            local_end = spans[right - 1][1]
        if local_end - local_start > 700:
            low = sentence.casefold()
            hit = min(low.find(anchor) for anchor in anchors if low.find(anchor) >= 0)
            local_start = start + max(0, hit - 180)
            local_end = min(end, local_start + 700)
            while local_start > start and not text[local_start - 1].isspace():
                local_start -= 1
            while local_end < end and not text[local_end].isspace():
                local_end += 1
        key = (local_start, local_end)
        if key in seen:
            continue
        seen.add(key)
        raw = text[local_start:local_end]
        stripped_left = len(raw) - len(raw.lstrip())
        stripped_right = len(raw.rstrip())
        premise = raw.strip()
        metric = _relevance_score(method, premise)
        if len(premise.split()) < 3 or not _eligible(metric):
            continue
        output.append({
            "doc_id": chunk.doc_id,
            "span_start": chunk.span_start + local_start + stripped_left,
            "span_end": chunk.span_start + local_start + stripped_right,
            "premise": premise,
            "score": metric,
        })
    return output


def _choice_key(item: dict[str, Any]) -> tuple[int, int, int, int, int, str, int]:
    metric = item["score"]
    return (
        metric["total"],
        metric["high_value_count"],
        metric["anchor_count"],
        metric["number_count_capped"],
        -len(item["premise"]),
        str(item["doc_id"]),
        -int(item["span_start"]),
    )


def _implication(prediction: dict[str, Any]) -> str:
    entity_id = str(prediction.get("entity_id") or "")
    if "label" in prediction:
        return f"For {entity_id}, this supports the submitted label {prediction['label']}."
    value = float(prediction["point_forecast"])
    return f"For {entity_id}, this supports the submitted point forecast {value:g}."


def _project_answer(prediction: dict[str, Any]) -> dict[str, Any]:
    return {
        key: prediction[key]
        for key in ("entity_id", "label", "point_forecast", "interval", "label_probs")
        if key in prediction
    }


def _project_reason(reason: dict[str, Any]) -> dict[str, Any]:
    return {key: reason[key] for key in ("reason_id", "premise", "mechanism", "answer_implication")}


def _compact_bytes(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode())
