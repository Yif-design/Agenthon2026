from __future__ import annotations

import argparse
import json
import hashlib
import os
import pathlib
import sys
import time
from dataclasses import asdict

from .formatting import build_answer
from .llm import LLM
from .predict import predict_rows
from .retrieve import BM25, build_index
from .taskio import load_task, write_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="analyze")
    parser.add_argument("verb", nargs="?", default="analyze", choices=["analyze"])
    parser.add_argument("--task", type=pathlib.Path, required=True)
    parser.add_argument("--corpus", type=pathlib.Path, required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--trace-dir", type=pathlib.Path)
    args = parser.parse_args(argv)

    task = load_task(args.task)
    corpus = build_index(args.corpus, task.cutoff_date)
    bm25 = BM25(corpus.chunks)
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    # Materialize a complete deterministic answer before making any network
    # request. If the model route stalls or the process is interrupted later,
    # the evaluator still receives a schema-valid answer file.
    baseline_llm = LLM(root_dir=repo_root, enabled=False)
    baseline_results = predict_rows(task, bm25, corpus, baseline_llm, max(1, args.top_k))
    answer = build_answer(task, baseline_results, corpus, baseline_llm.usage)
    write_json(args.out, answer)

    budget = min(450.0, max(0.0, float(os.environ.get("T4_MODEL_BUDGET_S", "420"))))
    llm = LLM(root_dir=repo_root, deadline_monotonic=time.monotonic() + budget)
    results = baseline_results
    if llm.enabled:
        try:
            enhanced_results = predict_rows(task, bm25, corpus, llm, max(1, args.top_k))
            enhanced_answer = build_answer(task, enhanced_results, corpus, llm.usage)
            if not (enhanced_answer.get("notes", {}).get("validation_errors") or []):
                results = enhanced_results
                answer = enhanced_answer
            else:
                llm.usage.errors.append("model-enhanced answer failed local validation; retained baseline")
                answer = build_answer(task, baseline_results, corpus, llm.usage)
        except Exception as exc:  # noqa: BLE001
            llm.usage.errors.append(f"model enhancement failed: {type(exc).__name__}: {str(exc)[:180]}")
            answer = build_answer(task, baseline_results, corpus, llm.usage)
        write_json(args.out, answer)

    trace_dir = args.trace_dir or (args.out.parent / "trace")
    try:
        _write_trace(trace_dir, task, results, llm)
    except Exception as exc:  # noqa: BLE001
        print(f"trace write failed after answer was saved: {exc}", file=sys.stderr)

    errors = answer.get("notes", {}).get("validation_errors") or []
    if errors:
        print(f"wrote {args.out} with {len(errors)} local validation warning(s)", file=sys.stderr)
    else:
        print(f"wrote {args.out}")
    return 0


def _write_trace(trace_dir: pathlib.Path, task, results, llm: LLM) -> None:
    trace_dir.mkdir(parents=True, exist_ok=True)
    route = {
        "task_id": task.task_id,
        "family": task.family,
        "target": task.target,
        "cutoff_date": task.cutoff_date,
    }
    (trace_dir / "route.json").write_text(json.dumps(route, ensure_ascii=False, indent=2) + "\n")
    rows = []
    for result in results:
        rows.append({
            "entity_id": result.prediction.get("entity_id"),
            "allowed_doc_ids": list(result.allowed_doc_ids),
            "retrieved_chunks": [asdict(chunk) for chunk in result.retrieved],
            "raw_model_output": result.raw_model,
            "validated_facts": [fact.as_dict() for fact in result.facts],
            "used_fact_ids": list(result.used_fact_ids),
            "rejected_facts": [fact.as_dict() for fact in result.rejected_facts],
            "method": result.method,
            "derivation": result.derivation or {},
            "calculator_inputs": result.calculator_inputs or {},
            "model_prompt_sha256": (
                hashlib.sha256(result.model_prompt.encode("utf-8")).hexdigest()
                if result.model_prompt is not None
                else None
            ),
            "fallback_reason": result.fallback_reason,
            "prediction": result.prediction,
        })
    (trace_dir / "rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    usage = asdict(llm.usage)
    usage.update({
        "model": llm.model,
        "temperature": llm.temperature,
        "seed": llm.seed,
        "enabled": llm.enabled,
        "allow_data_collection": llm.allow_data_collection,
        "enable_thinking": llm.enable_thinking,
    })
    (trace_dir / "usage.json").write_text(json.dumps(usage, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
