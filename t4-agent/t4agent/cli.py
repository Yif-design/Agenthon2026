from __future__ import annotations

import argparse
import pathlib
import sys

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
    args = parser.parse_args(argv)

    task = load_task(args.task)
    corpus = build_index(args.corpus, task.cutoff_date)
    bm25 = BM25(corpus.chunks)
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    llm = LLM(root_dir=repo_root)
    results = predict_rows(task, bm25, corpus, llm, max(1, args.top_k))
    answer = build_answer(task, results, corpus, llm.usage)
    write_json(args.out, answer)

    errors = answer.get("notes", {}).get("validation_errors") or []
    if errors:
        print(f"wrote {args.out} with {len(errors)} local validation warning(s)", file=sys.stderr)
    else:
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
