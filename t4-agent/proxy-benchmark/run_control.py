#!/usr/bin/env python3
"""Run the current model-free agent on every materialized proxy unit."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from score_proxy import score


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--name", default="control-v1")
    args = parser.parse_args()
    repo = args.repo.resolve()
    units = repo / "proxy-benchmark/units"
    output_root = repo / "proxy-benchmark/baselines" / args.name
    results = []
    for unit in sorted(path for path in units.iterdir() if path.is_dir()):
        destination = output_root / unit.name
        answer = destination / "answer.json"
        trace = destination / "trace"
        answer.parent.mkdir(parents=True, exist_ok=True)
        run([
            sys.executable, "-m", "t4agent.cli", "analyze",
            "--task", str(unit / "task.json"), "--corpus", str(unit / "corpus"),
            "--out", str(answer), "--trace-dir", str(trace),
        ], repo)
        metrics = score(unit, answer)
        (destination / "score.json").write_text(json.dumps(metrics, indent=2) + "\n")
        rows = json.loads((trace / "rows.json").read_text())
        methods = sorted({str(row["method"]) for row in rows})
        fallbacks = sum(row["fallback_reason"] is not None for row in rows)
        results.append({**metrics, "methods": methods, "fallback_rows": fallbacks})
        for path in trace.iterdir():
            path.unlink()
        trace.rmdir()
    report = {
        "experiment": "proxy-18-cot-control-v1",
        "hypothesis": "A transformed but economically equivalent schema will expose material field-name dependence in the current control.",
        "python": sys.version.split()[0],
        "model_api_calls": 0,
        "scoring_semantics": "Track 4 5.2.2 predictive and interval metrics before claim penalty",
        "official_track_commit": "ede7381d8c1ba9d8c84068f9d142f5e093a33892",
        "toolkit_tag": "v2.5.1",
        "results": results,
        "decision": "reject_hypothesized_degradation",
        "finding": (
            "The route and units changed, but transformed composite did not decrease on this event. "
            "One event cannot establish schema robustness; expand the proxy benchmark before changing production."
        ),
        "limitations": [
            "One time-forward event and one family only.",
            "The local score excludes the official claim contradiction penalty and reasoning bonus.",
            "The transformed generic point is emitted in fraction-like scale while the target is percentage points; ranking is scale-invariant but interval scoring is not.",
        ],
    }
    report_path = repo / "evaluation/reports/proxy-18-cot-control-v1.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
