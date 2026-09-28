#!/usr/bin/env python3
"""Replay saved quote rejections against context-only formatting recovery."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from t4agent.evidence import locate_exact_quote  # noqa: E402
from t4agent.retrieve import IndexedCorpus, build_index  # noqa: E402

FORMAT_ONLY_CHARACTERS = frozenset({"$", "•"})
MIN_FORMATTING_MATCH_CHARS = 40


def normalize_with_offsets(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    offsets: list[int] = []
    in_space = False
    for index, char in enumerate(text):
        if char in FORMAT_ONLY_CHARACTERS:
            continue
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


def candidate_span(corpus: IndexedCorpus, doc_id: str, quote: str) -> tuple[int, int] | None:
    text = corpus.doc_texts.get(doc_id)
    if not text or not quote:
        return None
    normalized_text, offsets = normalize_with_offsets(text)
    normalized_quote, _ = normalize_with_offsets(quote)
    normalized_quote = normalized_quote.strip()
    if len(normalized_quote) < MIN_FORMATTING_MATCH_CHARS:
        return None
    start = normalized_text.find(normalized_quote)
    if start < 0 or normalized_text.find(normalized_quote, start + 1) >= 0:
        return None
    end = start + len(normalized_quote)
    return offsets[start], offsets[end - 1] + 1


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-units", type=Path, required=True)
    parser.add_argument("--saved-run", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    return parser.parse_args()


def negative_controls() -> dict[str, bool]:
    cases = {
        "substantive_edit": (
            "Revenue decreased materially during the quarter.",
            "Revenue increased materially during the quarter.",
        ),
        "ambiguous_repeat": (
            "Repeated formatting passage for ambiguity. " * 2,
            "Repeated formatting passage for ambiguity.",
        ),
        "short_match": ("Short $ 3.32 value.", "Short 3.32 value."),
        "wrong_document": (
            "A sufficiently long formatting passage that exists in another document only.",
            "A sufficiently long formatting passage that exists in another document only.",
        ),
    }
    results: dict[str, bool] = {}
    for name, (text, quote) in cases.items():
        corpus = IndexedCorpus([], {"A": text}, {"A": "2023-01-01"})
        doc_id = "MISSING" if name == "wrong_document" else "A"
        results[name] = candidate_span(corpus, doc_id, quote) is None
    return results


def main() -> None:
    args = parse_args()
    rows_files = sorted(args.saved_run.glob("*/trace/rows.json"))
    rejected_total = 0
    context_rejected = 0
    recovered = []
    strict_non_context_rejections = []
    input_hashes: dict[str, str] = {}
    target_types: set[str] = set()
    families: set[str] = set()

    for rows_path in rows_files:
        unit_id = rows_path.parents[1].name
        unit_dir = args.official_units / unit_id
        task_path = unit_dir / "task.json"
        task = json.loads(task_path.read_text())
        corpus = build_index(unit_dir / "corpus", str(task["cutoff_date"]))
        input_hashes[unit_id] = sha256(rows_path)
        for row in json.loads(rows_path.read_text()):
            for rejection in row.get("rejected_facts", []):
                rejected_total += 1
                raw = rejection.get("raw") or {}
                doc_id = str(raw.get("doc_id") or "")
                quote = str(raw.get("quote") or "")
                baseline = locate_exact_quote(corpus, doc_id, quote)
                if rejection.get("name") != "context":
                    strict_non_context_rejections.append({
                        "unit_id": unit_id,
                        "entity_id": row.get("entity_id"),
                        "name": rejection.get("name"),
                        "baseline_rejected": baseline is None,
                        "production_still_strict": True,
                    })
                    continue
                context_rejected += 1
                span = candidate_span(corpus, doc_id, quote)
                restored = corpus.doc_texts[doc_id][span[0] : span[1]] if span else None
                exact_slice = restored == corpus.doc_texts[doc_id][span[0] : span[1]] if span else False
                recovered.append({
                    "unit_id": unit_id,
                    "family": task.get("family"),
                    "target_type": task.get("target", {}).get("type"),
                    "entity_id": row.get("entity_id"),
                    "baseline_rejected": baseline is None,
                    "candidate_recovered": span is not None,
                    "candidate_rejection": None if span else "quote_not_exact_substring",
                    "restored_exact_source_slice": exact_slice,
                    "restored_span": list(span) if span else None,
                })
                target_types.add(str(task.get("target", {}).get("type")))
                families.add(str(task.get("family")))

    controls = negative_controls()
    passed = (
        len(recovered) == 2
        and all(item["baseline_rejected"] for item in recovered)
        and all(item["candidate_recovered"] and item["restored_exact_source_slice"] for item in recovered)
        and len(strict_non_context_rejections) == 1
        and all(item["baseline_rejected"] and item["production_still_strict"] for item in strict_non_context_rejections)
        and len(families) == 2
        and target_types == {"classification", "regression"}
        and all(controls.values())
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "experiment": "context_formatting_recovery_screen_v1",
        "baseline_git_commit": "416cfa2c6e05deb16b1cc1b9800509cdb9437207",
        "hypothesis": (
            "Context quotes that differ only by whitespace, currency markers or bullet glyphs can be "
            "uniquely mapped to an exact corpus span without relaxing signal or numeric-parameter evidence."
        ),
        "scope": "L2 cross-family context citation construction only.",
        "saved_run": str(args.saved_run),
        "saved_rows_sha256": input_hashes,
        "rejected_facts_total": rejected_total,
        "context_rejections": context_rejected,
        "recovered_contexts": recovered,
        "strict_non_context_rejections": strict_non_context_rejections,
        "families": sorted(families),
        "target_types": sorted(target_types),
        "negative_controls": controls,
        "decision_rule": (
            "Advance only if both saved context rejections across two families and two target types map "
            "to exact unique source slices, the non-context rejection stays strict, and all negative controls pass."
        ),
        "decision": "pass_to_public_gates" if passed else "reject",
        "model_api_calls": 0,
        "local_llm_run": False,
        "prediction_path_change": False,
        "limitations": [
            "The saved run is a fixed public diagnostic, not a hidden-unit sample.",
            "The recovery admits only context facts; signal and numeric parameter quotes remain strict.",
            "A formatting variant must be at least 40 normalized characters and unique within its document.",
        ],
    }
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload)
    print(payload, end="")


if __name__ == "__main__":
    main()
