#!/usr/bin/env python3
"""Compare the legacy numeric-only generic input path with bounded scalar projection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from t4agent.family_specs import (  # noqa: E402
    GENERIC_MAX_SCALAR_FIELDS,
    GENERIC_STRING_FIELD_LIMIT,
    GENERIC_TOTAL_STRING_LIMIT,
    SPECS,
    project_entity,
)
from t4agent.retrieve import BM25, Chunk, query_for  # noqa: E402
from t4agent.taskio import Task  # noqa: E402


CASES: tuple[dict[str, Any], ...] = (
    {
        "target_type": "classification",
        "target_name": "future_credit_state",
        "field": "rating_bucket",
        "value": "deep speculative",
        "wrong": "The issuer remains investment grade.",
        "right": "The issuer is in a deep speculative rating bucket.",
    },
    {
        "target_type": "regression",
        "target_name": "future_delivery_delay_days",
        "field": "demand_regime",
        "value": "supply constrained",
        "wrong": "Supply and demand are balanced.",
        "right": "The market remains supply constrained.",
    },
    {
        "target_type": "ranking",
        "target_name": "relative_rate_move_rank",
        "field": "policy_stance",
        "value": "aggressive easing",
        "wrong": "Policy remains in a tightening stance.",
        "right": "The authority signaled aggressive easing.",
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def make_task(case: dict[str, Any], entity: dict[str, Any]) -> Task:
    target_type = str(case["target_type"])
    labels = ["positive", "negative"] if target_type == "classification" else []
    return Task(
        raw={},
        task_id=f"synthetic-{target_type}",
        schema_version="3",
        target={"name": case["target_name"], "type": target_type, "labels": labels},
        target_type=target_type,
        labels=labels,
        entities=[entity],
        cutoff_date="2024-01-01",
        interval_level=0.9,
        prompt="Use the supplied entity features and frozen evidence.",
        family="unseen_family",
    )


def legacy_projection(entity: dict[str, Any]) -> dict[str, Any]:
    projected = {key: entity[key] for key in ("entity_id", "name", "unit", "units") if key in entity}
    projected.update(
        {
            key: value
            for key, value in entity.items()
            if not isinstance(value, bool) and isinstance(value, (int, float))
        }
    )
    return projected


def main() -> None:
    args = parse_args()
    rows = []
    for index, case in enumerate(CASES):
        entity = {"entity_id": f"E{index}", case["field"]: case["value"]}
        task = make_task(case, entity)
        wrong = Chunk(f"WRONG_{index}", "2023-01-01", 0, len(case["wrong"]), case["wrong"])
        right = Chunk(f"RIGHT_{index}", "2023-01-01", 0, len(case["right"]), case["right"])
        bm25 = BM25([wrong, right])
        legacy_top1 = bm25.search(query_for(task, entity), top_k=1)[0].chunk.doc_id
        candidate_top1 = bm25.search(
            query_for(task, entity, include_all_scalar_fields=True), top_k=1
        )[0].chunk.doc_id
        old = legacy_projection(entity)
        new = project_entity(entity, SPECS["generic"])
        rows.append(
            {
                "target_type": case["target_type"],
                "field": case["field"],
                "legacy_field_visible": case["field"] in old,
                "candidate_field_visible": new.get(case["field"]) == case["value"],
                "legacy_retrieval_correct": legacy_top1 == right.doc_id,
                "candidate_retrieval_correct": candidate_top1 == right.doc_id,
            }
        )

    long_value = "x" * (GENERIC_STRING_FIELD_LIMIT + 200)
    bounded = project_entity(
        {
            "entity_id": "BOUND",
            "text_feature": long_value,
            "flag": True,
            "nested": {"ignored": True},
            "items": ["ignored"],
            "corpus_ref": "corpus/bound/",
        },
        SPECS["generic"],
    )
    many_fields = {"entity_id": "MANY"}
    many_fields.update({f"text_{index}": "y" * GENERIC_STRING_FIELD_LIMIT for index in range(80)})
    many_bounded = project_entity(many_fields, SPECS["generic"])
    report = {
        "schema_version": 1,
        "experiment": "generic_scalar_projection_v1",
        "baseline_git_commit": "61e9832c7da30256f75083cb25f92c7d53a8c017",
        "hypothesis": "Unknown-family rows need bounded categorical, boolean and text scalar features in both the model packet and lexical query; numeric-only projection silently removes official input types.",
        "dataset": "Three synthetic unseen schemas covering classification, regression and ranking.",
        "rows": rows,
        "results": {
            "legacy_scalar_fields_visible": sum(row["legacy_field_visible"] for row in rows),
            "candidate_scalar_fields_visible": sum(row["candidate_field_visible"] for row in rows),
            "legacy_top1_correct": sum(row["legacy_retrieval_correct"] for row in rows),
            "candidate_top1_correct": sum(row["candidate_retrieval_correct"] for row in rows),
            "cases": len(rows),
            "long_string_chars_input": len(long_value),
            "long_string_chars_projected": len(str(bounded["text_feature"])),
            "boolean_preserved": bounded.get("flag") is True,
            "nested_values_excluded": "nested" not in bounded and "items" not in bounded,
            "corpus_ref_excluded_from_model_packet": "corpus_ref" not in bounded,
            "many_fields_projected": len(many_bounded),
            "max_scalar_fields": GENERIC_MAX_SCALAR_FIELDS,
            "many_fields_string_chars": sum(
                len(value) for value in many_bounded.values() if isinstance(value, str)
            ),
            "total_string_char_limit": GENERIC_TOTAL_STRING_LIMIT,
        },
        "decision_rule": "Require scalar visibility and correct top-1 retrieval for all three target types, 1000-character string bounding, nested-value exclusion, unchanged known-family projection, and byte-identical public outputs.",
        "not_measured": "Predictive quality; this experiment isolates input and retrieval reachability for previously unseen schemas.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["results"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
