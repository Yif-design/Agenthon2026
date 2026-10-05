#!/usr/bin/env python3
"""Paired remote-model A/B for exact quotes versus prompt-local evidence IDs."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any

from t4agent.formatting import build_answer
from t4agent.llm import LLM, Usage, parse_json_object
from t4agent.predict import predict_rows
from t4agent.retrieve import BM25, Chunk, IndexedCorpus, build_index
from t4agent.taskio import Task, load_task
from t4agent.validate import validate_answer


PUBLIC_CASES = (
    "t4-EXAMPLE-eps-beat",
    "t4-credit-event-2023",
    "t4-fomc-curve-20240918",
)


class GeminiClient:
    def __init__(self, model: str, key: str) -> None:
        self.model = model
        self.key = key
        self.usage = Usage()
        self.prompt_chars = 0
        self.latencies: list[float] = []

    def chat_json(self, system: str, user: str, max_tokens: int = 700) -> dict | None:
        self.prompt_chars += len(system) + len(user)
        body = {
            "contents": [{"role": "user", "parts": [{"text": f"{system}\n\n{user}"}]}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": min(4000, max_tokens),
                "responseMimeType": "application/json",
                "seed": 1234,
            },
        }
        if self.model == "gemini-2.5-flash-lite":
            body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
        request = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.key}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        self.usage.calls += 1
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:160]
            self.usage.errors.append(f"HTTP {exc.code}: {detail}")
            return None
        except Exception as exc:  # noqa: BLE001
            self.usage.errors.append(f"{type(exc).__name__}: {str(exc)[:160]}")
            return None
        finally:
            self.latencies.append(time.monotonic() - started)
        metadata = payload.get("usageMetadata") or {}
        self.usage.prompt_tokens += int(metadata.get("promptTokenCount") or 0)
        self.usage.completion_tokens += int(metadata.get("candidatesTokenCount") or 0) + int(
            metadata.get("thoughtsTokenCount") or 0
        )
        parts = ((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        content = "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict))
        parsed = parse_json_object(content)
        if parsed is None:
            self.usage.errors.append("model returned content without one JSON object")
        return parsed


class OpenRouterClient:
    def __init__(self, model: str, key: str) -> None:
        saved = {name: os.environ.get(name) for name in (
            "MODEL_ENDPOINT", "MODEL_API_KEY", "MODEL_NAME", "T4_MODEL_ALLOW_DATA_COLLECTION",
            "T4_MODEL_MAX_CALLS", "T4_MODEL_RETRIES", "T4_TEMPERATURE", "T4_SEED",
        )}
        os.environ.update({
            "MODEL_ENDPOINT": "https://openrouter.ai/api/v1",
            "MODEL_API_KEY": key,
            "MODEL_NAME": model,
            "T4_MODEL_ALLOW_DATA_COLLECTION": "1",
            "T4_MODEL_MAX_CALLS": "25",
            "T4_MODEL_RETRIES": "1",
            "T4_TEMPERATURE": "0",
            "T4_SEED": "1234",
        })
        try:
            self.client = LLM(deadline_monotonic=time.monotonic() + 300)
        finally:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        self.usage = self.client.usage
        self.prompt_chars = 0
        self.latencies: list[float] = []

    def chat_json(self, system: str, user: str, max_tokens: int = 700) -> dict | None:
        self.prompt_chars += len(system) + len(user)
        started = time.monotonic()
        try:
            return self.client.chat_json(system, user, max_tokens)
        finally:
            self.latencies.append(time.monotonic() - started)


def ranking_case() -> tuple[Task, IndexedCorpus]:
    entities = [
        {"entity_id": "ALPHA", "current_score": 1.0},
        {"entity_id": "BETA", "current_score": 1.0},
        {"entity_id": "GAMMA", "current_score": 1.0},
    ]
    documents = {
        "ALPHA_DOC": "ALPHA order backlog rose sharply and customer demand strengthened.",
        "BETA_DOC": "BETA order backlog was stable and customer demand was unchanged.",
        "GAMMA_DOC": "GAMMA order backlog fell sharply and customer demand weakened.",
    }
    chunks = [Chunk(doc_id, "2024-01-01", 0, len(text), text) for doc_id, text in documents.items()]
    corpus = IndexedCorpus(chunks, documents, {doc_id: "2024-01-01" for doc_id in documents})
    task = Task(
        raw={}, task_id="synthetic-unknown-ranking", schema_version="3",
        target={"name": "future_momentum_rank", "type": "ranking"}, target_type="ranking", labels=[],
        entities=entities, cutoff_date="2024-01-01", interval_level=0.9,
        prompt="Rank entities by future momentum. Rising backlog is positive; falling backlog is negative.",
        family="unseen_family",
    )
    return task, corpus


def summarize(task: Task, corpus: IndexedCorpus, results: list, client: Any) -> dict[str, Any]:
    answer = build_answer(task, results, corpus, client.usage)
    errors = validate_answer(answer, task, corpus)
    rejected: dict[str, int] = {}
    for row in results:
        for item in row.rejected_facts:
            rejected[item.reason] = rejected.get(item.reason, 0) + 1
    return {
        "rows": len(results),
        "model_rows": sum(row.raw_model is not None for row in results),
        "non_context_facts": sum(fact.kind != "context" for row in results for fact in row.facts),
        "context_facts": sum(fact.kind == "context" for row in results for fact in row.facts),
        "rejected_facts": rejected,
        "validation_errors": errors,
        "predictions": [row.prediction for row in results],
        "raw_model": [row.raw_model for row in results],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("gemini", "openrouter"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--units-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    key = args.key_file.read_text().strip()
    arms = {}
    for arm, enabled in (("quotes", False), ("evidence_ids", True)):
        os.environ["T4_EVIDENCE_IDS"] = "1" if enabled else "0"
        client = GeminiClient(args.model, key) if args.provider == "gemini" else OpenRouterClient(args.model, key)
        cases = {}
        for unit_id in PUBLIC_CASES:
            task_path = args.units_dir / unit_id / "task.json"
            task = load_task(task_path)
            corpus = build_index(task_path.parent / "corpus", task.cutoff_date)
            results = predict_rows(task, BM25(corpus.chunks), corpus, client, 8)
            cases[unit_id] = summarize(task, corpus, results, client)
        task, corpus = ranking_case()
        results = predict_rows(task, BM25(corpus.chunks), corpus, client, 8)
        cases[task.task_id] = summarize(task, corpus, results, client)
        arm_result = {
            "usage": asdict(client.usage),
            "prompt_chars": client.prompt_chars,
            "latency_seconds": client.latencies,
            "cases": cases,
        }
        arms[arm] = arm_result
        target = args.run_dir / args.provider / args.model.replace("/", "_") / f"{arm}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(arm_result, indent=2, sort_keys=True) + "\n")
    report = {
        "schema_version": 1,
        "provider": args.provider,
        "model": args.model,
        "temperature": 0,
        "seed": 1234,
        "arms": {
            arm: {
                "usage": value["usage"],
                "prompt_chars": value["prompt_chars"],
                "latency_seconds": value["latency_seconds"],
                "cases": {
                    name: {key: case[key] for key in (
                        "rows", "model_rows", "non_context_facts", "context_facts",
                        "rejected_facts", "validation_errors",
                    )}
                    for name, case in value["cases"].items()
                },
            }
            for arm, value in arms.items()
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
