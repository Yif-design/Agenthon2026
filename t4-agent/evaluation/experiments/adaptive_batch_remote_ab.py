#!/usr/bin/env python3
"""Three-call synthetic weak-model check for batch widths three and four."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.experiments.evidence_id_remote_ab import GeminiClient, OpenRouterClient  # noqa: E402
from t4agent.predict import predict_rows  # noqa: E402
from t4agent.retrieve import BM25, Chunk, IndexedCorpus  # noqa: E402
from t4agent.taskio import Task  # noqa: E402


def synthetic_case() -> tuple[Task, IndexedCorpus]:
    facts = {
        "ALPHA": "Alpha customer orders rose and management raised its outlook.",
        "BETA": "Beta customer orders fell and management lowered its outlook.",
        "GAMMA": "Gamma customer orders were unchanged and guidance stayed flat.",
        "DELTA": "Delta customer orders rose and management raised its outlook.",
    }
    entities = [
        {"entity_id": entity_id, "name": entity_id.title(), "current_score": 0.0}
        for entity_id in facts
    ]
    chunks = [
        Chunk(f"{entity_id}_DOC", "2024-01-01", 0, len(text), text)
        for entity_id, text in facts.items()
    ]
    corpus = IndexedCorpus(
        chunks,
        {chunk.doc_id: chunk.text for chunk in chunks},
        {chunk.doc_id: chunk.doc_date for chunk in chunks},
    )
    target = {
        "name": "future_order_direction",
        "type": "classification",
        "labels": ["UP", "DOWN"],
    }
    task = Task(
        raw={"target": target},
        task_id="synthetic-adaptive-batch",
        schema_version="3",
        target=target,
        target_type="classification",
        labels=["UP", "DOWN"],
        entities=entities,
        cutoff_date="2024-01-31",
        interval_level=0.9,
        prompt="Predict order direction. Rising orders are UP; falling orders are DOWN; unchanged is neutral.",
        family="unseen_family",
    )
    return task, corpus


def run_arm(width: int, provider: str, model: str, key: str) -> dict:
    task, corpus = synthetic_case()
    os.environ["T4_MODEL_BATCH_SIZE"] = str(width)
    client = GeminiClient(model, key) if provider == "gemini" else OpenRouterClient(model, key)
    results = predict_rows(task, BM25(corpus.chunks), corpus, client, 2)
    final_batch_start = len(results) - (len(results) % width)
    return {
        "width": width,
        "usage": asdict(client.usage),
        "prompt_chars": client.prompt_chars,
        "latency_seconds": client.latencies,
        "model_rows": sum(row.raw_model is not None for row in results),
        "valid_identity_rows": sum(
            row.raw_model is not None
            and (
                (index >= final_batch_start and len(results) % width == 1)
                or (
                    row.raw_model.get("item_id") == index
                    and row.raw_model.get("entity_id") == task.entities[index]["entity_id"]
                )
            )
            for index, row in enumerate(results)
        ),
        "rejected_facts": sum(len(row.rejected_facts) for row in results),
        "raw_model": [row.raw_model for row in results],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("gemini", "openrouter"), default="gemini")
    parser.add_argument("--model", default="gemini-2.5-flash-lite")
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    key = args.key_file.read_text().strip()
    arms = {f"batch_{width}": run_arm(width, args.provider, args.model, key) for width in (3, 4)}
    args.run_dir.mkdir(parents=True, exist_ok=True)
    (args.run_dir / "adaptive-batch-remote-ab-raw.json").write_text(
        json.dumps({"provider": args.provider, "model": args.model, "arms": arms}, indent=2, sort_keys=True) + "\n"
    )
    report_arms = {
        name: {key: value[key] for key in (
            "width", "usage", "prompt_chars", "latency_seconds", "model_rows",
            "valid_identity_rows", "rejected_facts",
        )}
        for name, value in arms.items()
    }
    baseline = report_arms["batch_3"]
    candidate = report_arms["batch_4"]
    valid = (
        not baseline["usage"]["errors"]
        and not candidate["usage"]["errors"]
        and baseline["valid_identity_rows"] == 4
        and candidate["valid_identity_rows"] == 4
    )
    report = {
        "schema_version": 1,
        "experiment": "adaptive_batch_remote_ab_v1",
        "provider": "Google Gemini Developer API" if args.provider == "gemini" else "OpenRouter",
        "model": args.model,
        "synthetic_public_safe_data": True,
        "temperature": 0,
        "seed": 1234,
        "arms": report_arms,
        "decision_rule": "Batch four must retain all four correctly bound rows with no API or JSON errors; batch three is the paired reference.",
        "decision": "pass" if valid else "fail_or_unavailable",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    if not valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
