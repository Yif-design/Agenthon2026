from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "evaluation/experiments/canonical_numeric_context_ab.py"
SPEC = importlib.util.spec_from_file_location("canonical_numeric_context_ab", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CanonicalNumericContextABTest(unittest.TestCase):
    def test_selected_units_are_four_transformed_development_cases(self) -> None:
        units = MODULE.selected_units()
        self.assertEqual(len(units), 4)
        self.assertTrue(all(path.name.endswith("-transformed") for path in units))

    def test_request_pair_diff_is_confined_to_numeric_context(self) -> None:
        for unit in MODULE.selected_units():
            baseline = json.loads(
                (MODULE.PROXY / "baselines/control-v1" / unit.name / "answer.json").read_text()
            )
            control, control_evidence = MODULE.arm_request(unit, baseline, "control")
            candidate, candidate_evidence = MODULE.arm_request(unit, baseline, "candidate")
            self.assertEqual(control_evidence, candidate_evidence)
            self.assertEqual(
                MODULE.without_numeric_context(control),
                MODULE.without_numeric_context(candidate),
            )
            audit = MODULE.request_pair_audit(unit, baseline)
            self.assertTrue(audit["accepted_canonical_report_exact"])
            self.assertEqual(audit["forbidden_request_paths"], [])
            self.assertEqual(audit["forbidden_identifier_leaks"], [])

    def test_crude_candidate_converts_once_and_hides_abstained_values(self) -> None:
        unit = next(path for path in MODULE.selected_units() if "crude-inventory" in path.name)
        baseline = json.loads(
            (MODULE.PROXY / "baselines/control-v1" / unit.name / "answer.json").read_text()
        )
        control, _ = MODULE.arm_request(unit, baseline, "control")
        candidate, _ = MODULE.arm_request(unit, baseline, "candidate")
        entity_id = "EIA_CRUDE_PADD5_20260925"
        raw = next(row for row in control["rows"] if row["entity_id"] == entity_id)
        canonical = next(row for row in candidate["rows"] if row["entity_id"] == entity_id)
        raw_flow = next(row for row in raw["numeric_context"] if row["source_field"] == "one_period_flow_kb")
        converted = next(row for row in canonical["numeric_context"] if row["source_field"] == "one_period_flow_kb")
        self.assertEqual(raw_flow["value"], 569.0)
        self.assertAlmostEqual(converted["value"], 0.569)
        self.assertEqual(converted["unit"], "million_barrels")
        self.assertEqual(converted["status"], "canonical_once")

    def test_unknown_numeric_field_is_not_exposed_in_candidate_context(self) -> None:
        task = {"type": "regression", "name": "future_margin", "unit": "percent"}
        item = MODULE.canonicalize_entity(task, {"entity_id": "X", "mystery_value": 999.0})
        item["corpus_quantities"] = []
        self.assertEqual(MODULE.canonical_numeric_context(item), [])
        self.assertEqual(item["abstentions"][0]["source_field"], "mystery_value")


if __name__ == "__main__":
    unittest.main()
