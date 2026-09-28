from __future__ import annotations

import math
import re
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
    allow_scalar_entity_fields: bool = False


GENERIC_STRING_FIELD_LIMIT = 1000
GENERIC_TOTAL_STRING_LIMIT = 6000
GENERIC_MAX_SCALAR_FIELDS = 64
GENERIC_MAX_FIELD_NAME_CHARS = 128


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
        True,
    ),
    "generic": FamilySpec(
        "generic",
        ("entity_id", "name", "unit", "units"),
        (),
        (SignalSpec("directional_signal", "Simple target direction from explicit evidence; use 0 when unclear."),),
        True,
        True,
        True,
    ),
}


def family_spec(family: str, target_name: str) -> FamilySpec:
    family_tokens = _route_tokens(family)
    target_tokens = _route_tokens(target_name)
    if (
        target_name == "eps_outcome"
        or _has_sequence(family_tokens, ("eps", "beat", "consensus"))
        or _has_sequence(target_tokens, ("eps", "beat", "consensus"))
    ):
        return SPECS["eps_consensus"]
    if target_name == "eps_yoy_direction" or _has_sequence(family_tokens, ("eps", "yoy", "direction")):
        return SPECS["eps_yoy"]
    if target_name == "eps_yoy_growth_pct":
        return SPECS["bank_eps"]
    if _has_sequence(family_tokens, ("credit", "event")) or _has_sequence(target_tokens, ("credit", "event")):
        return SPECS["credit"]
    if _has_sequence(family_tokens, ("earnings", "reaction")) or _has_sequence(
        target_tokens, ("earnings", "reaction")
    ):
        return SPECS["reaction"]
    if _has_sequence(target_tokens, ("yield", "change", "bps")) or _has_sequence(
        family_tokens, ("rate", "curve")
    ):
        return SPECS["rates"]
    if _has_sequence(family_tokens, ("cpi", "component")) or _has_sequence(target_tokens, ("cpi", "component")):
        return SPECS["cpi"]
    if _has_sequence(family_tokens, ("macro", "revision")) or _has_sequence(
        target_tokens, ("estimate", "revision")
    ):
        return SPECS["macro_revision"]
    if _has_sequence(target_tokens, ("bid", "to", "cover")) or _has_sequence(
        family_tokens, ("auction", "demand")
    ):
        return SPECS["auction"]
    if (
        _has_sequence(family_tokens, ("positioning", "shift"))
        or _has_sequence(family_tokens, ("cftc", "positioning"))
        or _has_sequence(target_tokens, ("net", "positioning", "change"))
    ):
        return SPECS["positioning"]
    return SPECS["generic"]


_STRUCTURAL_SIGNATURES: tuple[
    tuple[str, str, frozenset[str], tuple[str, ...]], ...
] = (
    ("eps_consensus", "classification", frozenset(("consensus_eps", "threshold_pct")), ()),
    (
        "eps_yoy",
        "classification",
        frozenset(("prior_year_q_eps", "prior_year_quarter", "quarter_reported")),
        (),
    ),
    (
        "reaction",
        "classification",
        frozenset(("report_datetime", "event_window", "benchmark", "flat_threshold_abn_pct")),
        (),
    ),
    (
        "macro_revision",
        "classification",
        frozenset(("latest_precutoff_estimate", "latest_precutoff_vintage", "resolving_release_date")),
        (),
    ),
    (
        "bank_eps",
        "regression",
        frozenset(("cik", "prior_year_q_eps", "prior_year_quarter", "quarter_reported")),
        (),
    ),
    (
        "rates",
        "regression",
        frozenset(("maturity_years", "start_yield_pct", "as_of")),
        (),
    ),
    (
        "cpi",
        "regression",
        frozenset(("series_fred", "ref_month", "latest_published_mom_pct", "latest_published_ref_month")),
        (),
    ),
    (
        "auction",
        "regression",
        frozenset(("tenor", "auction_date", "new_or_reopening", "offering_amount_usd_bn")),
        (),
    ),
    (
        "positioning",
        "ranking",
        frozenset(("asset_class",)),
        ("net_noncommercial_", "open_interest_", "net_pct_oi_"),
    ),
)


def task_family_spec(
    family: str,
    target_name: str,
    target_type: str,
    entities: list[dict[str, object]] | tuple[dict[str, object], ...],
) -> FamilySpec:
    """Resolve a task route, using a strict entity-shape fallback only after name routing fails."""
    named = family_spec(family, target_name)
    if named.key != "generic" or not entities or any(not isinstance(entity, dict) for entity in entities):
        return named
    common_fields = set(entities[0])
    for entity in entities[1:]:
        common_fields.intersection_update(entity)
    matches = []
    normalized_type = target_type.strip().lower()
    for key, expected_type, required_fields, required_prefixes in _STRUCTURAL_SIGNATURES:
        if normalized_type != expected_type or not required_fields.issubset(common_fields):
            continue
        if any(
            not _usable_signature_value(entity.get(field))
            for entity in entities
            for field in required_fields
        ):
            continue
        if any(
            not all(
                any(
                    field.startswith(prefix) and _usable_signature_value(entity.get(field))
                    for field in common_fields
                )
                for entity in entities
            )
            for prefix in required_prefixes
        ):
            continue
        matches.append(key)
    return SPECS[matches[0]] if len(matches) == 1 else named


def _usable_signature_value(value: object) -> bool:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def _route_tokens(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", value.lower()))


def _has_sequence(tokens: tuple[str, ...], sequence: tuple[str, ...]) -> bool:
    width = len(sequence)
    return any(tokens[index : index + width] == sequence for index in range(len(tokens) - width + 1))


def project_entity(entity: dict[str, object], spec: FamilySpec) -> dict[str, object]:
    if spec.allow_scalar_entity_fields:
        projected: dict[str, object] = {}
        priority = [key for key in spec.allowed_entity_fields if key in entity]
        ordered_keys = priority + [key for key in entity if key not in priority]
        remaining_string_chars = GENERIC_TOTAL_STRING_LIMIT
        for key in ordered_keys:
            value = entity[key]
            if (
                len(projected) >= GENERIC_MAX_SCALAR_FIELDS
                or key == "corpus_ref"
                or len(key) > GENERIC_MAX_FIELD_NAME_CHARS
                or value is None
                or isinstance(value, (dict, list, tuple, set))
            ):
                continue
            if isinstance(value, bool):
                projected[key] = value
            elif isinstance(value, (int, float)) and math.isfinite(float(value)):
                projected[key] = value
            elif isinstance(value, str) and remaining_string_chars > 0:
                clipped = value[: min(GENERIC_STRING_FIELD_LIMIT, remaining_string_chars)]
                projected[key] = clipped
                remaining_string_chars -= len(clipped)
        return projected
    projected = {key: entity[key] for key in spec.allowed_entity_fields if key in entity}
    if spec.allow_numeric_entity_fields:
        for key, value in entity.items():
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                projected[key] = value
    return projected
