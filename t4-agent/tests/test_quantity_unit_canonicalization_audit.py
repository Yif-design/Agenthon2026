from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "evaluation/experiments/quantity_unit_canonicalization_audit.py"
SPEC = importlib.util.spec_from_file_location("quantity_unit_canonicalization_audit", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class QuantityUnitCanonicalizationTest(unittest.TestCase):
    def canonical(self, unit: str, field: str, value: float):
        result = MODULE.canonicalize_entity(
            {"type": "regression", "name": "future_value", "unit": unit},
            {"entity_id": "X", field: value},
        )
        self.assertEqual(len(result["quantities"]), 1)
        return result["quantities"][0]

    def test_fraction_to_percent_once(self) -> None:
        row = self.canonical("percent", "baseline_ratio_fraction", 0.03125)
        self.assertEqual(row["canonical_value"], 3.125)
        self.assertEqual(row["semantic_role"], "baseline_metric")
        self.assertEqual(MODULE.convert_once(row["canonical_value"], "percent", "percent"), 3.125)

    def test_basis_points_and_percent_conversion(self) -> None:
        self.assertEqual(self.canonical("basis_points", "recent_move_fraction", 0.0025)["canonical_value"], 25.0)
        self.assertEqual(self.canonical("basis_points", "recent_20d_change_bp", 25.0)["canonical_value"], 25.0)
        self.assertEqual(self.canonical("percent", "historical_variation_bp", 25.0)["canonical_value"], 0.25)

    def test_energy_scale_conversions(self) -> None:
        crude = self.canonical("million_barrels_change", "one_period_flow_kb", 569.0)
        gas = self.canonical("billion_cubic_feet_change", "one_period_flow_mmcf", 3000.0)
        self.assertAlmostEqual(crude["canonical_value"], 0.569)
        self.assertAlmostEqual(gas["canonical_value"], 3.0)
        self.assertEqual(crude["semantic_role"], gas["semantic_role"])

    def test_ambiguous_scalar_abstains(self) -> None:
        result = MODULE.canonicalize_entity(
            {"type": "regression", "name": "future_margin", "unit": "percent"},
            {"entity_id": "X", "mystery_value": 123.0},
        )
        self.assertEqual(result["quantities"], [])
        self.assertEqual(result["abstentions"][0]["reason"], "source_unit_not_explicit")

    def test_field_order_is_invariant(self) -> None:
        target = {"type": "regression", "name": "future_margin", "unit": "percent"}
        left = {"entity_id": "X", "baseline_ratio_fraction": 0.02, "recent_margin_pct": 2.5}
        right = dict(reversed(list(left.items())))
        self.assertEqual(MODULE.canonicalize_entity(target, left), MODULE.canonicalize_entity(target, right))

    def test_label_target_abstains(self) -> None:
        result = MODULE.canonicalize_entity(
            {"type": "classification", "name": "future_state", "unit": "label"},
            {"entity_id": "X", "tolerance_fraction": 0.01},
        )
        self.assertEqual(result["quantities"], [])
        self.assertEqual(result["abstentions"][0]["reason"], "target_has_no_supported_numeric_unit")


if __name__ == "__main__":
    unittest.main()
