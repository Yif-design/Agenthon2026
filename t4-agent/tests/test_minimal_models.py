from __future__ import annotations

import unittest
from dataclasses import replace
from statistics import pstdev

from t4agent.calculators.bank_eps import _find_pair
from t4agent.calc import select_default_point
from t4agent.family_specs import SPECS, family_spec, project_entity
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

    def test_eps_yoy_uses_cutoff_safe_calibrated_interval(self) -> None:
        current = task("eps_yoy_direction", "classification", ["up", "down"])
        result = solve_minimal(
            current,
            {"prior_year_q_eps": 2.0},
            SPECS["eps_yoy"],
            {"yoy_earnings_signal": 1},
            EMPTY_CORPUS,
            0,
            1,
        )
        self.assertAlmostEqual(result.point, 2.1)
        self.assertEqual(result.label, "up")
        self.assertAlmostEqual(result.interval["lo"], -0.65)
        self.assertAlmostEqual(result.interval["hi"], 4.85)
        self.assertTrue(result.derivation["calibrated_artifact_available"])

        historical = solve_minimal(
            replace(current, cutoff_date="2021-12-31"),
            {"prior_year_q_eps": 2.0},
            SPECS["eps_yoy"],
            {"yoy_earnings_signal": 1},
            EMPTY_CORPUS,
            0,
            1,
        )
        self.assertAlmostEqual(historical.point, result.point)
        self.assertAlmostEqual(historical.interval["lo"], 1.8)
        self.assertAlmostEqual(historical.interval["hi"], 2.4)
        self.assertFalse(historical.derivation["calibrated_artifact_available"])

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

    def test_generic_baseline_ignores_unrelated_numeric_metadata(self) -> None:
        entity = {
            "latest_revenue_growth_pct": 8.0,
            "market_cap_bn": 200.0,
            "fiscal_year": 2024,
            "internal_row_id": 999999,
        }

        point, field, reason = select_default_point(
            "regression", "revenue_growth_next_q_pct", entity, 0, 1
        )

        self.assertEqual(point, 8.0)
        self.assertEqual(field, "latest_revenue_growth_pct")
        self.assertEqual(reason, "target_token_match")

    def test_generic_baseline_prefers_current_over_prior_matching_field(self) -> None:
        point, field, reason = select_default_point(
            "regression",
            "revenue_growth_next_q_pct",
            {"prior_revenue_growth_pct": 3.0, "latest_revenue_growth_pct": 8.0},
            0,
            1,
        )

        self.assertEqual(point, 8.0)
        self.assertEqual(field, "latest_revenue_growth_pct")
        self.assertEqual(reason, "target_token_match")

    def test_generic_baseline_handles_camel_case_and_field_order(self) -> None:
        first = {"recentRevenueGrowthPct": 8.0, "currentRevenueGrowthPct": 7.0}
        second = dict(reversed(list(first.items())))

        choice_a = select_default_point("regression", "revenue_growth_next_q_pct", first, 0, 1)
        choice_b = select_default_point("regression", "revenue_growth_next_q_pct", second, 0, 1)

        self.assertEqual(choice_a, choice_b)
        self.assertEqual(choice_a[:2], (7.0, "currentRevenueGrowthPct"))

    def test_generic_ranking_baseline_is_invariant_to_row_order(self) -> None:
        first = {"recent_net_flow_change_pct_oi": -3.0, "market_size_bn": 100.0}
        second = {"recent_net_flow_change_pct_oi": 4.0, "market_size_bn": 200.0}
        target = "five_week_net_flow_change_pct_oi"

        original = [
            select_default_point("ranking", target, first, 0, 2)[0],
            select_default_point("ranking", target, second, 1, 2)[0],
        ]
        reordered = [
            select_default_point("ranking", target, second, 0, 2)[0],
            select_default_point("ranking", target, first, 1, 2)[0],
        ]

        self.assertEqual(original, [-3.0, 4.0])
        self.assertEqual(reordered, [4.0, -3.0])

    def test_generic_change_target_does_not_reuse_a_level_field(self) -> None:
        point, field, reason = select_default_point(
            "regression",
            "yield_delta_bps",
            {"start_yield_pct": 4.5, "maturity_years": 2, "fiscal_year": 2024},
            0,
            1,
        )

        self.assertEqual(point, 0.0)
        self.assertIsNone(field)
        self.assertEqual(reason, "change_without_matching_baseline")

    def test_generic_ambiguous_unrelated_fields_use_neutral_baseline(self) -> None:
        point, field, reason = select_default_point(
            "regression",
            "unknown_metric",
            {"market_cap_bn": 200.0, "fiscal_year": 2024},
            0,
            1,
        )

        self.assertEqual(point, 0.0)
        self.assertIsNone(field)
        self.assertEqual(reason, "no_unambiguous_baseline")

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
        self.assertEqual(result.interval, {"level": 0.9, "lo": 0.0, "hi": 1.0})

    def test_postearn_interval_uses_historical_announcement_volatility(self) -> None:
        current = task("earnings_reaction", "classification", ["positive_reaction", "negative_reaction", "flat"])
        result = solve_minimal(
            current,
            {"flat_threshold_abn_pct": 1.0},
            SPECS["reaction"],
            {"explicit_forward_outlook_signal": 0},
            EMPTY_CORPUS,
            0,
            1,
        )
        self.assertEqual(result.label, "flat")
        self.assertEqual(result.point, 0.0)
        self.assertEqual(result.interval, {"level": 0.9, "lo": -8.3, "hi": 8.3})
        historical = solve_minimal(
            replace(current, cutoff_date="2021-12-31"),
            {"flat_threshold_abn_pct": 1.0},
            SPECS["reaction"],
            {"explicit_forward_outlook_signal": 0},
            EMPTY_CORPUS,
            0,
            1,
        )
        self.assertEqual(historical.interval, {"level": 0.9, "lo": -2.5, "hi": 2.5})
        self.assertFalse(historical.derivation["calibrated_artifact_available"])

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

    def test_auction_uses_recent_six_mean_and_calibrated_interval(self) -> None:
        values = [1.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6]
        lines = ["10-Year Treasury auction results", "date | a | b | c | bid_to_cover"]
        lines.extend(
            f"2024-{month:02d}-01 | x | x | x | {value}"
            for month, value in enumerate(values, start=1)
        )
        text = "\n".join(lines)
        corpus = IndexedCorpus(
            [],
            {"TDIRECT_AUCTIONS_10Y": text},
            {"TDIRECT_AUCTIONS_10Y": "2024-08-01"},
        )
        current = task("bid_to_cover_ratio", "regression")
        result = solve_minimal(
            current,
            {"tenor": "10-Year"},
            SPECS["auction"],
            {},
            corpus,
            0,
            1,
        )
        recent = values[-6:]
        point = sum(recent) / len(recent)
        half = max(0.15, 2.5 * pstdev(recent))
        self.assertAlmostEqual(result.point, point)
        self.assertAlmostEqual(result.interval["lo"], point - half)
        self.assertAlmostEqual(result.interval["hi"], point + half)
        self.assertEqual(result.derivation["recent_values"], recent)
        self.assertNotIn("2024-01-01", result.evidence[0]["quote"])
        self.assertIn("2024-07-01", result.evidence[0]["quote"])

        historical = solve_minimal(
            replace(current, cutoff_date="2021-12-31"),
            {"tenor": "10-Year"},
            SPECS["auction"],
            {},
            corpus,
            0,
            1,
        )
        old_trend = min(0.08, max(-0.08, (values[-1] - values[-3]) / 2.0))
        self.assertAlmostEqual(historical.point, point + old_trend)
        self.assertEqual(historical.derivation["interval_pstdev_multiplier"], 1.65)
        self.assertFalse(historical.derivation["calibrated_artifact_available"])

    def test_auction_prefers_only_a_verified_recent_six_summary(self) -> None:
        values = [2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7]
        lines = ["10-Year Treasury auction results", "date | a | b | c | bid_to_cover"]
        lines.extend(
            f"2024-{month:02d}-01 | x | x | x | {value}"
            for month, value in enumerate(values, start=1)
        )
        verified_note = (
            "NOTES (derived from the table above): the average over the six most recent "
            "auctions is 2.450; the historical range was 2.10 to 2.70."
        )
        corpus = IndexedCorpus(
            [],
            {"TDIRECT_AUCTIONS_10Y": "\n".join(lines + ["", verified_note])},
            {"TDIRECT_AUCTIONS_10Y": "2024-08-01"},
        )
        current = task("bid_to_cover_ratio", "regression")

        result = solve_minimal(
            current,
            {"tenor": "10-Year"},
            SPECS["auction"],
            {},
            corpus,
            0,
            1,
        )

        self.assertEqual(result.evidence[0]["quote"], verified_note)

        bad_note = verified_note.replace("2.450", "9.999")
        mismatched = IndexedCorpus(
            [],
            {"TDIRECT_AUCTIONS_10Y": "\n".join(lines + ["", bad_note])},
            {"TDIRECT_AUCTIONS_10Y": "2024-08-01"},
        )
        mismatch_result = solve_minimal(
            current,
            {"tenor": "10-Year"},
            SPECS["auction"],
            {},
            mismatched,
            0,
            1,
        )
        self.assertNotIn("NOTES", mismatch_result.evidence[0]["quote"])

        historical_result = solve_minimal(
            replace(current, cutoff_date="2021-12-31"),
            {"tenor": "10-Year"},
            SPECS["auction"],
            {},
            corpus,
            0,
            1,
        )
        self.assertNotIn("NOTES", historical_result.evidence[0]["quote"])

    def test_positioning_uses_latest_dated_net_position(self) -> None:
        current = task("position_change_5wk_pct_oi", "ranking")
        entity = project_entity(
            {
                "entity_id": "GOLD_CMX",
                "trailing_4wk_net_change_pct_oi": 6.0,
                "net_pct_oi_20231231": 30.0,
                "net_pct_oi_20240101": -20.0,
                "net_pct_oi_20251231": -99.0,
            },
            SPECS["positioning"],
        )
        result = solve_minimal(current, entity, SPECS["positioning"], {}, EMPTY_CORPUS, 0, 1)
        self.assertEqual(result.point, 4.0)
        self.assertEqual(result.interval["level"], 0.9)
        self.assertAlmostEqual(result.interval["lo"], -7.3)
        self.assertAlmostEqual(result.interval["hi"], 15.3)
        self.assertEqual(result.method, "net_position_mean_reversion")
        self.assertEqual(result.derivation["current_net_pct_oi_field"], "net_pct_oi_20240101")
        historical = solve_minimal(
            replace(current, cutoff_date="2021-12-31"),
            entity,
            SPECS["positioning"],
            {},
            EMPTY_CORPUS,
            0,
            1,
        )
        self.assertEqual(historical.point, 6.0)
        self.assertEqual(historical.interval, {"level": 0.9, "lo": -2.0, "hi": 14.0})
        self.assertEqual(historical.method, "trailing_change_crowding_cap")
        self.assertFalse(historical.derivation["calibrated_artifact_available"])

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
        self.assertAlmostEqual(result.interval["lo"], -0.449)
        self.assertAlmostEqual(result.interval["hi"], 1.051)
        historical = solve_minimal(
            replace(current, cutoff_date="2021-12-31"),
            {"entity_id": "CPI_CORE", "name": "All items less food and energy (core CPI)", "latest_published_mom_pct": 0.31},
            SPECS["cpi"],
            {},
            corpus,
            0,
            1,
        )
        self.assertAlmostEqual(historical.point, result.point)
        self.assertAlmostEqual(historical.interval["lo"], result.point - 0.35)
        self.assertAlmostEqual(historical.interval["hi"], result.point + 0.35)
        self.assertFalse(historical.derivation["calibrated_artifact_available"])


if __name__ == "__main__":
    unittest.main()
