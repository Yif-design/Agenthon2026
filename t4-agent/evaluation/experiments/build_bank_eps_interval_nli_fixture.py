#!/usr/bin/env python3
"""Append the historical wide-interval answer to the NLI manifest at commit ``af25dc7``.

The production feature flag was removed by the scorer-5.2.2 rollback. Run this script from the
recorded historical commit; it is not a current validation entry point.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from t4agent.formatting import build_answer  # noqa: E402
from t4agent.llm import LLM  # noqa: E402
from t4agent.predict import predict_rows  # noqa: E402
from t4agent.retrieve import BM25, build_index  # noqa: E402
from t4agent.taskio import load_task, write_json  # noqa: E402
from t4agent.validate import validate_answer  # noqa: E402


UNIT_ID = "t4-eps-growth-2024Q3-banks"
CASE_ID = "t4-bank-eps-interval-candidate"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--track4-repo", type=Path, required=True)
    parser.add_argument("--answers-root", type=Path, required=True)
    parser.add_argument("--case-manifest", type=Path, required=True)
    args = parser.parse_args()

    unit_dir = args.track4_repo / "units" / UNIT_ID
    task = load_task(unit_dir / "task.json")
    corpus = build_index(unit_dir / "corpus", task.cutoff_date)
    llm = LLM(root_dir=ROOT.parent, enabled=False)
    previous = os.environ.get("T4_ENABLE_BANK_EPS_INTERVAL")
    os.environ["T4_ENABLE_BANK_EPS_INTERVAL"] = "1"
    try:
        results = predict_rows(task, BM25(corpus.chunks), corpus, llm, 8)
    finally:
        if previous is None:
            os.environ.pop("T4_ENABLE_BANK_EPS_INTERVAL", None)
        else:
            os.environ["T4_ENABLE_BANK_EPS_INTERVAL"] = previous
    answer = build_answer(task, results, corpus, llm.usage)
    errors = validate_answer(answer, task, corpus)
    if errors:
        raise RuntimeError(f"candidate answer failed local validation: {errors}")
    if len(results) != 8 or any(result.method != "seasonal_eps_delta_persistence" for result in results):
        raise RuntimeError("public bank fixture did not exercise all eight bank-EPS rows")
    answer_path = args.answers_root / CASE_ID / "answer.json"
    write_json(answer_path, answer)
    manifest = json.loads(args.case_manifest.read_text())
    manifest["cases"] = [case for case in manifest["cases"] if case.get("case_id") != CASE_ID]
    manifest["cases"].append({"case_id": CASE_ID, "unit_id": UNIT_ID, "answer": str(answer_path.resolve())})
    args.case_manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"case_id": CASE_ID, "unit_id": UNIT_ID, "rows": len(results)}))


if __name__ == "__main__":
    main()
