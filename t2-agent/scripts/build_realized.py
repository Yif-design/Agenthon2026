"""DEV ONLY — reconstruct realized outcomes for the practice units from sibling units' panels.

The organizers ship no realized values, but they also state (README, "Practice tasks") that for
75/103 practice units every realized value is present verbatim in a sibling unit's panel. That makes
a local *scoring* harness possible: run the official scorer with `--realized` and get real CRPS /
variogram / tail numbers instead of gates-only.

    python scripts/build_realized.py --repo ../starter-repos/track2-forecasting-public --out dev/realized

Rules of use:
* The output lives under `dev/`, which is in .dockerignore. It must NEVER reach the image, the
  agent, or any code path the agent executes. The agent reads one unit at a time and nothing else.
* Target-date convention: `h` rows of the pooled trading-day calendar after the as-of (monthly
  panels: the observation month that `asof + h BD - 45d` falls in). The organizers' exact
  target_dates are sealed, so the reconstruction can be off by a day; that is noise at the
  horizons we care about, and it only ever affects local development numbers.
* This is for calibration and ablation. Do not tune anything to a *specific* card's answer; use
  aggregate statistics (mean composite, PIT coverage, tail exceedance) across the suite.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from t2agent.cardio import asof_from_card, load_card, read_panels  # noqa: E402

PUBLICATION_LAG_DAYS = 45


def pool_panels(units: list[pathlib.Path]) -> dict[str, pd.DataFrame]:
    """Union of every unit's rows per panel stem; conflicting values on a date resolve to the median."""
    frames: dict[str, list[pd.DataFrame]] = {}
    for u in units:
        for stem, df in read_panels(u).items():
            frames.setdefault(stem, []).append(df[["date", "asset", "value"]])
    pooled = {}
    for stem, lst in frames.items():
        big = pd.concat(lst, ignore_index=True)
        pooled[stem] = big.groupby(["asset", "date"], as_index=False)["value"].median().sort_values(["asset", "date"])
    return pooled


def realized_for(unit: pathlib.Path, pooled: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame | None, str]:
    card = load_card(unit / "card.toml")
    panels = read_panels(unit)
    asof = asof_from_card(card, panels)
    tgt = card["targets"]
    assets, horizons, ttype = [str(a) for a in tgt["asset_ids"]], [int(h) for h in tgt["horizons"]], tgt.get("target_type", "level")
    panel_meta = {k: v for k, v in (card.get("panels") or {}).items() if isinstance(v, dict)}
    rows, notes = [], []
    for a in assets:
        stems = [k for k, v in panel_meta.items() if a in [str(x) for x in v.get("asset_ids", [])]] or list(panels.keys())
        stem = next((s for s in stems if s in pooled and (pooled[s]["asset"] == a).any()), None)
        if stem is None:
            return None, f"{a}: no pooled panel"
        freq = str(panel_meta.get(stem, {}).get("frequency", "business_daily"))
        s = pooled[stem][pooled[stem]["asset"] == a].set_index("date")["value"]
        s = s[~s.index.duplicated()]
        dates = list(s.index)
        if "month" in freq:
            last = pd.Timestamp(max(d for d in dates if d <= asof))
            for h in horizons:
                target = pd.Timestamp(asof) + pd.offsets.BDay(h) - pd.Timedelta(days=PUBLICATION_LAG_DAYS)
                key = f"{target.year:04d}-{target.month:02d}-01"
                if key not in s.index:
                    return None, f"{a}: month {key} not in pooled panel"
                rows.append({"asset": a, "horizon": h, "value": float(s[key])})
            continue
        # daily: h trading rows after the as-of row
        pos_asof = max(i for i, d in enumerate(dates) if d <= asof)
        if dates[pos_asof] != asof:
            notes.append(f"{a}: as-of {asof} not a panel date, using {dates[pos_asof]}")
        for h in horizons:
            j = pos_asof + h
            if j >= len(dates):
                return None, f"{a}: horizon {h} beyond pooled panel end {dates[-1]}"
            if ttype == "log_return":
                seg = s.iloc[pos_asof + 1: j + 1].to_numpy(dtype=float)
                if len(seg) != h or not np.all(np.isfinite(seg)):
                    return None, f"{a}: gap inside the {h}-day window"
                rows.append({"asset": a, "horizon": h, "value": float(np.sum(np.log1p(seg)))})
            else:
                rows.append({"asset": a, "horizon": h, "value": float(s.iloc[j])})
    return pd.DataFrame(rows), "; ".join(notes)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=pathlib.Path, required=True)
    p.add_argument("--out", type=pathlib.Path, default=HERE.parent / "dev" / "realized")
    a = p.parse_args()
    units = sorted(u for u in (a.repo / "units").iterdir() if u.is_dir() and (u / "card.toml").exists())
    pooled = pool_panels(units)
    print({k: (len(v), v["date"].min(), v["date"].max()) for k, v in pooled.items()})
    a.out.mkdir(parents=True, exist_ok=True)
    report = {}
    n_ok = 0
    for u in units:
        df, note = realized_for(u, pooled)
        if df is None:
            report[u.name] = {"ok": False, "why": note}
            print(f"--  {u.name:45s} {note}")
            continue
        df["asset"] = df["asset"].astype("string")
        df["horizon"] = df["horizon"].astype("int32")
        df.to_parquet(a.out / f"{u.name}.parquet", index=False)
        report[u.name] = {"ok": True, "cells": len(df), "note": note}
        n_ok += 1
        print(f"OK  {u.name:45s} {len(df)} cell(s) {note}")
    (a.out / "_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\n{n_ok}/{len(units)} units reconstructed -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
