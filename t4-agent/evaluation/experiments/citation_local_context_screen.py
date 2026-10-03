#!/usr/bin/env python3
"""Screen whether quote-local context adds coverage beyond existing retrieved chunks."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from t4agent.family_specs import task_family_spec
from t4agent.retrieve import build_index, tokenize
from t4agent.taskio import load_task


CONTEXT_CLAIM = "Cutoff-safe retrieved context relevant to this entity and target."
BEFORE_CHARS = 120
AFTER_CHARS = 240


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def words(value: object) -> set[str]:
    return {token for token in tokenize(str(value or "")) if len(token) >= 3}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    rows = []
    answer_hashes = {}
    for unit_dir in sorted(path for path in args.units.iterdir() if (path / "task.json").exists()):
        answer_path = args.answers / unit_dir.name / "answer.json"
        if not answer_path.exists():
            continue
        task = load_task(unit_dir / "task.json")
        family = task_family_spec(
            task.family,
            str(task.target.get("name", "")),
            task.target_type,
            task.entities,
        ).key
        corpus = build_index(unit_dir / "corpus", task.cutoff_date)
        answer = json.loads(answer_path.read_text())
        answer_hashes[unit_dir.name] = sha256(answer_path)
        entities = {str(entity.get("entity_id", "")): entity for entity in task.entities}
        for prediction in answer["entity_predictions"]:
            entity_id = str(prediction.get("entity_id", ""))
            entity = entities.get(entity_id, {})
            claims = prediction.get("claims", [])
            context_claims = [claim for claim in claims if claim.get("claim") == CONTEXT_CLAIM]
            fact_claims = [claim for claim in claims if claim.get("claim") != CONTEXT_CLAIM]
            identity_terms = words(entity_id) | words(entity.get("name")) | words(entity.get("ticker"))
            target_terms = words(task.target.get("name")) | words(family)
            for fact in fact_claims:
                doc_id = str(fact.get("doc_id", ""))
                text = corpus.doc_texts.get(doc_id, "")
                start, end = fact.get("span_start"), fact.get("span_end")
                if not isinstance(start, int) or not isinstance(end, int) or not (0 <= start < end <= len(text)):
                    continue
                expanded_start = max(0, start - BEFORE_CHARS)
                expanded_end = min(len(text), end + AFTER_CHARS)
                expanded = text[expanded_start:expanded_end]
                original = text[start:end]
                covering_context = [
                    claim for claim in context_claims
                    if claim.get("doc_id") == doc_id
                    and isinstance(claim.get("span_start"), int)
                    and isinstance(claim.get("span_end"), int)
                    and claim["span_start"] <= expanded_start
                    and claim["span_end"] >= expanded_end
                ]
                original_terms = words(original)
                added_terms = words(expanded) - original_terms
                adds_identity = bool(identity_terms & added_terms)
                adds_target = bool(target_terms & added_terms)
                rows.append({
                    "unit_id": unit_dir.name,
                    "family": family,
                    "target_type": task.target_type,
                    "entity_id": entity_id,
                    "doc_id": doc_id,
                    "original_chars": end - start,
                    "expanded_chars": expanded_end - expanded_start,
                    "fully_covered_by_existing_context": bool(covering_context),
                    "adds_identity_term": adds_identity,
                    "adds_target_term": adds_target,
                    "qualifying_unique_completion": (
                        not covering_context and adds_identity and adds_target
                    ),
                })

    qualifying = [row for row in rows if row["qualifying_unique_completion"]]
    qualifying_entities = {(row["unit_id"], row["entity_id"]) for row in qualifying}
    families = {row["family"] for row in qualifying}
    target_types = {row["target_type"] for row in qualifying}
    decision = "advance" if len(families) >= 2 and len(target_types) >= 2 else "reject_before_production"
    result = {
        "experiment": "citation_local_context_screen_v1",
        "baseline_git_commit": "03d2bee36f93824095a79e776167bf223427bca5",
        "reference": {
            "repository": "https://github.com/wangzgui/agenthon-t4-baseline-2026",
            "commit": "420bee094775f30e43fd18e10982402c91d90e23",
            "license": "MIT",
            "method": {"before_chars": BEFORE_CHARS, "after_chars": AFTER_CHARS},
        },
        "hypothesis": (
            "A bounded window around a verified quote supplies identity and target context that "
            "the production fact citation and its existing retrieved chunks do not already cover."
        ),
        "decision_rule": (
            "Advance only if unique completions occur in at least two families and two target types. "
            "Any later production candidate may add at most one citation per affected row and must "
            "preserve every existing citation."
        ),
        "source_answers": str(args.answers),
        "answer_sha256": answer_hashes,
        "facts_screened": len(rows),
        "facts_fully_covered_by_existing_context": sum(
            row["fully_covered_by_existing_context"] for row in rows
        ),
        "facts_not_fully_covered": sum(
            not row["fully_covered_by_existing_context"] for row in rows
        ),
        "qualifying_unique_completions": len(qualifying),
        "qualifying_entities": len(qualifying_entities),
        "qualifying_families": sorted(families),
        "qualifying_target_types": sorted(target_types),
        "facts_by_family": dict(sorted(Counter(row["family"] for row in rows).items())),
        "decision": decision,
        "decision_reason": (
            "The cross-family and cross-target unique-completion gate passed."
            if decision == "advance"
            else "The bounded windows did not add unique identity-plus-target context across two families and two target types."
        ),
        "rows": rows,
        "model_api_calls": 0,
        "local_llm_run": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in (
        "facts_screened",
        "facts_fully_covered_by_existing_context",
        "facts_not_fully_covered",
        "qualifying_unique_completions",
        "qualifying_entities",
        "qualifying_families",
        "qualifying_target_types",
        "decision",
        "decision_reason",
    )}, indent=2))


if __name__ == "__main__":
    main()
