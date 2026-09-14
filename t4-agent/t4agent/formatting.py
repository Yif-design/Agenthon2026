from __future__ import annotations

from typing import Any

from .llm import Usage
from .predict import RowResult
from .retrieve import IndexedCorpus
from .taskio import Task
from .validate import validate_answer


def build_answer(task: Task, results: list[RowResult], corpus: IndexedCorpus, usage: Usage) -> dict[str, Any]:
    answer = {
        "task_id": task.task_id,
        "schema_version": task.schema_version,
        "target_type": task.target_type,
        "entity_predictions": [r.prediction for r in results],
        "evidence_trace": (
            "t4-agent: cutoff-safe BM25 retrieval, deterministic calculations, "
            "Qwen-7B row predictor when MODEL_ENDPOINT is configured, exact-span citation grounding. "
            f"model_calls={usage.calls}, prompt_tokens={usage.prompt_tokens}, "
            f"completion_tokens={usage.completion_tokens}."
        ),
        "notes": {
            "agent": "t4-agent",
            "fallback_rows": [r.prediction.get("entity_id") for r in results if r.fallback_reason],
            "model_errors": usage.errors[:5],
        },
    }
    errors = validate_answer(answer, task, corpus)
    if errors:
        answer["notes"]["validation_errors"] = errors
    return answer
