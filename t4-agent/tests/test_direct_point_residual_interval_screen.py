from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "evaluation/experiments/direct_point_residual_interval_screen.py"
SPEC = importlib.util.spec_from_file_location("direct_point_residual_interval_screen", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DirectPointResidualIntervalScreenTest(unittest.TestCase):
    def test_locked_report_has_four_schema_pairs(self) -> None:
        rows = MODULE.locked_results()
        self.assertEqual(len(rows), 8)
        self.assertEqual({row["variant"] for row in rows}, {"explicit", "transformed"})

    def test_history_is_schema_invariant_and_selects_target_role(self) -> None:
        grouped = {}
        for locked in MODULE.locked_results():
            unit = MODULE.PROXY / "units" / locked["unit"]
            history = MODULE.extract_history(unit)
            grouped.setdefault(locked["unit"].rsplit("-", 1)[0], []).append(history)
            if "crude-inventory" in locked["unit"] or "natural-gas" in locked["unit"]:
                self.assertTrue(history["series"])
                self.assertTrue(all(row["role"] == "change" for row in history["series"].values()))
        for values in grouped.values():
            self.assertEqual(len(values), 2)
            self.assertEqual(values[0]["history_sha256"], values[1]["history_sha256"])
            self.assertEqual(
                MODULE.residual_policy(values[0])["residual_sha256"],
                MODULE.residual_policy(values[1])["residual_sha256"],
            )

    def test_capex_preserves_interval_when_target_history_is_insufficient(self) -> None:
        locked = next(row for row in MODULE.locked_results() if "capex" in row["unit"])
        unit = MODULE.PROXY / "units" / locked["unit"]
        history = MODULE.extract_history(unit)
        policy = MODULE.residual_policy(history)
        candidate, changed = MODULE.build_candidate(locked["candidate_answer"], history, policy)
        self.assertFalse(policy["eligible"])
        self.assertEqual(changed, 0)
        self.assertEqual(candidate, locked["candidate_answer"])

    def test_candidate_changes_only_intervals_and_contains_points(self) -> None:
        for locked in MODULE.locked_results():
            unit = MODULE.PROXY / "units" / locked["unit"]
            history = MODULE.extract_history(unit)
            policy = MODULE.residual_policy(history)
            candidate, _ = MODULE.build_candidate(locked["candidate_answer"], history, policy)
            self.assertEqual(
                MODULE.without_intervals(candidate),
                MODULE.without_intervals(locked["candidate_answer"]),
            )
            for row in candidate["entity_predictions"]:
                self.assertLessEqual(row["interval"]["lo"], row["point_forecast"])
                self.assertGreaterEqual(row["interval"]["hi"], row["point_forecast"])

    def test_report_source_is_locked_and_has_no_model_client(self) -> None:
        source = PATH.read_text()
        self.assertNotIn("GeminiClient", source)
        self.assertNotIn("OpenRouter", source)
        self.assertEqual(json.loads(MODULE.LOCKED_REPORT.read_text())["usage"]["calls"], 8)


if __name__ == "__main__":
    unittest.main()
