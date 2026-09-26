from __future__ import annotations

import unittest

from t4agent.family_specs import SPECS, family_spec, project_entity
from t4agent.calculators.bank_eps import _find_pair
from t4agent.minimal_models import normalize_parameters, normalize_signals, solve_minimal
from t4agent.retrieve import IndexedCorpus
from t4agent.taskio import Task


EMPTY_CORPUS = IndexedCorpus([], {}, {})


def task(target_name: str, target_type: str, labels: list[str] | None = None) -> Task:
    return Task(
        raw={},
        task_id="test",
        schema_version="3",
        target={"name": target_name, "type": target_type, "labels": labels or []},
        target_type=target_type,
        labels=labels or [],
        entities=[],
        cutoff_date="2024-01-01",
        interval_level=0.90,
        prompt="",
        family="",
    )


class FamilySpecTests(unittest.TestCase):
    def test_routes_known_targets(self) -> None:
        self.assertEqual(family_spec("", "eps_outcome").key, "eps_consensus")
        self.assertEqual(family_spec("", "bid_to_cover_ratio").key, "auction")
        self.assertEqual(family_spec("", "cpi_component_mom_first_print").key, "cpi")

    def test_signal_normalization_clamps_and_defaults(self) -> None:
        parsed = {"signals": {"target_period_earnings_signal": {"level": 9}}}
        self.assertEqual(normalize_signals(parsed, SPECS["eps_consensus"]), {"target_period_earnings_signal": 2})
        self.assertEqual(normalize_signals(None, SPECS["eps_consensus"]), {"target_period_earnings_signal": 0})

    def test_entity_projection_enforces_family_whitelist(self) -> None:
        projected = project_entity(
            {"entity_id": "AAPL", "consensus_eps": 1.5, "threshold_pct": 0.05, "mktcap_bn": 2600},
            SPECS["eps_consensus"],
        )
        self.assertEqual(projected, {"entity_id": "AAPL", "consensus_eps": 1.5, "threshold_pct": 0.05})

    def test_generic_projection_keeps_only_identity_and_numeric_baselines(self) -> None:
        projected = project_entity(
            {"entity_id": "X", "latest_value": 12.5, "description": "secret prose", "active": True},
            SPECS["generic"],
        )
        self.assertEqual(projected, {"entity_id": "X", "latest_value": 12.5})

    def test_numeric_parameters_require_explicit_values(self) -> None:
        parsed = {
            "parameters": {
                "latest_reported_eps": {"value": 1.2},
                "latest_reported_prior_year_eps": {"value": None},
            }
        }
        self.assertEqual(
            normalize_parameters(parsed, SPECS["bank_eps"]),
            {"latest_reported_eps": 1.2, "latest_reported_prior_year_eps": None},
        )


class MinimalModelTests(unittest.TestCase):
    def test_bank_eps_extracts_pair_across_comparison_amount(self) -> None:
        text = (
            "reported net income of $1.6 billion, or $0.97 per diluted common share, "
            "compared with $1.4 billion, or $0.84 per diluted common share, for the prior-year quarter"
        )
        pair = _find_pair(text)
        self.assertIsNotNone(pair)
        self.assertEqual(pair[:2], (0.97, 0.84))

    def test_eps_consensus_neutral_is_inline(self) -> None:
        current = task("eps_outcome", "classification", ["beat", "miss", "inline"])
        result = solve_minimal(
            current,
            {"consensus_eps": 1.5, "threshold_pct": 0.05},
            SPECS["eps_consensus"],
            {"target_period_earnings_signal": 0},
            EMPTY_CORPUS,
            0,
            1,
        )
        self.assertEqual(result.point, 1.5)
        self.assertEqual(result.label, "inline")

    def test_eps_consensus_only_strong_signal_crosses_threshold(self) -> None:
        current = task("eps_outcome", "classification", ["beat", "miss", "inline"])
        mild = solve_minimal(
            current,
            {"consensus_eps": 1.5, "threshold_pct": 0.05},
            SPECS["eps_consensus"],
            {"target_period_earnings_signal": 1},
            EMPTY_CORPUS,
            0,
            1,
        )
        strong = solve_minimal(
            current,
            {"consensus_eps": 1.5, "threshold_pct": 0.05},
            SPECS["eps_consensus"],
            {"target_period_earnings_signal": 2},
            EMPTY_CORPUS,
            0,
            1,
        )
        self.assertEqual(mild.label, "inline")
        self.assertEqual(strong.label, "beat")

    def test_generic_regression_uses_grounded_direction_as_small_adjustment(self) -> None:
        current = task("unknown_metric", "regression")
        neutral = solve_minimal(current, {"latest_value": 12.0}, SPECS["generic"], {}, EMPTY_CORPUS, 0, 1)
        positive = solve_minimal(
            current,
            {"latest_value": 12.0},
            SPECS["generic"],
            {"directional_signal": 1},
            EMPTY_CORPUS,
            0,
            1,
        )
        self.assertEqual(neutral.point, 12.0)
        self.assertGreater(positive.point, neutral.point)
        self.assertEqual(positive.method, "generic_evidence_adjusted")

    def test_credit_default_uses_high_risk_tier(self) -> None:
        current = task("credit_event_12m", "classification", ["credit_event", "no_event"])
        result = solve_minimal(
            current,
            {},
            SPECS["credit"],
            {"covenant_breach_or_payment_default": 2},
            EMPTY_CORPUS,
            0,
            1,
        )
        self.assertEqual(result.point, 0.85)
        self.assertEqual(result.label, "credit_event")

    def test_rates_use_fixed_maturity_sensitivity(self) -> None:
        current = task("yield_change_bps_intermeeting", "regression")
        points = []
        for maturity in (2, 10, 30):
            result = solve_minimal(
                current,
                {"maturity_years": maturity},
                SPECS["rates"],
                {"policy_direction": 1},
                EMPTY_CORPUS,
                0,
                1,
            )
            points.append(result.point)
        self.assertEqual(points, [15.0, 9.0, 6.0])

    def test_bank_eps_uses_recent_yoy_delta(self) -> None:
        current = task("eps_yoy_growth_pct", "regression")
        result = solve_minimal(
            current,
            {"prior_year_q_eps": 2.0},
            SPECS["bank_eps"],
            {},
            EMPTY_CORPUS,
            0,
            1,
            {"latest_reported_eps": 1.8, "latest_reported_prior_year_eps": 1.6},
        )
        self.assertAlmostEqual(result.point, 10.0)

    def test_bank_eps_missing_number_falls_back_to_zero_growth(self) -> None:
        current = task("eps_yoy_growth_pct", "regression")
        result = solve_minimal(
            current,
            {"prior_year_q_eps": 2.0},
            SPECS["bank_eps"],
            {},
            EMPTY_CORPUS,
            0,
            1,
            {"latest_reported_eps": 1.8, "latest_reported_prior_year_eps": None},
        )
        self.assertEqual(result.point, 0.0)

    def test_core_cpi_is_not_treated_as_energy(self) -> None:
        cpi_text = """U.S. CPI-U components\nmonth | All items less food and energy (core CPI) | Energy\n2024-07 | +0.17 | +0.03\n2024-08 | +0.28 | -0.78\n2024-09 | +0.31 | -1.85\n"""
        gas_text = "NOTE: U.S. regular gasoline retail price; the average pump price over the October weeks shown (3.137) is -2.4% versus September."
        corpus = IndexedCorpus([], {"CPI": cpi_text, "GAS": gas_text}, {"CPI": "2024-01-01", "GAS": "2024-01-01"})
        current = task("cpi_component_mom_first_print", "regression")
        result = solve_minimal(
            current,
            {"entity_id": "CPI_CORE", "name": "All items less food and energy (core CPI)", "latest_published_mom_pct": 0.31},
            SPECS["cpi"],
            {},
            corpus,
            0,
            1,
        )
        self.assertAlmostEqual(result.point, 0.301)


if __name__ == "__main__":
    unittest.main()
