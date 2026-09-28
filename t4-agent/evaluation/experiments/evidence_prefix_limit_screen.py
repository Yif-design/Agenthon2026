#!/usr/bin/env python3
"""Screen shorter evidence prefixes against previously validated remote-model facts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


CURRENT_LIMIT = 1400
CANDIDATE_LIMITS = (800, 900, 1000, 1100, 1200, 1300, 1400)


def quote_position(row: dict, fact: dict) -> tuple[int, int] | None:
    quote = fact.get("quote")
    doc_id = fact.get("doc_id")
    if not isinstance(quote, str) or not quote:
        return None
    matches = []
    for chunk in row.get("retrieved_chunks") or []:
        if chunk.get("doc_id") != doc_id:
            continue
        start = str(chunk.get("text", "")).find(quote)
        if start >= 0:
            matches.append((start, start + len(quote)))
    return min(matches) if matches else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline-commit", required=True)
    args = parser.parse_args()

    facts = []
    for rows_path in sorted(args.trace_root.glob("*/trace/rows.json")):
        task_id = rows_path.parent.parent.name
        route_path = rows_path.parent / "route.json"
        route = json.loads(route_path.read_text()) if route_path.exists() else {}
        family = str(route.get("family", "unknown"))
        for row in json.loads(rows_path.read_text()):
            for fact in row.get("validated_facts") or []:
                if fact.get("extractor") != "qwen":
                    continue
                position = quote_position(row, fact)
                if position is None:
                    continue
                facts.append(
                    {
                        "task_id": task_id,
                        "family": family,
                        "entity_id": row.get("entity_id"),
                        "fact_name": fact.get("name"),
                        "quote_start": position[0],
                        "quote_end": position[1],
                    }
                )

    candidates = []
    total = len(facts)
    for limit in CANDIDATE_LIMITS:
        preserved = [fact for fact in facts if fact["quote_end"] <= limit]
        families = sorted({fact["family"] for fact in preserved})
        candidates.append(
            {
                "limit_chars": limit,
                "facts_preserved": len(preserved),
                "facts_total": total,
                "fact_retention_pct": 100 * len(preserved) / total if total else 0.0,
                "families_preserved": families,
                "maximum_possible_evidence_text_savings_pct": 100 * (CURRENT_LIMIT - limit) / CURRENT_LIMIT,
                "passes": (
                    len(preserved) == total
                    and len(families) >= 2
                    and 100 * (CURRENT_LIMIT - limit) / CURRENT_LIMIT >= 10.0
                ),
            }
        )

    passing = [candidate for candidate in candidates if candidate["passes"]]
    report = {
        "schema_version": 1,
        "experiment": "evidence_prefix_limit_screen_v1",
        "baseline_git_commit": args.baseline_commit,
        "source_trace_root": str(args.trace_root),
        "hypothesis": "One shorter global evidence prefix preserves every validated weak-model fact while reducing evidence text by at least 10% across multiple families.",
        "decision_rule": "Proceed only if a limit preserves 100% of validated qwen facts across at least two families and can save at least 10% of evidence text.",
        "facts": {
            "total": total,
            "tasks": sorted({fact["task_id"] for fact in facts}),
            "families": sorted({fact["family"] for fact in facts}),
            "maximum_quote_end": max((fact["quote_end"] for fact in facts), default=None),
        },
        "candidates": candidates,
        "decision": "proceed_to_remote_ab" if passing else "reject_before_code",
        "production_change": "none",
        "model_api": {"requests": 0, "input_tokens": 0, "output_tokens": 0},
        "local_llm_run": False,
        "caveat": "The savings percentage is an upper bound because excerpts shorter than the cap cannot save the full cap difference.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"decision": report["decision"], "facts": report["facts"], "candidates": candidates}, indent=2))


if __name__ == "__main__":
    main()
