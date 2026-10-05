#!/usr/bin/env python3
"""Compare context-relevance reason selection with its rollback flag."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PUBLIC_UNITS = (
    "t4-EXAMPLE-eps-beat", "t4-auction-btc-202411-us7", "t4-cotpos-202411-us10",
    "t4-cpicomp-202410-us11", "t4-credit-event-2023", "t4-eps-growth-2024Q3-banks",
    "t4-eps-yoy-2023Q2-mixed", "t4-fomc-curve-20220728", "t4-fomc-curve-20240918",
    "t4-macrorev-20240930-us6", "t4-postearn-20240201-megacap",
)


def run(python: str, unit: Path, out: Path, enabled: bool) -> dict:
    env = {key: value for key, value in os.environ.items() if key not in {"MODEL_ENDPOINT", "MODEL_TOKEN", "MODEL_NAME"}}
    env.update({"PYTHONPATH": str(ROOT), "T4_ENABLE_REASON_RELEVANCE": "1" if enabled else "0"})
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [python, str(ROOT / "scripts/run_unit.py"), "--unit", str(unit), "--out", str(out)],
        cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL,
    )
    return json.loads(out.read_text(encoding="utf-8"))


def without_reasons(answer: dict) -> dict:
    copy = json.loads(json.dumps(answer))
    copy.pop("submitted_reasons", None)
    return copy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units", type=Path, required=True)
    parser.add_argument("--python", default="python3")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--baseline-commit", required=True)
    args = parser.parse_args()
    details = []
    for name in PUBLIC_UNITS:
        before = run(args.python, args.units / name, args.out_dir / "baseline" / name / "answer.json", False)
        after = run(args.python, args.units / name, args.out_dir / "candidate" / name / "answer.json", True)
        before_reasons = before.get("submitted_reasons", [])
        after_reasons = after.get("submitted_reasons", [])
        pairs = list(zip(before_reasons, after_reasons, strict=True))
        details.append({
            "task_id": name,
            "rows": len(after["entity_predictions"]),
            "reasons": len(after_reasons),
            "changed_reasons": sum(left != right for left, right in pairs),
            "changed_premises": sum(left["premise"] != right["premise"] for left, right in pairs),
            "non_reason_fields_identical": without_reasons(before) == without_reasons(after),
            "reason_structure_invariant": all(
                {key: left.get(key) for key in ("reason_id", "mechanism", "answer_implication", "scope")}
                == {key: right.get(key) for key in ("reason_id", "mechanism", "answer_implication", "scope")}
                for left, right in pairs
            ),
            "validation_errors": len(after.get("notes", {}).get("validation_errors") or []),
        })
    report = {
        "schema_version": 1,
        "date": "2026-10-01",
        "experiment": "reason_evidence_relevance_public_ab_v1",
        "baseline_commit": args.baseline_commit,
        "candidate_flag": "T4_ENABLE_REASON_RELEVANCE=1 (default)",
        "rollback_flag": "T4_ENABLE_REASON_RELEVANCE=0",
        "units": len(details),
        "rows": sum(item["rows"] for item in details),
        "reasons": sum(item["reasons"] for item in details),
        "changed_reasons": sum(item["changed_reasons"] for item in details),
        "changed_premises": sum(item["changed_premises"] for item in details),
        "non_reason_fields_identical_units": sum(item["non_reason_fields_identical"] for item in details),
        "reason_structure_invariant_units": sum(item["reason_structure_invariant"] for item in details),
        "validation_error_units": sum(bool(item["validation_errors"]) for item in details),
        "model_api_calls": 0,
        "local_llm_run": False,
        "details": details,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "units", "rows", "reasons", "changed_reasons", "changed_premises",
        "non_reason_fields_identical_units", "reason_structure_invariant_units", "validation_error_units",
    )}, indent=2))
    passed = (
        report["changed_reasons"] == 4
        and report["changed_premises"] == 4
        and report["non_reason_fields_identical_units"] == report["units"]
        and report["reason_structure_invariant_units"] == report["units"]
        and report["validation_error_units"] == 0
    )
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
