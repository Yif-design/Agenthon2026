from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "evaluation/experiments/direct_forecast_reference_screen.py"
SPEC = importlib.util.spec_from_file_location("direct_forecast_reference_screen", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DirectForecastAdmissionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = {
            "entity_id": "X",
            "point_forecast": 1.0,
            "interval": {"level": 0.9, "lo": 0.0, "hi": 2.0},
            "claims": [{"claim": "old", "doc_id": "D", "span_start": 0, "span_end": 3}],
        }
        self.evidence = [{
            "evidence_id": "E0", "doc_id": "D", "span_start": 100,
            "text": "The reported comparable value was 2.4 percent in the prior period.",
        }]

    def test_exact_quote_admits_direct_forecast(self) -> None:
        quote = "reported comparable value was 2.4 percent"
        row, reason = MODULE.admit_prediction(
            {"point_forecast": 2.5, "interval": {"lo": 1.0, "hi": 4.0},
             "evidence_id": "E0", "evidence_quote": quote},
            self.baseline, self.evidence, 0.9,
        )
        self.assertEqual(reason, "admitted")
        self.assertEqual(row["point_forecast"], 2.5)
        self.assertEqual(row["claims"][0]["span_start"], 104)

    def test_unverified_quote_falls_back_byte_for_byte(self) -> None:
        row, reason = MODULE.admit_prediction(
            {"point_forecast": 2.5, "interval": {"lo": 1.0, "hi": 4.0},
             "evidence_id": "E0", "evidence_quote": "invented evidence text"},
            self.baseline, self.evidence, 0.9,
        )
        self.assertEqual(reason, "unverified_quote")
        self.assertEqual(row, self.baseline)

    def test_invalid_interval_falls_back(self) -> None:
        row, reason = MODULE.admit_prediction(
            {"point_forecast": 5.0, "interval": {"lo": 1.0, "hi": 4.0},
             "evidence_id": "E0", "evidence_quote": self.evidence[0]["text"]},
            self.baseline, self.evidence, 0.9,
        )
        self.assertEqual(reason, "invalid_numeric_contract")
        self.assertEqual(row, self.baseline)


if __name__ == "__main__":
    unittest.main()
