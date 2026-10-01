#!/usr/bin/env python3
"""Compare bounded submitted reasons against a baseline checkout."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PUBLIC_UNIT_NAMES = (
    "t4-EXAMPLE-eps-beat",
    "t4-auction-btc-202411-us7",
    "t4-cotpos-202411-us10",
    "t4-cpicomp-202410-us11",
    "t4-credit-event-2023",
    "t4-eps-growth-2024Q3-banks",
    "t4-eps-yoy-2023Q2-mixed",
    "t4-fomc-curve-20220728",
    "t4-fomc-curve-20240918",
    "t4-macrorev-20240930-us6",
    "t4-postearn-20240201-megacap",
)


def run_answer(python: str, project: Path, unit: Path, out: Path, enabled: bool) -> dict:
    env = {key: value for key, value in os.environ.items() if key not in {"MODEL_ENDPOINT", "MODEL_TOKEN", "MODEL_NAME"}}
    env.update({"PYTHONPATH": str(project), "T4_ENABLE_SUBMITTED_REASONS": "1" if enabled else "0"})
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [python, str(project / "scripts/run_unit.py"), "--unit", str(unit), "--out", str(out)],
        cwd=project,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return json.loads(out.read_text(encoding="utf-8"))


def without_reasons(answer: dict) -> dict:
    copied = json.loads(json.dumps(answer))
    copied.pop("submitted_reasons", None)
    return copied


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units", type=Path, required=True)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--baseline-commit", required=True)
    parser.add_argument("--python", default="python3")
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    details = []
    for name in PUBLIC_UNIT_NAMES:
        baseline = run_answer(args.python, args.baseline_root, args.units / name, args.candidate_dir / "baseline" / name / "answer.json", False)
        candidate = run_answer(args.python, ROOT, args.units / name, args.candidate_dir / "candidate" / name / "answer.json", True)
        details.append({
            "task_id": name,
            "rows": len(candidate["entity_predictions"]),
            "reasons": len(candidate.get("submitted_reasons", [])),
            "analysis_fields_identical": without_reasons(candidate) == baseline,
            "baseline_validation_errors": len(baseline.get("notes", {}).get("validation_errors") or []),
            "candidate_validation_errors": len(candidate.get("notes", {}).get("validation_errors") or []),
        })
    report = {
        "schema_version": 1,
        "date": "2026-10-01",
        "experiment": "submitted_reasons_public_ab_v1",
        "baseline_commit": args.baseline_commit,
        "candidate_flag": "T4_ENABLE_SUBMITTED_REASONS=1 (default)",
        "rollback_flag": "T4_ENABLE_SUBMITTED_REASONS=0",
        "units": len(details),
        "rows": sum(item["rows"] for item in details),
        "reasons": sum(item["reasons"] for item in details),
        "units_with_reasons": sum(item["reasons"] > 0 for item in details),
        "analysis_fields_identical_units": sum(item["analysis_fields_identical"] for item in details),
        "validation_error_units": sum(bool(item["baseline_validation_errors"] or item["candidate_validation_errors"]) for item in details),
        "model_api_calls": 0,
        "local_llm_run": False,
        "details": details,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("units", "rows", "reasons", "units_with_reasons", "analysis_fields_identical_units", "validation_error_units")}, indent=2))
    if report["units_with_reasons"] != report["units"] or report["analysis_fields_identical_units"] != report["units"] or report["validation_error_units"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
