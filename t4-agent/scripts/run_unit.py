from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit", type=pathlib.Path, required=True)
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("runs/answer.json"))
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--trace-dir", type=pathlib.Path)
    args = parser.parse_args()
    cmd = [
        sys.executable,
        "-m",
        "t4agent.cli",
        "analyze",
        "--task",
        str(args.unit / "task.json"),
        "--corpus",
        str(args.unit / "corpus"),
        "--out",
        str(args.out),
        "--top-k",
        str(args.top_k),
    ]
    if args.trace_dir is not None:
        cmd.extend(["--trace-dir", str(args.trace_dir)])
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
