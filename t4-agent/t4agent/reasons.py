from __future__ import annotations

import json
import os
from typing import Any

from .retrieve import IndexedCorpus


MAX_REASONS = 3
MAX_ANSWER_BYTES = 3_000
MAX_REASON_BYTES = 6_500
MAX_EVIDENCE_BYTES = 46_500
MAX_CITATION_CHARS = 8_000

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
                return doc_id, start, end, premise
    return None


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
