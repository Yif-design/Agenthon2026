from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "evaluation/experiments/conservative_review_reference_screen.py"
SPEC = importlib.util.spec_from_file_location("conservative_review_reference_screen", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ConservativeReviewAdmissionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = {
            "entity_id": "X",
            "point_forecast": 1.0,
            "interval": {"level": 0.9, "lo": 0.0, "hi": 2.0},
            "claims": [{"claim": "old", "doc_id": "D", "span_start": 0, "span_end": 3}],
        }
        self.draft = {
            "entity_id": "X",
            "point_forecast": 4.0,
            "interval": {"level": 0.9, "lo": 2.0, "hi": 6.0},
            "claims": [{"claim": "draft", "doc_id": "D", "span_start": 10, "span_end": 15}],
        }
        self.quote = "reported comparable value was 2.4 percent"
        self.evidence = [{
            "evidence_id": "E0",
            "doc_id": "D",
            "span_start": 100,
            "text": "The reported comparable value was 2.4 percent in the prior period.",
        }]

    def review(self, **values):
        raw = {"action": "baseline", "evidence_id": "E0", "evidence_quote": self.quote}
        raw.update(values)
        return MODULE.review_prediction(raw, self.baseline, self.draft, self.evidence, 0.9)

    def test_grounded_baseline_selection_is_exact(self) -> None:
        row, reason = self.review()
        self.assertEqual(reason, "selected_baseline")
        self.assertEqual(row, self.baseline)

    def test_grounded_draft_selection_is_exact(self) -> None:
        row, reason = self.review(action="draft")
        self.assertEqual(reason, "selected_draft")
        self.assertEqual(row, self.draft)

    def test_grounded_revision_builds_exact_claim(self) -> None:
        row, reason = self.review(
            action="revised",
            point_forecast=2.5,
            interval={"lo": 1.0, "hi": 4.0},
        )
        self.assertEqual(reason, "selected_revised")
        self.assertEqual(row["point_forecast"], 2.5)
        self.assertEqual(row["claims"][0]["span_start"], 104)

    def test_unverified_quote_falls_back(self) -> None:
        row, reason = self.review(evidence_quote="invented evidence text")
        self.assertEqual(reason, "unverified_review_quote")
        self.assertEqual(row, self.baseline)

    def test_invalid_action_falls_back(self) -> None:
        row, reason = self.review(action="accept_everything")
        self.assertEqual(reason, "invalid_action")
        self.assertEqual(row, self.baseline)


if __name__ == "__main__":
    unittest.main()
