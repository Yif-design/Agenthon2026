from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "evaluation/experiments/direct_point_entity_residual_interval_screen.py"
SPEC = importlib.util.spec_from_file_location("direct_point_entity_residual_interval_screen", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DirectPointEntityResidualIntervalScreenTest(unittest.TestCase):
    def test_entity_policies_are_schema_invariant(self) -> None:
        grouped = {}
        for locked in MODULE.locked_results():
            unit = MODULE.PROXY / "units" / locked["unit"]
            history = MODULE.extract_history(unit)
            policy = MODULE.entity_residual_policy(history)
            grouped.setdefault(locked["unit"].rsplit("-", 1)[0], []).append(
                (history["history_sha256"], policy["entity_policy_sha256"])
            )
        for variants in grouped.values():
            self.assertEqual(len(variants), 2)
            self.assertEqual(variants[0], variants[1])

    def test_gas_aggregate_does_not_set_regional_scale(self) -> None:
        locked = next(row for row in MODULE.locked_results() if "natural-gas" in row["unit"])
        history = MODULE.extract_history(MODULE.PROXY / "units" / locked["unit"])
        entities = MODULE.entity_residual_policy(history)["entities"]
        aggregate = entities["EIA_GAS_LOWER48_20260925"]["absolute_residual_q90"]
        regional = [
            row["absolute_residual_q90"] for entity_id, row in entities.items()
            if entity_id != "EIA_GAS_LOWER48_20260925"
        ]
        self.assertTrue(all(value < aggregate for value in regional))

    def test_candidate_changes_only_intervals(self) -> None:
        for locked in MODULE.locked_results():
            unit = MODULE.PROXY / "units" / locked["unit"]
            policy = MODULE.entity_residual_policy(MODULE.extract_history(unit))
            candidate, _ = MODULE.build_candidate(locked["candidate_answer"], policy)
            self.assertEqual(
                MODULE.without_intervals(candidate),
                MODULE.without_intervals(locked["candidate_answer"]),
            )
            for row in candidate["entity_predictions"]:
                self.assertLessEqual(row["interval"]["lo"], row["point_forecast"])
                self.assertGreaterEqual(row["interval"]["hi"], row["point_forecast"])

    def test_runner_has_no_model_client(self) -> None:
        source = PATH.read_text()
        self.assertNotIn("GeminiClient", source)
        self.assertNotIn("OpenRouter", source)


if __name__ == "__main__":
    unittest.main()
