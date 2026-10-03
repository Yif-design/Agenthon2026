#!/usr/bin/env python3
"""Compare the legacy punctuation-retaining tokenizer with the current tokenizer."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from t4agent.retrieve import (  # noqa: E402
    BM25,
    Chunk,
    allowed_document_ids,
    build_index,
    query_for,
    tokenize,
)
from t4agent.taskio import load_task  # noqa: E402

LEGACY_TOKEN_RE = re.compile(r"[A-Za-z0-9_.$%-]+")


def legacy_tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in LEGACY_TOKEN_RE.finditer(text)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def _keys(index: BM25, query: str, top_k: int, allowed: set[str] | None = None) -> list[list[Any]]:
    return [
        [row.chunk.doc_id, row.chunk.span_start, row.chunk.span_end]
        for row in index.search(query, top_k=top_k, allowed_doc_ids=allowed)
    ]


def main() -> None:
    args = parse_args()
    synthetic_groups = [
        ["tier_high", "tier_medium", "tier_low"],
        ["action_up", "action_flat", "action_down"],
        ["capacity_expand", "capacity_hold", "capacity_contract"],
        ["risk_yes", "risk_no"],
        ["quality_pass", "quality_fail"],
    ]
    synthetic_chunks = []
    for group in synthetic_groups:
        for entity_id in group:
            text = f"{entity_id}. evidence for {entity_id}."
            synthetic_chunks.append(
                Chunk(f"DOC_{entity_id.upper()}", "2023-01-01", 0, len(text), text)
            )
    legacy_synthetic = BM25(synthetic_chunks, tokenizer=legacy_tokenize)
    candidate_synthetic = BM25(synthetic_chunks)
    synthetic_rows = []
    for entity_id in [item for group in synthetic_groups for item in group]:
        expected = f"DOC_{entity_id.upper()}"
        legacy = legacy_synthetic.search(entity_id, top_k=1)[0].chunk.doc_id
        candidate = candidate_synthetic.search(entity_id, top_k=1)[0].chunk.doc_id
        synthetic_rows.append(
            {
                "entity_id": entity_id,
                "expected": expected,
                "legacy": legacy,
                "candidate": candidate,
                "legacy_correct": legacy == expected,
                "candidate_correct": candidate == expected,
            }
        )

    public_changes = []
    public_rows = 0
    for task_path in sorted(args.units.glob("*/task.json")):
        task = load_task(task_path)
        corpus = build_index(task_path.parent / "corpus", task.cutoff_date)
        legacy_index = BM25(corpus.chunks, tokenizer=legacy_tokenize)
        candidate_index = BM25(corpus.chunks)
        for entity in task.entities:
            public_rows += 1
            entity_id = str(entity.get("entity_id", ""))
            allowed = allowed_document_ids(task, entity, corpus)
            query = query_for(task, entity)
            legacy = _keys(legacy_index, query, 8, allowed)
            candidate = _keys(candidate_index, query, 8, allowed)
            if legacy != candidate:
                public_changes.append(
                    {
                        "unit": task.task_id,
                        "entity_id": entity_id,
                        "top1_changed": legacy[:1] != candidate[:1],
                        "top3_changed": legacy[:3] != candidate[:3],
                        "legacy": legacy,
                        "candidate": candidate,
                    }
                )
    report = {
        "schema_version": 1,
        "experiment": "retrieval_tokenizer_punctuation_v1",
        "baseline_git_commit": "106117f",
        "official_track4_commit": "7b2bce1d80d96f5d5667d7f67bfaa945fa5d1491",
        "hypothesis": "Removing sentence-edge punctuation from lexical tokens restores exact entity and keyword matches without damaging financial numeric tokens.",
        "token_examples": {
            "candidate": tokenize("action_flat. $5.28, 10%; 2024-10-31 year-over-year."),
            "legacy": legacy_tokenize("action_flat. $5.28, 10%; 2024-10-31 year-over-year."),
        },
        "synthetic": {
            "legacy_top1_correct": sum(row["legacy_correct"] for row in synthetic_rows),
            "candidate_top1_correct": sum(row["candidate_correct"] for row in synthetic_rows),
            "rows": synthetic_rows,
        },
        "public": {
            "rows": public_rows,
            "rows_changed_top8": len(public_changes),
            "rows_changed_top1": sum(row["top1_changed"] for row in public_changes),
            "rows_changed_top3": sum(row["top3_changed"] for row in public_changes),
            "changed_units": sorted({row["unit"] for row in public_changes}),
            "changes": public_changes,
        },
        "decision_rule": "Require 13/13 synthetic top-1, token preservation tests, unchanged public predictions and smoke; rerun official NLI for every public unit with a changed top-three retrieval set.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "synthetic_legacy": report["synthetic"]["legacy_top1_correct"],
                "synthetic_candidate": report["synthetic"]["candidate_top1_correct"],
                **{key: value for key, value in report["public"].items() if key != "changes"},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
