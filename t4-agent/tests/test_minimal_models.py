from __future__ import annotations

import math
import unittest
from dataclasses import replace
from statistics import pstdev

from t4agent.calculators.bank_eps import _find_pair
from t4agent.calculators.generic import _label, infer_label_roles
from t4agent.calc import select_default_point
from t4agent.family_specs import SPECS, family_spec, project_entity, task_family_spec
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

    def test_router_uses_complete_signatures_instead_of_substrings(self) -> None:
        collisions = [
            ("inventory_forecast", "inventory_position_rank"),
            ("housing", "auction_price_change"),
            ("equity_research", "analyst_revision_probability"),
            ("agriculture", "cotton_yield_rank"),
            ("marketing", "credit_eventual_return"),
            ("sports", "rate_curveball_score"),
            ("supply_chain", "positioning_of_inventory"),
        ]

        self.assertEqual([family_spec(family, target).key for family, target in collisions], ["generic"] * 7)

    def test_router_accepts_anchored_known_family_variants(self) -> None:
        cases = [
            ("eps_beat_consensus_v2", "future_eps_class", "eps_consensus"),
            ("", "eps_beat_consensus_probability", "eps_consensus"),
            ("credit_event_cross_section", "event_probability", "credit"),
            ("post_earnings_reaction_v2", "abnormal_return_class", "reaction"),
            ("rate_curve_scenario", "tenor_move", "rates"),
            ("cpi_component_forecast", "first_print", "cpi"),
            ("macro_revision_panel", "direction", "macro_revision"),
            ("auction_demand_panel", "ratio", "auction"),
            ("positioning_shift_panel", "rank", "positioning"),
            ("cftc_positioning_panel", "rank", "positioning"),
        ]

        self.assertEqual(
            [family_spec(family, target).key for family, target, _ in cases],
            [expected for _, _, expected in cases],
        )

    def test_task_router_recovers_unique_complete_structural_signatures(self) -> None:
        cases = [
            ("classification", {"consensus_eps": 1.2, "threshold_pct": 0.05}, "eps_consensus"),
            (
                "classification",
                {"prior_year_q_eps": 1.0, "prior_year_quarter": "Q2", "quarter_reported": "Q2"},
                "eps_yoy",
            ),
            (
                "classification",
                {
                    "report_datetime": "2026-01-01",
                    "event_window": "next_day",
                    "benchmark": "SPY",
                    "flat_threshold_abn_pct": 1.0,
                },
                "reaction",
            ),
            (
                "classification",
                {
                    "latest_precutoff_estimate": 1.0,
                    "latest_precutoff_vintage": "2026-01-01",
                    "resolving_release_date": "2026-02-01",
                },
                "macro_revision",
            ),
            (
                "regression",
                {"cik": "1", "prior_year_q_eps": 1.0, "prior_year_quarter": "Q2", "quarter_reported": "Q2"},
                "bank_eps",
            ),
            ("regression", {"maturity_years": 2, "start_yield_pct": 4.0, "as_of": "2026-01-01"}, "rates"),
            (
                "regression",
                {
                    "series_fred": "CPI",
                    "ref_month": "2026-01",
                    "latest_published_mom_pct": 0.2,
                    "latest_published_ref_month": "2025-12",
                },
                "cpi",
            ),
            (
                "regression",
                {"tenor": "10Y", "auction_date": "2026-01-01", "new_or_reopening": "new", "offering_amount_usd_bn": 40},
                "auction",
            ),
            (
                "ranking",
                {
                    "asset_class": "rates",
                    "net_noncommercial_20260901": 1,
                    "open_interest_20260901": 2,
                    "net_pct_oi_20260901": 0.5,
                },
                "positioning",
            ),
        ]

        self.assertEqual(
            [task_family_spec("unseen_finance", "opaque_target", target_type, [entity]).key for target_type, entity, _ in cases],
            [expected for _, _, expected in cases],
        )

    def test_task_router_requires_complete_roster_wide_unique_signature(self) -> None:
        complete_rates = {"maturity_years": 2, "start_yield_pct": 4.0, "as_of": "2026-01-01"}
        partial_rates = {"maturity_years": 10, "start_yield_pct": 4.2}
        ambiguous_regression = {
            **complete_rates,
            "series_fred": "CPI",
            "ref_month": "2026-01",
            "latest_published_mom_pct": 0.2,
            "latest_published_ref_month": "2025-12",
        }

        self.assertEqual(
            task_family_spec("unseen_finance", "opaque_target", "regression", [complete_rates, partial_rates]).key,
            "generic",
        )
        self.assertEqual(
            task_family_spec("unseen_finance", "opaque_target", "regression", [ambiguous_regression]).key,
            "generic",
        )
        self.assertEqual(
            task_family_spec("unseen_finance", "opaque_target", "classification", [complete_rates]).key,
            "generic",
        )

    def test_task_router_rejects_present_but_unusable_signature_values(self) -> None:
        cases = [
            ("classification", {"consensus_eps": None, "threshold_pct": 0.05}),
            (
                "classification",
                {"prior_year_q_eps": math.nan, "prior_year_quarter": "Q2", "quarter_reported": "Q2"},
            ),
            (
                "classification",
                {
                    "report_datetime": " ",
                    "event_window": "next_day",
                    "benchmark": "SPY",
                    "flat_threshold_abn_pct": 1.0,
                },
            ),
            (
                "classification",
                {
                    "latest_precutoff_estimate": None,
                    "latest_precutoff_vintage": "2026-01-01",
                    "resolving_release_date": "2026-02-01",
                },
            ),
            (
                "regression",
                {"cik": "", "prior_year_q_eps": 1.0, "prior_year_quarter": "Q2", "quarter_reported": "Q2"},
            ),
            ("regression", {"maturity_years": 2, "start_yield_pct": math.inf, "as_of": "2026-01-01"}),
            (
                "regression",
                {
                    "series_fred": "CPI",
                    "ref_month": "2026-01",
                    "latest_published_mom_pct": None,
                    "latest_published_ref_month": "2025-12",
                },
            ),
            (
                "regression",
                {"tenor": "10Y", "auction_date": "2026-01-01", "new_or_reopening": " ", "offering_amount_usd_bn": 40},
            ),
            (
                "ranking",
                {
                    "asset_class": "rates",
                    "net_noncommercial_20260901": 1,
                    "open_interest_20260901": None,
                    "net_pct_oi_20260901": 0.5,
                },
            ),
        ]

        self.assertEqual(
            [task_family_spec("unseen_finance", "opaque_target", target_type, [entity]).key for target_type, entity in cases],
            ["generic"] * len(cases),
        )

    def test_signal_normalization_clamps_and_defaults(self) -> None:
        parsed = {"signals": {"target_period_earnings_signal": {"level": 9}}}
        self.assertEqual(normalize_signals(parsed, SPECS["eps_consensus"]), {"target_period_earnings_signal": 2})
        self.assertEqual(normalize_signals(None, SPECS["eps_consensus"]), {"target_period_earnings_signal": 0})

    def test_signal_normalization_rejects_boolean_and_nonfinite_levels(self) -> None:
        for value in (True, False, float("nan"), float("inf"), float("-inf")):
            parsed = {"signals": {"target_period_earnings_signal": {"level": value}}}
            self.assertEqual(
                normalize_signals(parsed, SPECS["eps_consensus"]),
                {"target_period_earnings_signal": 0},
            )

    def test_entity_projection_enforces_family_whitelist(self) -> None:
        projected = project_entity(
            {"entity_id": "AAPL", "consensus_eps": 1.5, "threshold_pct": 0.05, "mktcap_bn": 2600},
            SPECS["eps_consensus"],
        )
        self.assertEqual(projected, {"entity_id": "AAPL", "consensus_eps": 1.5, "threshold_pct": 0.05})

    def test_generic_projection_keeps_official_scalar_features_but_not_nested_values(self) -> None:
        projected = project_entity(
            {
                "entity_id": "X",
                "latest_value": 12.5,
                "description": "categorical context",
                "active": True,
                "nested": {"not": "a scalar feature"},
            },
            SPECS["generic"],
        )
        self.assertEqual(
            projected,
            {
                "entity_id": "X",
                "latest_value": 12.5,
                "description": "categorical context",
                "active": True,
            },
        )

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

    def test_numeric_parameters_reject_nonfinite_strings(self) -> None:
        for value in ("NaN", "Infinity", "-Infinity"):
            parsed = {
                "parameters": {
                    "latest_reported_eps": {"value": value},
                    "latest_reported_prior_year_eps": {"value": "1.25"},
                }
            }
            self.assertEqual(
                normalize_parameters(parsed, SPECS["bank_eps"]),
                {"latest_reported_eps": None, "latest_reported_prior_year_eps": 1.25},
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

        self.assertEqual(point, 4.0)
        self.assertEqual(field, "latest_revenue_growth_pct")
        self.assertEqual(reason, "damped_change_match")

    def test_generic_baseline_prefers_current_over_prior_matching_field(self) -> None:
        point, field, reason = select_default_point(
            "regression",
            "revenue_growth_next_q_pct",
            {"prior_revenue_growth_pct": 3.0, "latest_revenue_growth_pct": 8.0},
            0,
            1,
        )

        self.assertEqual(point, 4.0)
        self.assertEqual(field, "latest_revenue_growth_pct")
        self.assertEqual(reason, "damped_change_match")

    def test_generic_baseline_handles_camel_case_and_field_order(self) -> None:
        first = {"recentRevenueGrowthPct": 8.0, "currentRevenueGrowthPct": 7.0}
        second = dict(reversed(list(first.items())))

        choice_a = select_default_point("regression", "revenue_growth_next_q_pct", first, 0, 1)
        choice_b = select_default_point("regression", "revenue_growth_next_q_pct", second, 0, 1)

        self.assertEqual(choice_a, choice_b)
        self.assertEqual(choice_a, (3.5, "currentRevenueGrowthPct", "damped_change_match"))

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

        self.assertEqual(original, [-1.5, 2.0])
        self.assertEqual(reordered, [2.0, -1.5])

    def test_generic_change_shrinkage_does_not_affect_levels_or_classification(self) -> None:
        level = select_default_point(
            "regression", "future_margin_pct", {"current_margin_pct": 4.0}, 0, 1
        )
        classification = select_default_point(
            "classification", "future_margin_change_pct", {"latest_margin_change_pct": 4.0}, 0, 1
        )

        self.assertEqual(level, (4.0, "current_margin_pct", "target_token_match"))
        self.assertEqual(classification, (4.0, "latest_margin_change_pct", "target_token_match"))

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

    def test_generic_baseline_rejects_only_explicitly_incompatible_units(self) -> None:
        mismatch = select_default_point(
            "regression",
            "future_curve_response_bps",
            {"current_curve_response_pct": 4.5},
            0,
            1,
        )
        matching = select_default_point(
            "regression",
            "future_curve_response_bps",
            {"current_curve_response_bps": 45.0},
            0,
            1,
        )
        unspecified = select_default_point(
            "regression",
            "future_curve_response",
            {"current_curve_response": 4.5},
            0,
            1,
        )

        self.assertEqual(mismatch, (0.0, None, "no_unambiguous_baseline"))
        self.assertEqual(matching, (45.0, "current_curve_response_bps", "target_token_match"))
        self.assertEqual(unspecified, (4.5, "current_curve_response", "target_token_match"))

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

    def test_generic_label_roles_use_task_rules_and_ignore_label_order(self) -> None:
        prompt = "Use zeta when throughput climbs, eta when unchanged, and theta when throughput drops."
        labels = ["theta", "zeta", "eta"]

        self.assertEqual(infer_label_roles(labels, prompt, "throughput_direction"), {
            "negative": "theta",
            "positive": "zeta",
            "neutral": "eta",
        })
        self.assertEqual(_label(2, labels, prompt, "throughput_direction"), "zeta")
        self.assertEqual(_label(0, labels, prompt, "throughput_direction"), "eta")
        self.assertEqual(_label(-2, labels, prompt, "throughput_direction"), "theta")

    def test_generic_event_target_maps_negated_label_to_negative_role(self) -> None:
        labels = ["not_at_risk", "at_risk"]
        prompt = "Label at_risk if covenant failure is likely, otherwise not_at_risk."

        self.assertEqual(_label(2, labels, prompt, "covenant_risk"), "at_risk")
        self.assertEqual(_label(-2, labels, prompt, "covenant_risk"), "not_at_risk")

    def test_generic_solver_applies_task_label_roles(self) -> None:
        current = replace(
            task("throughput_direction", "classification", ["theta", "zeta", "eta"]),
            prompt="Use zeta when throughput climbs, eta when unchanged, and theta when throughput drops.",
        )
        result = solve_minimal(
            current,
            {},
            SPECS["generic"],
            {"directional_signal": 2},
            EMPTY_CORPUS,
            0,
            1,
        )

        self.assertEqual(result.label, "zeta")

    def test_generic_ambiguous_label_schema_returns_an_allowed_label(self) -> None:
        labels = ["class_x", "class_y"]

        self.assertIn(_label(1, labels, "Choose the appropriate class.", "unknown_target"), labels)

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

    def test_core_and_food_cpi_use_confirmed_mean12_only_after_available_date(self) -> None:
        months = "\n".join(
            f"2025-{month:02d} | +{month / 100:.2f} | +{(month + 12) / 100:.2f}"
            for month in range(1, 13)
        )
        cpi_text = (
            "U.S. CPI-U components\n"
            "month | All items less food and energy (core CPI) | Food\n"
            f"{months}\n"
        )
        corpus = IndexedCorpus([], {"CPI": cpi_text}, {"CPI": "2026-01-31"})
        current = replace(task("cpi_component_mom_first_print", "regression"), cutoff_date="2026-02-01")
        before = replace(current, cutoff_date="2026-01-31")
        core = {
            "entity_id": "CPI_CORE",
            "name": "All items less food and energy (core CPI)",
            "latest_published_mom_pct": 0.12,
        }
        food = {"entity_id": "CPI_FOOD", "name": "Food", "latest_published_mom_pct": 0.24}

        core_result = solve_minimal(current, core, SPECS["cpi"], {}, corpus, 0, 1)
        food_result = solve_minimal(current, food, SPECS["cpi"], {}, corpus, 0, 1)
        before_result = solve_minimal(before, core, SPECS["cpi"], {}, corpus, 0, 1)

        self.assertAlmostEqual(core_result.point, 0.065)
        self.assertAlmostEqual(food_result.point, 0.185)
        self.assertEqual(core_result.method, "component_history_mean12")
        self.assertTrue(core_result.derivation["mean12_applied"])
        self.assertAlmostEqual(before_result.point, 0.117)
        self.assertEqual(before_result.method, "component_history")
        self.assertFalse(before_result.derivation["mean12_applied"])

    def test_cpi_mean12_falls_back_when_history_is_incomplete(self) -> None:
        cpi_text = """U.S. CPI-U components
month | All items less food and energy (core CPI)
2025-10 | +0.20
2025-11 | +0.30
2025-12 | +0.40
"""
        corpus = IndexedCorpus([], {"CPI": cpi_text}, {"CPI": "2026-01-31"})
        current = replace(task("cpi_component_mom_first_print", "regression"), cutoff_date="2026-02-01")
        result = solve_minimal(
            current,
            {
                "entity_id": "CPI_CORE",
                "name": "All items less food and energy (core CPI)",
                "latest_published_mom_pct": 0.40,
            },
            SPECS["cpi"],
            {},
            corpus,
            0,
            1,
        )

        self.assertAlmostEqual(result.point, 0.37)
        self.assertEqual(result.method, "component_history")
        self.assertFalse(result.derivation["mean12_applied"])


if __name__ == "__main__":
    unittest.main()
