#!/usr/bin/env python3
"""Build proxy-16 crude-inventory-change variants from frozen EIA weekly data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import statistics
from datetime import date, datetime
from pathlib import Path
from typing import Any


QUESTION_ID = "proxy-16-crude-inventory-change"
CUTOFF_RELEASE = date(2026, 9, 23)
CUTOFF_WEEK = date(2026, 9, 18)
TARGET_WEEK = date(2026, 9, 25)
RESOLUTION_RELEASE = date(2026, 9, 30)
LICENSE = "Public domain (U.S. Energy Information Administration data)"
SOURCE_URL = "https://www.eia.gov/petroleum/supply/weekly/"
ARCHIVE_URL = "https://www.eia.gov/petroleum/supply/weekly/archive/{year}/{release}/csv/table4.csv"
SERIES = (
    ("WCESTUS1", "US", "United States", 0, "Commercial (Excluding SPR)"),
    ("WCESTP11", "PADD1", "East Coast (PADD 1)", 1, "East Coast (PADD 1)"),
    ("WCESTP21", "PADD2", "Midwest (PADD 2)", 2, "Midwest (PADD 2)"),
    ("WCESTP31", "PADD3", "Gulf Coast (PADD 3)", 3, "Gulf Coast (PADD 3)"),
    ("WCESTP41", "PADD4", "Rocky Mountain (PADD 4)", 4, "Rocky Mountain (PADD 4)"),
    ("WCESTP51", "PADD5", "West Coast (PADD 5)", 5, "West Coast (PADD 5)"),
)


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_source_snapshot(raw_dir: Path, snapshot: Path) -> None:
    observations = {series: [] for series, *_ in SERIES}
    raw_sources = []
    for raw in sorted(raw_dir.glob("table4-*.csv")):
        release_token = raw.stem.removeprefix("table4-")
        release = date.fromisoformat(release_token.replace("_", "-"))
        with raw.open(newline="", encoding="utf-8-sig") as handle:
            table = list(csv.reader(handle))
        week = datetime.strptime(table[0][1], "%m/%d/%y").date()
        rows_by_name = {row[0]: row for row in table[1:] if row}
        for series, _code, _name, _padd, source_name in SERIES:
            source_row = rows_by_name.get(source_name)
            if source_row is None:
                raise ValueError(f"{raw.name} is missing {source_name}")
            observations[series].append({
                "week_ending": week.isoformat(),
                "release_date": release.isoformat(),
                "stock_million_barrels": float(source_row[1]),
                "change_million_barrels": float(source_row[3]),
                "source_sha256": sha256(raw),
            })
        raw_sources.append({
            "week_ending": week.isoformat(),
            "release_date": release.isoformat(),
            "url": ARCHIVE_URL.format(year=release.year, release=release_token),
            "sha256": sha256(raw),
            "bytes": raw.stat().st_size,
        })
    required_recent = {date(2025, 9, 26).toordinal() + 7 * index for index in range(52)}
    required_recent = {date.fromordinal(value).isoformat() for value in required_recent}
    required = required_recent | {"2021-10-01", "2022-09-30", "2023-09-29", "2024-09-27", TARGET_WEEK.isoformat()}
    available = {item["week_ending"] for item in raw_sources}
    if available != required:
        raise ValueError(f"archive weeks differ: missing={sorted(required - available)}, extra={sorted(available - required)}")
    rows = []
    for series, code, name, padd_number, _source_name in SERIES:
        series_observations = sorted(observations[series], key=lambda row: row["week_ending"])
        if len(series_observations) != len(required):
            raise ValueError(f"{series} has {len(series_observations)} archive observations")
        rows.append({
            "series_id": series,
            "region_code": code,
            "region_name": name,
            "padd_number": padd_number,
            "observations": series_observations,
        })
    dump(snapshot, {
        "snapshot_version": "1.0.0",
        "retrieved_at": "2026-10-03",
        "license": LICENSE,
        "units": "million barrels",
        "definition": "Weekly ending stocks excluding SPR of commercial crude oil",
        "cutoff_release_date": CUTOFF_RELEASE.isoformat(),
        "cutoff_week_ending": CUTOFF_WEEK.isoformat(),
        "target_week_ending": TARGET_WEEK.isoformat(),
        "resolution_release_date": RESOLUTION_RELEASE.isoformat(),
        "raw_sources": raw_sources,
        "rows": rows,
    })


def prepare(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    prepared = []
    for source in snapshot["rows"]:
        observations = sorted(source["observations"], key=lambda row: row["week_ending"])
        by_date = {date.fromisoformat(row["week_ending"]): row for row in observations}
        if CUTOFF_WEEK not in by_date or TARGET_WEEK not in by_date:
            raise ValueError(f"missing cutoff or target observation for {source['series_id']}")
        visible = [
            row for row in observations
            if date(2025, 9, 26) <= date.fromisoformat(row["week_ending"]) <= CUTOFF_WEEK
        ]
        if len(visible) != 52:
            raise ValueError(f"{source['series_id']} has {len(visible)} visible releases, expected 52")
        target_iso_week = TARGET_WEEK.isocalendar().week
        seasonal = [
            float(row["change_million_barrels"])
            for row in observations
            if 2021 <= date.fromisoformat(row["week_ending"]).year <= 2025
            and date.fromisoformat(row["week_ending"]).isocalendar().week == target_iso_week
        ]
        if len(seasonal) != 5:
            raise ValueError(f"{source['series_id']} has {len(seasonal)} seasonal peers, expected 5")
        recent_changes = [float(row["change_million_barrels"]) for row in visible]
        truth = float(by_date[TARGET_WEEK]["change_million_barrels"])
        naive_point = statistics.fmean(seasonal)
        naive_half = max(0.10, 1.65 * statistics.pstdev(seasonal))
        prepared.append({
            **{key: source[key] for key in ("series_id", "region_code", "region_name", "padd_number")},
            "entity_id": f"EIA_CRUDE_{source['region_code']}_20260925",
            "visible": visible,
            "recent_changes": recent_changes,
            "seasonal_changes": seasonal,
            "truth": truth,
            "naive_point": naive_point,
            "naive_half_width": naive_half,
        })
    return prepared


def task_for(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    explicit = variant == "explicit"
    ordered = rows if explicit else list(reversed(rows))
    entities = []
    for index, row in enumerate(ordered):
        latest_level = float(row["visible"][-1]["stock_million_barrels"])
        latest_change = row["recent_changes"][-1]
        entity = {
            "entity_id": row["entity_id"],
            "name": row["region_name"],
            "corpus_ref": f"corpus/{row['entity_id']}.json",
        }
        if explicit:
            entity.update({
                "region": row["region_code"],
                "padd_number": row["padd_number"],
                "latest_stock_mmbbl": latest_level,
                "last_week_change_mmbbl": latest_change,
                "seasonal_change_mean_mmbbl": row["naive_point"],
                "unit": "million_barrels_change",
            })
        else:
            entity.update({
                "area_code": f"R{row['padd_number']}" if row["padd_number"] else "NAT",
                "terminal_volume_kb": latest_level * 1000.0,
                "one_period_flow_kb": latest_change * 1000.0,
                "week_39_norm_kb": row["naive_point"] * 1000.0,
                "display_scale": "thousand_barrels",
                "irrelevant_product_code": f"EPC{index + 7}",
            })
        entities.append(entity)
    return {
        "task_id": f"{QUESTION_ID}-20260923-{variant}",
        "schema_version": "3",
        "family": "energy_inventory_change" if explicit else "petroleum_balance_shift",
        "target": {
            "name": "weekly_crude_inventory_change_mmbbl" if explicit else "commercial_crude_stock_delta_million_barrels",
            "type": "regression",
            "unit": "million_barrels_change",
            "horizon": "next EIA weekly petroleum release",
            "definition": "target-week commercial crude stock minus the prior-week stock, excluding SPR",
        },
        "prompt": (
            "Forecast the next weekly change in commercial crude-oil inventories excluding the Strategic Petroleum Reserve "
            "for the United States and each listed PADD region. A positive value is a stock build and a negative value is "
            "a draw. Use only information public with the EIA release on 2026-09-23 and return million barrels with a 90% interval."
        ),
        "cutoff_date": CUTOFF_RELEASE.isoformat(),
        "resolution_date": RESOLUTION_RELEASE.isoformat(),
        "interval_level": 0.9,
        "schema_variant": variant,
        "entities": entities,
    }


def corpus_document(row: dict[str, Any]) -> dict[str, Any]:
    lines = [
        f"EIA weekly commercial crude oil stocks excluding SPR for {row['region_name']}.",
        "week_ending | commercial_crude_stock_mmbbl | weekly_change_mmbbl",
    ]
    for item in row["visible"]:
        level = float(item["stock_million_barrels"])
        change = float(item["change_million_barrels"])
        lines.append(f"{item['week_ending']} | {level:.3f} | {change:.3f}")
    seasonal = ", ".join(f"{value:.3f}" for value in row["seasonal_changes"])
    lines.extend([
        f"The five prior changes for ISO week {TARGET_WEEK.isocalendar().week} were {seasonal} million barrels.",
        f"Their mean was {row['naive_point']:.3f} million barrels.",
    ])
    return {
        "doc_id": f"EIA_CRUDE_HISTORY_{row['region_code']}_20260923",
        "doc_date": CUTOFF_RELEASE.isoformat(),
        "entities": [row["entity_id"]],
        "source": "U.S. Energy Information Administration",
        "source_url": SOURCE_URL,
        "license": LICENSE,
        "text": "\n".join(lines),
    }


def naive_answer(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    ordered = rows if variant == "explicit" else list(reversed(rows))
    predictions = []
    for row in ordered:
        point, half = row["naive_point"], row["naive_half_width"]
        predictions.append({
            "entity_id": row["entity_id"],
            "point_forecast": point,
            "interval": {"lo": point - half, "hi": point + half, "level": 0.9},
            "claims": [{
                "doc_id": f"EIA_CRUDE_HISTORY_{row['region_code']}_20260923",
                "span_start": 0,
                "span_end": 1,
                "claim": "EIA source.",
            }],
        })
    return {
        "task_id": f"{QUESTION_ID}-20260923-{variant}",
        "schema_version": "3",
        "target_type": "regression",
        "entity_predictions": predictions,
        "notes": {"baseline_id": "prior-five-same-iso-week-mean"},
    }


def outcome(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    ordered = rows if variant == "explicit" else list(reversed(rows))
    return {
        "task_id": f"{QUESTION_ID}-20260923-{variant}",
        "outcomes": [{"entity_id": row["entity_id"], "y": row["truth"]} for row in ordered],
    }


def card(variant: str) -> str:
    unit_id = f"{QUESTION_ID}-20260923-{variant}"
    family = "energy_inventory_change" if variant == "explicit" else "petroleum_balance_shift"
    return f'''schema_version = "2.0"

[task]
id = "{unit_id}"
track = "analysis"
title = "Weekly commercial crude inventory change ({variant})"
split = "confirmation"
family = "{family}"
target_type = "regression"
cutoff_date = "{CUTOFF_RELEASE.isoformat()}"
resolution_date = "{RESOLUTION_RELEASE.isoformat()}"

[provenance]
license = "{LICENSE}"
data_source = "{SOURCE_URL}"
data_cutoff = "{CUTOFF_RELEASE.isoformat()}"
redistributable = true
manifest = "manifest.json"

[scoring]
verifier = "t4.faithful_analysis"
metric = "analysis_composite"
admissibility_gates = ["g0_integrity", "g1_schema", "g2_cutoff_resource", "g3_domain_semantics"]

[scoring.params]
faithfulness_threshold = 0.80
interval_level = 0.90
target_type = "regression"
composite_weights = [0.7, 0.3]
tau_citation = 0.5

[agent]
timeout_sec = 600.0
'''


def build_unit(root: Path, rows: list[dict[str, Any]], snapshot_path: Path, variant: str) -> None:
    unit = root / f"{QUESTION_ID}-20260923-{variant}"
    if unit.exists():
        shutil.rmtree(unit)
    (unit / "corpus").mkdir(parents=True)
    dump(unit / "task.json", task_for(rows, variant))
    (unit / "card.toml").write_text(card(variant))
    for row in rows:
        dump(unit / "corpus" / f"{row['entity_id']}.json", corpus_document(row))
    dump(unit / "reference/outcome.json", outcome(rows, variant))
    dump(unit / "reference/naive_answer.json", naive_answer(rows, variant))
    snapshot = json.loads(snapshot_path.read_text())
    dump(unit / "provenance.json", {
        "question_id": QUESTION_ID,
        "variant": variant,
        "split": "confirmation",
        "source_urls": [item["url"] for item in snapshot["raw_sources"]],
        "source_snapshot": str(snapshot_path),
        "source_snapshot_sha256": sha256(snapshot_path),
        "source_raw_sha256": {item["release_date"]: item["sha256"] for item in snapshot["raw_sources"]},
        "download_date": snapshot["retrieved_at"],
        "cutoff_date": CUTOFF_RELEASE.isoformat(),
        "cutoff_week_ending": CUTOFF_WEEK.isoformat(),
        "resolution_date": RESOLUTION_RELEASE.isoformat(),
        "target_week_ending": TARGET_WEEK.isoformat(),
        "license": LICENSE,
        "availability": {
            "last_visible_week_release": CUTOFF_RELEASE.isoformat(),
            "target_week_release": RESOLUTION_RELEASE.isoformat(),
        },
        "generator": "proxy-benchmark/build_energy_proxy.py",
        "generator_version": "1.0.0",
    })
    files = []
    for path in sorted(p for p in unit.rglob("*") if p.is_file() and p.name != "manifest.json"):
        files.append({"path": path.relative_to(unit).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)})
    dump(unit / "manifest.json", {"manifest_version": "1.0", "unit_id": unit.name, "files": files})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=Path("proxy-benchmark/sources/proxy-16-eia-crude-2026.json"))
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--units", type=Path, default=Path("proxy-benchmark/units"))
    args = parser.parse_args()
    if args.raw_dir:
        build_source_snapshot(args.raw_dir, args.snapshot)
    snapshot = json.loads(args.snapshot.read_text())
    rows = prepare(snapshot)
    for variant in ("explicit", "transformed"):
        build_unit(args.units, rows, args.snapshot, variant)
    print(json.dumps({"question": QUESTION_ID, "variants": 2, "entities": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
