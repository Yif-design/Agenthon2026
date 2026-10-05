#!/usr/bin/env python3
"""Screen bounded temporal query values before changing production retrieval."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from t4agent.retrieve import BM25, Chunk, allowed_document_ids, build_index, query_for
from t4agent.taskio import Task, load_task


TEMPORAL_FIELDS = (
    "quarter_reported",
    "prior_year_quarter",
    "report_datetime",
    "ref_month",
    "latest_published_ref_month",
    "as_of",
    "auction_date",
    "latest_precutoff_vintage",
    "resolving_release_date",
)


def candidate_query(task: Task, entity: dict) -> str:
    base = query_for(task, entity)
    temporal = [str(entity[key]) for key in TEMPORAL_FIELDS if entity.get(key) not in (None, "")]
    return " ".join((base, *temporal))


def synthetic_task(family: str, target_name: str, entity: dict) -> Task:
    return Task(
        raw={},
        task_id=f"screen-{family}",
        schema_version="3",
        target={"name": target_name, "type": "regression"},
        target_type="regression",
        labels=[],
        entities=[entity],
        cutoff_date="2025-01-01",
        interval_level=0.9,
        prompt="",
        family=family,
    )


def synthetic_results() -> list[dict]:
    cases = [
        (
            synthetic_task(
                "eps_yoy_direction",
                "eps_yoy_direction",
                {"entity_id": "ACME", "name": "Acme", "quarter_reported": "2024Q3"},
            ),
            [
                Chunk("A_DISTRACTOR", "2024-01-01", 0, 42, "Acme EPS earnings outlook for 2023Q3 period."),
                Chunk("Z_MATCH", "2024-10-01", 0, 37, "Acme EPS earnings outlook for 2024Q3."),
            ],
        ),
        (
            synthetic_task(
                "rate_curve",
                "yield_change_bps",
                {"entity_id": "US10Y", "name": "10-year", "tenor": "10Y", "as_of": "2024-09-18"},
            ),
            [
                Chunk("A_DISTRACTOR", "2024-01-31", 0, 53, "10-year FOMC policy yield curve snapshot 2024-01-31."),
                Chunk("Z_MATCH", "2024-09-18", 0, 53, "10-year FOMC policy yield curve snapshot 2024-09-18."),
            ],
        ),
        (
            synthetic_task(
                "auction_demand",
                "bid_to_cover",
                {"entity_id": "US7Y", "name": "7-year", "tenor": "7Y", "auction_date": "2024-11-27"},
            ),
            [
                Chunk("A_DISTRACTOR", "2024-10-31", 0, 51, "7-year auction bid cover demand held 2024-10-31."),
                Chunk("Z_MATCH", "2024-11-27", 0, 51, "7-year auction bid cover demand held 2024-11-27."),
            ],
        ),
    ]
    out = []
    for task, chunks in cases:
        entity = task.entities[0]
        engine = BM25(chunks)
        baseline = engine.search(query_for(task, entity), top_k=1)[0].chunk.doc_id
        candidate = engine.search(candidate_query(task, entity), top_k=1)[0].chunk.doc_id
        out.append(
            {
                "family": task.family,
                "baseline_top1": baseline,
                "candidate_top1": candidate,
                "baseline_correct": baseline == "Z_MATCH",
                "candidate_correct": candidate == "Z_MATCH",
            }
        )
    return out


def public_results(units_dir: Path) -> dict:
    rows = 0
    top1_changed = 0
    top3_changed = 0
    by_family: Counter[str] = Counter()
    examples = []
    for task_path in sorted(units_dir.glob("*/task.json")):
        task = load_task(task_path)
        corpus = build_index(task_path.parent / "corpus", task.cutoff_date)
        engine = BM25(corpus.chunks)
        for entity in task.entities:
            rows += 1
            allowed = allowed_document_ids(task, entity, corpus)
            baseline = engine.search(query_for(task, entity), top_k=3, allowed_doc_ids=allowed)
            candidate = engine.search(candidate_query(task, entity), top_k=3, allowed_doc_ids=allowed)
            base_ids = [item.chunk.doc_id for item in baseline]
            candidate_ids = [item.chunk.doc_id for item in candidate]
            if base_ids[:1] != candidate_ids[:1]:
                top1_changed += 1
                by_family[task.family] += 1
                examples.append(
                    {
                        "task_id": task.task_id,
                        "entity_id": str(entity.get("entity_id", "")),
                        "baseline_top1": base_ids[0] if base_ids else None,
                        "candidate_top1": candidate_ids[0] if candidate_ids else None,
                    }
                )
            if base_ids != candidate_ids:
                top3_changed += 1
    return {
        "units": len(list(units_dir.glob("*/task.json"))),
        "rows": rows,
        "top1_changed": top1_changed,
        "top3_changed": top3_changed,
        "top1_changed_by_family": dict(sorted(by_family.items())),
        "top1_examples": examples,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    synthetic = synthetic_results()
    public = public_results(args.units_dir)
    synthetic_before = sum(item["baseline_correct"] for item in synthetic)
    synthetic_after = sum(item["candidate_correct"] for item in synthetic)
    accepted_for_implementation = (
        synthetic_after == 3
        and synthetic_before == 0
        and public["top1_changed"] <= 7
        and public["top3_changed"] <= 15
    )
    report = {
        "schema_version": 1,
        "experiment": "known_family_temporal_query_screen_v1",
        "baseline_git_commit": "751d04db14b1d464e3e7ec6916913c6c5900f51a",
        "hypothesis": "Appending bounded task-supplied temporal values improves period-specific retrieval across known families without broad public citation churn.",
        "decision_rule": "Proceed to production A/B only if all 3 target families move from wrong to correct top-1 and public changes stay at <=7/78 top-1 and <=15/78 top-3 rows.",
        "synthetic": {
            "baseline_correct": synthetic_before,
            "candidate_correct": synthetic_after,
            "total": len(synthetic),
            "cases": synthetic,
        },
        "public": public,
        "decision": "proceed_to_implementation" if accepted_for_implementation else "reject_before_code",
        "model_api": {"requests": 0, "input_tokens": 0, "output_tokens": 0},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
