#!/usr/bin/env python3
"""Build the two schema variants for proxy-18 from a frozen CFTC snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any


QUESTION_ID = "proxy-18-cot-positioning-rank"
AS_OF = date(2023, 9, 26)
NEXT_AS_OF = date(2023, 10, 3)
CUTOFF = date(2023, 9, 29)
RESOLUTION = date(2023, 10, 6)
SOURCE_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
LICENSE = "Public domain (U.S. Commodity Futures Trading Commission data)"
MARKETS = {
    "CORN_CBT": ("Corn futures", "agriculture"),
    "ES_SP500": ("E-mini S&P 500 futures", "equity"),
    "EURO_FX": ("Euro FX futures", "fx"),
    "GOLD_CMX": ("Gold futures", "metals"),
    "JPY_CME": ("Japanese yen futures", "fx"),
    "NATGAS_NYMEX": ("Henry Hub natural gas futures", "energy"),
    "SILVER_CMX": ("Silver futures", "metals"),
    "UST_10Y": ("U.S. Treasury 10-Year Note futures", "rates"),
    "UST_2Y": ("U.S. Treasury 2-Year Note futures", "rates"),
    "WTI_NYMEX": ("WTI crude oil futures", "energy"),
}


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_source_snapshot(raw_cache: Path, snapshot: Path) -> None:
    rows = json.loads(raw_cache.read_text())
    start = AS_OF - timedelta(days=182)
    selected = [
        row for row in rows
        if start.isoformat() <= str(row["report_date_as_yyyy_mm_dd"])[:10] <= NEXT_AS_OF.isoformat()
    ]
    reverse = {code: entity for entity, code in _codes(rows).items()}
    selected = [row for row in selected if row["cftc_contract_market_code"] in reverse]
    selected.sort(key=lambda row: (str(row["report_date_as_yyyy_mm_dd"]), row["cftc_contract_market_code"]))
    dump(snapshot, {
        "snapshot_version": "1.0.0",
        "source_url": SOURCE_URL,
        "source_raw_sha256": sha256(raw_cache),
        "retrieved_at": "2026-09-26",
        "license": LICENSE,
        "report_availability": {
            AS_OF.isoformat(): CUTOFF.isoformat(),
            NEXT_AS_OF.isoformat(): RESOLUTION.isoformat(),
        },
        "rows": selected,
    })


def _codes(rows: list[dict[str, Any]]) -> dict[str, str]:
    known = {
        "CORN_CBT": "002602", "ES_SP500": "13874A", "EURO_FX": "099741",
        "GOLD_CMX": "088691", "JPY_CME": "097741", "NATGAS_NYMEX": "023651",
        "SILVER_CMX": "084691", "UST_10Y": "043602", "UST_2Y": "042601",
        "WTI_NYMEX": "067651",
    }
    present = {str(row.get("cftc_contract_market_code")) for row in rows}
    missing = sorted(set(known.values()) - present)
    if missing:
        raise ValueError(f"source snapshot lacks market codes: {missing}")
    return known


def prepare(snapshot: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    code_to_entity = {code: entity for entity, code in _codes(snapshot["rows"]).items()}
    series: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in snapshot["rows"]:
        entity = code_to_entity.get(str(raw["cftc_contract_market_code"]))
        if entity is None:
            continue
        day = str(raw["report_date_as_yyyy_mm_dd"])[:10]
        oi = float(raw["open_interest_all"])
        long = float(raw["noncomm_positions_long_all"])
        short = float(raw["noncomm_positions_short_all"])
        net = long - short
        series[entity].append({
            "date": day, "open_interest": oi, "long": long, "short": short,
            "net": net, "net_pct_oi": 100.0 * net / oi,
        })
    prepared: list[dict[str, Any]] = []
    for entity_id in MARKETS:
        rows = sorted(series[entity_id], key=lambda row: row["date"])
        by_date = {row["date"]: row for row in rows}
        current = by_date[AS_OF.isoformat()]
        future = by_date[NEXT_AS_OF.isoformat()]
        prior = by_date[(AS_OF - timedelta(days=28)).isoformat()]
        visible = [row for row in rows if row["date"] <= AS_OF.isoformat()]
        historical_changes = [
            100.0 * (right["net"] - left["net"]) / left["open_interest"]
            for left, right in zip(visible, visible[1:], strict=False)
        ]
        abs_positions = sorted(abs(row["net_pct_oi"]) for row in visible)
        crowd_index = max(0, math.ceil(0.9 * len(abs_positions)) - 1)
        prepared.append({
            "entity_id": entity_id,
            "name": MARKETS[entity_id][0],
            "asset_class": MARKETS[entity_id][1],
            "market_code": _codes(snapshot["rows"])[entity_id],
            "current": current,
            "visible": visible,
            "current_net_pct_oi": current["net_pct_oi"],
            "trailing_4wk_net_change_pct_oi": 100.0 * (current["net"] - prior["net"]) / prior["open_interest"],
            "history_pstdev_pct_oi": statistics.pstdev(historical_changes),
            "crowded": abs(current["net_pct_oi"]) >= abs_positions[crowd_index],
            "truth": 100.0 * (future["net"] - current["net"]) / current["open_interest"],
            "naive_half_width": max(0.5, _quantile([abs(value) for value in historical_changes], 0.9)),
        })
    return series, prepared


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lo, hi = math.floor(position), math.ceil(position)
    return ordered[lo] if lo == hi else ordered[lo] * (hi - position) + ordered[hi] * (position - lo)


def task_for(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    entities = []
    source_rows = rows if variant == "explicit" else list(reversed(rows))
    for index, row in enumerate(source_rows):
        common = {
            "entity_id": row["entity_id"], "name": row["name"],
            "corpus_ref": f"corpus/{row['entity_id']}.json",
        }
        if variant == "explicit":
            common.update({
                "asset_class": row["asset_class"],
                "net_noncommercial_20230926": round(row["current"]["net"], 6),
                "open_interest_20230926": round(row["current"]["open_interest"], 6),
                "net_pct_oi_20230926": round(row["current_net_pct_oi"], 8),
                "trailing_4wk_net_change_pct_oi": round(row["trailing_4wk_net_change_pct_oi"], 8),
                "history_pstdev_pct_oi": round(row["history_pstdev_pct_oi"], 8),
                "crowded": row["crowded"], "unit": "percent_of_open_interest",
            })
        else:
            common.update({
                "group_code": row["asset_class"],
                "position_share_bp": round(100.0 * row["current_net_pct_oi"], 6),
                "recent_four_report_shift_fraction": round(row["trailing_4wk_net_change_pct_oi"] / 100.0, 10),
                "historical_variation_bp": round(100.0 * row["history_pstdev_pct_oi"], 6),
                "extreme_position_flag": row["crowded"],
                "measurement_scale": "basis_points_of_open_interest",
                "irrelevant_row_number": index + 101,
            })
        entities.append(common)
    explicit = variant == "explicit"
    return {
        "task_id": f"{QUESTION_ID}-20230926-{variant}",
        "schema_version": "3",
        "family": "cftc_positioning_proxy" if explicit else "relative_flow_ordering",
        "target": {
            "name": "net_positioning_change_pct_oi_rank" if explicit else "future_speculator_shift_order",
            "type": "ranking",
            "unit": "percent_of_start_open_interest",
            "direction": "descending",
            "horizon": "next CFTC report",
        },
        "prompt": (
            "Rank the ten futures markets by the next CFTC report's change in noncommercial net "
            "position, measured as a percent of the cutoff report's open interest. Rank 1 is the "
            "largest increase. Use only the frozen CFTC corpus and task fields; return a point "
            "forecast in percentage points and a 90% interval for every market."
        ),
        "cutoff_date": CUTOFF.isoformat(),
        "resolution_date": RESOLUTION.isoformat(),
        "interval_level": 0.9,
        "schema_variant": variant,
        "entities": entities,
    }


def corpus_document(row: dict[str, Any]) -> dict[str, Any]:
    lines = [
        f"CFTC legacy futures-only history for {row['name']} ({row['entity_id']}).",
        "report_as_of | open_interest | noncommercial_long | noncommercial_short | net | net_%OI",
    ]
    for item in row["visible"]:
        lines.append(
            f"{item['date']} | {item['open_interest']:.0f} | {item['long']:.0f} | "
            f"{item['short']:.0f} | {item['net']:.0f} | {item['net_pct_oi']:.6f}"
        )
    lines.append("The report contains Tuesday positions and is normally published by CFTC on Friday.")
    return {
        "doc_id": f"CFTC_{row['entity_id']}_20230929",
        "doc_date": CUTOFF.isoformat(),
        "entities": [row["entity_id"]],
        "source": "CFTC",
        "source_url": SOURCE_URL,
        "license": LICENSE,
        "text": "\n".join(lines),
    }


def answer(rows: list[dict[str, Any]], variant: str, *, truth: bool) -> dict[str, Any]:
    ordered = rows if variant == "explicit" else list(reversed(rows))
    values = [row["truth"] if truth else 0.0 for row in ordered]
    rank_order = sorted(range(len(values)), key=lambda i: (-values[i], ordered[i]["entity_id"]))
    ranks = {index: rank + 1 for rank, index in enumerate(rank_order)}
    predictions = []
    for index, row in enumerate(ordered):
        point = row["truth"] if truth else 0.0
        half = 0.000001 if truth else row["naive_half_width"]
        predictions.append({
            "entity_id": row["entity_id"], "point_forecast": point, "rank": ranks[index],
            "interval": {"lo": point - half, "hi": point + half, "level": 0.9},
            "claims": [{
                "doc_id": f"CFTC_{row['entity_id']}_20230929", "span_start": 0, "span_end": 1,
                "claim": "CFTC source.",
            }],
        })
    return {
        "task_id": f"{QUESTION_ID}-20230926-{variant}", "schema_version": "3",
        "target_type": "ranking", "entity_predictions": predictions,
        "notes": {"baseline_id": "perfect-reference" if truth else "zero-change-precutoff-90pct-absolute-move"},
    }


def outcome(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    ordered = rows if variant == "explicit" else list(reversed(rows))
    return {
        "task_id": f"{QUESTION_ID}-20230926-{variant}",
        "outcomes": [{"entity_id": row["entity_id"], "y": row["truth"]} for row in ordered],
    }


def card(variant: str) -> str:
    unit_id = f"{QUESTION_ID}-20230926-{variant}"
    family = "cftc_positioning_proxy" if variant == "explicit" else "relative_flow_ordering"
    return f'''schema_version = "2.0"

[task]
id = "{unit_id}"
track = "analysis"
title = "Next-report COT positioning-change ranking ({variant})"
split = "time_forward_test"
family = "{family}"
target_type = "ranking"
cutoff_date = "{CUTOFF.isoformat()}"
resolution_date = "{RESOLUTION.isoformat()}"

[provenance]
license = "{LICENSE}"
data_source = "{SOURCE_URL}"
data_cutoff = "{CUTOFF.isoformat()}"
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


def build_unit(root: Path, rows: list[dict[str, Any]], snapshot_path: Path, variant: str) -> None:
    unit = root / f"{QUESTION_ID}-20230926-{variant}"
    if unit.exists():
        shutil.rmtree(unit)
    (unit / "corpus").mkdir(parents=True)
    dump(unit / "task.json", task_for(rows, variant))
    (unit / "card.toml").write_text(card(variant))
    for row in rows:
        dump(unit / "corpus" / f"{row['entity_id']}.json", corpus_document(row))
    dump(unit / "reference" / "outcome.json", outcome(rows, variant))
    dump(unit / "reference" / "naive_answer.json", answer(rows, variant, truth=False))
    dump(unit / "provenance.json", {
        "question_id": QUESTION_ID, "variant": variant, "split": "time_forward_test",
        "source_url": SOURCE_URL, "source_snapshot": str(snapshot_path),
        "source_snapshot_sha256": sha256(snapshot_path), "source_raw_sha256": json.loads(snapshot_path.read_text())["source_raw_sha256"],
        "download_date": "2026-09-26", "cutoff_date": CUTOFF.isoformat(),
        "resolution_date": RESOLUTION.isoformat(), "license": LICENSE,
        "availability": {"cutoff_report_public": CUTOFF.isoformat(), "outcome_report_public": RESOLUTION.isoformat()},
        "generator": "proxy-benchmark/build_cot_proxy.py", "generator_version": "1.0.0",
    })
    files = []
    for path in sorted(p for p in unit.rglob("*") if p.is_file() and p.name != "manifest.json"):
        files.append({"path": path.relative_to(unit).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)})
    dump(unit / "manifest.json", {"manifest_version": "1.0", "unit_id": unit.name, "files": files})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=Path("proxy-benchmark/sources/proxy-18-cot-2023.json"))
    parser.add_argument("--raw-cache", type=Path)
    parser.add_argument("--units", type=Path, default=Path("proxy-benchmark/units"))
    args = parser.parse_args()
    if args.raw_cache:
        build_source_snapshot(args.raw_cache, args.snapshot)
    snapshot = json.loads(args.snapshot.read_text())
    _, rows = prepare(snapshot)
    for variant in ("explicit", "transformed"):
        build_unit(args.units, rows, args.snapshot, variant)
    print(json.dumps({"question": QUESTION_ID, "variants": 2, "entities": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
