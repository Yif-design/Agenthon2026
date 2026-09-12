"""Text stage: dated documents -> Adjustments (the three knobs), via an LLM.

Two passes, by design:

* **Pass A — one call per document.** The model sees ONE dated document plus the unit context
  and returns a structured signal card: established facts vs inferred tone, per-asset direction
  / strength / uncertainty, and whether a discrete event sits inside the horizon. Reading
  documents one at a time keeps attribution honest (every adjustment cites a doc_id) and makes
  disagreement between documents visible instead of averaged away — the failure mode the
  organizers measured on their salted adversarial corpora.
* **Pass B — one aggregation call.** The model sees the signal cards plus the panel's own recent
  behaviour and returns the scenario mixture. Code then clamps every number, enforces the
  "inferred tone may not narrow" rule, normalizes weights and drops evidence ids that do not
  exist in the corpus.

Any failure — no endpoint, bad JSON, budget exhausted, timeout — degrades to the neutral
Adjustments with a note in the rationale. A unit that errors costs 4.0; a neutral unit costs ~1.0.
"""

from __future__ import annotations

import json
import math
import os as _os
import pathlib
import re as _re
import time
from typing import Any

import numpy as np

from .cardio import Unit
from .engine import prepare_asset, steps_for, vol_path
from .knobs import Adjustments, Scenario
from .llm import LLM, parse_json

MAX_DOC_CHARS = 9000          # per document sent to pass A (≈2.5k tokens)
PROMPT_VERSION = "b4"         # bump when SYSTEM_B / pass-B schema changes (invalidates the pass-B cache)
PROMPT_A_VERSION = "a2"       # bump when SYSTEM_A / pass-A schema or asset context changes
MAX_DOCS = 16
MAX_SCENARIOS = 4
TIME_BUDGET_S = 240.0         # leave headroom under the ~400 s/unit effective phase budget
DRIFT_CLAMP = 0.75            # |drift| in horizon-sd units — the playbook: "a fraction of the sd"
VOL_MULT_RANGE = (0.6, 3.0)

# ---- guardrails -----------------------------------------------------------------------------
# A 7B model asked "is this more uncertain?" answers yes almost every time, and its magnitudes
# carry no calibration at all. So the *code* demands corroboration rather than trusting what the
# model returns: shrink every magnitude, require agreement across documents before moving the
# centre, and require a real share of document weight before touching the width. The width knob
# is the dangerous one now that the engine's own scale is calibrated — widening is no longer free.
DRIFT_SHRINK = float(_os.environ.get("T2_TS_DRIFT_SHRINK", 0.7))    # scale on the model's drift
VM_SHRINK = float(_os.environ.get("T2_TS_VM_SHRINK", 0.5))          # pull vol_mult toward 1.0
FLOOR_SCALE = float(_os.environ.get("T2_TS_FLOOR_SCALE", 0.0))      # scale on the cards' width floor
MIN_DRIFT_EVIDENCE = float(_os.environ.get("T2_TS_MIN_DRIFT", 0.20))  # |cards-implied| below this: no drift
MIN_AGREEING_DOCS = int(_os.environ.get("T2_TS_MIN_DOCS", 3))       # documents that must agree on the sign
MIN_WIDTH_SHARE = float(_os.environ.get("T2_TS_MIN_WIDTH_SHARE", 0.25))  # doc weight needed to widen
MAX_WIDTH = float(_os.environ.get("T2_TS_MAX_WIDTH", 1.6))          # cap on a non-event width multiplier
EVENT_STRICT = _os.environ.get("T2_TS_EVENT_STRICT", "1") == "1"    # scheduled meetings are not events
TAIL_ENABLED = _os.environ.get("T2_TS_TAIL", "0") == "1"            # Student-t scale mixing (measured: hurts)
SP_ENABLED = _os.environ.get("T2_TS_SP", "0") == "1"                # text-set stress_prob (measured: hurts)

# A scheduled meeting or data release is *not* an event in the sense that matters: the market has
# priced a distribution over it for weeks. A genuinely binary, unpriced outcome is.
SCHEDULED_RE = _re.compile(
    r"fomc|meeting|statement|decision|release|cpi|nfp|payroll|hike|cut|dot|minutes|speech|"
    r"testimony|taper|pace|qqe|purchase|conference|press|jackson|beige|gdp|pce|inflation print", _re.I)
BINARY_RE = _re.compile(
    r"binary|referendum|election|vote|peg|floor|band|default|downgrade|emergency|bank run|"
    r"failure|collapse|war|invasion|virus|outbreak|pandemic|guidance|withdraw|shutdown|ceiling|"
    r"brexit|devalu|intervention", _re.I)


def _is_real_event(cards: list[dict[str, Any]]) -> bool:
    """True when some card flags an in-window event that reads as binary rather than scheduled."""
    for c in cards:
        ev = c.get("event_in_window") or {}
        if not _truthy(ev.get("exists")):
            continue
        if not EVENT_STRICT:
            return True
        kind = str(ev.get("type", "")).strip().lower()
        if kind.startswith("binary"):      # the model classified it (pass-A schema a2)
            return True
        if kind.startswith("scheduled"):
            continue
        blob = " ".join(str(ev.get(k, "")) for k in ("what", "description", "name", "why")) or str(ev)
        if BINARY_RE.search(blob) and not SCHEDULED_RE.search(blob):
            return True
    return False


SYSTEM_A = """You are a quantitative macro analyst working for a forecasting desk.
You will be shown ONE dated document and a forecasting task. Extract only what this document
implies for the target series over the stated horizon. Rules:
- Separate ESTABLISHED FACTS the document states (a decision taken, a data print released, a level
  or date announced) from INFERRED TONE (what you read between the lines).
- Each target carries a `direction_convention` saying what direction = +1 means for THAT series.
  Read it and follow it literally. Never infer a quote convention from the asset's name.
- An event is `scheduled` when the market has known its date for weeks (a policy meeting, a data
  release) and `binary` only when the outcome itself is unpriced and resolves one way or the other.
- You stand at the as-of date. Use nothing you know about what happened afterwards. If you recognise
  the historical episode, ignore the outcome; judge only what this text says as of its date.
- Be concise and literal. Do not narrate. Keep every text field short.
Respond with a single JSON object and nothing else."""

SYSTEM_B = """You are the lead of a probabilistic forecasting desk. You receive (1) a forecasting task,
(2) what the numeric panel has been doing, and (3) signal cards extracted from dated documents.
Turn them into a small set of weighted SCENARIOS for a Monte-Carlo forecast. Each scenario has:
- drift: per target asset, a shift of the distribution centre in units of the ONE-HORIZON STANDARD
  DEVIATION at the shortest horizon (e.g. +0.3 = move the centre up by 0.3 sd). Keep it modest:
  documents move the centre by a fraction of the sd, not multiples. Sign convention: positive =
  the series VALUE goes up (for a yield: higher yield; for a quote like JPY-per-USD: more JPY per USD).
- vol_mult: per target asset, a multiplier on the spread (1.0 = unchanged, 1.5 = 50% wider).
- evidence: the doc_ids that support the scenario.
Besides the scenarios you give ONE number, stress_prob: the probability (0-0.6) that a
crisis/stress regime — historically high volatility, clustered moves, for equities a drawdown —
materializes inside the horizon. The unconditional base rate is about 0.10; raise it when the
documents describe an emerging external shock, a guidance withdrawal, funding stress, a peg under
attack or a binary event with a bad branch; lower it only when a stated fact removes such a risk.
Rules you must follow:
1. Scenarios are MUTUALLY EXCLUSIVE OUTCOMES (e.g. "hold as signalled" vs "surprise cut", "peg holds"
   vs "peg breaks", "data confirms" vs "data disappoints"). They are NOT confidence levels of one
   view — never produce a conservative/moderate/aggressive ladder of the same direction.
2. Stay consistent with the signal cards: the weighted-average drift of each asset must have the
   same sign as the cards' per-asset directions, and be zero when the cards say 0. Different
   assets may move differently (a curve can steepen or flatten; currencies can diverge).
3. When documents disagree with each other, or with what the panel has been doing, do NOT average:
   make separate scenarios (2-4) with weights, and say which document is on which side.
4. A discrete event inside the horizon window (policy meeting, vote, referendum, peg decision,
   scheduled release with a binary outcome) means: widen (vol_mult > 1) and fatten tails.
5. Never narrow the spread (vol_mult < 1) on the strength of tone; only a stated fact that removes
   uncertainty justifies it, and only slightly.
6. Shocks in this competition's history are overwhelmingly downside; if in doubt, keep the downside
   tail wider than the upside.
7. You stand at the as-of date. Do not use hindsight. A remembered outcome is not evidence.
Keep every text field short. Respond with a single JSON object and nothing else."""


# --------------------------------------------------------------------------------------------
# context builders
# --------------------------------------------------------------------------------------------


def _read_docs(unit: Unit) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    if unit.text_dir is None or not unit.text_dir.is_dir():
        return docs
    seen: set[str] = set()
    for d in unit.docs:
        f = unit.text_dir / str(d.get("file", ""))
        if not f.is_file() or f.name in seen:
            continue
        seen.add(f.name)
        docs.append({
            "doc_id": str(d.get("doc_id", f.stem)),
            "timestamp": str(d.get("timestamp", ""))[:10],
            "doc_type": str(d.get("doc_type", d.get("source", ""))),
            "text": f.read_text(encoding="utf-8", errors="replace"),
        })
    for f in sorted(unit.text_dir.glob("*.txt")):        # files the index forgot
        if f.name not in seen:
            docs.append({"doc_id": f.stem, "timestamp": "", "doc_type": "", "text": f.read_text(encoding="utf-8", errors="replace")})
    docs.sort(key=lambda d: d["timestamp"])
    return docs[-MAX_DOCS:]


# FX quote convention. A 7B model reads "the yen weakened" and returns direction = -1 for
# USDJPY, which is backwards: that panel is JPY per USD, so a weaker yen is a HIGHER value. The
# sign convention has to be spelled out per asset or half the currency reads come back inverted.
_USD_PER_CCY = {"EUR", "GBP", "AUD", "NZD"}
_CCY_PER_USD = {"JPY", "CHF", "CAD", "SEK", "NOK", "DKK", "CNY", "CNH", "BRL", "INR", "MXN",
                "ZAR", "TRY", "KRW", "TWD", "SGD", "PLN", "HUF", "CZK", "RUB", "THB", "IDR"}


def _direction_hint(asset: str, panel: str, space: str) -> str:
    """What direction = +1 means for this asset, in words the model cannot invert."""
    if space == "cumlog":
        return f"+1 = {asset} returns POSITIVE over the horizon, -1 = negative"
    token = "".join(ch for ch in asset.upper() if ch.isalpha())
    is_fx = "fx" in panel.lower() or "transfer" in panel.lower() or token[:3] in _USD_PER_CCY | _CCY_PER_USD
    if is_fx:
        for ccy in _USD_PER_CCY:
            if ccy in token:
                return (f"this series is USD per {ccy}: +1 = {ccy} STRENGTHENS against the dollar, "
                        f"-1 = {ccy} WEAKENS")
        for ccy in _CCY_PER_USD:
            if ccy in token:
                return (f"this series is {ccy} per USD: +1 = {ccy} WEAKENS against the dollar "
                        f"(more {ccy} buys one dollar), -1 = {ccy} STRENGTHENS")
    if space == "diff":
        return f"+1 = {asset} rises (a HIGHER yield/rate), -1 = falls"
    return f"+1 = the {asset} value rises, -1 = falls"


def _asset_context(unit: Unit, asof: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Per-asset numbers the model needs to reason in the right units, plus a shared summary."""
    ctx: dict[str, dict[str, Any]] = {}
    h0 = min(unit.horizons)
    for a in unit.assets:
        spec = prepare_asset(unit, a, asof)
        st = steps_for(spec, unit.horizons, asof)
        sig = vol_path(spec, max(st.values()))
        sd0 = float(math.sqrt(np.sum(sig[: st[h0]] ** 2)))
        w = spec.incr
        n21 = min(len(w), 21 if spec.freq == "daily" else 1)
        n63 = min(len(w), 63 if spec.freq == "daily" else 3)
        chg21, chg63 = float(w.iloc[-n21:].sum()), float(w.iloc[-n63:].sum())
        if spec.space == "log":
            unit_desc, sd_nat = "level (multiplicative moves)", spec.anchor * sd0
            chg21_s, chg63_s = f"{100 * chg21:+.2f}%", f"{100 * chg63:+.2f}%"
        elif spec.space == "diff":
            unit_desc, sd_nat = "level (additive moves, e.g. percentage points of yield)", sd0
            chg21_s, chg63_s = f"{chg21:+.3f}", f"{chg63:+.3f}"
        else:
            unit_desc, sd_nat = "cumulative log return from the as-of (0 = flat)", sd0
            chg21_s, chg63_s = f"{100 * chg21:+.2f}%", f"{100 * chg63:+.2f}%"
        ctx[a] = {
            "current_level": round(spec.anchor, 6) if spec.space != "cumlog" else 0.0,
            "target_type": unit_desc,
            "one_horizon_sd_in_value_units": round(sd_nat, 6),
            "recent_change_1m": chg21_s,
            "recent_change_3m": chg63_s,
            "vol_regime": f"current vol is {spec.vol0 / max(spec.vol_lr, 1e-12):.2f}x the long-run vol",
            "panel": spec.panel,
            "direction_convention": _direction_hint(a, spec.panel, spec.space),
        }
    meta = unit.card.get("metadata", {})
    card_md = unit.unit_dir / "forecast_card.md"
    summary = {
        "unit_id": unit.unit_id,
        "family": unit.family,
        "asof": asof,
        "horizons_business_days": unit.horizons,
        "target_type": unit.target_type,
        "value_unit": unit.value_unit,
        "task_description": str(meta.get("description", ""))[:1500],
        "card_notes": card_md.read_text(encoding="utf-8", errors="replace")[:2500] if card_md.is_file() else "",
    }
    return ctx, summary


# --------------------------------------------------------------------------------------------
# pass A
# --------------------------------------------------------------------------------------------


def _pass_a(llm: LLM, doc: dict[str, Any], summary: dict[str, Any], actx: dict[str, Any]) -> dict[str, Any] | None:
    assets = list(actx.keys())
    user = json.dumps({
        "task": summary,
        "targets": actx,
        "document": {
            "doc_id": doc["doc_id"], "date": doc["timestamp"], "type": doc["doc_type"],
            "text": doc["text"][:MAX_DOC_CHARS],
        },
        "respond_with": {
            "doc_id": doc["doc_id"],
            "summary": "<= 25 words",
            "established_facts": ["<= 3 items, <= 15 words each: facts the document STATES (decisions, prints, levels, dates)"],
            "inferred_tone": "hawkish | dovish | risk-off | risk-on | neutral | mixed",
            "per_asset": {a: {"direction": "-1 | 0 | 1 — the sign of the VALUE move, using this asset's direction_convention above; do NOT guess the quote convention", "strength": "0.0-1.0",
                              "uncertainty": "lower | same | higher", "why": "<= 12 words"} for a in assets},
            "event_in_window": {"exists": "true|false", "what": "<= 8 words",
                                "type": "scheduled (a meeting/release the market has priced for weeks) | binary (an unpriced outcome that resolves one way or the other: vote, peg decision, default, guidance withdrawal)", "date": "YYYY-MM-DD or empty"},
            "relevance": "0.0-1.0",
        },
    }, ensure_ascii=False)
    out = parse_json(llm.chat(SYSTEM_A, user, max_tokens=600))
    if not out or not isinstance(out.get("per_asset"), dict):
        return None
    out["doc_id"] = doc["doc_id"]
    out["date"] = doc["timestamp"]
    return out


# --------------------------------------------------------------------------------------------
# pass B
# --------------------------------------------------------------------------------------------


def _pass_b(llm: LLM, cards: list[dict[str, Any]], summary: dict[str, Any], actx: dict[str, Any]) -> dict[str, Any] | None:
    assets = list(actx.keys())
    user = json.dumps({
        "task": summary,
        "targets": actx,
        "signal_cards": cards,
        "cards_implied_drift_sd_units": {a: round(v, 2) for a, v in implied_drift(cards, assets).items()},
        "respond_with": {
            "scenarios": [{
                "name": "<= 4 words, names the OUTCOME", "weight": "0-1, weights sum to 1, 1 to 4 scenarios",
                "drift": {a: f"number in [-{DRIFT_CLAMP}, {DRIFT_CLAMP}] (one-horizon sd units)" for a in assets},
                "vol_mult": {a: f"number in [{VOL_MULT_RANGE[0]}, {VOL_MULT_RANGE[1]}]" for a in assets},
                "evidence": ["doc_ids"], "rationale": "<= 25 words",
            }],
            "stress_prob": "0.0-0.6, probability of a crisis regime inside the horizon (base rate ~0.10)",
            "tail_df": "null, or 4-8 to add extra fat tails when a discrete event sits in the window",
            "disagreement": "<= 30 words: where documents and/or the panel disagree, and which doc is on which side",
        },
    }, ensure_ascii=False)
    return parse_json(llm.chat(SYSTEM_B, user, max_tokens=900))


# --------------------------------------------------------------------------------------------
# card-level statistics and guardrails
# --------------------------------------------------------------------------------------------


def _num(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def _truthy(x: Any) -> bool:
    return str(x).strip().lower() in ("true", "1", "yes")


def implied_drift(cards: list[dict[str, Any]], assets: list[str]) -> dict[str, float]:
    """What the per-document reads add up to, per asset, in horizon-sd units.

    relevance-weighted mean of direction x strength, scaled so that a unanimous full-strength
    read is +/-0.5 sd — the playbook's "a fraction of the sd, not multiples".
    """
    out: dict[str, float] = {}
    for a in assets:
        num = den = 0.0
        for c in cards:
            pa = (c.get("per_asset") or {}).get(a)
            if not isinstance(pa, dict):
                continue
            rel = float(np.clip(_num(c.get("relevance"), 0.5), 0.0, 1.0))
            d = float(np.clip(_num(pa.get("direction")), -1.0, 1.0))
            s = float(np.clip(_num(pa.get("strength"), 0.5), 0.0, 1.0))
            num += rel * d * s
            den += rel
        out[a] = float(np.clip(0.5 * num / den, -0.5, 0.5)) if den > 0 else 0.0
    return out


def card_uncertainty(cards: list[dict[str, Any]], assets: list[str]) -> tuple[dict[str, float], bool]:
    """Share of relevance saying 'higher' uncertainty per asset, and whether any card flags an event."""
    share: dict[str, float] = {}
    for a in assets:
        hi = den = 0.0
        for c in cards:
            pa = (c.get("per_asset") or {}).get(a)
            if not isinstance(pa, dict):
                continue
            rel = float(np.clip(_num(c.get("relevance"), 0.5), 0.0, 1.0))
            den += rel
            if str(pa.get("uncertainty", "")).lower() == "higher":
                hi += rel
        share[a] = hi / den if den > 0 else 0.0
    event = any(_truthy((c.get("event_in_window") or {}).get("exists")) for c in cards)
    return share, event


def fallback_scenarios(cards: list[dict[str, Any]], assets: list[str], notes: list[str]) -> Adjustments:
    """Deterministic scenarios straight from the signal cards, used when pass B fails."""
    drift = implied_drift(cards, assets)
    share, event = card_uncertainty(cards, assets)
    vm = {a: (1.3 if event else 1.0) * (1.0 + 0.2 * share[a]) for a in assets}
    ev = [str(c.get("doc_id")) for c in cards if _num(c.get("relevance"), 0.0) >= 0.5]
    notes.append("pass B unavailable; scenario built deterministically from the signal cards")
    hi = max(share.values()) if share else 0.0
    return Adjustments(
        scenarios=[Scenario(
            name="cards-consensus", weight=1.0,
            drift={a: v for a, v in drift.items() if abs(v) > 0.02},
            vol_mult={a: round(v, 2) for a, v in vm.items() if abs(v - 1.0) > 0.02},
            evidence=ev, established=False,
        )],
        tail_df=6.0 if event else None,
        stress_prob=min(0.6, 0.10 + 0.15 * event + 0.2 * hi),
        notes=notes,
    )


def _to_adjustments(raw: dict[str, Any] | None, unit: Unit, cards: list[dict[str, Any]],
                    doc_ids: set[str], notes: list[str]) -> Adjustments:
    assets = unit.assets
    if not raw or not isinstance(raw.get("scenarios"), list) or not raw["scenarios"]:
        return fallback_scenarios(cards, assets, notes) if cards else Adjustments(scenarios=[Scenario("baseline", 1.0)], notes=notes)

    facts_by_doc = {str(c.get("doc_id")): bool(c.get("established_facts")) for c in cards}
    scenarios: list[Scenario] = []
    for s in raw["scenarios"][:MAX_SCENARIOS]:
        if not isinstance(s, dict):
            continue
        ev = [e for e in (s.get("evidence") or []) if isinstance(e, str) and e in doc_ids]
        drift = {a: float(np.clip(DRIFT_SHRINK * _num((s.get("drift") or {}).get(a)), -DRIFT_CLAMP, DRIFT_CLAMP))
                 for a in assets}
        # `established` is decided by code, not by the model: every cited document states a fact
        # AND the scenario is not a directional bet (|drift| <= 0.15 sd).
        est = bool(ev) and all(facts_by_doc.get(e, False) for e in ev) and all(abs(v) <= 0.15 for v in drift.values())
        vm: dict[str, float] = {}
        for a in assets:
            m = float(np.clip(_num((s.get("vol_mult") or {}).get(a), 1.0), *VOL_MULT_RANGE))
            m = 1.0 + VM_SHRINK * (m - 1.0)   # the model's magnitudes are not calibrated; shrink them
            if m < 1.0:
                if not est:
                    notes.append(f"scenario {s.get('name')!r} tried to narrow {a} (x{m:.2f}) on inferred tone; reset to x1.00")
                    m = 1.0
                else:
                    m = max(m, 0.8)
            vm[a] = m
        scenarios.append(Scenario(
            name=str(s.get("name", f"scenario-{len(scenarios) + 1}"))[:40],
            weight=max(_num(s.get("weight"), 0.0), 0.0),
            drift=drift, vol_mult=vm, evidence=ev, established=est,
        ))
        if s.get("rationale"):
            notes.append(f"{scenarios[-1].name}: {str(s['rationale'])[:200]}")
    if not scenarios or sum(sc.weight for sc in scenarios) <= 0:
        return fallback_scenarios(cards, assets, notes)
    total = sum(sc.weight for sc in scenarios)
    for sc in scenarios:
        sc.weight /= total

    # ---- guardrail 1: the mixture centre must agree with the per-document reads ------------
    implied = implied_drift(cards, assets)
    for a in assets:
        m = sum(sc.weight * sc.drift.get(a, 0.0) for sc in scenarios)
        target = m
        if implied[a] * m < 0 and abs(implied[a]) > 0.05:           # opposite sign: pull to the cards
            target = 0.5 * implied[a]
        elif abs(m) > abs(implied[a]) + 0.3:                        # far beyond what the cards say
            target = math.copysign(abs(implied[a]) + 0.3, m)
        if abs(target - m) > 1e-6:
            for sc in scenarios:
                sc.drift[a] = float(np.clip(sc.drift.get(a, 0.0) + (target - m), -DRIFT_CLAMP, DRIFT_CLAMP))
            notes.append(f"guardrail: {a} mixture drift {m:+.2f} sd vs cards-implied {implied[a]:+.2f}; shifted to {target:+.2f}")

    # ---- guardrail 1b: moving the centre needs a real, corroborated read --------------------
    # A single document with a weak directional hint is not evidence. Require the cards-implied
    # drift to clear a floor AND at least MIN_AGREEING_DOCS documents to agree on the sign.
    for a in assets:
        signs = [np.sign(_num((c.get("per_asset") or {}).get(a, {}).get("direction")))
                 for c in cards if isinstance((c.get("per_asset") or {}).get(a), dict)]
        agree = max(sum(1 for x in signs if x > 0), sum(1 for x in signs if x < 0)) if signs else 0
        if abs(implied[a]) < MIN_DRIFT_EVIDENCE or agree < MIN_AGREEING_DOCS:
            if any(abs(sc.drift.get(a, 0.0)) > 1e-9 for sc in scenarios):
                notes.append(f"evidence bar: {a} cards-implied drift {implied[a]:+.2f} sd with {agree} "
                             f"agreeing doc(s); centre left unmoved")
            for sc in scenarios:
                sc.drift[a] = 0.0

    # ---- guardrail 2: width only moves where the documents corroborate it -------------------
    # The engine's own scale is calibrated, so widening is no longer free: an uncorroborated
    # widening costs CRPS on every card it touches. Require a real share of document weight to
    # report higher uncertainty (or a genuinely binary event), and cap what that share can buy.
    share, _model_event = card_uncertainty(cards, assets)
    event = _is_real_event(cards)
    for a in assets:
        corroborated = share[a] >= MIN_WIDTH_SHARE or (event and share[a] > 0)
        if not corroborated:
            if any(sc.vol_mult.get(a, 1.0) > 1.0 for sc in scenarios):
                notes.append(f"corroboration bar: only {share[a]:.0%} of document weight reports higher "
                             f"uncertainty for {a} (event={event}); width left at x1.00")
            for sc in scenarios:
                sc.vol_mult[a] = 1.0
            continue
        mix = sum(sc.weight * sc.vol_mult.get(a, 1.0) for sc in scenarios)
        floor = 1.0 + FLOOR_SCALE * ((1.15 if event else 1.0) * (1.0 + 0.10 * share[a]) - 1.0)
        cap = min(MAX_WIDTH if not event else VOL_MULT_RANGE[1], 1.0 + 0.6 * share[a] + (0.15 if event else 0.0))
        target = float(np.clip(mix, floor, max(cap, 1.0)))
        if mix > 0 and abs(target - mix) > 1e-6:
            for sc in scenarios:
                sc.vol_mult[a] = float(np.clip(sc.vol_mult.get(a, 1.0) * target / mix, *VOL_MULT_RANGE))
            notes.append(f"guardrail: {a} width x{mix:.2f} -> x{target:.2f} (event={event}, "
                         f"higher-uncertainty share {share[a]:.0%}, cap x{cap:.2f})")

    # A cap applied proportionally can push a scenario that sat at exactly 1.00 below 1.00, which
    # Adjustments.validate() rejects for a non-established scenario (and a rejected adjustment set
    # costs the whole unit). Clip once, at the end, before the no-op entries are dropped.
    for sc in scenarios:
        lo = 0.8 if sc.established else 1.0
        sc.vol_mult = {a: float(np.clip(v, lo, VOL_MULT_RANGE[1])) for a, v in sc.vol_mult.items()}

    for sc in scenarios:   # drop no-op entries so the ledger stays readable
        sc.drift = {a: v for a, v in sc.drift.items() if abs(v) > 1e-9}
        sc.vol_mult = {a: v for a, v in sc.vol_mult.items() if abs(v - 1.0) > 1e-9}

    # tail_df and stress_prob are the two knobs that act on *every asset at once*: Student-t scale
    # mixing draws one chi-square per path and the stress regime switches the whole unit into
    # crisis rows together. Both therefore inflate cross-asset dependence, which is 30 % of the
    # score on a multi-asset card. Gate them behind the same corroboration the width needs.
    tail_df = raw.get("tail_df")
    tail = float(np.clip(_num(tail_df, 0.0), 4.0, 8.0)) if tail_df not in (None, "null", "") and _num(tail_df, 0.0) > 0 else None
    if tail is None and event:
        tail = 6.0
    if TAIL_ENABLED and len(assets) > 1 and not event:
        tail = None   # joint card with no binary event: a common fat-tail factor is a fake correlation
    if not TAIL_ENABLED:
        tail = None
    # stress regime probability: the model's number, floored by what the cards say
    sp = None
    if SP_ENABLED:
        sp_raw = raw.get("stress_prob")
        sp = float(np.clip(_num(sp_raw, 0.10), 0.0, 0.6)) if sp_raw not in (None, "null", "") else 0.10
        hi = max(share.values()) if share else 0.0
        floor_sp = min(0.6, 0.10 + 0.15 * event + 0.2 * hi)
        if sp < floor_sp:
            notes.append(f"guardrail: stress_prob {sp:.2f} below the cards' floor {floor_sp:.2f}; raised")
            sp = floor_sp
        if len(assets) > 1 and not event:
            notes.append(f"joint card with no binary event: stress_prob {sp:.2f} dropped, the engine "
                         "default applies (a unit-wide regime switch is a fake cross-asset correlation)")
            sp = None
    if raw.get("disagreement"):
        notes.append(f"disagreement: {str(raw['disagreement'])[:240]}")
    return Adjustments(scenarios=scenarios, tail_df=tail, stress_prob=sp, notes=notes).normalized()


# --------------------------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------------------------


def _model_key(llm: LLM) -> str:
    return llm.model.replace("/", "_").replace(":", "_")


def run_text_stage(
    unit: Unit,
    asof: str,
    llm: LLM | None = None,
    cache_dir: pathlib.Path | None = None,
    time_budget_s: float = TIME_BUDGET_S,
) -> tuple[Adjustments, dict[str, Any]]:
    """Return (Adjustments, diagnostics). Never raises."""
    t0 = time.time()
    llm = llm or LLM()
    notes: list[str] = []
    diag: dict[str, Any] = {"model": llm.model, "endpoint": llm.endpoint, "cards": [], "raw_b": None}
    try:
        docs = _read_docs(unit)
        if not docs:
            notes.append("no documents in the text corpus; neutral adjustments used")
            adj = Adjustments.neutral(); adj.notes = notes
            return adj, diag
        actx, summary = _asset_context(unit, asof)
        diag["context"] = {"targets": actx, "task": {k: v for k, v in summary.items() if k != "card_notes"}}

        # caches: pass-A cards keyed by (unit, model) and doc_id; pass-B keyed by prompt version too
        cards_cache = passb_cache = None
        cached_cards: dict[str, Any] = {}
        if cache_dir is not None:
            (cache_dir / "cards").mkdir(parents=True, exist_ok=True)
            (cache_dir / "passb").mkdir(parents=True, exist_ok=True)
            cards_cache = cache_dir / "cards" / f"{unit.unit_id}.{_model_key(llm)}.{PROMPT_A_VERSION}.json"
            passb_cache = cache_dir / "passb" / f"{unit.unit_id}.{_model_key(llm)}.{PROMPT_VERSION}.json"
            if cards_cache.is_file():
                try:
                    cached_cards = json.loads(cards_cache.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    cached_cards = {}

        cards: list[dict[str, Any]] = []
        n_new = 0
        for doc in docs:
            if doc["doc_id"] in cached_cards:
                cards.append(cached_cards[doc["doc_id"]])
                continue
            if time.time() - t0 > time_budget_s * 0.7:
                notes.append(f"time budget: stopped reading documents after {len(cards)}/{len(docs)}")
                break
            card = _pass_a(llm, doc, summary, actx)
            if card is not None:
                cards.append(card)
                cached_cards[doc["doc_id"]] = card
                n_new += 1
        if cards_cache is not None and n_new:
            cards_cache.write_text(json.dumps(cached_cards, indent=1, ensure_ascii=False), encoding="utf-8")
        diag["cards"] = cards
        if not cards:
            notes.append(f"model produced no usable signal cards ({len(llm.usage.errors)} errors); neutral adjustments used")
            adj = Adjustments.neutral(); adj.notes = notes
            return adj, diag

        raw_b = None
        if passb_cache is not None and passb_cache.is_file():
            try:
                raw_b = json.loads(passb_cache.read_text(encoding="utf-8"))
                diag["cached_b"] = True
            except json.JSONDecodeError:
                raw_b = None
        if raw_b is None and time.time() - t0 < time_budget_s:
            raw_b = _pass_b(llm, cards, summary, actx)
            if passb_cache is not None and raw_b is not None:
                passb_cache.write_text(json.dumps(raw_b, indent=1, ensure_ascii=False), encoding="utf-8")
        diag["raw_b"] = raw_b
        diag["implied_drift"] = implied_drift(cards, unit.assets)
        return _to_adjustments(raw_b, unit, cards, {d["doc_id"] for d in docs}, notes), diag
    except Exception as exc:  # noqa: BLE001 — never let the text stage kill a unit
        notes.append(f"text stage failed ({type(exc).__name__}: {str(exc)[:160]}); neutral adjustments used")
        adj = Adjustments.neutral(); adj.notes = notes
        return adj, diag
    finally:
        diag["usage"] = {**llm.usage.__dict__, "elapsed_s": round(time.time() - t0, 1)}
