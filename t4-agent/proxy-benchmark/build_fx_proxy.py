#!/usr/bin/env python3
"""Build proxy-19 forward FX realized-volatility ranking variants."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import shutil
import statistics
from pathlib import Path
from typing import Any
from urllib.request import urlopen


QUESTION_ID = "proxy-19-fx-volatility-rank"
CUTOFF = "2023-09-29"
RETRIEVED_AT = "2026-10-03"
SOURCE_ROOT = "https://fred.stlouisfed.org/graph/fredgraph.csv"
LICENSE = "Federal Reserve Board H.10 exchange-rate data; U.S. government source"
SERIES = (
    ("DEXUSEU", "Euro", "USD per EUR"),
    ("DEXJPUS", "Japanese yen", "JPY per USD"),
    ("DEXUSUK", "British pound", "USD per GBP"),
    ("DEXCAUS", "Canadian dollar", "CAD per USD"),
    ("DEXCHUS", "Chinese yuan", "CNY per USD"),
    ("DEXKOUS", "South Korean won", "KRW per USD"),
    ("DEXMXUS", "Mexican peso", "MXN per USD"),
    ("DEXBZUS", "Brazilian real", "BRL per USD"),
    ("DEXINUS", "Indian rupee", "INR per USD"),
    ("DEXSFUS", "South African rand", "ZAR per USD"),
)


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _download(series_id: str) -> tuple[str, str, list[dict[str, Any]]]:
    url = f"{SOURCE_ROOT}?id={series_id}&cosd=2023-01-01&coed=2023-11-30"
    raw = urlopen(url, timeout=30).read()
    rows = []
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8"))):
        value = row[series_id]
        if value not in ("", "."):
            rows.append({"date": row["observation_date"], "value": float(value)})
    return url, hashlib.sha256(raw).hexdigest(), rows


def build_source_snapshot(snapshot: Path) -> None:
    rows = []
    for series_id, name, convention in SERIES:
        url, raw_sha, observations = _download(series_id)
        rows.append({
            "series_id": series_id,
            "name": name,
            "quote_convention": convention,
            "source_url": url,
            "source_raw_sha256": raw_sha,
            "observations": observations,
        })
    common = set.intersection(*({row["date"] for row in item["observations"]} for item in rows))
    future = sorted(day for day in common if day > CUTOFF)
    if len(future) < 20:
        raise ValueError("fewer than 20 common post-cutoff observations")
    dump(snapshot, {
        "snapshot_version": "1.0.0",
        "retrieved_at": RETRIEVED_AT,
        "license": LICENSE,
        "cutoff_date": CUTOFF,
        "resolution_date": future[19],
        "horizon": "next 20 common eligible daily returns",
        "rows": rows,
    })


def _vol(values: list[float]) -> float:
    returns = [math.log(right / left) for left, right in zip(values, values[1:])]
    return 100.0 * math.sqrt(252.0) * statistics.pstdev(returns)


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lo, hi = math.floor(position), math.ceil(position)
    return ordered[lo] if lo == hi else ordered[lo] * (hi - position) + ordered[hi] * (position - lo)


def prepare(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    common = set.intersection(*({row["date"] for row in item["observations"]} for item in snapshot["rows"]))
    visible_dates = sorted(day for day in common if day <= CUTOFF)
    future_dates = sorted(day for day in common if day > CUTOFF)[:20]
    if len(visible_dates) < 81 or len(future_dates) != 20:
        raise ValueError("insufficient common FX history")
    result = []
    for source in snapshot["rows"]:
        by_date = {row["date"]: row["value"] for row in source["observations"]}
        visible = [{"date": day, "value": by_date[day]} for day in visible_dates[-81:]]
        visible_values = [row["value"] for row in visible]
        forward_values = [visible_values[-1], *(by_date[day] for day in future_dates)]
        trailing_vol = _vol(visible_values[-21:])
        rolling = [_vol(visible_values[index - 20:index + 1]) for index in range(20, len(visible_values))]
        half = max(0.5, _quantile([abs(value - trailing_vol) for value in rolling], 0.9))
        result.append({
            "entity_id": f"FX_{source['series_id']}_20230929",
            "series_id": source["series_id"],
            "name": source["name"],
            "quote_convention": source["quote_convention"],
            "visible": visible,
            "trailing_20d_vol_pct": trailing_vol,
            "trailing_60d_vol_pct": _vol(visible_values[-61:]),
            "truth": _vol(forward_values),
            "naive_half_width": half,
        })
    return result


def task_for(rows: list[dict[str, Any]], variant: str, resolution: str) -> dict[str, Any]:
    explicit = variant == "explicit"
    ordered = rows if explicit else list(reversed(rows))
    entities = []
    for index, row in enumerate(ordered):
        entity = {
            "entity_id": row["entity_id"],
            "name": row["name"],
            "corpus_ref": f"corpus/{row['entity_id']}.json",
        }
        if explicit:
            entity.update({
                "fred_series_id": row["series_id"],
                "quote_convention": row["quote_convention"],
                "last_exchange_rate": row["visible"][-1]["value"],
                "trailing_20d_annualized_volatility_pct": row["trailing_20d_vol_pct"],
                "trailing_60d_annualized_volatility_pct": row["trailing_60d_vol_pct"],
            })
        else:
            entity.update({
                "market_key": f"XR-{index + 71}",
                "reciprocal_terminal_quote": 1.0 / row["visible"][-1]["value"],
                "short_window_sigma_fraction": row["trailing_20d_vol_pct"] / 100.0,
                "long_window_sigma_fraction": row["trailing_60d_vol_pct"] / 100.0,
                "quote_transform": "reciprocal_of_published_series",
                "volatility_scale": "annualized_fraction",
            })
        entities.append(entity)
    return {
        "task_id": f"{QUESTION_ID}-20230929-{variant}",
        "schema_version": "3",
        "family": "fx_realized_volatility" if explicit else "relative_market_variation",
        "target": {
            "name": "forward_20d_annualized_volatility_pct_rank" if explicit else "next_window_sigma_order",
            "type": "ranking", "unit": "annualized_percent", "direction": "descending",
            "horizon": "next 20 common eligible daily returns",
        },
        "prompt": (
            "Rank currencies by annualized realized volatility over the next 20 common eligible daily returns. "
            "Rank 1 is highest volatility. Quote inversion does not change log-return volatility. Return an "
            "annualized-percent point forecast and 90% interval for each row."
        ),
        "cutoff_date": CUTOFF,
        "resolution_date": resolution,
        "interval_level": 0.9,
        "schema_variant": variant,
        "entities": entities,
    }


def corpus_document(row: dict[str, Any], variant: str) -> dict[str, Any]:
    inverse = variant == "transformed"
    lines = [
        f"Federal Reserve H.10 exchange-rate history for {row['name']} ({row['series_id']}).",
        f"Published quote convention: {row['quote_convention']}.",
        "date | exchange_rate" if not inverse else "date | reciprocal_exchange_rate",
    ]
    for item in row["visible"]:
        value = 1.0 / item["value"] if inverse else item["value"]
        lines.append(f"{item['date']} | {value:.10f}")
    return {
        "doc_id": f"FRED_{row['series_id']}_20230929_{variant}",
        "doc_date": CUTOFF,
        "entities": [row["entity_id"]],
        "source": "Federal Reserve Board H.10 via FRED",
        "source_url": SOURCE_ROOT,
        "license": LICENSE,
        "text": "\n".join(lines),
    }


def naive_answer(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    ordered = rows if variant == "explicit" else list(reversed(rows))
    order = sorted(range(len(ordered)), key=lambda i: (-ordered[i]["trailing_20d_vol_pct"], ordered[i]["entity_id"]))
    ranks = {index: rank + 1 for rank, index in enumerate(order)}
    predictions = []
    for index, row in enumerate(ordered):
        point, half = row["trailing_20d_vol_pct"], row["naive_half_width"]
        predictions.append({
            "entity_id": row["entity_id"], "point_forecast": point, "rank": ranks[index],
            "interval": {"lo": max(0.0, point - half), "hi": point + half, "level": 0.9},
            "claims": [{
                "doc_id": f"FRED_{row['series_id']}_20230929_{variant}",
                "span_start": 0, "span_end": 1, "claim": "Federal Reserve source.",
            }],
        })
    return {
        "task_id": f"{QUESTION_ID}-20230929-{variant}", "schema_version": "3",
        "target_type": "ranking", "entity_predictions": predictions,
        "notes": {"baseline_id": "trailing-20-common-day-realized-volatility"},
    }


def outcome(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    ordered = rows if variant == "explicit" else list(reversed(rows))
    return {"task_id": f"{QUESTION_ID}-20230929-{variant}",
            "outcomes": [{"entity_id": row["entity_id"], "y": row["truth"]} for row in ordered]}


def card(variant: str, resolution: str) -> str:
    unit_id = f"{QUESTION_ID}-20230929-{variant}"
    family = "fx_realized_volatility" if variant == "explicit" else "relative_market_variation"
    return f'''schema_version = "2.0"

[task]
id = "{unit_id}"
track = "analysis"
title = "Forward FX realized-volatility ranking ({variant})"
split = "time_forward_test"
family = "{family}"
target_type = "ranking"
cutoff_date = "{CUTOFF}"
resolution_date = "{resolution}"

[provenance]
license = "{LICENSE}"
data_source = "{SOURCE_ROOT}"
data_cutoff = "{CUTOFF}"
redistributable = true
manifest = "manifest.json"

[scoring]
verifier = "t4.faithful_analysis"
metric = "analysis_composite"
admissibility_gates = ["g0_integrity", "g1_schema", "g2_cutoff_resource", "g3_domain_semantics"]

[scoring.params]
faithfulness_threshold = 0.80
interval_level = 0.90
target_type = "ranking"
composite_weights = [0.7, 0.3]
tau_citation = 0.5

[agent]
timeout_sec = 600.0
'''


def build_unit(root: Path, rows: list[dict[str, Any]], snapshot_path: Path, variant: str, resolution: str) -> None:
    unit = root / f"{QUESTION_ID}-20230929-{variant}"
    if unit.exists():
        shutil.rmtree(unit)
    (unit / "corpus").mkdir(parents=True)
    dump(unit / "task.json", task_for(rows, variant, resolution))
    (unit / "card.toml").write_text(card(variant, resolution))
    for row in rows:
        dump(unit / "corpus" / f"{row['entity_id']}.json", corpus_document(row, variant))
    dump(unit / "reference/outcome.json", outcome(rows, variant))
    dump(unit / "reference/naive_answer.json", naive_answer(rows, variant))
    snapshot = json.loads(snapshot_path.read_text())
    dump(unit / "provenance.json", {
        "question_id": QUESTION_ID, "variant": variant, "split": "time_forward_test",
        "source_urls": [row["source_url"] for row in snapshot["rows"]],
        "source_raw_sha256": {row["series_id"]: row["source_raw_sha256"] for row in snapshot["rows"]},
        "source_snapshot": str(snapshot_path), "source_snapshot_sha256": sha256(snapshot_path),
        "download_date": snapshot["retrieved_at"], "cutoff_date": CUTOFF,
        "resolution_date": resolution, "license": LICENSE,
        "generator": "proxy-benchmark/build_fx_proxy.py", "generator_version": "1.0.0",
    })
    files = []
    for path in sorted(p for p in unit.rglob("*") if p.is_file() and p.name != "manifest.json"):
        files.append({"path": path.relative_to(unit).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)})
    dump(unit / "manifest.json", {"manifest_version": "1.0", "unit_id": unit.name, "files": files})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=Path("proxy-benchmark/sources/proxy-19-fx-2023.json"))
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--units", type=Path, default=Path("proxy-benchmark/units"))
    args = parser.parse_args()
    if args.fetch:
        build_source_snapshot(args.snapshot)
    snapshot = json.loads(args.snapshot.read_text())
    rows = prepare(snapshot)
    for variant in ("explicit", "transformed"):
        build_unit(args.units, rows, args.snapshot, variant, snapshot["resolution_date"])
    print(json.dumps({"question": QUESTION_ID, "variants": 2, "entities": len(rows),
                      "resolution_date": snapshot["resolution_date"]}, indent=2))


if __name__ == "__main__":
    main()
