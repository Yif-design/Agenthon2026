#!/usr/bin/env python3
"""Benchmark the production generic classifier on time-forward real outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from evaluation.experiments.evidence_id_remote_ab import GeminiClient, OpenRouterClient  # noqa: E402
from t4agent.predict import predict_rows  # noqa: E402
from t4agent.retrieve import BM25, Chunk, IndexedCorpus  # noqa: E402
from t4agent.taskio import Task  # noqa: E402


SCHEMAS = {
    "semantic": {
        "labels": ["up", "down"],
        "prompt": "Predict the sign of the next observation. Use up when it will be above zero and down when it will be below zero.",
        "expected": {1: "up", -1: "down"},
    },
    "opaque": {
        "labels": ["class_a", "class_b"],
        "prompt": "Predict the sign of the next observation. class_a means above zero; class_b means below zero.",
        "expected": {1: "class_a", -1: "class_b"},
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _balanced(rows: list[dict[str, Any]], count_per_class: int = 3) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for direction in (1, -1):
        selected.extend([row for row in rows if row["truth_direction"] == direction][:count_per_class])
    return sorted(selected, key=lambda row: row["entity_id"])


def load_examples(root: Path) -> tuple[dict[str, dict[str, list[dict[str, Any]]]], dict[str, str]]:
    paths = {
        "cpi": root / "cpi" / "components_2015_2023.json",
        "cpi_confirmation": root / "cpi" / "components_2024_2025_confirmation.json",
        "cot": root / "cot" / "legacy10_2015_2023.json",
        "macro_revision": root / "macro_revision" / "alfred_monthend_2014_2024.json",
    }
    docs = {name: json.loads(path.read_text()) for name, path in paths.items()}
    output: dict[str, dict[str, list[dict[str, Any]]]] = {"test": {}, "confirmation": {}}

    for split, document, years in (
        ("test", docs["cpi"], {"2022"}),
        ("confirmation", docs["cpi_confirmation"], {"2024", "2025"}),
    ):
        rows = []
        for row in document["rows"]:
            if row["ref_month"][:4] not in years or not row["known_mom_pct"]:
                continue
            truth = sign(float(row["target_mom_pct"]))
            if not truth:
                continue
            feature = float(row["known_mom_pct"][-1])
            rows.append({
                "entity_id": f"cpi-{row['ref_month']}-{row['entity_id']}",
                "cutoff": row["cutoff_vintage"],
                "feature": feature,
                "truth_direction": truth,
                "evidence": f"At the cutoff, the latest published month-over-month component change was {feature:+.6f} percent.",
            })
        output[split]["cpi"] = _balanced(sorted(rows, key=lambda row: row["entity_id"]))

    for split, years in (("test", {"2022"}), ("confirmation", {"2023"})):
        rows = []
        for group in docs["cot"]["groups"]:
            if group["start_date"][:4] not in years:
                continue
            for row in group["rows"]:
                truth = sign(float(row["target_5wk_change_pct_start_oi"]))
                if not truth:
                    continue
                feature = float(row["trailing_4wk_net_change_pct_oi"])
                rows.append({
                    "entity_id": f"cot-{group['start_date']}-{row['entity_id']}",
                    "cutoff": group["start_date"],
                    "feature": feature,
                    "truth_direction": truth,
                    "evidence": f"At the cutoff, the trailing four-week net-position change was {feature:+.6f} percent of open interest.",
                })
        output[split]["cot"] = _balanced(sorted(rows, key=lambda row: row["entity_id"]))

    for split, years in (("test", {"2021", "2022"}), ("confirmation", {"2023"})):
        rows = []
        for row in docs["macro_revision"]["rows"]:
            if row["cutoff_vintage"][:4] not in years or not row["all_history_changes"]:
                continue
            truth = sign(float(row["target_change"]))
            if not truth:
                continue
            feature = float(statistics.median(row["all_history_changes"]))
            rows.append({
                "entity_id": f"macro-{row['cutoff_vintage']}-{row['series_id']}-{row['ref_month']}",
                "cutoff": row["cutoff_vintage"],
                "feature": feature,
                "truth_direction": truth,
                "evidence": f"At the cutoff, the median historical revision for this series was {feature:+.6f} in the series unit.",
            })
        output[split]["macro_revision"] = _balanced(sorted(rows, key=lambda row: row["entity_id"]))
    return output, {name: sha256(path) for name, path in paths.items()}


def build_case(rows: list[dict[str, Any]], split: str, domain: str, schema_name: str) -> tuple[Task, IndexedCorpus]:
    schema = SCHEMAS[schema_name]
    entities = []
    chunks = []
    documents: dict[str, str] = {}
    dates: dict[str, str] = {}
    paths: dict[str, str] = {}
    for row in rows:
        doc_id = "BENCH_" + hashlib.sha256(row["entity_id"].encode()).hexdigest()[:16].upper()
        text = row["evidence"]
        documents[doc_id] = text
        dates[doc_id] = row["cutoff"]
        paths[doc_id] = f"{doc_id}.txt"
        chunks.append(Chunk(doc_id, row["cutoff"], 0, len(text), text))
        entities.append({
            "entity_id": row["entity_id"],
            "latest_signal_value": row["feature"],
            "corpus_ref": f"corpus/{doc_id}.txt",
        })
    task = Task(
        raw={},
        task_id=f"generic-classification-{split}-{domain}-{schema_name}",
        schema_version="3",
        target={"name": "next_observation_sign", "type": "classification", "labels": schema["labels"]},
        target_type="classification",
        labels=list(schema["labels"]),
        entities=entities,
        cutoff_date=max(row["cutoff"] for row in rows),
        interval_level=0.9,
        prompt=schema["prompt"],
        family="unseen_directional_task",
    )
    return task, IndexedCorpus(chunks, documents, dates, paths)


def metrics(rows: list[dict[str, Any]], labels: list[str]) -> dict[str, Any]:
    total = len(rows)
    correct = sum(row["predicted"] == row["expected"] for row in rows)
    f1s = []
    for label in labels:
        tp = sum(row["predicted"] == label and row["expected"] == label for row in rows)
        fp = sum(row["predicted"] == label and row["expected"] != label for row in rows)
        fn = sum(row["predicted"] != label and row["expected"] == label for row in rows)
        f1s.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
    # Mean squared error across both one-hot class coordinates; hard predictions have no confidence output.
    brier = statistics.fmean(
        statistics.fmean((float(row["predicted"] == label) - float(row["expected"] == label)) ** 2 for label in labels)
        for row in rows
    )
    return {
        "rows": total,
        "accuracy": correct / total if total else 0.0,
        "macro_f1": statistics.fmean(f1s) if f1s else 0.0,
        "hard_label_brier": brier,
        "nonzero_signal_rate": sum(row["signal"] != 0 for row in rows) / total if total else 0.0,
        "validated_signal_quote_rate": sum(row["signal"] == 0 or row["validated_signal_quote"] for row in rows) / total if total else 0.0,
        "fallback_rate": sum(bool(row["fallback_reason"]) for row in rows) / total if total else 0.0,
        "prediction_counts": dict(Counter(row["predicted"] for row in rows)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("gemini", "openrouter"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, default=PROJECT / "evaluation" / "datasets")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline-commit", required=True)
    args = parser.parse_args()

    examples, hashes = load_examples(args.dataset_root)
    key = args.key_file.read_text().strip()
    client = GeminiClient(args.model, key) if args.provider == "gemini" else OpenRouterClient(args.model, key)
    old_batch = os.environ.get("T4_MODEL_BATCH_SIZE")
    os.environ["T4_MODEL_BATCH_SIZE"] = "6"
    result_rows: list[dict[str, Any]] = []
    try:
        for split, domains in examples.items():
            for domain, rows in domains.items():
                for schema_name, schema in SCHEMAS.items():
                    task, corpus = build_case(rows, split, domain, schema_name)
                    results = predict_rows(task, BM25(corpus.chunks), corpus, client, 2)
                    by_id = {row["entity_id"]: row for row in rows}
                    for result in results:
                        source = by_id[result.prediction["entity_id"]]
                        signal = int((result.calculator_inputs or {}).get("signals", {}).get("directional_signal", 0))
                        result_rows.append({
                            "split": split,
                            "domain": domain,
                            "schema": schema_name,
                            "entity_id": source["entity_id"],
                            "feature": source["feature"],
                            "truth_direction": source["truth_direction"],
                            "expected": schema["expected"][source["truth_direction"]],
                            "predicted": result.prediction["label"],
                            "signal": signal,
                            "validated_signal_quote": any(fact.name == "directional_signal" for fact in result.facts),
                            "fallback_reason": result.fallback_reason,
                            "rejected_fact_reasons": [fact.reason for fact in result.rejected_facts],
                        })
    finally:
        if old_batch is None:
            os.environ.pop("T4_MODEL_BATCH_SIZE", None)
        else:
            os.environ["T4_MODEL_BATCH_SIZE"] = old_batch

    scores: dict[str, Any] = {}
    for split in examples:
        scores[split] = {}
        for schema_name, schema in SCHEMAS.items():
            selected = [row for row in result_rows if row["split"] == split and row["schema"] == schema_name]
            scores[split][schema_name] = metrics(selected, schema["labels"])
            scores[split][schema_name]["by_domain"] = {
                domain: metrics([row for row in selected if row["domain"] == domain], schema["labels"])
                for domain in sorted(examples[split])
            }
    paired = {}
    for split in examples:
        semantic = {row["entity_id"]: row for row in result_rows if row["split"] == split and row["schema"] == "semantic"}
        opaque = {row["entity_id"]: row for row in result_rows if row["split"] == split and row["schema"] == "opaque"}
        paired[split] = {
            "rows": len(semantic),
            "same_directional_signal": sum(semantic[key]["signal"] == opaque[key]["signal"] for key in semantic),
            "same_correctness": sum(
                (semantic[key]["predicted"] == semantic[key]["expected"])
                == (opaque[key]["predicted"] == opaque[key]["expected"])
                for key in semantic
            ),
        }
    report = {
        "schema_version": 1,
        "experiment": "generic_classification_benchmark_v1",
        "baseline_git_commit": args.baseline_commit,
        "provider": args.provider,
        "model": args.model,
        "hypothesis": "The production generic signal extractor plus deterministic label mapper beats the neutral first-label fallback consistently across time-forward domains and semantic versus opaque labels.",
        "dataset_sha256": hashes,
        "sampling": "For each split and domain, first three positive and first three negative outcomes after deterministic entity/date sorting.",
        "outcome_leakage_control": "Future outcomes are used only by the scorer; model evidence contains one cutoff-safe lagged feature and no target outcome.",
        "scores": scores,
        "schema_pair_consistency": paired,
        "usage": {
            "calls": client.usage.calls,
            "prompt_tokens": client.usage.prompt_tokens,
            "completion_tokens": client.usage.completion_tokens,
            "errors": client.usage.errors,
        },
        "rows": result_rows,
        "unresolved_model_rows": sum(
            row["fallback_reason"] == "model_unavailable_or_bad_json" for row in result_rows
        ),
        "benchmark_valid": (
            len(result_rows) == 72
            and not client.usage.errors
            and not any(row["fallback_reason"] == "model_unavailable_or_bad_json" for row in result_rows)
            and all(
                row["signal"] == 0 or row["validated_signal_quote"]
                for row in result_rows
            )
            and all(value["same_correctness"] == value["rows"] for value in paired.values())
            and client.usage.calls <= 25
        ),
        "benchmark_validity_gate": "Require 36 rows per schema, all non-neutral signal quotes validated, identical correctness across schemas, at most 25 requests, no unresolved model rows, and no API errors.",
        "production_adoption_gate": "No production change from this benchmark alone; any later candidate must improve macro-F1 on both test and confirmation without worsening any domain or faithfulness.",
        "local_llm_run": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"scores": scores, "schema_pair_consistency": paired, "usage": report["usage"]}, indent=2))


if __name__ == "__main__":
    main()
