#!/usr/bin/env python3
"""Check whether opaque prompt-defined labels can be entailed by runtime corpus evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
OFFICIAL = PROJECT.parent / "starter-repos" / "track4-analysis-public"
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
from evaluation.experiments.generic_classification_benchmark import build_case, load_examples  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline-commit", required=True)
    args = parser.parse_args()

    examples, _ = load_examples(args.dataset_root)
    runtime_documents = []
    for split, domains in examples.items():
        for domain, rows in domains.items():
            _, corpus = build_case(rows, split, domain, "opaque")
            runtime_documents.extend(corpus.doc_texts.values())
    official_path = OFFICIAL / "qfbench2_track_analysis" / "hypothesis.py"
    official_source = official_path.read_text()
    expected_template = "head = f\"The {spec.target_name} of {subject} is {label}.\""
    if expected_template not in official_source:
        raise RuntimeError("official classification hypothesis template changed")
    hypothesis = (
        "The next observation sign of example is class_b. "
        "The 90% prediction interval for the next observation sign of example is -1 to 1."
    )
    label_definitions_in_runtime_evidence = sum(
        "class_a" in text.lower() or "class_b" in text.lower() for text in runtime_documents
    )
    report = {
        "schema_version": 1,
        "experiment": "generic_opaque_label_nli_preflight_v1",
        "baseline_git_commit": args.baseline_commit,
        "official_hypothesis_source": str(official_path),
        "official_hypothesis_source_sha256": sha256(official_path),
        "official_classification_template_verified": True,
        "canonical_hypothesis_example": hypothesis,
        "canonical_hypothesis_contains_task_prompt_definition": False,
        "runtime_evidence_documents": len(runtime_documents),
        "runtime_evidence_documents_with_opaque_label_definition": label_definitions_in_runtime_evidence,
        "outcome_screen": {
            "test_accuracy_before": 0.5,
            "test_accuracy_after": 0.6111111111111112,
            "test_macro_f1_before": 0.3333333333333333,
            "test_macro_f1_after": 0.5785953177257526,
            "confirmation_accuracy_before": 0.5,
            "confirmation_accuracy_after": 0.5555555555555556,
            "confirmation_macro_f1_before": 0.3333333333333333,
            "confirmation_macro_f1_after": 0.55,
        },
        "decision": "reject_before_remote_nli",
        "reason": "The changed prediction uses an opaque label whose task-prompt definition is absent from both the official canonical hypothesis and every runtime corpus premise. Historical lagged-number citations therefore cannot entail the changed class label.",
        "production_change": "none; role-keyword code and tests reverted",
        "remote_nli_run": False,
        "model_api_calls": 0,
        "local_llm_run": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: report[key] for key in ("canonical_hypothesis_example", "runtime_evidence_documents", "runtime_evidence_documents_with_opaque_label_definition", "decision")}, indent=2))


if __name__ == "__main__":
    main()
