#!/usr/bin/env python3
"""Build proxy-10 payroll-surprise classification variants from ALFRED vintages."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
import statistics
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


QUESTION_ID = "proxy-10-payroll-surprise-band"
CUTOFF = date(2023, 8, 31)
RESOLUTION = date(2023, 9, 1)
TARGET_MONTH = "2023-08-01"
RETRIEVED_AT = "2026-10-03"
ALFRED_URL = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
BLS_RELEASE_URL = "https://www.bls.gov/news.release/archives/empsit_09012023.htm"
LICENSE = "BLS data are U.S. government works; ALFRED redistribution metadata recorded"
SERIES = (
    ("PAYEMS", "Total nonfarm payrolls"),
    ("USCONS", "Construction"),
    ("MANEMP", "Manufacturing"),
    ("USTPU", "Trade, transportation, and utilities"),
    ("USWTRADE", "Wholesale trade"),
    ("USINFO", "Information"),
    ("USFIRE", "Financial activities"),
    ("USPBS", "Professional and business services"),
    ("USEHS", "Education and health services"),
    ("USLAH", "Leisure and hospitality"),
    ("USGOVT", "Government"),
)
LABELS = ("positive_surprise", "inline", "negative_surprise")


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _download(series_id: str, vintage: date) -> tuple[str, str, list[dict[str, Any]]]:
    params = urlencode({
        "id": series_id,
        "cosd": "2022-12-01",
        "coed": TARGET_MONTH,
        "vintage_date": vintage.isoformat(),
    })
    url = f"{ALFRED_URL}?{params}"
    raw = urlopen(url, timeout=30).read()
    body = raw.decode("utf-8")
    parsed = []
    for row in csv.DictReader(io.StringIO(body)):
        raw_value = next(value for key, value in row.items() if key != "observation_date")
        if raw_value not in ("", "."):
            parsed.append({"month": row["observation_date"], "level_thousands": float(raw_value)})
    return url, hashlib.sha256(raw).hexdigest(), parsed


def build_source_snapshot(snapshot: Path) -> None:
    rows = []
    source_urls = []
    for series_id, name in SERIES:
        cutoff_url, cutoff_sha, cutoff_rows = _download(series_id, CUTOFF)
        resolution_url, resolution_sha, resolution_rows = _download(series_id, RESOLUTION)
        cutoff_by_month = {row["month"]: row["level_thousands"] for row in cutoff_rows}
        resolution_by_month = {row["month"]: row["level_thousands"] for row in resolution_rows}
        if TARGET_MONTH in cutoff_by_month or TARGET_MONTH not in resolution_by_month:
            raise ValueError(f"vintage separation failed for {series_id}")
        if "2023-07-01" not in resolution_by_month:
            raise ValueError(f"resolution vintage lacks July comparison for {series_id}")
        rows.append({
            "series_id": series_id,
            "name": name,
            "cutoff_vintage": cutoff_rows,
            "resolution_july_level_thousands": resolution_by_month["2023-07-01"],
            "resolution_august_level_thousands": resolution_by_month[TARGET_MONTH],
            "cutoff_url": cutoff_url,
            "cutoff_raw_sha256": cutoff_sha,
            "resolution_url": resolution_url,
            "resolution_raw_sha256": resolution_sha,
        })
        source_urls.extend((cutoff_url, resolution_url))
    dump(snapshot, {
        "snapshot_version": "1.0.0",
        "retrieved_at": RETRIEVED_AT,
        "license": LICENSE,
        "units": "thousands of persons, seasonally adjusted",
        "cutoff_date": CUTOFF.isoformat(),
        "resolution_date": RESOLUTION.isoformat(),
        "resolution_release_timestamp": "2023-09-01T08:30:00-04:00",
        "target_month": TARGET_MONTH,
        "release_url": BLS_RELEASE_URL,
        "source_urls": source_urls,
        "rows": rows,
    })


def prepare(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for source in snapshot["rows"]:
        history = source["cutoff_vintage"]
        changes = [
            history[index]["level_thousands"] - history[index - 1]["level_thousands"]
            for index in range(1, len(history))
        ]
        if len(changes) < 6 or history[-1]["month"] != "2023-07-01":
            raise ValueError(f"insufficient cutoff history for {source['series_id']}")
        reference = statistics.fmean(changes[-3:])
        band = max(5.0, 0.5 * statistics.pstdev(changes[-6:]))
        actual = source["resolution_august_level_thousands"] - source["resolution_july_level_thousands"]
        surprise = actual - reference
        label = LABELS[0] if surprise > band else LABELS[2] if surprise < -band else LABELS[1]
        result.append({
            "entity_id": f"BLS_{source['series_id']}_202308",
            "series_id": source["series_id"],
            "name": source["name"],
            "history": history,
            "recent_changes": changes[-6:],
            "reference": reference,
            "band": band,
            "actual": actual,
            "surprise": surprise,
            "label": label,
        })
    return result


def task_for(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
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
                "series_id": row["series_id"],
                "reference_change_thousands": row["reference"],
                "surprise_band_half_width_thousands": row["band"],
                "latest_monthly_change_thousands": row["recent_changes"][-1],
                "six_month_change_volatility_thousands": statistics.pstdev(row["recent_changes"]),
            })
        else:
            entity.update({
                "industry_key": f"CES-G{index + 41}",
                "benchmark_flow_persons": row["reference"] * 1000.0,
                "tolerance_persons": row["band"] * 1000.0,
                "terminal_delta_persons": row["recent_changes"][-1] * 1000.0,
                "dispersion_persons": statistics.pstdev(row["recent_changes"]) * 1000.0,
                "display_scale": "persons",
            })
        entities.append(entity)
    target_name = "payroll_surprise_band" if explicit else "workforce_deviation_class"
    prompt = (
        "Forecast the August 2023 first-print monthly payroll change relative to each row's frozen "
        "reference. Return positive_surprise above +band, negative_surprise below -band, and inline otherwise."
        if explicit else
        "Classify the next workforce flow against benchmark_flow_persons: positive_surprise when the "
        "deviation exceeds +tolerance_persons, negative_surprise below -tolerance_persons, and inline otherwise."
    )
    return {
        "task_id": f"{QUESTION_ID}-202308-{variant}",
        "schema_version": "3",
        "target": {"type": "classification", "name": target_name, "labels": list(LABELS)},
        "cutoff_date": CUTOFF.isoformat(),
        "interval_level": 0.9,
        "prompt": prompt,
        "entities": entities,
    }


def corpus_document(row: dict[str, Any], variant: str) -> dict[str, Any]:
    explicit = variant == "explicit"
    scale = 1.0 if explicit else 1000.0
    unit = "thousand persons" if explicit else "persons"
    lines = [
        f"Series: {row['name']} ({row['series_id']}).",
        f"ALFRED vintage date: {CUTOFF.isoformat()}; values are seasonally adjusted {unit}.",
        f"Frozen reference change: {row['reference'] * scale:.6f} {unit}.",
        f"Classification half-band: {row['band'] * scale:.6f} {unit}.",
        "Cutoff-vintage monthly levels:",
    ]
    lines.extend(
        f"{item['month']}: {item['level_thousands'] * scale:.3f} {unit}."
        for item in row["history"]
    )
    return {
        "doc_id": f"ALFRED_{row['series_id']}_VINTAGE_20230831",
        "doc_date": CUTOFF.isoformat(),
        "entity_id": row["entity_id"],
        "source": ALFRED_URL,
        "title": f"Cutoff-vintage payroll history for {row['name']}",
        "text": "\n".join(lines),
    }


def naive_answer(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    ordered = rows if variant == "explicit" else list(reversed(rows))
    predictions = []
    for row in ordered:
        predictions.append({
            "entity_id": row["entity_id"],
            "label": "inline",
            "point_forecast": 0.5,
            "interval": {"lo": 0.0, "hi": 1.0, "level": 0.9},
            "claims": [{
                "doc_id": f"ALFRED_{row['series_id']}_VINTAGE_20230831",
                "span_start": 0,
                "span_end": 1,
                "claim": "ALFRED source.",
            }],
        })
    return {
        "task_id": f"{QUESTION_ID}-202308-{variant}",
        "schema_version": "3",
        "target_type": "classification",
        "entity_predictions": predictions,
        "notes": {"baseline_id": "always-inline"},
    }


def outcome(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    ordered = rows if variant == "explicit" else list(reversed(rows))
    return {
        "task_id": f"{QUESTION_ID}-202308-{variant}",
        "outcomes": [{"entity_id": row["entity_id"], "true_label": row["label"]} for row in ordered],
    }


def card(variant: str) -> str:
    unit_id = f"{QUESTION_ID}-202308-{variant}"
    family = "payroll_surprise_band" if variant == "explicit" else "workforce_deviation_class"
    return f'''schema_version = "2.0"

[task]
id = "{unit_id}"
track = "analysis"
title = "Payroll first-print surprise ({variant})"
split = "time_forward_test"
family = "{family}"
target_type = "classification"
cutoff_date = "{CUTOFF.isoformat()}"
resolution_date = "{RESOLUTION.isoformat()}"

[provenance]
license = "{LICENSE}"
data_source = "{ALFRED_URL}"
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
interval_leg = false
target_type = "classification"
labels = ["positive_surprise", "inline", "negative_surprise"]
composite_weights = [0.7, 0.3]
tau_citation = 0.5

[agent]
timeout_sec = 600.0
'''


def build_unit(root: Path, rows: list[dict[str, Any]], snapshot_path: Path, variant: str) -> None:
    unit = root / f"{QUESTION_ID}-202308-{variant}"
    if unit.exists():
        shutil.rmtree(unit)
    (unit / "corpus").mkdir(parents=True)
    dump(unit / "task.json", task_for(rows, variant))
    (unit / "card.toml").write_text(card(variant))
    for row in rows:
        dump(unit / "corpus" / f"{row['entity_id']}.json", corpus_document(row, variant))
    dump(unit / "reference/outcome.json", outcome(rows, variant))
    dump(unit / "reference/naive_answer.json", naive_answer(rows, variant))
    snapshot = json.loads(snapshot_path.read_text())
    dump(unit / "provenance.json", {
        "question_id": QUESTION_ID,
        "variant": variant,
        "split": "time_forward_test",
        "source_urls": snapshot["source_urls"] + [snapshot["release_url"]],
        "source_snapshot": str(snapshot_path),
        "source_snapshot_sha256": sha256(snapshot_path),
        "download_date": snapshot["retrieved_at"],
        "cutoff_date": CUTOFF.isoformat(),
        "resolution_date": RESOLUTION.isoformat(),
        "target_month": TARGET_MONTH,
        "license": LICENSE,
        "availability": {"cutoff_vintage": CUTOFF.isoformat(), "first_print_vintage": RESOLUTION.isoformat()},
        "generator": "proxy-benchmark/build_payroll_proxy.py",
        "generator_version": "1.0.0",
    })
    files = []
    for path in sorted(p for p in unit.rglob("*") if p.is_file() and p.name != "manifest.json"):
        files.append({"path": path.relative_to(unit).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)})
    dump(unit / "manifest.json", {"manifest_version": "1.0", "unit_id": unit.name, "files": files})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=Path("proxy-benchmark/sources/proxy-10-payroll-2023.json"))
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--units", type=Path, default=Path("proxy-benchmark/units"))
    args = parser.parse_args()
    if args.fetch:
        build_source_snapshot(args.snapshot)
    snapshot = json.loads(args.snapshot.read_text())
    rows = prepare(snapshot)
    for variant in ("explicit", "transformed"):
        build_unit(args.units, rows, args.snapshot, variant)
    print(json.dumps({
        "question": QUESTION_ID,
        "variants": 2,
        "entities": len(rows),
        "labels": {label: sum(row["label"] == label for row in rows) for label in LABELS},
    }, indent=2))


if __name__ == "__main__":
    main()
