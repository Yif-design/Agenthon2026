"""Compare two run directories (e.g. text vs --no-text) unit by unit, using the engine ledgers.

    python scripts/compare_runs.py runs_text runs_notext

Prints, per unit and asset/horizon, how the text stage moved the centre (in horizon-sd units)
and rescaled the 5-95 % width, plus the scenarios it chose. No realized data is needed.
"""

from __future__ import annotations

import json
import pathlib
import sys


def load(runs: pathlib.Path) -> dict[str, dict]:
    out = {}
    for f in sorted((runs / "_diag").glob("*.json")):
        try:
            out[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return out


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    a, b = load(pathlib.Path(sys.argv[1])), load(pathlib.Path(sys.argv[2]))
    print(f"{'unit':44s} {'asset':8s} {'h':>4s} {'Δcentre/sd':>10s} {'width×':>7s}  scenarios")
    shifts, widths = [], []
    for unit in sorted(set(a) & set(b)):
        da, db = a[unit], b[unit]
        scen = ", ".join(f"{s['name']}({s['weight']:.2f})" for s in da.get("scenarios", []))
        for asset, xa in da["assets"].items():
            xb = db["assets"].get(asset)
            if not xb:
                continue
            for h, ha in xa["horizons"].items():
                hb = xb["horizons"].get(h) or xb["horizons"].get(str(h))
                if not hb:
                    continue
                wb = hb["q95"] - hb["q05"]
                wa = ha["q95"] - ha["q05"]
                sd_units = wb / 3.29 if wb > 0 else float("nan")   # 90 % interval ≈ 3.29 sd
                shift = (ha["q50"] - hb["q50"]) / sd_units if sd_units and sd_units == sd_units else float("nan")
                ratio = wa / wb if wb else float("nan")
                shifts.append(shift); widths.append(ratio)
                print(f"{unit:44s} {asset:8s} {str(h):>4s} {shift:>+10.2f} {ratio:>7.2f}  {scen}")
    if shifts:
        import statistics as st
        print(f"\n{len(shifts)} cells: mean |Δcentre| = {st.mean(abs(s) for s in shifts):.2f} sd, "
              f"median width× = {st.median(widths):.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
