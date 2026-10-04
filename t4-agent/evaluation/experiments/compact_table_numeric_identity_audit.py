#!/usr/bin/env python3
"""Audit table-preserving passages and stable numeric identities without outcomes."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.run_benchmark_suite import discover_public_units  # noqa: E402
from t4agent.family_specs import task_family_spec  # noqa: E402
from t4agent.retrieve import (  # noqa: E402
    BM25,
    Chunk,
    IndexedCorpus,
    _chunks_for_text,
    allowed_document_ids,
    build_index,
    query_for,
    tokenize,
)
from t4agent.taskio import load_task  # noqa: E402

MAX_PASSAGE = 2200
MIN_BREAK = 1200
OVERLAP = 250
EVIDENCE_BUDGET = 16_000
TOP_K = 8
REPORT = ROOT / "evaluation/reports/compact-table-numeric-identity-audit-v1.json"
NUMERIC_IDENTITY = re.compile(
    r"(?<![\w.+\-\u2010-\u2015\u2212])([0-9]+(?:\.[0-9]+)?)"
    r"[^\S\r\n\v\f\x1c-\x1e\x85\u2028\u2029]*[-\u2010-\u2015\u2212]"
    r"[^\S\r\n\v\f\x1c-\x1e\x85\u2028\u2029]*([a-z]{2,})\b",
    re.I,
)
HEADER_NOISE = {
    "as", "at", "date", "entity", "id", "name", "period", "quarter", "series",
    "the", "time", "value", "year", "years",
}


@dataclass(frozen=True)
class CompactTable:
    start: int
    end: int
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    row_spans: tuple[tuple[int, int], ...]


def _cells(line: str) -> list[str]:
    row = line.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [cell.strip() for cell in row.split("|")]


def compact_tables(text: str) -> list[CompactTable]:
    """Return conservative table spans in the scorer's original text coordinates."""
    lines = text.splitlines(keepends=True)
    starts: list[int] = []
    offset = 0
    for line in lines:
        starts.append(offset)
        offset += len(line)
    out: list[CompactTable] = []
    index = 0
    while index < len(lines):
        if "|" not in lines[index]:
            index += 1
            continue
        first = index
        while index < len(lines) and "|" in lines[index]:
            index += 1
        last = index
        start = starts[first]
        end = starts[last] if last < len(lines) else len(text)
        block = lines[first:last]
        if end - start > MAX_PASSAGE or any("\\|" in line for line in block):
            continue
        rows = [_cells(line) for line in block]
        if (
            len(rows) < 2
            or any(len(row) < 2 or not all(row) for row in rows)
            or any(len(row) != len(rows[0]) for row in rows[1:])
            or not any(char.isalpha() for char in "".join(rows[0]))
        ):
            continue
        separators = [all(re.fullmatch(r":?-{3,}:?", cell) for cell in row) for row in rows]
        has_separator = len(rows) > 1 and separators[1]
        data_start = 2 if has_separator else 1
        if len(rows) <= data_start or any(separators[data_start:]):
            continue
        data_rows = rows[data_start:]
        if any(not any(char.isdigit() for char in "".join(row)) for row in data_rows):
            continue
        row_spans = tuple(
            (starts[first + row_index], starts[first + row_index] + len(lines[first + row_index]))
            for row_index in range(data_start, len(rows))
        )
        table_start = start
        if first:
            caption = lines[first - 1].strip()
            caption_start = starts[first - 1]
            if (
                caption
                and len(caption) <= 200
                and "|" not in caption
                and (caption.endswith(":") or re.search(r"\bunits?\b", caption, re.I))
                and end - caption_start <= MAX_PASSAGE
            ):
                table_start = caption_start
        out.append(
            CompactTable(
                table_start,
                end,
                tuple(rows[0]),
                tuple(tuple(row) for row in data_rows),
                row_spans,
            )
        )
    return out


def candidate_chunks_for_text(doc_id: str, doc_date: str | None, text: str, base_offset: int) -> list[Chunk]:
    """Use production spans unless a recognized table would be split."""
    tables = compact_tables(text)
    if not tables:
        return _chunks_for_text(doc_id, doc_date, text, base_offset)
    if len(text) <= 2400:
        return [Chunk(doc_id, doc_date, base_offset, base_offset + len(text), text)]
    out: list[Chunk] = []
    start = 0
    while start < len(text):
        end = min(start + MAX_PASSAGE, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n", start + MIN_BREAK, end), text.rfind(". ", start + MIN_BREAK, end))
            if boundary > start:
                end = boundary + 1
        cut_before = False
        for table in tables:
            if table.start < end < table.end:
                if table.end - start <= MAX_PASSAGE:
                    end = table.end
                else:
                    end = table.start
                    cut_before = True
                break
        if end <= start:
            raise ValueError("table-aware chunker made no progress")
        piece = text[start:end]
        if piece.strip():
            out.append(Chunk(doc_id, doc_date, base_offset + start, base_offset + end, piece))
        if end >= len(text):
            break
        next_start = end if cut_before else max(start + 1, end - OVERLAP)
        for table in tables:
            if table.start < next_start < table.end:
                next_start = table.end
                break
        start = next_start
    return out


def numeric_identity_tokenize(value: str) -> list[str]:
    text = str(value).lower()
    tokens = tokenize(text)
    for match in NUMERIC_IDENTITY.finditer(text):
        previous = match.start() - 1
        while previous >= 0 and text[previous].isspace() and text[previous] not in "\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029":
            previous -= 1
        if previous >= 0 and text[previous] in "+-\u2010\u2011\u2012\u2013\u2014\u2015\u2212":
            continue
        if previous >= 0 and text[previous] in ".,":
            previous -= 1
            while previous >= 0 and text[previous].isspace() and text[previous] not in "\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029":
                previous -= 1
            if previous < 0 or text[previous].isdigit() or text[previous] in ".,+-\u2010\u2011\u2012\u2013\u2014\u2015\u2212":
                continue
        tokens.append(match.group(1) + match.group(2))
    return tokens


def build_candidate_index(corpus_dir: Path, cutoff_date: str) -> IndexedCorpus:
    production = build_index(corpus_dir, cutoff_date)
    chunks: list[Chunk] = []
    for doc_id, relative_path in production.doc_paths.items():
        doc = json.loads((corpus_dir / relative_path).read_text(encoding="utf-8"))
        parts = [doc["text"]] if isinstance(doc.get("text"), str) else [
            str(span.get("text", "")) for span in doc.get("spans", []) if isinstance(span, dict)
        ]
        offset = 0
        for text in parts:
            if text.strip():
                chunks.extend(candidate_chunks_for_text(doc_id, production.doc_dates[doc_id], text, offset))
            offset += len(text) + 1
    return IndexedCorpus(chunks, production.doc_texts, production.doc_dates, production.doc_paths)


def budgeted_search(index: BM25, query: str, allowed: set[str]) -> list[Any]:
    ranked = index.search(query, top_k=TOP_K, allowed_doc_ids=allowed)
    selected = []
    used = 0
    for item in ranked:
        size = len(item.chunk.text)
        if used + size <= EVIDENCE_BUDGET:
            selected.append(item)
            used += size
    return selected


def _semantic_terms(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z]{2,}", value.lower())
        if token not in HEADER_NOISE
    }


def target_compatible(table: CompactTable, task: Any, entity: dict[str, Any]) -> bool:
    header = " ".join(table.header)
    header_terms = _semantic_terms(header)
    target_text = " ".join(
        str(value) for value in (
            task.target.get("name", ""), task.target.get("unit", ""), task.family,
            entity.get("series_id", ""), entity.get("series_name", ""), entity.get("tenor", ""),
            entity.get("name", ""), entity.get("units", ""), entity.get("unit", ""),
        )
    )
    target_terms = _semantic_terms(target_text)
    if header_terms & target_terms:
        return True
    # Tables headed only by dates and values are compatible when their containing
    # document is already entity-scoped by corpus_ref/ownership.
    return bool(header_terms & {"actual", "amount", "estimate", "level", "rate", "ratio", "yield"})


def _covers(items: list[Any], doc_id: str, start: int, end: int) -> bool:
    return any(
        item.chunk.doc_id == doc_id and item.chunk.span_start <= start and item.chunk.span_end >= end
        for item in items
    )


def _identity_terms(value: str) -> set[str]:
    return {match.group(1).lower() + match.group(2).lower() for match in NUMERIC_IDENTITY.finditer(value)}


def _event_weighted(rows: list[dict[str, Any]], key: str, eligible_key: str) -> float | None:
    variants: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row[eligible_key]:
            variants[row["event_id"]].append(float(row[key]))
    events = [statistics.fmean(values) for values in variants.values() if values]
    return statistics.fmean(events) if events else None


def run_audit(manifest_path: Path = ROOT / "evaluation/benchmark_suite.json", public_units: Path | None = None) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    public_root = public_units or discover_public_units()
    if public_root is None:
        raise RuntimeError("public units not found")
    rows: list[dict[str, Any]] = []
    ordinary_docs = changed_ordinary_docs = 0
    violations = {"cutoff": 0, "ownership": 0, "offset": 0, "budget": 0, "top_k": 0}
    max_chars = 0
    max_selected = 0
    expected_entities = 0
    permutation_violations = 0
    for entry in manifest["units"]:
        unit = ROOT / entry["path"] if entry["cohort"] == "proxy" else public_root / entry["unit_id"]
        task = load_task(unit / "task.json")
        expected_entities += len(task.entities)
        production = build_index(unit / "corpus", task.cutoff_date)
        candidate = build_candidate_index(unit / "corpus", task.cutoff_date)
        prod_bm25, cand_bm25 = BM25(production.chunks), BM25(candidate.chunks, tokenizer=numeric_identity_tokenize)
        for doc_id, text in production.doc_texts.items():
            if not compact_tables(text):
                ordinary_docs += 1
                p = [(c.span_start, c.span_end) for c in production.chunks if c.doc_id == doc_id]
                c = [(x.span_start, x.span_end) for x in candidate.chunks if x.doc_id == doc_id]
                changed_ordinary_docs += p != c
        spec = task_family_spec(task.family, str(task.target.get("name", "")), task.target_type, task.entities)
        for entity in task.entities:
            allowed = allowed_document_ids(task, entity, production)
            query = query_for(task, entity, include_all_scalar_fields=spec.key == "generic")
            baseline_items = prod_bm25.search(query, top_k=TOP_K, allowed_doc_ids=allowed)
            candidate_items = budgeted_search(cand_bm25, query, allowed)
            reversed_entity = dict(reversed(list(entity.items())))
            reversed_query = query_for(task, reversed_entity, include_all_scalar_fields=spec.key == "generic")
            reversed_items = budgeted_search(cand_bm25, reversed_query, allowed_document_ids(task, reversed_entity, production))
            signature = [(item.chunk.doc_id, item.chunk.span_start, item.chunk.span_end) for item in candidate_items]
            reversed_signature = [(item.chunk.doc_id, item.chunk.span_start, item.chunk.span_end) for item in reversed_items]
            permutation_violations += signature != reversed_signature
            chars = sum(len(item.chunk.text) for item in candidate_items)
            max_chars = max(max_chars, chars)
            max_selected = max(max_selected, len(candidate_items))
            violations["budget"] += chars > EVIDENCE_BUDGET
            violations["top_k"] += len(candidate_items) > TOP_K
            for item in candidate_items:
                violations["ownership"] += item.chunk.doc_id not in allowed
                doc_text = candidate.doc_texts[item.chunk.doc_id]
                violations["offset"] += doc_text[item.chunk.span_start:item.chunk.span_end] != item.chunk.text
                doc_date = candidate.doc_dates[item.chunk.doc_id]
                violations["cutoff"] += bool(doc_date and doc_date[:10] > task.cutoff_date[:10])
            eligible: list[tuple[str, CompactTable]] = []
            for doc_id in allowed:
                for table in compact_tables(production.doc_texts[doc_id]):
                    if target_compatible(table, task, entity):
                        eligible.append((doc_id, table))
            base_complete = any(_covers(baseline_items, doc_id, table.start, table.end) for doc_id, table in eligible)
            cand_complete = any(_covers(candidate_items, doc_id, table.start, table.end) for doc_id, table in eligible)
            base_latest = any(_covers(baseline_items, doc_id, *table.row_spans[-1]) for doc_id, table in eligible)
            cand_latest = any(_covers(candidate_items, doc_id, *table.row_spans[-1]) for doc_id, table in eligible)
            target_docs = {doc_id for doc_id, _ in eligible}
            base_doc = any(item.chunk.doc_id in target_docs for item in baseline_items)
            cand_doc = any(item.chunk.doc_id in target_docs for item in candidate_items)
            identity_source = " ".join(str(v) for v in entity.values() if not isinstance(v, (dict, list))) + " " + query
            identities = _identity_terms(identity_source)
            base_identity = not identities or all(any(term in numeric_identity_tokenize(item.chunk.text) for item in baseline_items) for term in identities)
            cand_identity = not identities or all(any(term in numeric_identity_tokenize(item.chunk.text) for item in candidate_items) for term in identities)
            rows.append({
                "unit_id": entry["unit_id"], "event_id": entry["event_id"], "cohort": entry["cohort"],
                "variant": entry["variant"], "target_type": task.target_type,
                "entity_id": str(entity.get("entity_id", "")), "eligible_table": bool(eligible),
                "eligible_tables": len(eligible), "identity_bearing": bool(identities),
                "baseline_complete": base_complete, "candidate_complete": cand_complete,
                "baseline_latest": base_latest, "candidate_latest": cand_latest,
                "baseline_target_doc": base_doc, "candidate_target_doc": cand_doc,
                "baseline_identity": base_identity, "candidate_identity": cand_identity,
                "candidate_chars": chars, "candidate_passages": len(candidate_items),
            })
    eligible_rows = [row for row in rows if row["eligible_table"]]
    identity_rows = [row for row in rows if row["identity_bearing"]]
    metrics = {
        "units": len({row["unit_id"] for row in rows}), "entities": len(rows),
        "eligible_table_entities": len(eligible_rows), "identity_bearing_entities": len(identity_rows),
        "ordinary_non_table_documents": ordinary_docs, "changed_ordinary_non_table_documents": changed_ordinary_docs,
        "baseline_complete_table_coverage": _event_weighted(rows, "baseline_complete", "eligible_table"),
        "candidate_complete_table_coverage": _event_weighted(rows, "candidate_complete", "eligible_table"),
        "baseline_latest_row_visibility": _event_weighted(rows, "baseline_latest", "eligible_table"),
        "candidate_latest_row_visibility": _event_weighted(rows, "candidate_latest", "eligible_table"),
        "baseline_target_doc_retrieval": _event_weighted(rows, "baseline_target_doc", "eligible_table"),
        "candidate_target_doc_retrieval": _event_weighted(rows, "candidate_target_doc", "eligible_table"),
        "baseline_numeric_identity_accuracy": _event_weighted(rows, "baseline_identity", "identity_bearing"),
        "candidate_numeric_identity_accuracy": _event_weighted(rows, "candidate_identity", "identity_bearing"),
        "max_candidate_chars": max_chars, "max_candidate_passages": max_selected,
    }
    def delta(candidate_key: str, baseline_key: str) -> float:
        return float(metrics[candidate_key] or 0) - float(metrics[baseline_key] or 0)
    paired: dict[str, dict[str, list[dict[str, bool]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        paired[row["event_id"]][row["variant"]].append({
            "eligible": row["eligible_table"], "baseline": row["baseline_complete"], "candidate": row["candidate_complete"]
        })
    gaps = {}
    for name in ("baseline", "candidate"):
        values = []
        for variants in paired.values():
            if "explicit" in variants and "transformed" in variants:
                explicit = [float(row[name]) for row in variants["explicit"] if row["eligible"]]
                transformed = [float(row[name]) for row in variants["transformed"] if row["eligible"]]
                if explicit and transformed:
                    values.append(abs(statistics.fmean(explicit) - statistics.fmean(transformed)))
        gaps[name] = statistics.fmean(values) if values else 0.0
    gates = {
        "all_51_units_and_every_entity_audited": metrics["units"] == 51 and metrics["entities"] == expected_entities,
        "cutoff_ownership_offset_violations_zero": not any(violations[key] for key in ("cutoff", "ownership", "offset")),
        "candidate_budget_and_top_k_bounded": max_chars <= EVIDENCE_BUDGET and max_selected <= TOP_K,
        "complete_table_coverage_gain_at_least_0_05": delta("candidate_complete_table_coverage", "baseline_complete_table_coverage") >= 0.05,
        "no_target_doc_latest_row_or_identity_loss": all(
            delta(candidate_key, baseline_key) >= -1e-12 for candidate_key, baseline_key in (
                ("candidate_target_doc_retrieval", "baseline_target_doc_retrieval"),
                ("candidate_latest_row_visibility", "baseline_latest_row_visibility"),
                ("candidate_numeric_identity_accuracy", "baseline_numeric_identity_accuracy"),
            )
        ),
        "candidate_complete_table_coverage_at_least_0_95": (metrics["candidate_complete_table_coverage"] or 0) >= 0.95,
        "schema_gap_not_wider": gaps["candidate"] <= gaps["baseline"] + 1e-12,
        "ordinary_non_table_document_spans_unchanged": changed_ordinary_docs == 0,
        "row_and_field_permutation_invariant": permutation_violations == 0,
    }
    report = {
        "schema_version": 1,
        "experiment": "compact_table_numeric_identity_audit_v1",
        "scope": "evaluation_only_51_unit_retrieval_audit_no_outcomes_no_model_calls_no_production_change",
        "hypothesis": "Preserving eligible compact tables and unsigned numeric identities improves complete target-table retrieval without weakening isolation or robustness.",
        "reference": {"source": "Team Optivex public submission source", "snapshot": "b897309bb591d98cf6aabb3cf04f71770e969af5", "license": "Apache-2.0", "mechanisms": ["compact table passages", "unsigned numeric identity tokens", "16000 character evidence budget"]},
        "model_api_calls": 0,
        "policy": {"max_passage": MAX_PASSAGE, "top_k": TOP_K, "evidence_budget_chars": EVIDENCE_BUDGET, "outcomes_read": False},
        "metrics": metrics, "violations": {**violations, "field_permutation": permutation_violations}, "schema_complete_table_gap": gaps,
        "gates": gates,
        "decision": "accept_evaluation_infrastructure_only" if all(gates.values()) else "reject_no_production_change",
        "rows": rows,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--public-units", type=Path)
    args = parser.parse_args()
    report = run_audit(public_units=args.public_units)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"decision": report["decision"], "metrics": report["metrics"], "gates": report["gates"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
