from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


def load_runner():
    path = PROJECT / "evaluation/run_benchmark_suite.py"
    spec = importlib.util.spec_from_file_location("run_benchmark_suite", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BenchmarkSuiteTest(unittest.TestCase):
    def test_unified_manifest_counts_events_once(self) -> None:
        manifest = json.loads((PROJECT / "evaluation/benchmark_suite.json").read_text())
        units = manifest["units"]
        self.assertEqual(len(units), 51)
        self.assertEqual(len({row["event_id"] for row in units}), 31)
        self.assertEqual(sum(float(row["event_weight"]) for row in units), 31.0)
        proxy_events = {row["event_id"] for row in units if row["cohort"] == "proxy"}
        for event_id in proxy_events:
            variants = [row for row in units if row["event_id"] == event_id]
            self.assertEqual({row["variant"] for row in variants}, {"explicit", "transformed"})
            self.assertEqual(sum(float(row["event_weight"]) for row in variants), 1.0)

    def test_public_predictive_quality_contract(self) -> None:
        runner = load_runner()
        rows = [
            {"point_forecast": 3.0, "label": "up"},
            {"point_forecast": 1.0, "label": "down"},
        ]
        truth = [
            {"value": 3.0, "label": "up"},
            {"value": 1.0, "label": "down"},
        ]
        self.assertEqual(runner.public_predictive_quality("classification", rows, truth), 1.0)
        self.assertEqual(runner.public_predictive_quality("regression", rows, truth), 1.0)
        self.assertEqual(runner.public_predictive_quality("ranking", rows, truth), 1.0)


if __name__ == "__main__":
    unittest.main()
