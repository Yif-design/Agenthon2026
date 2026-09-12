"""Run the agent over every practice unit and push each output through the official smoke scorer.

    python scripts/run_all_units.py --repo ../starter-repos/track2-forecasting-public [--only F4] [--limit 5]

Writes runs/<unit>/forecast.* and runs/summary.csv; prints a pass/fail table.
Accuracy is NOT available locally (realized outcomes are sealed) — this checks admissibility
(g0–g3), runtime, and the shape of each distribution.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from t2agent.cardio import asof_from_card, load_card, read_panels  # noqa: E402
from t2agent.cli import main as forecast_main  # noqa: E402


def pit_stats(forecast: pathlib.Path, realized: pathlib.Path | None) -> dict:
    """Calibration diagnostics per cell: PIT of the realized value in our draws, and where it sits
    relative to our 1/5/95/99 % quantiles. Averaged over cells of the unit."""
    if realized is None or not realized.exists():
        return {}
    import pandas as pd
    f = pd.read_parquet(forecast)
    r = pd.read_parquet(realized)
    pits, below01, below05, above95, above99, zs = [], [], [], [], [], []
    for _, row in r.iterrows():
        x = f[(f["asset"] == row["asset"]) & (f["horizon"] == row["horizon"])]["value"].to_numpy()
        if len(x) == 0:
            continue
        y = float(row["value"])
        pits.append(float((x < y).mean()))
        q01, q05, q95, q99 = [float(v) for v in pd.Series(x).quantile([0.01, 0.05, 0.95, 0.99])]
        below01.append(y < q01); below05.append(y < q05); above95.append(y > q95); above99.append(y > q99)
        sd = float(x.std()) or 1e-12
        zs.append((y - float(x.mean())) / sd)
    if not pits:
        return {}
    n = len(pits)
    return {
        "pit_mean": round(sum(pits) / n, 3),
        "in50": round(sum(0.25 <= p_ <= 0.75 for p_ in pits) / n, 3),
        "in90": round(sum(0.05 <= p_ <= 0.95 for p_ in pits) / n, 3),
        "below01": round(sum(below01) / n, 3), "below05": round(sum(below05) / n, 3),
        "above95": round(sum(above95) / n, 3), "above99": round(sum(above99) / n, 3),
        "z_mean": round(sum(zs) / n, 3), "z_absmax": round(max(abs(z) for z in zs), 2),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=pathlib.Path, required=True, help="track2-forecasting-public checkout")
    p.add_argument("--runs", type=pathlib.Path, default=HERE.parent / "runs")
    p.add_argument("--only", default=None, help="substring filter on unit id (e.g. F4, ust, 2020)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--n-draws", type=int, default=2000)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--adjustments-dir", type=pathlib.Path, default=None,
                   help="dir of <unit_id>.json adjustment files (phase 3 dev); missing = neutral")
    p.add_argument("--no-text", action="store_true", help="text-ablated run (backbone only)")
    p.add_argument("--text-cache", type=pathlib.Path, default=None,
                   help="cache model outputs per unit here (default: <runs>/_textcache)")
    p.add_argument("--text-budget", type=float, default=240.0)
    p.add_argument("--realized-dir", type=pathlib.Path, default=None,
                   help="DEV: dir of <unit>.parquet realized outcomes (scripts/build_realized.py) -> real scores")
    p.add_argument("--baseline", action="store_true",
                   help="run the organizers' reference CLI (Gaussian random walk) instead of t2agent")
    a = p.parse_args()

    units_dir = a.repo / "units"
    scorer = a.repo / "scoring" / "scoring.py"
    units = sorted(u for u in units_dir.iterdir() if u.is_dir() and (u / "card.toml").exists())
    if a.only:
        units = [u for u in units if a.only.lower() in u.name.lower()]
    if a.limit:
        units = units[: a.limit]
    a.runs.mkdir(parents=True, exist_ok=True)

    rows = []
    for u in units:
        card = load_card(u / "card.toml")
        asof = asof_from_card(card, read_panels(u))
        out_dir = a.runs / u.name
        out_dir.mkdir(parents=True, exist_ok=True)
        argv = ["--panels", str(u), "--text", str(u / "text"), "--asof", asof,
                "--out", str(out_dir / "forecast.parquet"), "--n-draws", str(a.n_draws),
                "--seed", str(a.seed), "--info", str(a.runs / "_diag" / f"{u.name}.json")]
        # NB: g0_integrity refuses an output dir holding anything but the three deliverables,
        # so diagnostics go to runs/_diag/, never next to forecast.parquet.
        adj = (a.adjustments_dir / f"{u.name}.json") if a.adjustments_dir else None
        if adj and adj.exists():
            argv += ["--adjustments", str(adj)]
        elif a.no_text:
            argv += ["--no-text"]
        else:
            argv += ["--text-cache", str(a.text_cache or (a.runs / "_textcache")), "--text-budget", str(a.text_budget)]
        if a.baseline:
            argv = ["--panels", str(u), "--text", str(u / "text"), "--asof", asof,
                    "--out", str(out_dir / "forecast.parquet"), "--n-draws", str(a.n_draws), "--seed", str(a.seed)]
        t0 = time.time()
        err = ""
        try:
            if a.baseline:
                from qfbench2_track_forecasting.cli import main as reference_main
                reference_main(argv)
            else:
                forecast_main(argv)
        except SystemExit as exc:  # our own refusals
            err = f"agent: {exc}"
        except Exception as exc:  # noqa: BLE001
            err = f"agent crashed: {type(exc).__name__}: {exc}"
        elapsed = time.time() - t0

        verdict: dict = {}
        realized = (a.realized_dir / f"{u.name}.parquet") if a.realized_dir else None
        if not err:
            cmd = [sys.executable, str(scorer), "score", "--card", str(u / "card.toml"),
                   "--forecast", str(out_dir / "forecast.parquet")]
            if realized is not None and realized.exists():
                cmd += ["--realized", str(realized)]
            res = subprocess.run(cmd, capture_output=True, text=True)
            try:
                verdict = json.loads(res.stdout)
            except json.JSONDecodeError:
                err = f"scorer: {res.stderr.strip()[-300:] or res.stdout[-300:]}"
        text_info: dict = {}
        try:
            diag = json.loads((a.runs / "_diag" / f"{u.name}.json").read_text(encoding="utf-8"))
            ts = diag.get("text_stage") or {}
            usage = ts.get("usage") or {}
            text_info = {
                "text": ts.get("source", ""),
                "scenarios": len(diag.get("scenarios") or []),
                "docs_read": len(ts.get("cards") or []),
                "llm_calls": usage.get("calls", 0),
                "tokens_in": usage.get("prompt_tokens", 0),
                "tokens_out": usage.get("completion_tokens", 0),
                "llm_errors": len(usage.get("errors") or []),
            }
        except (OSError, json.JSONDecodeError):
            pass
        score_info: dict = {}
        if verdict.get("admissible") and "composite_score" in verdict:
            score_info = {k: verdict.get(k) for k in ("marginal_crps", "joint_variogram", "tail_penalty", "composite_score")}
            score_info.update(pit_stats(out_dir / "forecast.parquet", realized))
        tgt = card["targets"]
        row = {
            "unit": u.name,
            "family": card.get("metadata", {}).get("category", ""),
            "target": tgt.get("target_type"),
            "n_assets": len(tgt["asset_ids"]),
            "horizons": " ".join(str(h) for h in tgt["horizons"]),
            "asof": asof,
            "admissible": verdict.get("admissible", False),
            "gates": " ".join(f"{k[:2]}={'P' if v == 'pass' else 'F'}" for k, v in verdict.get("gates", {}).items()),
            "elapsed_s": round(elapsed, 1),
            **text_info,
            **score_info,
            "error": err or json.dumps(verdict.get("detail", ""))[:200] if not verdict.get("admissible") else "",
        }
        rows.append(row)
        flag = "OK " if row["admissible"] else "FAIL"
        sc = f" S={row['composite_score']:.4f} pit={row.get('pit_mean', float('nan')):.2f}" if "composite_score" in row else ""
        print(f"{flag} {u.name:45s} {row['family']:6s} {row['target']:10s} {row['elapsed_s']:6.1f}s "
              f"text={row.get('text', '-')}/{row.get('scenarios', '-')}sc/{row.get('docs_read', '-')}docs{sc} "
              f"{row['error']}")

    with (a.runs / "summary.csv").open("w", newline="") as fh:
        fields = list(dict.fromkeys(k for r in rows for k in r.keys()))
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    n_ok = sum(r["admissible"] for r in rows)
    print(f"\n{n_ok}/{len(rows)} admissible; mean {sum(r['elapsed_s'] for r in rows) / max(len(rows), 1):.1f}s per unit; "
          f"summary at {a.runs / 'summary.csv'}")
    return 0 if n_ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
