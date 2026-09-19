from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SignalSpec:
    name: str
    description: str


@dataclass(frozen=True)
class NumericParameterSpec:
    name: str
    description: str


@dataclass(frozen=True)
class FamilySpec:
    key: str
    allowed_entity_fields: tuple[str, ...]
    numeric_parameters: tuple[NumericParameterSpec, ...]
    signals: tuple[SignalSpec, ...]
    model_required: bool
    allow_numeric_entity_fields: bool = False


SPECS: dict[str, FamilySpec] = {
    "eps_consensus": FamilySpec(
        "eps_consensus",
        ("entity_id", "name", "consensus_eps", "threshold_pct"),
        (),
        (
            SignalSpec(
                "target_period_earnings_signal",
                "Direction of target-period earnings from explicit revenue, margin, cost, or outlook language. "
                "Historical EPS alone is neutral.",
            ),
        ),
        True,
    ),
    "eps_yoy": FamilySpec(
        "eps_yoy",
        ("entity_id", "name", "quarter_reported", "prior_year_quarter", "prior_year_q_eps"),
        (),
        (
            SignalSpec(
                "yoy_earnings_signal",
                "Direction of earnings versus the same quarter one year earlier. Quarter-over-quarter evidence alone is neutral.",
            ),
        ),
        True,
    ),
    "bank_eps": FamilySpec(
        "bank_eps",
        ("entity_id", "name", "cik", "quarter_reported", "prior_year_quarter", "prior_year_q_eps"),
        (
            NumericParameterSpec(
                "latest_reported_eps",
                "GAAP diluted EPS for the most recent reported three-month quarter in the evidence table.",
            ),
            NumericParameterSpec(
                "latest_reported_prior_year_eps",
                "GAAP diluted EPS for the same three-month quarter one year earlier, from the same table.",
            ),
        ),
        (),
        True,
    ),
    "credit": FamilySpec(
        "credit",
        ("entity_id", "name", "industry", "cik"),
        (),
        (
            SignalSpec("going_concern_present", "Use +2 only for explicit going-concern language; otherwise 0."),
            SignalSpec(
                "liquidity_explicitly_insufficient",
                "Use +2 only when liquidity is explicitly insufficient or severely constrained; otherwise 0.",
            ),
            SignalSpec(
                "covenant_breach_or_payment_default",
                "Use +2 only for an actual unresolved breach or payment default. Risk boilerplate and cured waivers are 0.",
            ),
            SignalSpec(
                "near_term_debt_without_stated_funding",
                "Use +1 only for a near-term maturity with no stated funding source; otherwise 0.",
            ),
        ),
        True,
    ),
    "reaction": FamilySpec(
        "reaction",
        ("entity_id", "name", "report_datetime", "event_window", "benchmark", "flat_threshold_abn_pct"),
        (),
        (
            SignalSpec(
                "explicit_forward_outlook_signal",
                "Direction of explicit forward guidance. Historical results without forward guidance are neutral.",
            ),
        ),
        True,
    ),
    "rates": FamilySpec(
        "rates",
        ("entity_id", "name", "maturity_years", "start_yield_pct", "as_of"),
        (),
        (
            SignalSpec(
                "policy_direction",
                "Hawkish is positive for yields, dovish is negative, and unclear or balanced language is neutral.",
            ),
        ),
        True,
    ),
    "cpi": FamilySpec(
        "cpi",
        ("entity_id", "name", "series_fred", "ref_month", "latest_published_mom_pct", "latest_published_ref_month"),
        (),
        (),
        False,
    ),
    "macro_revision": FamilySpec(
        "macro_revision",
        (
            "entity_id",
            "series_id",
            "series_name",
            "agency",
            "units",
            "ref_month",
            "latest_precutoff_estimate",
            "latest_precutoff_vintage",
            "resolving_release_date",
        ),
        (),
        (),
        False,
    ),
    "auction": FamilySpec(
        "auction",
        ("entity_id", "name", "tenor", "auction_date", "new_or_reopening", "offering_amount_usd_bn"),
        (),
        (),
        False,
    ),
    "positioning": FamilySpec(
        "positioning",
        (
            "entity_id",
            "name",
            "asset_class",
            "net_noncommercial_20241022",
            "open_interest_20241022",
            "net_pct_oi_20241022",
            "trailing_4wk_net_change_pct_oi",
        ),
        (),
        (),
        False,
    ),
    "generic": FamilySpec(
        "generic",
        ("entity_id", "name", "unit", "units"),
        (),
        (SignalSpec("directional_signal", "Simple target direction from explicit evidence; use 0 when unclear."),),
        True,
        True,
    ),
}


def family_spec(family: str, target_name: str) -> FamilySpec:
    text = f"{family} {target_name}".lower()
    if target_name == "eps_outcome" or "eps_beat_consensus" in text:
        return SPECS["eps_consensus"]
    if target_name == "eps_yoy_direction":
        return SPECS["eps_yoy"]
    if target_name == "eps_yoy_growth_pct":
        return SPECS["bank_eps"]
    if "credit_event" in text:
        return SPECS["credit"]
    if "earnings_reaction" in text or "post_earnings_reaction" in text:
        return SPECS["reaction"]
    if "yield_change_bps" in text or "rate_curve" in text:
        return SPECS["rates"]
    if "cpi_component" in text:
        return SPECS["cpi"]
    if "revision" in text:
        return SPECS["macro_revision"]
    if "bid_to_cover" in text or "auction" in text:
        return SPECS["auction"]
    if "position" in text or "cot" in text:
        return SPECS["positioning"]
    return SPECS["generic"]


def project_entity(entity: dict[str, object], spec: FamilySpec) -> dict[str, object]:
    projected = {key: entity[key] for key in spec.allowed_entity_fields if key in entity}
    if spec.allow_numeric_entity_fields:
        for key, value in entity.items():
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                projected[key] = value
    return projected
