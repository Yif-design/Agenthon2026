#!/usr/bin/env python3
"""Build proxy-17 natural-gas storage variants from frozen official EIA data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import statistics
from datetime import date
from pathlib import Path
from typing import Any


QUESTION_ID = "proxy-17-natural-gas-storage-change"
CUTOFF_RELEASE = date(2026, 9, 24)
CUTOFF_WEEK = date(2026, 9, 18)
TARGET_WEEK = date(2026, 9, 25)
RESOLUTION_RELEASE = date(2026, 10, 1)
RETRIEVED_AT = "2026-10-03"
LICENSE = "Public domain (U.S. Energy Information Administration data)"
SOURCE_URL = "https://ir.eia.gov/ngs/"
HISTORY_URL = SOURCE_URL + "ngshistory.xls"
REVISIONS_URL = SOURCE_URL + "revisions.xls"
RELEASE_URL = SOURCE_URL + "wngsr.json"
REGIONS = (
    ("LOWER48", "Total Lower 48", "Total Lower 48", "total lower 48 states"),
    ("EAST", "East", "East Region", "east region"),
    ("MIDWEST", "Midwest", "Midwest Region", "midwest region"),
    ("MOUNTAIN", "Mountain", "Mountain Region", "mountain region"),
    ("PACIFIC", "Pacific", "Pacific Region", "pacific region"),
    ("SOUTH_CENTRAL", "South Central", "South Central Region", "south central region"),
)


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _iso_week_friday(year: int, week: int) -> date:
    return date.fromisocalendar(year, week, 5)


def _history_rows(path: Path) -> tuple[dict[date, dict[str, int]], list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    header_index = next(index for index, row in enumerate(rows) if row and row[0] == "Week ending")
    header = rows[header_index]
    result: dict[date, dict[str, int]] = {}
    for row in rows[header_index + 1 :]:
        if len(row) < len(header):
            continue
        try:
            week = date.fromisoformat(f"{row[0][6:10]}-{row[0][0:2]}-{row[0][3:5]}")
        except (ValueError, IndexError):
            continue
        result[week] = {column: int(row[index]) for index, column in enumerate(header[2:], 2)}
    return result, header


def _latest_revision_week(path: Path) -> date:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    weeks = []
    for row in rows:
        if not row or len(row[0]) != 10 or row[0][2] != "/":
            continue
        try:
            weeks.append(date.fromisoformat(f"{row[0][6:10]}-{row[0][0:2]}-{row[0][3:5]}"))
        except ValueError:
            continue
    if not weeks:
        raise ValueError("revision history contains no dated rows")
    return max(weeks)


def build_source_snapshot(
    history_csv: Path,
    history_xls: Path,
    revisions_csv: Path,
    revisions_xls: Path,
    release_json: Path,
    snapshot: Path,
) -> None:
    history, header = _history_rows(history_csv)
    revision_through = _latest_revision_week(revisions_csv)
    release = json.loads(release_json.read_text(encoding="utf-8-sig"))
    if date.fromisoformat(release["current_week"]) != TARGET_WEEK:
        raise ValueError("release current week differs from target")
    if date.fromisoformat(release["week_ago"]) != CUTOFF_WEEK:
        raise ValueError("release prior week differs from cutoff week")
    release_date = date.fromisoformat(
        release["release_date"].split()[0].replace("-Oct-", "-10-")
    )
    if release_date != RESOLUTION_RELEASE:
        raise ValueError("release date differs from resolution")
    release_by_name = {str(row["name"]).lower(): row for row in release["series"]}

    recent = {
        date.fromordinal(date(2025, 9, 26).toordinal() + 7 * index) for index in range(52)
    }
    seasonal = {_iso_week_friday(year, TARGET_WEEK.isocalendar().week) for year in range(2021, 2026)}
    required = recent | seasonal | {TARGET_WEEK}
    missing = sorted(required - set(history))
    if missing:
        raise ValueError(f"history is missing required weeks: {missing}")

    rows = []
    for code, name, history_column, release_name in REGIONS:
        if history_column not in header:
            raise ValueError(f"history is missing {history_column}")
        published = release_by_name.get(release_name)
        if published is None:
            raise ValueError(f"release is missing {release_name}")
        if any(flag != "false" for flag in published["revision_flag"][:2]):
            raise ValueError(f"release marks target/prior revision for {release_name}")
        if any(flag != "false" for flag in published["reclassification_flag"][:2]):
            raise ValueError(f"release marks target/prior reclassification for {release_name}")
        official_change = int(published["calculated"]["net_change"])
        derived_change = history[TARGET_WEEK][history_column] - history[CUTOFF_WEEK][history_column]
        if official_change != derived_change:
            raise ValueError(f"target change differs for {release_name}")
        observations = []
        for week in sorted(required):
            previous = date.fromordinal(week.toordinal() - 7)
            if previous not in history:
                raise ValueError(f"history is missing prior week for {week}")
            change = history[week][history_column] - history[previous][history_column]
            observations.append(
                {
                    "week_ending": week.isoformat(),
                    "stock_bcf": history[week][history_column],
                    "change_bcf": change,
                    "available_by": (
                        RESOLUTION_RELEASE.isoformat()
                        if week == TARGET_WEEK
                        else CUTOFF_RELEASE.isoformat()
                    ),
                }
            )
        rows.append(
            {
                "region_code": code,
                "region_name": name,
                "history_column": history_column,
                "release_series_id": published["series_id"],
                "target_revision_flag": published["revision_flag"][0],
                "prior_revision_flag": published["revision_flag"][1],
                "target_reclassification_flag": published["reclassification_flag"][0],
                "prior_reclassification_flag": published["reclassification_flag"][1],
                "observations": observations,
            }
        )
    dump(
        snapshot,
        {
            "snapshot_version": "1.0.0",
            "retrieved_at": RETRIEVED_AT,
            "license": LICENSE,
            "units": "billion cubic feet",
            "definition": "Weekly net change in working gas in underground storage",
            "cutoff_release_date": CUTOFF_RELEASE.isoformat(),
            "cutoff_week_ending": CUTOFF_WEEK.isoformat(),
            "target_week_ending": TARGET_WEEK.isoformat(),
            "resolution_release_date": RESOLUTION_RELEASE.isoformat(),
            "revision_history_latest_dated_row": revision_through.isoformat(),
            "raw_sources": [
                {
                    "url": RELEASE_URL,
                    "sha256": sha256(release_json),
                    "bytes": release_json.stat().st_size,
                    "role": "target_first_release_with_revision_and_reclassification_flags",
                },
                {
                    "url": HISTORY_URL,
                    "sha256": sha256(history_xls),
                    "bytes": history_xls.stat().st_size,
                    "role": "official_history_current_at_target_release",
                    "converted_csv_sha256": sha256(history_csv),
                },
                {
                    "url": REVISIONS_URL,
                    "sha256": sha256(revisions_xls),
                    "bytes": revisions_xls.stat().st_size,
                    "role": "official_revision_and_reclassification_history",
                    "converted_csv_sha256": sha256(revisions_csv),
                },
            ],
            "rows": rows,
        },
    )


def prepare(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for source in snapshot["rows"]:
        observations = {
            date.fromisoformat(row["week_ending"]): row for row in source["observations"]
        }
        visible = [
            observations[date.fromordinal(date(2025, 9, 26).toordinal() + 7 * index)]
            for index in range(52)
        ]
        seasonal = [
            float(observations[_iso_week_friday(year, TARGET_WEEK.isocalendar().week)]["change_bcf"])
            for year in range(2021, 2026)
        ]
        target = observations[TARGET_WEEK]
        point = statistics.fmean(seasonal)
        half = max(1.0, 1.65 * statistics.pstdev(seasonal))
        result.append(
            {
                **{key: source[key] for key in ("region_code", "region_name")},
                "entity_id": f"EIA_GAS_{source['region_code']}_{TARGET_WEEK.strftime('%Y%m%d')}",
                "visible": visible,
                "seasonal_changes": seasonal,
                "truth": float(target["change_bcf"]),
                "naive_point": point,
                "naive_half_width": half,
            }
        )
    return result


def task_for(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    explicit = variant == "explicit"
    ordered = rows if explicit else list(reversed(rows))
    entities = []
    for index, row in enumerate(ordered):
        latest = row["visible"][-1]
        entity = {
            "entity_id": row["entity_id"],
            "name": row["region_name"],
            "corpus_ref": f"corpus/{row['entity_id']}.json",
        }
        if explicit:
            entity.update(
                {
                    "region": row["region_code"],
                    "latest_working_gas_bcf": latest["stock_bcf"],
                    "last_week_change_bcf": latest["change_bcf"],
                    "seasonal_change_mean_bcf": row["naive_point"],
                    "unit": "billion_cubic_feet_change",
                }
            )
        else:
            entity.update(
                {
                    "area_key": f"UGS-{index + 31}",
                    "terminal_volume_mmcf": latest["stock_bcf"] * 1000,
                    "one_period_flow_mmcf": latest["change_bcf"] * 1000,
                    "week_39_norm_mmcf": row["naive_point"] * 1000,
                    "display_scale": "million_cubic_feet",
                    "irrelevant_facility_class": f"C{index + 4}",
                }
            )
        entities.append(entity)
    return {
        "task_id": f"{QUESTION_ID}-20260924-{variant}",
        "schema_version": "3",
        "family": "natural_gas_storage_change" if explicit else "underground_reserve_flow",
        "target": {
            "name": (
                "weekly_working_gas_change_bcf"
                if explicit
                else "underground_reserve_delta_billion_cubic_feet"
            ),
            "type": "regression",
            "unit": "billion_cubic_feet_change",
            "horizon": "next EIA Weekly Natural Gas Storage Report",
            "definition": "target-week working-gas stock minus prior-week stock",
        },
        "prompt": (
            "Forecast the next weekly net change in working gas in underground storage for the Lower 48 "
            "and each listed EIA region. Positive values are injections and negative values are withdrawals. "
            "Use only information public with the 2026-09-24 report and return Bcf with a 90% interval."
        ),
        "cutoff_date": CUTOFF_RELEASE.isoformat(),
        "resolution_date": RESOLUTION_RELEASE.isoformat(),
        "interval_level": 0.9,
        "schema_variant": variant,
        "entities": entities,
    }


def corpus_document(row: dict[str, Any]) -> dict[str, Any]:
    lines = [
        f"EIA weekly working gas in underground storage for {row['region_name']}.",
        "week_ending | working_gas_bcf | weekly_change_bcf",
    ]
    for item in row["visible"]:
        lines.append(f"{item['week_ending']} | {item['stock_bcf']} | {item['change_bcf']}")
    seasonal = ", ".join(f"{value:.0f}" for value in row["seasonal_changes"])
    lines.extend(
        [
            f"The five prior changes for ISO week {TARGET_WEEK.isocalendar().week} were {seasonal} Bcf.",
            f"Their mean was {row['naive_point']:.3f} Bcf.",
        ]
    )
    return {
        "doc_id": f"EIA_GAS_HISTORY_{row['region_code']}_20260924",
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
        predictions.append(
            {
                "entity_id": row["entity_id"],
                "point_forecast": point,
                "interval": {"lo": point - half, "hi": point + half, "level": 0.9},
                "claims": [
                    {
                        "doc_id": f"EIA_GAS_HISTORY_{row['region_code']}_20260924",
                        "span_start": 0,
                        "span_end": 1,
                        "claim": "EIA source.",
                    }
                ],
            }
        )
    return {
        "task_id": f"{QUESTION_ID}-20260924-{variant}",
        "schema_version": "3",
        "target_type": "regression",
        "entity_predictions": predictions,
        "notes": {"baseline_id": "prior-five-same-iso-week-mean"},
    }


def outcome(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    ordered = rows if variant == "explicit" else list(reversed(rows))
    return {
        "task_id": f"{QUESTION_ID}-20260924-{variant}",
        "outcomes": [{"entity_id": row["entity_id"], "y": row["truth"]} for row in ordered],
    }


def card(variant: str) -> str:
    unit_id = f"{QUESTION_ID}-20260924-{variant}"
    family = "natural_gas_storage_change" if variant == "explicit" else "underground_reserve_flow"
    return f'''schema_version = "2.0"

[task]
id = "{unit_id}"
track = "analysis"
title = "Weekly natural-gas storage change ({variant})"
split = "time_forward_test"
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
    unit = root / f"{QUESTION_ID}-20260924-{variant}"
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
    dump(
        unit / "provenance.json",
        {
            "question_id": QUESTION_ID,
            "variant": variant,
            "split": "time_forward_test",
            "source_urls": [item["url"] for item in snapshot["raw_sources"]],
            "source_snapshot": str(snapshot_path),
            "source_snapshot_sha256": sha256(snapshot_path),
            "source_raw_sha256": {item["url"]: item["sha256"] for item in snapshot["raw_sources"]},
            "download_date": snapshot["retrieved_at"],
            "cutoff_date": CUTOFF_RELEASE.isoformat(),
            "cutoff_week_ending": CUTOFF_WEEK.isoformat(),
            "resolution_date": RESOLUTION_RELEASE.isoformat(),
            "target_week_ending": TARGET_WEEK.isoformat(),
            "target_revision_flag": False,
            "target_reclassification_flag": False,
            "license": LICENSE,
            "generator": "proxy-benchmark/build_gas_proxy.py",
            "generator_version": "1.0.0",
        },
    )
    files = []
    for path in sorted(p for p in unit.rglob("*") if p.is_file() and p.name != "manifest.json"):
        files.append(
            {
                "path": path.relative_to(unit).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    dump(unit / "manifest.json", {"manifest_version": "1.0", "unit_id": unit.name, "files": files})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path("proxy-benchmark/sources/proxy-17-eia-gas-2026.json"),
    )
    parser.add_argument("--history-csv", type=Path)
    parser.add_argument("--history-xls", type=Path)
    parser.add_argument("--revisions-csv", type=Path)
    parser.add_argument("--revisions-xls", type=Path)
    parser.add_argument("--release-json", type=Path)
    parser.add_argument("--units", type=Path, default=Path("proxy-benchmark/units"))
    args = parser.parse_args()
    raw = (
        args.history_csv,
        args.history_xls,
        args.revisions_csv,
        args.revisions_xls,
        args.release_json,
    )
    if any(raw) and not all(raw):
        parser.error("all five raw-source arguments are required together")
    if all(raw):
        build_source_snapshot(*raw, args.snapshot)
    snapshot = json.loads(args.snapshot.read_text())
    rows = prepare(snapshot)
    for variant in ("explicit", "transformed"):
        build_unit(args.units, rows, args.snapshot, variant)
    print(json.dumps({"question": QUESTION_ID, "variants": 2, "entities": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
