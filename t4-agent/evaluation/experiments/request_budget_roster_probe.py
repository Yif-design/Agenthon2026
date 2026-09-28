#!/usr/bin/env python3
"""Compare roster coverage under bounded House request caps without a model."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from t4agent.llm import LLM  # noqa: E402


class Response:
    def __init__(self, content: str) -> None:
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(
            {
                "choices": [{"message": {"content": self.content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4},
            }
        ).encode()


def simulate(roster: int, cap: int, failure: str = "none") -> dict:
    network_calls = 0

    def respond(*_args, **_kwargs):
        nonlocal network_calls
        network_calls += 1
        malformed = failure == "persistent" or (failure == "one_transient" and network_calls == 1)
        return Response("not json" if malformed else '{"signals": {}}')

    environment = {
        "MODEL_ENDPOINT": "http://model:8443",
        "MODEL_NAME": "house",
        "MODEL_TOKEN": "test-only-token",
        "T4_MODEL_RETRIES": "2",
        "T4_MODEL_MAX_CALLS": str(cap),
    }
    enhanced = 0
    with (
        patch.dict(os.environ, environment, clear=False),
        patch("urllib.request.urlopen", side_effect=respond),
        patch("time.sleep"),
    ):
        llm = LLM()
        for start in range(0, roster, 3):
            if llm.chat_json("system", f"batch {start // 3}") is not None:
                enhanced += min(3, roster - start)
    return {
        "roster": roster,
        "enhanced_rows": enhanced,
        "fallback_rows": roster - enhanced,
        "attempted_calls": llm.usage.calls,
        "network_calls": network_calls,
        "configured_cap": cap,
        "circuit_open": llm.usage.circuit_open,
        "disabled_reason": llm.usage.disabled_reason,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    scenarios = {
        "all_success_60": (60, "none"),
        "all_success_75": (75, "none"),
        "all_success_78": (78, "none"),
        "one_transient_60": (60, "one_transient"),
        "one_transient_75": (75, "one_transient"),
        "persistent_60": (60, "persistent"),
    }
    report = {
        "schema_version": 1,
        "date": "2026-09-28",
        "experiment": "official_request_budget_roster_v1",
        "baseline_git_commit": "17d1d4539a92b3761f3c094aeb8dfed60ba059c6",
        "hypothesis": (
            "Using the full official 25-request allowance increases large-roster model coverage "
            "without issuing a 26th request or weakening the persistent-failure circuit."
        ),
        "batch_size": 3,
        "per_batch_retries": 2,
        "official_request_cap": 25,
        "baseline_default_cap": 18,
        "candidate_default_cap": 25,
        "baseline": {
            name: simulate(roster, 18, failure) for name, (roster, failure) in scenarios.items()
        },
        "candidate": {
            name: simulate(roster, 25, failure) for name, (roster, failure) in scenarios.items()
        },
        "remote_model_calls": 0,
        "local_llm_run": False,
        "source": (
            "https://github.com/Agenthon-2026/Agenthon2026-public/blob/main/"
            "docs/DEVELOPMENT-RUNTIME.md#house-request-allowance"
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
