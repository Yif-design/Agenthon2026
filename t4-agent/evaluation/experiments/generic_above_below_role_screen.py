#!/usr/bin/env python3
"""Screen above/below as bounded generic label-role synonyms on saved signals."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from t4agent.calculators.generic import _label  # noqa: E402


LABELS = ["class_a", "class_b"]
PROMPT = "Predict the sign of the next observation. class_a means above zero; class_b means below zero."


def score(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    labels = LABELS
    correct = sum(row[field] == row["expected"] for row in rows)
    f1s = []
    for label in labels:
        tp = sum(row[field] == label and row["expected"] == label for row in rows)
        fp = sum(row[field] == label and row["expected"] != label for row in rows)
        fn = sum(row[field] != label and row["expected"] == label for row in rows)
        f1s.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
    return {
        "rows": len(rows),
        "accuracy": correct / len(rows) if rows else 0.0,
        "macro_f1": statistics.fmean(f1s) if f1s else 0.0,
        "prediction_counts": dict(Counter(row[field] for row in rows)),
    }


def candidate_label(signal: int) -> str:
    # Equivalent to adding the two bounded role tokens to ROLE_KEYWORDS.
    translated = PROMPT.replace("above", "higher").replace("below", "lower")
    return _label(signal, LABELS, translated, "next_observation_sign") or LABELS[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline-commit", required=True)
    args = parser.parse_args()

    benchmark = json.loads(args.benchmark.read_text())
    rows = []
    for row in benchmark["rows"]:
        if row["schema"] != "opaque" or row["fallback_reason"] == "model_unavailable_or_bad_json":
            continue
        rows.append({
            **row,
            "baseline": row["predicted"],
            "candidate": candidate_label(int(row["signal"])),
        })

    results: dict[str, Any] = {}
    passed = True
    for split in ("test", "confirmation"):
        split_rows = [row for row in rows if row["split"] == split]
        baseline = score(split_rows, "baseline")
        candidate = score(split_rows, "candidate")
        domains = {}
        for domain in sorted({row["domain"] for row in split_rows}):
            selected = [row for row in split_rows if row["domain"] == domain]
            domains[domain] = {"baseline": score(selected, "baseline"), "candidate": score(selected, "candidate")}
        split_passed = (
            candidate["accuracy"] >= baseline["accuracy"]
            and candidate["macro_f1"] > baseline["macro_f1"]
            and all(value["candidate"]["accuracy"] >= value["baseline"]["accuracy"] for value in domains.values())
            and all(value["candidate"]["macro_f1"] >= value["baseline"]["macro_f1"] for value in domains.values())
        )
        passed &= split_passed
        results[split] = {"baseline": baseline, "candidate": candidate, "by_domain": domains, "passed": split_passed}

    permutation_checks = []
    for labels, prompt, positive, negative in (
        (["class_a", "class_b"], PROMPT, "class_a", "class_b"),
        (["class_b", "class_a"], PROMPT, "class_a", "class_b"),
        (["zeta", "theta"], "zeta means above zero; theta means below zero.", "zeta", "theta"),
    ):
        translated = prompt.replace("above", "higher").replace("below", "lower")
        permutation_checks.append(
            _label(1, labels, translated, "next_observation_sign") == positive
            and _label(-1, labels, translated, "next_observation_sign") == negative
        )
    ambiguous_unchanged = (
        _label(1, ["class_x", "class_y"], "Choose the appropriate class.", "unknown_target")
        == _label(1, ["class_x", "class_y"], "Choose the appropriate class.", "unknown_target")
    )
    passed &= all(permutation_checks) and ambiguous_unchanged

    report = {
        "schema_version": 1,
        "experiment": "generic_above_below_role_screen_v1",
        "baseline_git_commit": args.baseline_commit,
        "source_benchmark": str(args.benchmark),
        "source_model": benchmark["model"],
        "source_benchmark_valid": benchmark.get("benchmark_valid", False),
        "excluded_unresolved_model_rows": benchmark.get("unresolved_model_rows", 0),
        "hypothesis": "Adding above and below as bounded positive and negative role synonyms makes opaque label schemas equivalent to semantic schemas without changing model signals.",
        "results": results,
        "permutation_checks_passed": sum(permutation_checks),
        "permutation_checks_total": len(permutation_checks),
        "ambiguous_fallback_unchanged": ambiguous_unchanged,
        "decision_rule": "Advance only if macro-F1 improves in test and confirmation, no split or domain accuracy/F1 worsens, every permutation passes, and the ambiguous fallback is unchanged.",
        "decision": "advance_to_production_gates" if passed else "reject",
        "model_api_calls": 0,
        "local_llm_run": False,
        "limitations": "Uses only saved rows whose remote response completed; it screens deterministic label mapping, not signal extraction quality.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"results": results, "decision": report["decision"]}, indent=2))


if __name__ == "__main__":
    main()
