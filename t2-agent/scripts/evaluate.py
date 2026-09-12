"""DEV — compare run summaries the way the leaderboard would: per-card ratio to a reference.

    python scripts/evaluate.py runs_baseline/summary.csv runs_notext/summary.csv [runs_text/summary.csv ...]

The first summary is the reference (ideally the organizers' Gaussian random walk, `--baseline`).
For every other run, each card's composite is divided by the reference card's composite (the
leaderboard divides by the organizers' text-blind baseline the same way; 1.0 = no better), and the
equal-weight mean over cards is the headline. Calibration is reported from the PIT columns.
"""

from __future__ import annotations

import csv
import math
import pathlib
import statistics as st
import sys


def load(path: str) -> dict[str, dict]:
    rows = {}
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("composite_score"):
                rows[r["unit"]] = r
    return rows


def f(x: str | None) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return math.nan


def summarize(name: str, rows: dict[str, dict], ref: dict[str, dict]) -> None:
    common = sorted(set(rows) & set(ref))
    ratios, by_family, by_target = [], {}, {}
    for u in common:
        r, b = f(rows[u]["composite_score"]), f(ref[u]["composite_score"])
        if not (b > 0):
            continue
        ratio = min(r / b, 4.0)
        ratios.append(ratio)
        by_family.setdefault(rows[u]["family"], []).append(ratio)
        by_target.setdefault(rows[u]["target"], []).append(ratio)
    if not ratios:
        print(f"{name}: no scored cards in common with the reference")
        return
    print(f"\n== {name}  ({len(ratios)} cards vs reference)")
    print(f"   mean ratio {st.mean(ratios):.3f}   median {st.median(ratios):.3f}   "
          f"cards better than ref {sum(x < 1 for x in ratios)}/{len(ratios)}   worst {max(ratios):.2f}")
    for k, v in sorted(by_family.items()):
        print(f"   {k:6s} n={len(v):3d} mean {st.mean(v):.3f}")
    for k, v in sorted(by_target.items()):
        print(f"   {k:10s} n={len(v):3d} mean {st.mean(v):.3f}")
    # calibration over all cards (cell-weighted approx by unit mean)
    def m(col: str) -> float:
        vals = [f(rows[u].get(col)) for u in rows if rows[u].get(col)]
        vals = [v for v in vals if not math.isnan(v)]
        return st.mean(vals) if vals else math.nan
    print(f"   calibration: in50 {m('in50'):.2f} (ideal .50)  in90 {m('in90'):.2f} (.90)  "
          f"below05 {m('below05'):.2f} (.05)  above95 {m('above95'):.2f} (.05)  "
          f"below01 {m('below01'):.3f} (.01)  above99 {m('above99'):.3f} (.01)  z_mean {m('z_mean'):+.2f}")
    raw = [f(rows[u]["marginal_crps"]) for u in rows]
    worst = sorted(((min(f(rows[u]['composite_score']) / f(ref[u]['composite_score']), 4.0), u) for u in common if f(ref[u]['composite_score']) > 0), reverse=True)[:6]
    print("   worst cards: " + ", ".join(f"{u} {r:.2f}" for r, u in worst))


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    ref = load(sys.argv[1])
    print(f"reference: {sys.argv[1]} ({len(ref)} scored cards)")
    for path in sys.argv[2:]:
        summarize(pathlib.Path(path).parent.name, load(path), ref)
    return 0


if __name__ == "__main__":
    sys.exit(main())
