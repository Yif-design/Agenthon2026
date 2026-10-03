#!/usr/bin/env python3
"""Retest grounded unknown-label selection after the shared tokenizer repair."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from t4agent.calculators.generic import _label  # noqa: E402
from t4agent.llm import LLM  # noqa: E402
from t4agent.retrieve import BM25, Chunk  # noqa: E402


GROUPS: tuple[dict[str, Any], ...] = (
    {
        "id": "demand_tier",
        "prompt": "Label high when demand rises strongly, medium when stable, and low when it falls.",
        "labels": ["high", "medium", "low"],
        "rows": [
            ("tier_high", "Customer orders increased 18 percent from the prior quarter.", "high", 2),
            ("tier_medium", "Customer orders were unchanged from the prior quarter.", "medium", 0),
            ("tier_low", "Customer orders declined 12 percent from the prior quarter.", "low", -2),
        ],
    },
    {
        "id": "credit_action",
        "prompt": "Choose upgrade for improving credit quality, unchanged for stable credit quality, or downgrade for deterioration.",
        "labels": ["upgrade", "unchanged", "downgrade"],
        "rows": [
            ("action_up", "Leverage fell and interest coverage improved materially.", "upgrade", 2),
            ("action_flat", "Leverage and interest coverage were stable.", "unchanged", 0),
            ("action_down", "Leverage rose sharply and interest coverage deteriorated.", "downgrade", -2),
        ],
    },
    {
        "id": "capacity_action",
        "prompt": "Label expand if capacity will rise, hold if unchanged, or contract if it will fall.",
        "labels": ["expand", "hold", "contract"],
        "rows": [
            ("capacity_expand", "Management approved two new production lines for next quarter.", "expand", 2),
            ("capacity_hold", "Management plans to keep production capacity unchanged next quarter.", "hold", 0),
            ("capacity_contract", "Management will close one production line next quarter.", "contract", -2),
        ],
    },
    {
        "id": "covenant_risk",
        "prompt": "Label at_risk if covenant failure is likely, otherwise not_at_risk.",
        "labels": ["at_risk", "not_at_risk"],
        "rows": [
            ("risk_yes", "Liquidity is insufficient and a covenant breach is expected next quarter.", "at_risk", 2),
            ("risk_no", "The company has ample liquidity and expects to remain in covenant compliance.", "not_at_risk", -2),
        ],
    },
    {
        "id": "quality_gate",
        "prompt": "Label pass when every quality requirement is met, otherwise fail.",
        "labels": ["pass", "fail"],
        "rows": [
            ("quality_pass", "The sample met every stated quality requirement.", "pass", 2),
            ("quality_fail", "The sample exceeded the maximum impurity limit.", "fail", -2),
        ],
    },
)

SYSTEM = """Classify every item using only its evidence and the supplied allowed labels.
Return one JSON object and no prose. Copy one exact supporting quote and its doc_id for every item."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def _group_prompt(group: dict[str, Any], index: BM25) -> tuple[str, dict[str, Chunk]]:
    selected: dict[str, Chunk] = {}
    items = []
    for entity_id, _, _, _ in group["rows"]:
        chunk = index.search(entity_id, top_k=1)[0].chunk
        selected[entity_id] = chunk
        items.append(
            {
                "entity_id": entity_id,
                "doc_id": chunk.doc_id,
                "evidence": chunk.text,
            }
        )
    request = {
        "instruction": group["prompt"],
        "allowed_labels": group["labels"],
        "items": items,
    }
    schema = {
        "entities": [
            {
                "entity_id": "copy entity_id",
                "label": "exactly one allowed label",
                "doc_id": "copy that item's doc_id",
                "quote": "one verbatim supporting passage from that item's evidence",
            }
        ]
    }
    return (
        "REQUEST_JSON:\n"
        + json.dumps(request, ensure_ascii=False, sort_keys=True)
        + "\nOUTPUT_SCHEMA_JSON:\n"
        + json.dumps(schema, ensure_ascii=False)
    ), selected


def _validated_rows(
    parsed: dict[str, Any] | None,
    group: dict[str, Any],
    selected: dict[str, Chunk],
) -> dict[str, dict[str, Any]]:
    raw_rows = parsed.get("entities") if isinstance(parsed, dict) else None
    if not isinstance(raw_rows, list):
        return {}
    allowed = set(group["labels"])
    output: dict[str, dict[str, Any]] = {}
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        entity_id = str(raw.get("entity_id", ""))
        chunk = selected.get(entity_id)
        label = raw.get("label")
        doc_id = raw.get("doc_id")
        quote = raw.get("quote")
        if (
            chunk is None
            or entity_id in output
            or label not in allowed
            or doc_id != chunk.doc_id
            or not isinstance(quote, str)
            or not quote
            or quote not in chunk.text
        ):
            continue
        output[entity_id] = {"label": label, "doc_id": doc_id, "quote": quote}
    return output


def main() -> None:
    args = parse_args()
    llm = LLM(PROJECT)
    if not llm.enabled:
        raise SystemExit("MODEL_ENDPOINT and a usable project credential are required")
    rows = []
    retrieved_correct = 0
    for group in GROUPS:
        chunks = []
        expected_docs = {}
        for entity_id, evidence, _, _ in group["rows"]:
            doc_id = f"SYNTH_{entity_id.upper()}"
            text = f"{entity_id}. {evidence}"
            chunks.append(Chunk(doc_id, "2023-12-31", 0, len(text), text))
            expected_docs[entity_id] = doc_id
        index = BM25(chunks)
        prompt, selected = _group_prompt(group, index)
        retrieved_correct += sum(
            selected[entity_id].doc_id == expected_docs[entity_id]
            for entity_id, _, _, _ in group["rows"]
        )
        parsed = llm.chat_json(SYSTEM, prompt, max_tokens=900)
        validated = _validated_rows(parsed, group, selected)
        for entity_id, _, expected, signal in group["rows"]:
            baseline = _label(signal, group["labels"])
            item = validated.get(entity_id)
            candidate = item["label"] if item else baseline
            rows.append(
                {
                    "group": group["id"],
                    "entity_id": entity_id,
                    "expected": expected,
                    "baseline": baseline,
                    "candidate": candidate,
                    "baseline_correct": baseline == expected,
                    "candidate_correct": candidate == expected,
                    "retrieved_doc_correct": selected[entity_id].doc_id == expected_docs[entity_id],
                    "validated_label_quote": item is not None,
                }
            )
    report = {
        "schema_version": 1,
        "experiment": "generic_grounded_direct_label_v2_retest",
        "baseline_git_commit": "0a9682b21e04ec0bc91e941e9c238c55c3f18399",
        "dataset": "13 synthetic rows across five unseen label schemas",
        "model": llm.model,
        "temperature": llm.temperature,
        "seed": llm.seed,
        "baseline_correct": sum(row["baseline_correct"] for row in rows),
        "candidate_correct": sum(row["candidate_correct"] for row in rows),
        "retrieved_correct": retrieved_correct,
        "validated_label_quotes": sum(row["validated_label_quote"] for row in rows),
        "total_rows": len(rows),
        "usage": {
            "calls": llm.usage.calls,
            "prompt_tokens": llm.usage.prompt_tokens,
            "completion_tokens": llm.usage.completion_tokens,
            "cost": llm.usage.total_cost,
            "errors": llm.usage.errors,
        },
        "rows": rows,
        "decision_rule": "Advance only if two fixed seeds each score at least 12/13, validate all 13 label quotes, and stay within the 25-request unit limit.",
        "limitation": "Synthetic schema robustness evidence only; no real-outcome predictive claim.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "seed",
                    "baseline_correct",
                    "candidate_correct",
                    "retrieved_correct",
                    "validated_label_quotes",
                    "total_rows",
                    "usage",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
