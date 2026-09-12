"""The `forecast` verb.

    forecast --panels /input/panels --text /input/text --asof YYYY-MM-DD --out /output/forecast.parquet

Writes forecast.parquet, forecast_meta.json and forecast_rationale.md next to --out.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time

import numpy as np
import pandas as pd

from . import __version__
from .cardio import load_unit
from .engine import build_draws
from .knobs import Adjustments
from .rationale import write_rationale

DEFAULT_DRAWS = 2000
MAX_DRAWS = 20_000          # contract ceiling (qfbench2_track_forecasting.limits.ParseLimits)
RATIONALE = "forecast_rationale.md"


def get_adjustments(unit, asof: str, args: argparse.Namespace) -> tuple[Adjustments, dict]:
    """Build Adjustments for this unit.

    Precedence: an explicit --adjustments JSON file (dev/testing) > --no-text / T2_TEXT=off
    (neutral backbone, used for the text-ablated run) > the LLM text stage.
    """
    if args.adjustments:
        data = json.loads(pathlib.Path(args.adjustments).read_text(encoding="utf-8"))
        from .knobs import Scenario
        adj = Adjustments(
            scenarios=[Scenario(**s) for s in data["scenarios"]],
            tail_df=data.get("tail_df"),
            notes=data.get("notes", []),
        )
        return adj, {"source": "file", "path": str(args.adjustments)}
    if args.no_text or os.environ.get("T2_TEXT", "").lower() in ("off", "0", "false"):
        adj = Adjustments.neutral()
        adj.notes = ["text stage disabled (ablation run): no document was read"]
        return adj, {"source": "disabled"}
    from .textstage import run_text_stage
    adj, diag = run_text_stage(
        unit, asof,
        cache_dir=pathlib.Path(args.text_cache) if args.text_cache else None,
        time_budget_s=args.text_budget,
    )
    diag["source"] = "llm"
    return adj, diag


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="forecast", description=f"Agenthon 2026 Track 2 agent v{__version__}")
    p.add_argument("--panels", type=pathlib.Path, required=True)
    p.add_argument("--text", type=pathlib.Path, required=True)
    p.add_argument("--asof", required=True)
    p.add_argument("--out", type=pathlib.Path, required=True, help="path to forecast.parquet")
    p.add_argument("--card", type=pathlib.Path, default=None, help="card.toml (default: <panels>/card.toml or parent)")
    p.add_argument("--n-draws", type=int, default=DEFAULT_DRAWS)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--adjustments", default=None, help="JSON file with scenarios (dev/testing hook)")
    p.add_argument("--info", default=None, help="write the engine ledger as JSON to this path (diagnostics)")
    p.add_argument("--no-text", action="store_true", help="skip the LLM text stage (text-ablated backbone run)")
    p.add_argument("--text-cache", default=None, help="dir to cache model outputs per unit (dev only)")
    p.add_argument("--text-budget", type=float, default=240.0, help="seconds allowed for the text stage")
    a = p.parse_args(argv)

    t0 = time.time()
    unit = load_unit(a.panels, a.text, a.card)
    n_draws = min(max(a.n_draws, unit.n_draws_min, 200), MAX_DRAWS)

    adj, text_diag = get_adjustments(unit, a.asof, a)
    samples, info = build_draws(unit, a.asof, n_draws, a.seed, adj)
    info["text_stage"] = text_diag

    if not np.isfinite(samples).all():
        raise SystemExit("non-finite values in draws; refusing to write")

    out_dir = a.out.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    n_a, n_h = len(unit.assets), len(unit.horizons)
    draw_idx = np.repeat(np.arange(n_draws, dtype=np.int32), n_a * n_h)
    asset_col = np.tile(np.repeat(np.array(unit.assets, dtype=object), n_h), n_draws)
    horizon_col = np.tile(np.array(unit.horizons, dtype=np.int32), n_draws * n_a)
    df = pd.DataFrame(
        {
            "draw": draw_idx,
            "asset": pd.array(asset_col, dtype="string"),
            "horizon": horizon_col,
            "value": samples.reshape(-1).astype(np.float64),
        }
    )
    df.to_parquet(a.out, index=False)

    meta = {
        "unit_id": unit.unit_id,
        "asof": a.asof,
        "representation": "samples",
        "asset_ids": unit.assets,
        "horizons": unit.horizons,
        "n_draws": int(n_draws),
        "target": unit.target_type,
        "rationale": {"file": RATIONALE, "method": f"t2agent v{__version__}: {info['mode']}, scenario mixture, text={text_diag.get('source')}"},
        "agent": {"version": __version__, "seed": a.seed, "elapsed_s": round(time.time() - t0, 2),
                  "text_source": text_diag.get("source"), "model": text_diag.get("model"),
                  "model_usage": text_diag.get("usage")},
    }
    (out_dir / "forecast_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    (out_dir / RATIONALE).write_text(write_rationale(unit, a.asof, n_draws, info), encoding="utf-8")
    if a.info:  # diagnostics only; g0_integrity refuses extra files next to forecast.parquet
        if pathlib.Path(a.info).resolve().parent == out_dir.resolve():
            raise SystemExit("--info must not point inside the output directory (g0_integrity)")
        pathlib.Path(a.info).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(a.info).write_text(json.dumps(info, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"wrote {a.out.name}, forecast_meta.json and {RATIONALE} to {out_dir}")
    u = text_diag.get("usage") or {}
    print(f"  {n_a} asset(s) x {n_h} horizon(s), {n_draws} draws, {info['mode']}, text={text_diag.get('source')}"
          f" ({u.get('calls', 0)} calls, {u.get('prompt_tokens', 0)}+{u.get('completion_tokens', 0)} tok), "
          f"{len(adj.scenarios)} scenario(s), {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
