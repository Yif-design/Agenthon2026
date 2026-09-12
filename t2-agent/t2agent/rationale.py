"""forecast_rationale.md — required, never scored, read by a human in Verification.

It has to make two things visible line by line: which adjustment is *established* vs *inferred*,
and which dated document drove which adjustment. Phase 2 has no adjustments, and says so.
"""

from __future__ import annotations

from typing import Any

from .cardio import Unit


def _fmt(x: float) -> str:
    return f"{x:.6g}"


def write_rationale(unit: Unit, asof: str, n_draws: int, info: dict[str, Any]) -> str:
    hz = ", ".join(str(h) for h in unit.horizons)
    lines: list[str] = []
    lines.append(f"# Forecast rationale — {unit.unit_id}")
    lines.append("")
    lines.append(
        f"As of **{asof}**, joint predictive distribution over {', '.join(unit.assets)} at "
        f"horizon(s) {hz} business days; target type `{unit.target_type}` "
        f"({unit.value_unit or 'card units'}); {n_draws} draws."
    )
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append(
        f"Mode: **{info['mode']}** on {info['freq']} increments. Paths of {info['path_steps']} steps are "
        f"built by stationary block bootstrap (mean block {info['block_mean']}) of demeaned historical "
        f"increments, mixing a recent pool ({info['pool_recent_rows']} rows, weight {info['w_recent']:.0%}) "
        f"with the full history ({info['pool_full_rows']} rows). The pools hold *vol-standardized* shocks, "
        "so they supply shape (fat tails, clustering, skew) while the scale comes from a volatility path "
        f"that starts at the as-of EWMA vol and mean-reverts to the long-run vol (e-folding time "
        f"{info['vol_revert_tau']:.0f} steps). Rows are sampled jointly across assets, so cross-asset "
        "correlation is preserved; every horizon is read from the same path, so cross-horizon structure "
        "is consistent."
    )
    lines.append("")
    lines.append("## Anchor and scale")
    lines.append("")
    lines.append("| asset | panel | space | anchor (last obs) | last date | vol/step as-of | vol/step long-run | vol/step full sample | prior drift/step |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for a, d in info["assets"].items():
        lines.append(
            f"| {a} | {d['panel']} | {d['space']} | {_fmt(d['anchor'])} | {d['last_date']} | "
            f"{_fmt(d['vol0'])} | {_fmt(d['vol_lr'])} | {_fmt(d['vol_full'])} | {_fmt(d.get('prior_drift_step', 0.0))} |"
        )
    lines.append("")
    lines.append(
        "Prior drift is statistical (established from the panel, not the text): half the full-sample "
        "mean for cumulative-return targets, a shrunk trend for index-like monthly series, zero for "
        "FX, yields and rates."
    )
    lines.append("")
    lines.append("| asset | horizon (BD) | path steps | sd at horizon (working space) | q05 | q50 | q95 |")
    lines.append("|---|---|---|---|---|---|---|")
    for a, d in info["assets"].items():
        for h, hd in d["horizons"].items():
            lines.append(
                f"| {a} | {h} | {hd['steps']} | {_fmt(hd['sd_working'])} | {_fmt(hd['q05'])} | "
                f"{_fmt(hd['q50'])} | {_fmt(hd['q95'])} |"
            )
    for a, d in info["assets"].items():
        for n in d.get("notes", []):
            lines.append("")
            lines.append(f"- {a}: {n}")
    lines.append("")
    lines.append("## Adjustment ledger")
    lines.append("")
    lines.append("| scenario | weight | draws | drift (horizon-sd units) | vol multiplier | established? | evidence (doc_id) |")
    lines.append("|---|---|---|---|---|---|---|")
    for sc in info["scenarios"]:
        drift = ", ".join(f"{k}: {v:+.2f}" for k, v in sc["drift"].items()) or "0 (all assets)"
        vm = ", ".join(f"{k}: x{v:.2f}" for k, v in sc["vol_mult"].items()) or "x1.00 (all assets)"
        ev = ", ".join(sc["evidence"]) or "—"
        lines.append(
            f"| {sc['name']} | {sc['weight']:.2f} | {sc['n_draws']} | {drift} | {vm} | "
            f"{'yes' if sc['established'] else 'no'} | {ev} |"
        )
    lines.append("")
    lines.append(
        f"Regime mixture: {info.get('p_stress', 0):.0%} of paths are drawn from the historical stress "
        f"regime ({info.get('stress_rows', 0)} rows whose lagged rolling vol sat above the {85}th percentile), "
        f"the rest from the normal regime with a lognormal vol-uncertainty factor (sd {info.get('vol_uncertainty', 0):.2f})."
    )
    if info.get("tail_df"):
        lines.append("")
        lines.append(f"Extra Student-t scale mixing with df={info['tail_df']}.")
    for n in info.get("notes", []):
        lines.append("")
        lines.append(f"- {n}")
    lines.append("")
    lines.append("## Documents read")
    lines.append("")
    cards = (info.get("text_stage") or {}).get("cards") or []
    if cards:
        lines.append("| doc_id | date | tone | relevance | established facts | per-asset read |")
        lines.append("|---|---|---|---|---|---|")
        for c in cards:
            facts = "; ".join(str(f) for f in (c.get("established_facts") or [])[:3])[:200] or "—"
            pa = "; ".join(
                f"{a}: {v.get('direction', 0)} ({v.get('uncertainty', 'same')})"
                for a, v in (c.get("per_asset") or {}).items() if isinstance(v, dict)
            )[:160]
            lines.append(
                f"| `{c.get('doc_id')}` | {c.get('date', '')} | {c.get('inferred_tone', '')} | "
                f"{c.get('relevance', '')} | {facts} | {pa} |"
            )
        lines.append("")
        for c in cards:
            if c.get("summary"):
                lines.append(f"- `{c.get('doc_id')}`: {str(c['summary'])[:300]}")
        lines.append("")
    lines.append("## What the text corpus contributed")
    lines.append("")
    only_baseline = len(info["scenarios"]) == 1 and not info["scenarios"][0]["drift"] and not info["scenarios"][0]["vol_mult"]
    if unit.docs:
        lines.append(f"{len(unit.docs)} dated document(s) were available at the text path:")
        lines.append("")
        for d in unit.docs:
            ts = d.get("timestamp", "")
            lines.append(f"- `{d.get('doc_id', d.get('file', '?'))}` ({ts}) — {d.get('doc_type', d.get('source', ''))}")
        lines.append("")
    if only_baseline:
        lines.append(
            "**None.** No document was read for this run: the centre is the anchor with zero drift and "
            "the spread is the unadjusted regime-blended historical vol. This is the statistical "
            "backbone the text stage is meant to improve on; every adjustment is listed as zero above "
            "rather than omitted, so the ledger sums."
        )
    else:
        lines.append(
            "Adjustments above are derived from the listed evidence. Rows marked established = yes "
            "rest on facts the documents state; rows marked no rest on inferred tone and only move "
            "the centre or widen the spread — they never narrow it."
        )
    lines.append("")
    lines.append("## What would change this forecast")
    lines.append("")
    lines.append(
        "A dated document establishing a policy decision, a data print, or a regime change inside "
        "the horizon window would move the centre (drift), widen the spread (vol multiplier), or "
        "split the distribution into weighted scenarios. A disagreement between the panel's recent "
        "path and the documents' argument would widen the distribution rather than be averaged away."
    )
    lines.append("")
    return "\n".join(lines)
