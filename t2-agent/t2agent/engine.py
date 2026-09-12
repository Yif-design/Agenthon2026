"""Statistical backbone: a regime-aware, joint block-bootstrap Monte Carlo engine.

What it does, per unit:

1. For every target asset, load history up to the as-of and move it into a *working space*
   where increments are roughly stationary:
     - ``log``    for positive level series (FX spot, CPI index, payrolls, unemployment rate)
     - ``diff``   for yields / rates (can be negative, additive moves)
     - ``cumlog`` for ``log_return`` targets (factor panels): working series = cumsum(log1p(r)),
                  anchor = 0, the target is the cumulative log return after the as-of.
2. Build gap-aware increments and **standardize** them by their own lagged EWMA volatility, so
   the bootstrap pool holds *shocks in units of sd* (shape: fat tails, clustering, skew) rather
   than raw moves whose scale belongs to another regime.
3. Draw joint shock paths by **stationary block bootstrap** of the aligned, demeaned shocks —
   rows are sampled together across assets, so cross-asset correlation comes for free. Blocks
   come from a *recent* pool (60 %) and the *full* history (40 %) so tails reflect stress the
   calm period lacks.
4. Rescale each shock by a **volatility path** that starts at the as-of EWMA vol and
   mean-reverts toward a long-run vol (for yields, a level-aware long-run vol: a 0.3 % 2-year
   note cannot move like a 5 % one). This is the "as tight as the evidence justifies and no
   tighter" rule made explicit.
5. Overlay the statistical prior drift and the text-derived ``Adjustments`` (scenario mixture of
   drift / vol multipliers), cumulate along the path, read every horizon from the *same* path
   (cross-horizon consistency), then map back to the card's units.

Nothing in here reads the text corpus.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .cardio import Unit, series_for
from .knobs import Adjustments

RECENT_ROWS = {"daily": 252, "monthly": 36}
BLOCK_MEAN = {"daily": 7, "monthly": 3}
EWMA_HALFLIFE = {"daily": 20, "monthly": 6}
VOL_REVERT_TAU = {"daily": 60.0, "monthly": 6.0}   # steps for vol to mean-revert (e-folding)
W_RECENT = 0.6              # mixture weight of the recent shock pool
MIN_JOINT_ROWS = 60         # below this, fall back to per-asset independent bootstrap
MIN_ROWS_BOOTSTRAP = 30     # below this, Gaussian fallback
Z_VOL_FLOOR_FRAC = 0.25     # lagged vol floor (fraction of full-sample sd) when standardizing
PEG_VOL_TRIGGER_FRAC = 0.25 # FX assets: treat as pegged when own vol < this x the panel's median vol
PEG_VOL_FLOOR_FRAC = 0.5    # ... and then floor the spread at this x the median
PUBLICATION_LAG_DAYS = 45   # macro panels: observation month lags the calendar by ~45 days
STRESS_WINDOW = {"daily": 21, "monthly": 6}       # rolling-vol window that defines "stress" rows
STRESS_PCTL = 85.0                                # rows whose lagged rolling vol is above this pctl
P_STRESS = float(os.environ.get("T2_P_STRESS", 0.12))   # prob. a path is drawn from the stress regime
VOL_UNCERTAINTY = float(os.environ.get("T2_VOL_VV", 0.25))  # lognormal sd of the per-path vol factor
WIDTH_MULT = float(os.environ.get("T2_WIDTH", 1.00))        # global multiplier on the vol path (calibration)
CUMLOG_DRIFT = float(os.environ.get("T2_CUMLOG_DRIFT", 0.0))  # shrink on the full-sample mean for cumlog targets
VOL0_FLOOR = float(os.environ.get("T2_VOL0_FLOOR", 1.5))  # floor on the as-of vol as a fraction of long-run vol


@dataclass
class AssetSpec:
    asset: str
    panel: str
    freq: str                    # "daily" | "monthly"
    space: str                   # "diff" | "log" | "cumlog"
    anchor: float                # last observed level (0.0 for cumlog)
    last_date: str
    incr: pd.Series              # working-space increments, gap-aware, indexed by date
    z: pd.Series                 # increments standardized by lagged EWMA vol
    vol_full: float              # full-sample sd of increments
    vol0: float                  # EWMA vol at the as-of (start of the vol path)
    vol_lr: float                # long-run vol the path reverts to (level-aware for yields)
    level_factor: float = 1.0    # yields: min(1, sqrt(level_now / mean level))
    prior_drift: float = 0.0     # working units per step (statistical, declared)
    stress: pd.Series | None = None   # bool per increment date: lagged rolling vol in the top tail
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------------------------
# per-asset preparation
# --------------------------------------------------------------------------------------------


def _freq_key(freq: str) -> str:
    return "monthly" if "month" in (freq or "").lower() else "daily"


def _working(unit: Unit, panel: str, s: pd.Series) -> tuple[str, pd.Series, float]:
    if unit.target_type == "log_return":
        work = np.log1p(s).cumsum()
        return "cumlog", work, 0.0
    if "rate" in panel.lower() or (s <= 0).any():
        return "diff", s.astype(float), float(s.iloc[-1])
    return "log", np.log(s.astype(float)), float(s.iloc[-1])


def _increments(work: pd.Series, freq: str) -> pd.Series:
    """First differences, dropping any that span a hole in the data (transfer cards)."""
    d = work.diff()
    when = pd.to_datetime(pd.Series(work.index, index=work.index), errors="coerce")
    step = when.diff().dt.days
    if step.notna().sum() == 0:
        return d.dropna()
    med = float(step.median())
    typical = med if not math.isnan(med) else (1.0 if freq == "daily" else 31.0)
    return d.where(step <= max(typical * 10.0, 5.0)).dropna()


def _ewma_vol(incr: pd.Series, freq: str) -> pd.Series:
    """sqrt of the EWMA of squared increments — the local vol *including* the current row."""
    return incr.pow(2).ewm(halflife=EWMA_HALFLIFE[freq], min_periods=5).mean().pow(0.5)


def _standardize(incr: pd.Series, freq: str) -> tuple[pd.Series, float, float]:
    """Shocks z_t = x_t / vol_{t-1}; returns (z, vol0, vol_full)."""
    vol_full = float(incr.std(ddof=1)) if len(incr) > 2 else float(np.abs(incr).mean())
    local = _ewma_vol(incr, freq)
    lagged = local.shift(1).bfill().clip(lower=Z_VOL_FLOOR_FRAC * vol_full)
    z = (incr / lagged).dropna()
    vol0 = float(local.iloc[-1]) if np.isfinite(local.iloc[-1]) and local.iloc[-1] > 0 else vol_full
    return z, vol0, vol_full


def _panel_reference(unit: Unit, panel: str, asof: str, exclude: str) -> tuple[float, str, pd.Series] | None:
    """Median full-history log-vol across the other assets of an FX-like panel, plus the
    increments of the asset closest to that median (a proxy series for pegged targets)."""
    df = unit.panels.get(panel)
    if df is None:
        return None
    cands: list[tuple[float, str, pd.Series]] = []
    for a in df["asset"].unique():
        if a == exclude:
            continue
        sub = df[(df["asset"] == a) & (df["date"] <= asof)].sort_values("date")
        s = sub.set_index("date")["value"].astype(float)
        s = s[~s.index.duplicated(keep="last")]
        if len(s) < 100 or (s <= 0).any():
            continue
        incr = _increments(np.log(s), "daily")
        cands.append((float(incr.std()), str(a), incr))
    if not cands:
        return None
    med = float(np.median([v for v, _, _ in cands]))
    _, name, incr = min(cands, key=lambda c: abs(c[0] - med))
    return med, name, incr


def _prior_drift(space: str, freq: str, incr: pd.Series) -> float:
    """A small, statistical drift per step for series that trend by construction.

    * cumulative log-return targets (factor panels): half the full-sample mean return — the
      equity/factor premium is real but we shrink it;
    * monthly positive index series with a strongly significant mean (CPI, payrolls): the mean
      of the full-sample and recent-window means;
    * everything else (FX, yields, unemployment): zero — a driftless random walk is the honest
      centre, and any directional view has to come from the text with evidence.
    """
    x = incr.to_numpy(dtype=float)
    if len(x) < 30:
        return 0.0
    mean_full = float(x.mean())
    t_stat = mean_full / (x.std(ddof=1) / math.sqrt(len(x)) + 1e-12)
    if space == "cumlog":
        return CUMLOG_DRIFT * mean_full
    if space == "log" and freq == "monthly" and t_stat > 3.0:
        recent = x[-RECENT_ROWS["monthly"]:]
        return 0.5 * (mean_full + float(recent.mean()))
    return 0.0


def prepare_asset(unit: Unit, asset: str, asof: str) -> AssetSpec:
    s, panel, freq_decl = series_for(unit, asset, asof)
    freq = _freq_key(freq_decl)
    space, work, anchor = _working(unit, panel, s)
    incr = _increments(work, freq)
    if len(incr) < 5:
        raise SystemExit(f"{asset}: only {len(incr)} usable increments; cannot forecast")
    notes: list[str] = []

    # Pegged / managed currencies: the own history says "no vol", which is exactly what an F2
    # peg-break card is about. Borrow the *shape* of a typical panel currency's increments
    # (dated, so joint alignment survives), scaled to a floor; the anchor stays the own level.
    if space == "log" and freq == "daily":
        ref_panel = panel if "fx" in panel.lower() else next((k for k in unit.panels if "fx" in k.lower()), None)
        ref = _panel_reference(unit, ref_panel, asof, exclude=asset) if ref_panel else None
        own_vol = float(incr.std(ddof=1))
        if ref is not None and own_vol < PEG_VOL_TRIGGER_FRAC * ref[0]:
            med, proxy_name, proxy_incr = ref
            floor = PEG_VOL_FLOOR_FRAC * med
            incr = proxy_incr * (floor / float(proxy_incr.std()))
            notes.append(
                f"own-history vol {own_vol:.5f}/step is below {PEG_VOL_TRIGGER_FRAC:.0%} of the panel's "
                f"median FX vol {med:.5f} (managed/pegged series): innovations borrowed from {proxy_name} "
                f"and scaled to {floor:.5f}/step; centre stays at the own anchor"
            )

    z, vol0, vol_full = _standardize(incr, freq)
    vol_lr, level_factor = vol_full, 1.0
    if space == "diff":
        # Yields: absolute vol scales with the level (roughly sqrt-CIR). A 2-year note at 0.3 %
        # does not carry the 2008 vol of a 5 % note; shrink the long-run vol accordingly.
        mean_level = float(s.mean())
        if mean_level > 0 and anchor > 0:
            level_factor = min(1.0, math.sqrt(anchor / mean_level))
            vol_lr = vol_full * level_factor
            if level_factor < 0.999:
                notes.append(
                    f"long-run vol scaled by sqrt(level/mean level) = {level_factor:.2f} "
                    f"(level {anchor:.3g} vs sample mean {mean_level:.3g})"
                )
    roll = incr.rolling(STRESS_WINDOW[freq], min_periods=3).std().shift(1)
    thr = float(np.nanpercentile(roll.dropna(), STRESS_PCTL)) if roll.notna().sum() > 20 else float("inf")
    stress = (roll >= thr).fillna(False)
    return AssetSpec(
        asset=asset, panel=panel, freq=freq, space=space, anchor=anchor, last_date=str(s.index[-1]),
        incr=incr, z=z, vol_full=vol_full, vol0=vol0, vol_lr=vol_lr, level_factor=level_factor,
        prior_drift=_prior_drift(space, freq, incr), stress=stress, notes=notes,
    )


# --------------------------------------------------------------------------------------------
# horizon -> path step, vol path
# --------------------------------------------------------------------------------------------


def steps_for(spec: AssetSpec, horizons: list[int], asof: str) -> dict[int, int]:
    if spec.freq == "daily":
        return {h: int(h) for h in horizons}
    out: dict[int, int] = {}
    last = pd.Timestamp(spec.last_date)
    for h in horizons:
        target = pd.Timestamp(asof) + pd.offsets.BDay(int(h)) - pd.Timedelta(days=PUBLICATION_LAG_DAYS)
        months = (target.year - last.year) * 12 + (target.month - last.month) + (target.day - last.day) / 30.0
        out[h] = max(1, int(round(months)))
    return out


def vol_path(spec: AssetSpec, L: int) -> np.ndarray:
    """sigma_s for s = 1..L: starts at the as-of EWMA vol, e-folds toward the long-run vol."""
    s = np.arange(1, L + 1, dtype=float)
    tau = VOL_REVERT_TAU[spec.freq]
    # The as-of EWMA vol is the *worst* scale estimate exactly where it matters most: a tail-shock
    # card is dated the day before the shock, so recent realized vol is low precisely because the
    # move has not happened yet ("calm before the storm"). With tau = 60 a 5-day path never leaves
    # vol0, which is why short-horizon F4 cards sit at below05 = 0.46. Floor vol0 against the
    # long-run vol: the floor only bites when vol0 << vol_lr, so calm-before-storm cards widen and
    # already-volatile cards are untouched.
    vol0 = max(spec.vol0, VOL0_FLOOR * spec.vol_lr)
    var = spec.vol_lr**2 + (vol0**2 - spec.vol_lr**2) * np.exp(-s / tau)
    return WIDTH_MULT * np.sqrt(np.clip(var, 1e-18, None))


# --------------------------------------------------------------------------------------------
# bootstrap
# --------------------------------------------------------------------------------------------


def _block_indices(rng: np.random.Generator, n_rows: int, length: int, mean_block: float) -> np.ndarray:
    """Stationary (Politis–Romano) block bootstrap indices, circular."""
    idx = np.empty(length, dtype=np.int64)
    filled = 0
    p = 1.0 / mean_block
    while filled < length:
        start = int(rng.integers(n_rows))
        blen = int(rng.geometric(p))
        take = min(blen, length - filled)
        idx[filled:filled + take] = (start + np.arange(take)) % n_rows
        filled += take
    return idx


def _pools(aligned: np.ndarray, freq: str) -> tuple[np.ndarray, np.ndarray]:
    """Full-history and recent shock pools, each demeaned on its own and re-scaled to unit
    variance per column (the scale is the vol path's job, the pool only supplies shape)."""

    def norm(a: np.ndarray) -> np.ndarray:
        a = a - a.mean(axis=0, keepdims=True)
        sd = a.std(axis=0, ddof=1, keepdims=True) if len(a) > 2 else np.ones((1, a.shape[1]))
        return a / np.where(sd > 0, sd, 1.0)

    r = RECENT_ROWS[freq]
    recent = aligned[-r:] if len(aligned) > r else aligned
    return norm(aligned), norm(recent)


# --------------------------------------------------------------------------------------------
# main entry
# --------------------------------------------------------------------------------------------


def build_draws(
    unit: Unit,
    asof: str,
    n_draws: int,
    seed: int,
    adj: Adjustments | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Return samples[n_draws, n_assets, n_horizons] in the card's units, plus an info ledger."""
    adj = (adj or Adjustments.neutral()).normalized()
    problems = adj.validate(unit.assets)
    if problems:
        raise SystemExit("invalid adjustments: " + "; ".join(problems))

    rng = np.random.default_rng(seed)
    specs = [prepare_asset(unit, a, asof) for a in unit.assets]
    n_a, n_h = len(specs), len(unit.horizons)
    freqs = {s.freq for s in specs}
    freq = specs[0].freq if len(freqs) == 1 else "daily"

    steps = [steps_for(s, unit.horizons, asof) for s in specs]
    L = max(st[h] for st in steps for h in unit.horizons)
    sig = np.stack([vol_path(s, L) for s in specs], axis=1)             # (L, n_a)
    cum_var = np.cumsum(sig**2, axis=0)                                  # (L, n_a)

    # ---- aligned shock matrix (joint) or per-asset (independent) ----------------------------
    frame = pd.concat([s.z.rename(s.asset) for s in specs], axis=1).dropna()
    joint = (n_a == 1) or (len(freqs) == 1 and len(frame) >= MIN_JOINT_ROWS)
    lf = np.array([s.level_factor for s in specs])
    if joint:
        mode = "joint-bootstrap"
        pools = [_pools(frame.to_numpy(dtype=float), freq)]
        cols = [list(range(n_a))]
        raw = pd.concat([s.incr.rename(s.asset) for s in specs], axis=1).reindex(frame.index)
        smask = pd.concat([s.stress.rename(s.asset) for s in specs], axis=1).reindex(frame.index).fillna(False).any(axis=1)
        stress_pools = [raw[smask.to_numpy()].to_numpy(dtype=float) * lf[None, :]]
    else:
        mode = "independent-bootstrap"
        pools, cols, stress_pools = [], [], []
        for i, s in enumerate(specs):
            pools.append(_pools(s.z.to_numpy(dtype=float).reshape(-1, 1), s.freq))
            cols.append([i])
            stress_pools.append(s.incr[s.stress.reindex(s.incr.index).fillna(False).to_numpy()].to_numpy(dtype=float).reshape(-1, 1) * lf[i])
    p_stress = adj.stress_prob if adj.stress_prob is not None else P_STRESS
    stress_ok = all(len(sp) >= MIN_ROWS_BOOTSTRAP for sp in stress_pools)
    if not stress_ok:
        p_stress = 0.0

    # ---- scenario assignment ----------------------------------------------------------------
    weights = np.array([sc.weight for sc in adj.scenarios], dtype=float)
    which = rng.choice(len(adj.scenarios), size=n_draws, p=weights / weights.sum())
    h0 = min(unit.horizons)
    steps_h0 = np.array([st[h0] for st in steps], dtype=float)
    sd_h0 = np.array([math.sqrt(cum_var[int(steps_h0[i]) - 1, i]) for i in range(n_a)])

    # ---- simulate ---------------------------------------------------------------------------
    # Two regimes per path. Normal (1 - p_stress): unit-variance shocks x the vol path x a
    # lognormal vol-uncertainty factor (we do not know next month's vol to 10 %). Stress
    # (p_stress): raw increments bootstrapped from the historical rows whose lagged rolling vol sat
    # in the top tail — crisis scale, clustering and skew taken from history as they were.
    regime = rng.random(n_draws) < p_stress                             # True = stress path
    shocks = np.zeros((n_draws, L, n_a), dtype=float)
    paths = np.zeros((n_draws, L, n_a), dtype=float)
    vv = VOL_UNCERTAINTY
    vol_factor = np.exp(vv * rng.standard_normal(n_draws) - 0.5 * vv * vv)
    for d in range(n_draws):
        view = shocks[d]
        if regime[d]:
            for sp, c in zip(stress_pools, cols):
                idx = _block_indices(rng, len(sp), L, BLOCK_MEAN[freq])
                paths[d][:, c] = sp[idx]
            continue
        use_recent = rng.random() < W_RECENT
        for (full, recent), c in zip(pools, cols):
            pool = recent if use_recent else full
            if len(pool) >= MIN_ROWS_BOOTSTRAP:
                idx = _block_indices(rng, len(pool), L, BLOCK_MEAN[freq])
                view[:, c] = pool[idx]
            else:  # Gaussian fallback on tiny histories
                view[:, c] = rng.standard_normal((L, len(c)))
    if adj.tail_df:
        shocks *= np.sqrt(adj.tail_df / rng.chisquare(adj.tail_df, size=(n_draws, 1, 1)))
    normal = ~regime
    paths[normal] = shocks[normal] * sig[None, :, :] * vol_factor[normal][:, None, None]
    base_paths = paths.copy()                                            # before drift / scenario overlays

    # statistical prior drift (declared in the ledger; zero for FX / yields / unemployment)
    prior = np.array([s.prior_drift for s in specs])
    paths += prior[None, None, :]

    # text-derived scenario overlays: vol multipliers and drift
    for k, sc in enumerate(adj.scenarios):
        sel = which == k
        if not sel.any():
            continue
        vm = np.array([sc.vol_mult.get(s.asset, 1.0) for s in specs])
        dr = np.array([sc.drift.get(s.asset, 0.0) for s in specs])
        paths[sel] = base_paths[sel] * vm[None, None, :] + prior[None, None, :]
        per_step = dr * sd_h0 / steps_h0                       # working units per step
        paths[sel] += per_step[None, None, :]

    cum = np.cumsum(paths, axis=1)                             # (n_draws, L, n_a)
    samples = np.empty((n_draws, n_a, n_h), dtype=float)
    for i, s in enumerate(specs):
        for j, h in enumerate(unit.horizons):
            x = cum[:, steps[i][h] - 1, i]
            if s.space == "log":
                samples[:, i, j] = s.anchor * np.exp(x)
            elif s.space == "diff":
                samples[:, i, j] = s.anchor + x
            else:  # cumlog
                samples[:, i, j] = x

    # ---- ledger -----------------------------------------------------------------------------
    q = np.quantile(samples, [0.05, 0.5, 0.95], axis=0)       # (3, n_a, n_h)
    info: dict[str, Any] = {
        "mode": mode,
        "freq": freq,
        "aligned_rows": int(len(frame)),
        "pool_recent_rows": int(len(pools[0][1])),
        "pool_full_rows": int(len(pools[0][0])),
        "w_recent": W_RECENT,
        "block_mean": BLOCK_MEAN[freq],
        "vol_revert_tau": VOL_REVERT_TAU[freq],
        "p_stress": float(p_stress),
        "stress_rows": int(len(stress_pools[0])),
        "vol_uncertainty": vv,
        "path_steps": int(L),
        "scenarios": [
            {"name": sc.name, "weight": float(sc.weight), "drift": sc.drift, "vol_mult": sc.vol_mult,
             "evidence": sc.evidence, "established": sc.established,
             "n_draws": int((which == k).sum())}
            for k, sc in enumerate(adj.scenarios)
        ],
        "tail_df": adj.tail_df,
        "notes": list(adj.notes),
        "assets": {},
    }
    for i, s in enumerate(specs):
        info["assets"][s.asset] = {
            "panel": s.panel, "space": s.space, "freq": s.freq, "anchor": s.anchor,
            "last_date": s.last_date, "n_increments": int(len(s.incr)),
            "vol0": s.vol0, "vol_full": s.vol_full, "vol_lr": s.vol_lr, "level_factor": s.level_factor,
            "prior_drift_step": float(s.prior_drift), "notes": s.notes,
            "horizons": {
                int(h): {
                    "steps": int(steps[i][h]),
                    "sd_working": float(math.sqrt(cum_var[steps[i][h] - 1, i])),
                    "q05": float(q[0, i, j]), "q50": float(q[1, i, j]), "q95": float(q[2, i, j]),
                }
                for j, h in enumerate(unit.horizons)
            },
        }
    return samples, info
