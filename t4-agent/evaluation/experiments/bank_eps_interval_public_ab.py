#!/usr/bin/env python3
"""Verify the accepted bank-EPS interval changes only the intended public fields."""

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units", type=Path, required=True)
    parser.add_argument("--python", default="python3")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "evaluation/reports/bank-eps-interval-public-ab-v1.json",
    )
    return parser.parse_args()


def run_answer(python: str, unit: Path, out: Path, enabled: str) -> dict:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"MODEL_ENDPOINT", "MODEL_TOKEN", "MODEL_NAME"}
    }
    env.update({"PYTHONPATH": str(ROOT), "T4_ENABLE_BANK_EPS_INTERVAL": enabled})
    subprocess.run(
        [python, str(ROOT / "scripts/run_unit.py"), "--unit", str(unit), "--out", str(out)],
        cwd=ROOT,
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
    args = parse_args()
    details = []
    with TemporaryDirectory(prefix="t4-bank-eps-ab-") as tmp:
        out_root = Path(tmp)
        for name in PUBLIC_UNIT_NAMES:
            unit = args.units / name
            legacy = run_answer(args.python, unit, out_root / f"{name}-legacy.json", "0")
            candidate = run_answer(args.python, unit, out_root / f"{name}-candidate.json", "1")
            legacy_rows = {row["entity_id"]: row for row in legacy["entity_predictions"]}
            candidate_rows = {row["entity_id"]: row for row in candidate["entity_predictions"]}
            changed_intervals = sum(
                legacy_rows[entity_id]["interval"] != row["interval"]
                for entity_id, row in candidate_rows.items()
            )
            details.append(
                {
                    "task_id": name,
                    "rows": len(candidate_rows),
                    "changed_intervals": changed_intervals,
                    "non_interval_fields_identical": without_intervals(legacy) == without_intervals(candidate),
                    "legacy_validation_errors": len(legacy.get("notes", {}).get("validation_errors") or []),
                    "candidate_validation_errors": len(candidate.get("notes", {}).get("validation_errors") or []),
                }
            )

    expected_changes = {"t4-eps-growth-2024Q3-banks": 8}
    report = {
        "schema_version": 1,
        "experiment": "bank_eps_interval_public_ab_v1",
        "candidate_flag": "T4_ENABLE_BANK_EPS_INTERVAL=1",
        "rollback_flag": "T4_ENABLE_BANK_EPS_INTERVAL=0",
        "model_calls": 0,
        "units": len(details),
        "rows": sum(item["rows"] for item in details),
        "changed_interval_rows": sum(item["changed_intervals"] for item in details),
        "non_interval_fields_identical_units": sum(item["non_interval_fields_identical"] for item in details),
        "validation_error_units": sum(
            bool(item["legacy_validation_errors"] or item["candidate_validation_errors"])
            for item in details
        ),
        "details": details,
    }
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "units", "rows", "changed_interval_rows", "non_interval_fields_identical_units", "validation_error_units"
    )}, indent=2))

    for item in details:
        if item["changed_intervals"] != expected_changes.get(item["task_id"], 0):
            raise SystemExit(f"unexpected interval changes in {item['task_id']}")
    if report["non_interval_fields_identical_units"] != report["units"] or report["validation_error_units"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
