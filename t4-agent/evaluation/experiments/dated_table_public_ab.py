#!/usr/bin/env python3
"""Compare the enabled dated-table candidate with a clean Git baseline on public units."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units", type=Path, required=True)
    parser.add_argument("--baseline-commit", default="e7bd672dc3c9592e4835eaf9dff8198615c6f236")
    parser.add_argument(
        "--python", default="/opt/anaconda3/bin/python" if Path("/opt/anaconda3/bin/python").exists() else "python3"
    )
    parser.add_argument(
        "--out", type=Path, default=ROOT / "evaluation/reports/generic-dated-table-public-ab-v1.json"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    clean_env = {key: value for key, value in os.environ.items() if key not in {"MODEL_ENDPOINT", "MODEL_TOKEN", "MODEL_NAME"}}
    with TemporaryDirectory(prefix="t4-dated-baseline-") as baseline_tmp, TemporaryDirectory(prefix="t4-dated-candidate-") as candidate_tmp:
        baseline_root = Path(baseline_tmp)
        candidate_root = Path(candidate_tmp)
        archive = subprocess.check_output(
            ["git", "archive", args.baseline_commit, "t4-agent"], cwd=REPO
        )
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            bundle.extractall(baseline_root)
        baseline_project = baseline_root / "t4-agent"
        details = []
        for unit in sorted(path for path in args.units.iterdir() if path.is_dir()):
            baseline_answer = baseline_root / "out" / unit.name / "answer.json"
            candidate_answer = candidate_root / "out" / unit.name / "answer.json"
            baseline_answer.parent.mkdir(parents=True)
            candidate_answer.parent.mkdir(parents=True)
            subprocess.run(
                [args.python, str(baseline_project / "scripts/run_unit.py"), "--unit", str(unit), "--out", str(baseline_answer)],
                cwd=baseline_project,
                env=clean_env | {"PYTHONPATH": str(baseline_project)},
                check=True,
                stdout=subprocess.DEVNULL,
            )
            subprocess.run(
                [args.python, str(ROOT / "scripts/run_unit.py"), "--unit", str(unit), "--out", str(candidate_answer)],
                cwd=ROOT,
                env=clean_env | {"PYTHONPATH": str(ROOT), "T4_ENABLE_DATED_TABLE_BASELINE": "1"},
                check=True,
                stdout=subprocess.DEVNULL,
            )
            baseline_bytes = baseline_answer.read_bytes()
            candidate_bytes = candidate_answer.read_bytes()
            answer = json.loads(candidate_bytes)
            details.append(
                {
                    "task_id": unit.name,
                    "byte_identical": baseline_bytes == candidate_bytes,
                    "candidate_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
                    "rows": len(answer.get("entity_predictions", [])),
                    "validation_errors": len(answer.get("notes", {}).get("validation_errors") or []),
                }
            )
    report = {
        "experiment": "generic_dated_table_public_ab_v1",
        "baseline_commit": args.baseline_commit,
        "candidate_flag": "T4_ENABLE_DATED_TABLE_BASELINE=1",
        "model_calls": 0,
        "units": len(details),
        "rows": sum(item["rows"] for item in details),
        "byte_identical": sum(item["byte_identical"] for item in details),
        "validation_error_units": sum(bool(item["validation_errors"]) for item in details),
        "details": details,
    }
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("units", "rows", "byte_identical", "validation_error_units")}, indent=2))
    if report["byte_identical"] != report["units"] or report["validation_error_units"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
