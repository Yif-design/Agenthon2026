"""Reading a Track 2 unit: card.toml, panels, text corpus index.

Everything here is *input* handling. No modelling.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

try:  # 3.11+
    import tomllib
except ModuleNotFoundError:  # 3.10
    import tomli as tomllib  # type: ignore[no-redef]


_ASSET_COLS = ("asset", "asset_id")


@dataclass
class Unit:
    card_path: pathlib.Path
    card: dict[str, Any]
    unit_id: str
    family: str
    assets: list[str]
    horizons: list[int]
    target_type: str            # "level" | "log_return"
    value_unit: str
    n_draws_min: int
    panels: dict[str, pd.DataFrame]          # panel stem -> long dataframe
    panel_meta: dict[str, dict[str, Any]]    # card [panels.<id>] tables
    text_dir: pathlib.Path | None
    docs: list[dict[str, Any]] = field(default_factory=list)

    @property
    def unit_dir(self) -> pathlib.Path:
        return self.card_path.parent


def load_card(path: pathlib.Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def find_card(panels_dir: pathlib.Path, explicit: pathlib.Path | None = None) -> pathlib.Path:
    if explicit is not None:
        if not explicit.exists():
            raise SystemExit(f"--card {explicit} does not exist")
        return explicit
    for cand in (panels_dir / "card.toml", panels_dir.parent / "card.toml"):
        if cand.exists():
            return cand
    raise SystemExit(f"card.toml not found in {panels_dir} or {panels_dir.parent}; pass --card")


def read_panels(panels_dir: pathlib.Path) -> dict[str, pd.DataFrame]:
    """Every parquet under --panels; tolerate the exemplar layout (panels at the unit root)."""
    found = sorted(panels_dir.glob("*.parquet"))
    if not found and panels_dir.parent.is_dir():
        found = sorted(panels_dir.parent.glob("*.parquet"))
    if not found:
        raise SystemExit(f"no .parquet found under {panels_dir} (or its parent)")
    out: dict[str, pd.DataFrame] = {}
    for p in found:
        df = pd.read_parquet(p)
        col = next((c for c in _ASSET_COLS if c in df.columns), None)
        if col is None or "date" not in df.columns or "value" not in df.columns:
            continue
        df = df.rename(columns={col: "asset"})
        df["asset"] = df["asset"].astype(str)
        df["date"] = df["date"].astype(str).str.slice(0, 10)
        out[p.stem] = df[["date", "asset", "value"] + [c for c in df.columns if c == "panel_id"]]
    if not out:
        raise SystemExit("no parquet with (date, asset|asset_id, value) columns found")
    return out


def read_text_index(text_dir: pathlib.Path | None) -> list[dict[str, Any]]:
    """Document list from corpus_index.json, falling back to the .txt files present."""
    if text_dir is None or not text_dir.is_dir():
        return []
    idx = text_dir / "corpus_index.json"
    if idx.exists():
        try:
            data = json.loads(idx.read_text(encoding="utf-8"))
            docs = data.get("documents", data if isinstance(data, list) else [])
            return [d for d in docs if isinstance(d, dict)]
        except (json.JSONDecodeError, AttributeError):
            pass
    return [{"doc_id": p.stem, "file": p.name} for p in sorted(text_dir.glob("*.txt"))]


def load_unit(
    panels_dir: pathlib.Path,
    text_dir: pathlib.Path | None,
    card_path: pathlib.Path | None = None,
) -> Unit:
    card_path = find_card(panels_dir, card_path)
    card = load_card(card_path)
    tgt = card["targets"]
    scoring_params = card.get("scoring", {}).get("params", {}) or {}
    n_min = int(tgt.get("n_draws_min") or scoring_params.get("n_draws_min") or 200)
    panels_tbl = card.get("panels", {}) or {}
    panel_meta = {k: v for k, v in panels_tbl.items() if isinstance(v, dict)}
    return Unit(
        card_path=card_path,
        card=card,
        unit_id=str(card["task"]["id"]),
        family=str(card.get("metadata", {}).get("category", "")),
        assets=[str(a) for a in tgt["asset_ids"]],
        horizons=[int(h) for h in tgt["horizons"]],
        target_type=str(tgt.get("target_type", "level")),
        value_unit=str(tgt.get("value_unit", "")),
        n_draws_min=n_min,
        panels=read_panels(panels_dir),
        panel_meta=panel_meta,
        text_dir=text_dir,
        docs=read_text_index(text_dir),
    )


def asof_from_card(card: dict[str, Any], panels: dict[str, pd.DataFrame]) -> str:
    """The as-of the harness will pass: provenance.data_cutoff, else the latest panel date."""
    asof = card.get("provenance", {}).get("data_cutoff")
    if asof:
        return str(asof)[:10]
    return max(df["date"].max() for df in panels.values())


def series_for(unit: Unit, asset: str, asof: str) -> tuple[pd.Series, str, str]:
    """History of one asset up to the as-of.

    Returns (series indexed by ISO date, panel stem it came from, declared frequency).
    Prefers the panel that the card's [panels.*] table lists the asset under.
    """
    preferred: list[str] = []
    for pid, meta in unit.panel_meta.items():
        if asset in [str(a) for a in meta.get("asset_ids", [])]:
            preferred.append(pid)
    order = preferred + [k for k in unit.panels if k not in preferred]
    for stem in order:
        df = unit.panels.get(stem)
        if df is None:
            continue
        sub = df[(df["asset"] == asset) & (df["date"] <= asof)].sort_values("date")
        if sub.empty:
            continue
        s = sub.set_index("date")["value"].astype(float)
        s = s[~s.index.duplicated(keep="last")]
        freq = str(unit.panel_meta.get(stem, {}).get("frequency", "")) or _infer_freq(s)
        return s, stem, freq
    seen = sorted({a for df in unit.panels.values() for a in df["asset"].unique()})
    raise SystemExit(f"asset {asset!r} not in any panel at or before {asof}; panels carry {seen}")


def _infer_freq(s: pd.Series) -> str:
    d = pd.to_datetime(pd.Series(s.index)).diff().dt.days.median()
    if pd.isna(d):
        return "business_daily"
    return "monthly" if d >= 20 else "business_daily"
