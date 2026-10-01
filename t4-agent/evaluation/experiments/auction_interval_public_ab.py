#!/usr/bin/env python3
"""Compare Treasury-auction interval rollback outputs against a baseline checkout."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


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


def run_answer(python: str, project: Path, unit: Path, out: Path) -> dict:
    env = {key: value for key, value in os.environ.items() if key not in {"MODEL_ENDPOINT", "MODEL_TOKEN", "MODEL_NAME"}}
    env["PYTHONPATH"] = str(project)
    subprocess.run(
        [python, str(project / "scripts/run_unit.py"), "--unit", str(unit), "--out", str(out)],
        cwd=project,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return json.loads(out.read_text(encoding="utf-8"))


def without_intervals(answer: dict) -> dict:
    copied = json.loads(json.dumps(answer))
    for row in copied.get("entity_predictions", []):
        row.pop("interval", None)
    return copied


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units", type=Path, required=True)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--baseline-commit", required=True)
    parser.add_argument("--python", default="python3")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    details = []
    with TemporaryDirectory(prefix="t4-auction-522-ab-") as tmp:
        out_root = Path(tmp)
        for name in PUBLIC_UNIT_NAMES:
            before = run_answer(args.python, args.baseline_root, args.units / name, out_root / f"{name}-before.json")
            after = run_answer(args.python, ROOT, args.units / name, out_root / f"{name}-after.json")
            before_rows = {row["entity_id"]: row for row in before["entity_predictions"]}
            after_rows = {row["entity_id"]: row for row in after["entity_predictions"]}
            details.append({
                "task_id": name,
                "rows": len(after_rows),
                "changed_intervals": sum(before_rows[key]["interval"] != row["interval"] for key, row in after_rows.items()),
                "non_interval_fields_identical": without_intervals(before) == without_intervals(after),
                "before_validation_errors": len(before.get("notes", {}).get("validation_errors") or []),
                "after_validation_errors": len(after.get("notes", {}).get("validation_errors") or []),
            })
    report = {
        "schema_version": 1,
        "date": "2026-10-01",
        "experiment": "auction_interval_official_522_public_ab_v1",
        "before_commit": args.baseline_commit,
        "before_rule": "max(0.15, 2.5 * recent-six pstdev) for post-2021 cutoffs",
        "after_rule": "max(0.15, 1.65 * recent-six pstdev)",
        "units": len(details),
        "rows": sum(item["rows"] for item in details),
        "changed_interval_rows": sum(item["changed_intervals"] for item in details),
        "non_interval_fields_identical_units": sum(item["non_interval_fields_identical"] for item in details),
        "validation_error_units": sum(bool(item["before_validation_errors"] or item["after_validation_errors"]) for item in details),
        "model_api_calls": 0,
        "local_llm_run": False,
        "details": details,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("units", "rows", "changed_interval_rows", "non_interval_fields_identical_units", "validation_error_units")}, indent=2))
    changed_tasks = {item["task_id"] for item in details if item["changed_intervals"]}
    if changed_tasks - {"t4-auction-btc-202411-us7"}:
        raise SystemExit(f"unexpected changed tasks: {sorted(changed_tasks)}")
    if report["non_interval_fields_identical_units"] != report["units"] or report["validation_error_units"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
