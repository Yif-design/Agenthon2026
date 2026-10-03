#!/usr/bin/env python3
"""Screen a deterministic selector for context-only submitted-reason evidence.

The screen consumes saved public traces.  It never changes an answer and it does
not call a model.  Computed-input rows are controls: their current premises must
remain selected byte-for-byte.  Context-only rows may replace the current premise
only when a short exact slice has a strictly better, predeclared method-specific
relevance score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


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

HIGH_VALUE = {
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


def score(method: str, text: str) -> dict[str, Any]:
    low = text.casefold()
    anchors = METHOD_ANCHORS.get(method, ())
    matched = [anchor for anchor in anchors if anchor in low]
    high = [anchor for anchor in matched if anchor in HIGH_VALUE]
    junk = [pattern for pattern in JUNK_PATTERNS if pattern in low]
    numbers = min(3, len(NUMBER_RE.findall(text)))
    weighted = sum(3 if anchor in HIGH_VALUE else 1 for anchor in matched)
    total = weighted + numbers - 4 * len(junk)
    return {
        "total": total,
        "anchor_weight": weighted,
        "anchor_count": len(matched),
        "high_value_count": len(high),
        "number_count_capped": numbers,
        "junk_count": len(junk),
        "matched_anchors": matched,
        "matched_junk": junk,
    }


def eligible(method: str, metric: dict[str, Any]) -> bool:
    # One mechanism-specific phrase is enough; otherwise require two independent
    # family terms.  A non-positive passage cannot explain a forecast.
    return metric["total"] > 0 and (
        metric["high_value_count"] >= 1 or metric["anchor_count"] >= 2
    )


def windows(chunk: dict[str, Any], method: str) -> list[dict[str, Any]]:
    """Return exact <=700-character sentence groups containing an anchor."""
    text = str(chunk["text"])
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
    out: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    anchors = METHOD_ANCHORS.get(method, ())
    for index, (start, end) in enumerate(spans):
        sentence = text[start:end]
        if not any(anchor in sentence.casefold() for anchor in anchors):
            continue
        left = index
        right = index + 1
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
            # A table-like sentence can be huge.  Use a bounded exact word-aligned
            # neighborhood around the first family anchor in that sentence.
            low = sentence.casefold()
            positions = [low.find(anchor) for anchor in anchors if low.find(anchor) >= 0]
            hit = min(positions)
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
        premise = text[local_start:local_end].strip()
        stripped_left = len(text[local_start:local_end]) - len(text[local_start:local_end].lstrip())
        stripped_right = len(text[local_start:local_end].rstrip())
        exact_start = int(chunk["span_start"]) + local_start + stripped_left
        exact_end = int(chunk["span_start"]) + local_start + stripped_right
        metric = score(method, premise)
        if len(premise.split()) >= 3 and eligible(method, metric):
            out.append({
                "doc_id": chunk["doc_id"],
                "span_start": exact_start,
                "span_end": exact_end,
                "premise": premise,
                "score": metric,
            })
    return out


def choice_key(candidate: dict[str, Any]) -> tuple[int, int, int, int, int, str, int]:
    metric = candidate["score"]
    return (
        metric["total"],
        metric["high_value_count"],
        metric["anchor_count"],
        metric["number_count_capped"],
        -len(candidate["premise"]),
        str(candidate["doc_id"]),
        -int(candidate["span_start"]),
    )


def reason_by_entity(answer: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(reason.get("scope", {}).get("entities", [""])[0]): reason
        for reason in answer.get("submitted_reasons", [])
        if reason.get("scope", {}).get("entities")
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--traces", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline-commit", required=True)
    args = parser.parse_args()

    rows_out: list[dict[str, Any]] = []
    for rows_path in sorted(args.traces.glob("*/trace/rows.json")):
        unit = rows_path.parents[1].name
        answer = json.loads((rows_path.parents[1] / "answer.json").read_text(encoding="utf-8"))
        current = reason_by_entity(answer)
        for row in json.loads(rows_path.read_text(encoding="utf-8")):
            entity = str(row["entity_id"])
            reason = current.get(entity)
            if reason is None:
                continue
            kinds = sorted({str(fact.get("kind")) for fact in row.get("validated_facts", [])})
            context_only = kinds == ["context"]
            baseline = {
                "doc_id": reason["citations"][0]["doc_id"],
                "span_start": reason["citations"][0]["span_start"],
                "span_end": reason["citations"][0]["span_end"],
                "premise": reason["premise"],
                "score": score(str(row["method"]), str(reason["premise"])),
            }
            candidates = [baseline]
            if context_only:
                for chunk in row.get("retrieved_chunks", []):
                    candidates.extend(windows(chunk, str(row["method"])))
            selected = max(candidates, key=choice_key)
            score_gain = selected["score"]["total"] - baseline["score"]["total"]
            improved = context_only and choice_key(selected) > choice_key(baseline) and score_gain >= 4
            if not improved:
                selected = baseline
            rows_out.append({
                "unit": unit,
                "entity_id": entity,
                "method": row["method"],
                "fact_kinds": kinds,
                "context_only": context_only,
                "changed": selected["premise"] != baseline["premise"],
                "baseline": baseline,
                "selected": selected,
                "candidate_count": len(candidates),
            })

    controls = [row for row in rows_out if not row["context_only"]]
    contexts = [row for row in rows_out if row["context_only"]]
    changed = [row for row in contexts if row["changed"]]
    control_unchanged = all(not row["changed"] for row in controls)
    strict = all(
        choice_key(row["selected"]) > choice_key(row["baseline"])
        and row["selected"]["score"]["total"] - row["baseline"]["score"]["total"] >= 4
        for row in changed
    )
    exact = True
    for row in changed:
        unit_root = args.traces / row["unit"]
        trace_rows = json.loads((unit_root / "trace" / "rows.json").read_text(encoding="utf-8"))
        source_row = next(item for item in trace_rows if str(item["entity_id"]) == row["entity_id"])
        source = next(
            chunk for chunk in source_row["retrieved_chunks"]
            if chunk["doc_id"] == row["selected"]["doc_id"]
            and chunk["span_start"] <= row["selected"]["span_start"]
            and chunk["span_end"] >= row["selected"]["span_end"]
        )
        a = row["selected"]["span_start"] - source["span_start"]
        b = row["selected"]["span_end"] - source["span_start"]
        exact = exact and source["text"][a:b] == row["selected"]["premise"]

    passed = bool(changed) and control_unchanged and strict and exact
    report = {
        "schema_version": 1,
        "experiment": "reason_evidence_relevance_screen_v1",
        "baseline_git_commit": args.baseline_commit,
        "hypothesis": "Method-aware exact-window selection can strictly improve context-only reason relevance while leaving computed-input premises unchanged.",
        "decision_rule": "Proceed only if at least one context-only premise changes, every changed row improves the predeclared relevance total by at least four points, all computed-input controls are unchanged, and every replacement is an exact retrieved corpus slice.",
        "official_versions_unchanged": True,
        "rows_with_reasons": len(rows_out),
        "computed_input_controls": len(controls),
        "context_only_rows": len(contexts),
        "changed_context_rows": len(changed),
        "computed_input_controls_unchanged": control_unchanged,
        "changed_rows_strictly_better": strict,
        "replacement_spans_exact": exact,
        "decision": "proceed_to_production_candidate" if passed else "reject",
        "production_change": "none",
        "model_api": {"requests": 0, "input_tokens": 0, "output_tokens": 0},
        "local_llm_run": False,
        "public_trace_sha256": hashlib.sha256(
            b"".join(path.read_bytes() for path in sorted(args.traces.glob("*/trace/rows.json")))
        ).hexdigest(),
        "rows": rows_out,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "rows_with_reasons", "computed_input_controls", "context_only_rows", "changed_context_rows",
        "computed_input_controls_unchanged", "changed_rows_strictly_better", "replacement_spans_exact", "decision",
    )}, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
