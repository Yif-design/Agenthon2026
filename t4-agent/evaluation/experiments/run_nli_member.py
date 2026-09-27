#!/usr/bin/env python3
"""Run one official Track 4 NLI ensemble member with bounded memory."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import sys
import time
from importlib.metadata import version
from pathlib import Path
from typing import Any


class RecordingJudge:
    """Record the exact premise/hypothesis pairs requested by the official checker."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.calls: dict[tuple[str, str], float] = {}

    def entail(self, premise: str, hypothesis: str) -> float:
        score = float(self.inner.entail(premise, hypothesis))
        self.calls[(premise, hypothesis)] = score
        return score


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--track4-repo", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--unit", type=Path)
    mode.add_argument("--unit-id", action="append", dest="unit_ids")
    mode.add_argument("--case-manifest", type=Path)
    parser.add_argument("--answer", type=Path)
    parser.add_argument("--answers-root", type=Path)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def _case_paths(args: argparse.Namespace) -> list[tuple[str, Path, Path]]:
    if args.unit is not None:
        if args.answer is None or args.answers_root is not None:
            raise ValueError("single-unit mode requires --answer and forbids --answers-root")
        return [(args.unit.name, args.unit, args.answer)]
    if args.case_manifest is not None:
        if args.answer is not None or args.answers_root is not None:
            raise ValueError("manifest mode forbids --answer and --answers-root")
        payload = json.loads(args.case_manifest.read_text(encoding="utf-8"))
        rows = payload.get("cases") if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or not rows:
            raise ValueError("case manifest must contain a non-empty cases list")
        manifest_root = args.case_manifest.parent
        cases: list[tuple[str, Path, Path]] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("each case manifest row must be an object")
            case_id = row.get("case_id")
            unit_id = row.get("unit_id")
            answer = row.get("answer")
            if not all(isinstance(value, str) and value for value in (case_id, unit_id, answer)):
                raise ValueError("each case requires non-empty case_id, unit_id, and answer")
            answer_path = Path(answer)
            if not answer_path.is_absolute():
                answer_path = manifest_root / answer_path
            cases.append((case_id, args.track4_repo / "units" / unit_id, answer_path))
        case_ids = [case_id for case_id, _, _ in cases]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("case manifest case_id values must be unique")
        return cases
    if not args.unit_ids or args.answers_root is None or args.answer is not None:
        raise ValueError("suite mode requires --unit-id and --answers-root and forbids --answer")
    if len(set(args.unit_ids)) != len(args.unit_ids):
        raise ValueError("suite unit ids must be unique")
    return [
        (unit_id, args.track4_repo / "units" / unit_id, args.answers_root / unit_id / "answer.json")
        for unit_id in args.unit_ids
    ]


def _check_case(
    case_id: str,
    unit: Path,
    answer_path: Path,
    judge: object,
    build_unit_context: object,
    check_answer: object,
) -> dict:
    answer_bytes = answer_path.read_bytes()
    answer = json.loads(answer_bytes)
    rows = answer.get("entity_predictions")
    if not isinstance(rows, list):
        raise ValueError("answer entity_predictions must be a list")

    ctx = build_unit_context(unit)
    recorder = RecordingJudge(judge)
    started = time.monotonic()
    result = check_answer(answer, ctx, recorder)
    elapsed = time.monotonic() - started
    params = ctx["_params"]
    return {
        "case_id": case_id,
        "unit_id": unit.name,
        "answer_sha256": hashlib.sha256(answer_bytes).hexdigest(),
        "elapsed_seconds": elapsed,
        "tau_citation": float(params.tau_citation),
        "faithfulness_threshold": float(params.faithfulness_threshold),
        "single_member_faithfulness": result.faithfulness,
        "single_member_gate_pass": result.gate_pass,
        "predictions": [
            {
                "entity_id": item.entity_id,
                "hypothesis": item.hypothesis,
                "score": item.score,
                "supported": item.supported,
                "citation_scores": [
                    {
                        "premise_sha256": hashlib.sha256(premise.encode("utf-8")).hexdigest(),
                        "premise_chars": len(premise),
                        "score": score,
                    }
                    for (premise, hypothesis), score in recorder.calls.items()
                    if hypothesis == item.hypothesis
                ],
            }
            for item in result.predictions
        ],
    }


def main() -> None:
    args = parse_args()
    cases = _case_paths(args)
    sys.path.insert(0, str(args.track4_repo.resolve()))

    from faithfulness.judge import DeBERTaNLIJudge, build_unit_context, check_answer

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    judge_parameters = inspect.signature(DeBERTaNLIJudge).parameters
    if "revision" in judge_parameters:
        judge = DeBERTaNLIJudge(
            model_id=args.model_id,
            revision=args.revision,
            cache_dir=str(args.cache_dir),
            device=-1,
        )
    else:
        snapshot = (
            args.cache_dir
            / f"models--{args.model_id.replace('/', '--')}"
            / "snapshots"
            / args.revision
        )
        if not snapshot.is_dir():
            raise FileNotFoundError(
                f"pinned model snapshot is unavailable for {args.model_id}@{args.revision}: "
                f"{snapshot}"
            )
        judge = DeBERTaNLIJudge(
            model_id=str(snapshot),
            cache_dir=str(args.cache_dir),
            device=-1,
        )
    common = {
        "model_id": args.model_id,
        "model_revision": args.revision,
        "device": "cpu",
        "runtime": {
            "python": sys.version.split()[0],
            "torch": version("torch"),
            "transformers": version("transformers"),
            "qfbench2-common": version("qfbench2-common"),
        },
    }
    checked = [
        _check_case(case_id, unit, answer, judge, build_unit_context, check_answer)
        for case_id, unit, answer in cases
    ]
    if len(checked) == 1 and args.unit is not None:
        report = {"schema_version": 1, **checked[0], **common}
    else:
        report = {
            "schema_version": 2,
            **common,
            "aggregation_scope": (
                "Each case calls the official check_answer sequentially while reusing one loaded model; "
                "every distinct citation premise score is retained for exact ensemble aggregation."
            ),
            "total_elapsed_seconds": sum(float(case["elapsed_seconds"]) for case in checked),
            "cases": checked,
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "model_id": args.model_id,
                "case_count": len(checked),
                "elapsed_seconds": sum(float(case["elapsed_seconds"]) for case in checked),
                "faithfulness": [
                    {
                        "case_id": case["case_id"],
                        "unit_id": case["unit_id"],
                        "value": case["single_member_faithfulness"],
                    }
                    for case in checked
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
