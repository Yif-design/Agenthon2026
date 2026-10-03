#!/usr/bin/env python3
"""Build proxy-15 indirect-bidder-share schema variants from frozen Treasury data."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any


QUESTION_ID = "proxy-15-auction-indirect-bidder-share"
ANNOUNCEMENT = date(2023, 8, 2)
RESOLUTION = date(2023, 8, 10)
SOURCE_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"
LICENSE = "Public domain (U.S. Treasury auction data)"
TERMS = ("3-Year", "10-Year", "30-Year")


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_source_snapshot(raw_cache: Path, snapshot: Path) -> None:
    document = json.loads(raw_cache.read_text())
    selected = []
    for row in document["data"]:
        if (
            row.get("floating_rate") == "No"
            and row.get("inflation_index_security") == "No"
            and row.get("original_security_term") in TERMS
            and "2018-01-01" <= str(row.get("auction_date", "")) <= RESOLUTION.isoformat()
        ):
            selected.append(row)
    selected.sort(key=lambda row: (row["auction_date"], row["original_security_term"]))
    dump(snapshot, {
        "snapshot_version": "1.0.0",
        "source_url": SOURCE_URL,
        "source_raw_sha256": sha256(raw_cache),
        "source_record_count": len(document["data"]),
        "retrieved_at": "2026-09-27",
        "license": LICENSE,
        "target_announcement_date": ANNOUNCEMENT.isoformat(),
        "target_result_available_by": RESOLUTION.isoformat(),
        "rows": selected,
    })


def share(row: dict[str, Any]) -> float:
    accepted = float(row["total_accepted"])
    indirect = float(row["indirect_bidder_accepted"])
    if accepted <= 0 or indirect < 0 or indirect > accepted:
        raise ValueError(f"invalid indirect/total accepted amounts for {row.get('cusip')}")
    return 100.0 * indirect / accepted


def prepare(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    by_term: dict[str, list[dict[str, Any]]] = defaultdict(list)
    targets: dict[str, dict[str, Any]] = {}
    for row in snapshot["rows"]:
        term = row["original_security_term"]
        if row["announcemt_date"] == ANNOUNCEMENT.isoformat():
            if term in targets:
                raise ValueError(f"duplicate target term {term}")
            targets[term] = row
        elif row["auction_date"] < ANNOUNCEMENT.isoformat():
            by_term[term].append(row)
    if set(targets) != set(TERMS):
        raise ValueError(f"target announcement has terms {sorted(targets)}, expected {list(TERMS)}")
    prepared = []
    for term in TERMS:
        history = sorted(by_term[term], key=lambda row: row["auction_date"])[-12:]
        if len(history) != 12:
            raise ValueError(f"{term} has only {len(history)} prior observations")
        recent = [share(row) for row in history[-6:]]
        target = targets[term]
        point = statistics.fmean(recent)
        half = max(0.15, 1.65 * statistics.pstdev(recent))
        prepared.append({
            "entity_id": f"TREASURY_{term.replace('-', '').upper()}_{target['auction_date'].replace('-', '')}",
            "name": f"{term} Treasury auction on {target['auction_date']}",
            "term": term,
            "target": target,
            "history": history,
            "truth": share(target),
            "naive_point": point,
            "naive_half_width": half,
        })
    return prepared


def task_for(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    explicit = variant == "explicit"
    ordered = rows if explicit else list(reversed(rows))
    entities = []
    for index, row in enumerate(ordered):
        target = row["target"]
        entity = {
            "entity_id": row["entity_id"],
            "name": row["name"],
            "corpus_ref": f"corpus/{row['entity_id']}.json",
        }
        if explicit:
            entity.update({
                "tenor": row["term"],
                "auction_date": target["auction_date"],
                "new_or_reopening": "reopening" if target["reopening"] == "Yes" else "new",
                "offering_amount_usd_bn": float(target["offering_amt"]) / 1e9,
                "unit": "percent_of_total_accepted",
            })
        else:
            years = int(row["term"].split("-")[0])
            entity.update({
                "security_bucket_months": years * 12,
                "sale_day": target["auction_date"],
                "amount_millions": float(target["offering_amt"]) / 1e6,
                "is_reopened_line": target["reopening"] == "Yes",
                "measurement_scale": "percentage_points",
                "irrelevant_batch_index": index + 501,
            })
        entities.append(entity)
    return {
        "task_id": f"{QUESTION_ID}-20230802-{variant}",
        "schema_version": "3",
        "family": "treasury_auction_share" if explicit else "remote_allotment",
        "target": {
            "name": "indirect_bidder_acceptance_share_pct" if explicit else "remote_allotment_fraction_pct",
            "type": "regression",
            "unit": "percent_of_total_accepted",
            "horizon": "announced auction result",
            "definition": "indirect bidder accepted amount divided by total accepted amount, times 100",
        },
        "prompt": (
            "Forecast the indirect-bidder acceptance share for each announced Treasury auction. "
            "The target equals indirect bidder accepted amount divided by total accepted amount, "
            "times 100. Use only information public by the 2023-08-02 announcement cutoff and "
            "return a point forecast and 90% interval in percentage points."
        ),
        "cutoff_date": ANNOUNCEMENT.isoformat(),
        "resolution_date": RESOLUTION.isoformat(),
        "interval_level": 0.9,
        "schema_variant": variant,
        "entities": entities,
    }


def corpus_document(row: dict[str, Any]) -> dict[str, Any]:
    lines = [
        f"Treasury auction history for {row['term']} securities.",
        "auction_date | offering_amount_usd_bn | new_or_reopening | total_accepted_usd_bn | indirect_bidder_acceptance_share_pct",
    ]
    for item in row["history"]:
        lines.append(
            f"{item['auction_date']} | {float(item['offering_amt']) / 1e9:.3f} | "
            f"{'reopening' if item['reopening'] == 'Yes' else 'new'} | "
            f"{float(item['total_accepted']) / 1e9:.6f} | {share(item):.6f}"
        )
    lines.append(
        f"The average over the six most recent auctions is {row['naive_point']:.6f} percent of total accepted."
    )
    return {
        "doc_id": f"TREASURY_INDIRECT_{row['term'].replace('-', '').upper()}_20230802",
        "doc_date": ANNOUNCEMENT.isoformat(),
        "entities": [row["entity_id"]],
        "source": "U.S. Treasury Fiscal Data",
        "source_url": SOURCE_URL,
        "license": LICENSE,
        "text": "\n".join(lines),
    }


def naive_answer(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    ordered = rows if variant == "explicit" else list(reversed(rows))
    predictions = []
    for row in ordered:
        point = row["naive_point"]
        half = row["naive_half_width"]
        predictions.append({
            "entity_id": row["entity_id"], "point_forecast": point,
            "interval": {"lo": point - half, "hi": point + half, "level": 0.9},
            "claims": [{
                "doc_id": f"TREASURY_INDIRECT_{row['term'].replace('-', '').upper()}_20230802",
                "span_start": 0, "span_end": 1, "claim": "Treasury source.",
            }],
        })
    return {
        "task_id": f"{QUESTION_ID}-20230802-{variant}", "schema_version": "3",
        "target_type": "regression", "entity_predictions": predictions,
        "notes": {"baseline_id": "recent-six-same-term-mean"},
    }


def outcome(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    ordered = rows if variant == "explicit" else list(reversed(rows))
    return {
        "task_id": f"{QUESTION_ID}-20230802-{variant}",
        "outcomes": [{"entity_id": row["entity_id"], "y": row["truth"]} for row in ordered],
    }


def card(variant: str) -> str:
    unit_id = f"{QUESTION_ID}-20230802-{variant}"
    family = "treasury_auction_share" if variant == "explicit" else "remote_allotment"
    return f'''schema_version = "2.0"

[task]
id = "{unit_id}"
track = "analysis"
title = "Treasury indirect-bidder acceptance share ({variant})"
split = "time_forward_test"
family = "{family}"
target_type = "regression"
cutoff_date = "{ANNOUNCEMENT.isoformat()}"
resolution_date = "{RESOLUTION.isoformat()}"

[provenance]
license = "{LICENSE}"
data_source = "{SOURCE_URL}"
data_cutoff = "{ANNOUNCEMENT.isoformat()}"
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
    unit = root / f"{QUESTION_ID}-20230802-{variant}"
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
        "question_id": QUESTION_ID, "variant": variant, "split": "time_forward_test",
        "source_url": SOURCE_URL, "source_snapshot": str(snapshot_path),
        "source_snapshot_sha256": sha256(snapshot_path), "source_raw_sha256": snapshot["source_raw_sha256"],
        "download_date": snapshot["retrieved_at"], "cutoff_date": ANNOUNCEMENT.isoformat(),
        "resolution_date": RESOLUTION.isoformat(), "license": LICENSE,
        "availability": {"announcement_public": ANNOUNCEMENT.isoformat(), "last_result_public": RESOLUTION.isoformat()},
        "generator": "proxy-benchmark/build_auction_proxy.py", "generator_version": "1.0.0",
    })
    files = []
    for path in sorted(p for p in unit.rglob("*") if p.is_file() and p.name != "manifest.json"):
        files.append({"path": path.relative_to(unit).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)})
    dump(unit / "manifest.json", {"manifest_version": "1.0", "unit_id": unit.name, "files": files})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=Path("proxy-benchmark/sources/proxy-15-auctions-2023.json"))
    parser.add_argument("--raw-cache", type=Path)
    parser.add_argument("--units", type=Path, default=Path("proxy-benchmark/units"))
    args = parser.parse_args()
    if args.raw_cache:
        build_source_snapshot(args.raw_cache, args.snapshot)
    snapshot = json.loads(args.snapshot.read_text())
    rows = prepare(snapshot)
    for variant in ("explicit", "transformed"):
        build_unit(args.units, rows, args.snapshot, variant)
    print(json.dumps({"question": QUESTION_ID, "variants": 2, "entities": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
