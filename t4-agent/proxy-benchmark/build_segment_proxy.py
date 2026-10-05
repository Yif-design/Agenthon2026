#!/usr/bin/env python3
"""Build proxy-09 from dimensioned segment facts in SEC inline XBRL filings."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any

from proxy_factory import dump, materialize_pair


CUTOFF = "2023-04-28"
RESOLUTION = "2023-08-04"
RETRIEVED = "2026-10-03"
LICENSE = "Public SEC EDGAR inline XBRL filings; accessions and filing dates retained"
FILES = {
    "amzn_q1": ("AMZN", "2023-04-28", "0001018724-23-000008", "https://www.sec.gov/Archives/edgar/data/1018724/000101872423000008/amzn-20230331.htm"),
    "amzn_q2": ("AMZN", "2023-08-04", "0001018724-23-000012", "https://www.sec.gov/Archives/edgar/data/1018724/000101872423000012/amzn-20230630.htm"),
    "msft_q1": ("MSFT", "2023-04-25", "0000950170-23-014423", "https://www.sec.gov/Archives/edgar/data/789019/000095017023014423/msft-20230331.htm"),
    "msft_q2": ("MSFT", "2023-07-27", "0000950170-23-035122", "https://www.sec.gov/Archives/edgar/data/789019/000095017023035122/msft-20230630.htm"),
}
SEGMENTS = {
    "amzn:NorthAmericaSegmentMember": "North America",
    "amzn:InternationalSegmentMember": "International",
    "amzn:AmazonWebServicesSegmentMember": "Amazon Web Services",
    "msft:ProductivityAndBusinessProcessesMember": "Productivity and Business Processes",
    "msft:IntelligentCloudMember": "Intelligent Cloud",
    "msft:MorePersonalComputingMember": "More Personal Computing",
}


def attributes(value: str) -> dict[str, str]:
    return {key.lower(): html.unescape(item) for key, item in re.findall(r"([\w:-]+)\s*=\s*[\"']([^\"']*)[\"']", value)}


def clean(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def dimensioned_revenue(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(errors="ignore")
    contexts: dict[str, tuple[str, str, list[tuple[str, str]]]] = {}
    for match in re.finditer(r"<xbrli:context\b([^>]*)>(.*?)</xbrli:context>", text, re.I | re.S):
        attr, body = attributes(match.group(1)), match.group(2)
        start = re.search(r"<xbrli:startDate>(.*?)</xbrli:startDate>", body, re.I)
        end = re.search(r"<xbrli:endDate>(.*?)</xbrli:endDate>", body, re.I)
        members = []
        for member in re.finditer(r"<xbrldi:explicitMember\b([^>]*)>(.*?)</xbrldi:explicitMember>", body, re.I | re.S):
            members.append((attributes(member.group(1)).get("dimension", ""), clean(member.group(2))))
        contexts[attr.get("id", "")] = (clean(start.group(1)) if start else "", clean(end.group(1)) if end else "", members)
    facts = []
    for match in re.finditer(r"<ix:nonFraction\b([^>]*)>(.*?)</ix:nonFraction>", text, re.I | re.S):
        attr = attributes(match.group(1))
        if attr.get("name", "").lower() != "us-gaap:revenuefromcontractwithcustomerexcludingassessedtax".lower():
            continue
        start, end, members = contexts.get(attr.get("contextref", ""), ("", "", []))
        segment = [member for dimension, member in members if dimension == "us-gaap:StatementBusinessSegmentsAxis"]
        if not segment or segment[0] not in SEGMENTS:
            continue
        numeric = clean(match.group(2)).replace(",", "").replace("$", "")
        facts.append({"segment_member": segment[0], "start": start, "end": end, "value_millions": float(numeric)})
    return facts


def one(facts: list[dict[str, Any]], segment: str, start: str, end: str) -> float:
    values = [row["value_millions"] for row in facts if row["segment_member"] == segment and row["start"] == start and row["end"] == end]
    if len(values) != 1:
        raise ValueError(f"expected one fact for {segment} {start} {end}, got {values}")
    return values[0]


def build_snapshot(raw_dir: Path, destination: Path) -> None:
    parsed = {key: dimensioned_revenue(raw_dir / f"{key}.htm") for key in FILES}
    rows = []
    for member, name in SEGMENTS.items():
        ticker = "AMZN" if member.startswith("amzn:") else "MSFT"
        if ticker == "AMZN":
            q1_22 = one(parsed["amzn_q1"], member, "2022-01-01", "2022-03-31")
            q1_23 = one(parsed["amzn_q1"], member, "2023-01-01", "2023-03-31")
            q2_22 = one(parsed["amzn_q2"], member, "2022-04-01", "2022-06-30")
            q2_23 = one(parsed["amzn_q2"], member, "2023-04-01", "2023-06-30")
            outcome_method = "direct Q2 inline XBRL segment facts"
        else:
            q1_22 = one(parsed["msft_q1"], member, "2022-01-01", "2022-03-31")
            q1_23 = one(parsed["msft_q1"], member, "2023-01-01", "2023-03-31")
            nine_22 = one(parsed["msft_q1"], member, "2021-07-01", "2022-03-31")
            nine_23 = one(parsed["msft_q1"], member, "2022-07-01", "2023-03-31")
            year_22 = one(parsed["msft_q2"], member, "2021-07-01", "2022-06-30")
            year_23 = one(parsed["msft_q2"], member, "2022-07-01", "2023-06-30")
            q2_22, q2_23 = year_22 - nine_22, year_23 - nine_23
            outcome_method = "fiscal-year segment revenue minus pre-cutoff nine-month segment revenue"
        rows.append({
            "ticker": ticker, "segment_member": member, "segment_name": name,
            "q1_2022_revenue_millions": q1_22, "q1_2023_revenue_millions": q1_23,
            "q2_2022_revenue_millions": q2_22, "q2_2023_revenue_millions": q2_23,
            "signal_growth_pct": 100 * (q1_23 / q1_22 - 1),
            "outcome_growth_pct": 100 * (q2_23 / q2_22 - 1),
            "outcome_method": outcome_method,
        })
    raw_sources = []
    for key, (ticker, filed, accession, url) in FILES.items():
        path = raw_dir / f"{key}.htm"
        raw_sources.append({"ticker": ticker, "filed": filed, "accession": accession, "url": url, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    dump(destination, {"snapshot_version": "1.0.0", "retrieved_at": RETRIEVED, "generator": "proxy-benchmark/build_segment_proxy.py", "license": LICENSE, "cutoff": CUTOFF, "resolution": RESOLUTION, "raw_sources": raw_sources, "segments": rows})


def build(snapshot_path: Path, units: Path) -> None:
    snapshot = json.loads(snapshot_path.read_text())
    rows = []
    for item in snapshot["segments"]:
        entity = f"{item['ticker']}_{item['segment_member'].split(':', 1)[1].replace('Member', '')}"
        signal, truth = item["signal_growth_pct"], item["outcome_growth_pct"]
        rows.append({
            "entity_id": entity, "name": f"{item['ticker']} — {item['segment_name']}",
            "explicit": {"ticker": item["ticker"], "segment": item["segment_name"], "prior_q1_revenue_millions": item["q1_2022_revenue_millions"], "latest_q1_revenue_millions": item["q1_2023_revenue_millions"], "latest_q1_yoy_growth_pct": signal},
            "transformed": {"issuer_segment_key": entity, "base_period_turnover_thousands": item["q1_2022_revenue_millions"] * 1000, "current_period_turnover_thousands": item["q1_2023_revenue_millions"] * 1000, "observed_change_fraction": signal / 100},
            "corpus_explicit": f"SEC inline XBRL segment facts for {item['ticker']} {item['segment_name']}. Q1 2022 revenue USD {item['q1_2022_revenue_millions']:.0f} million; Q1 2023 revenue USD {item['q1_2023_revenue_millions']:.0f} million. Filed no later than {CUTOFF}.",
            "corpus_transformed": f"SEC inline XBRL dimension member {item['segment_member']}. Prior period turnover {item['q1_2022_revenue_millions'] * 1000:.0f} thousand scaled units; current period turnover {item['q1_2023_revenue_millions'] * 1000:.0f} thousand scaled units. Filed no later than {CUTOFF}.",
            "truth": truth, "naive_point": signal, "naive_half": max(5.0, abs(signal) * 0.75),
        })
    materialize_pair(
        root=units, snapshot_path=snapshot_path, question_id="proxy-09-segment-growth-rank",
        origin="20230428", cutoff=CUTOFF, resolution=RESOLUTION, split="time_forward_test",
        target_type="ranking", target_names={"explicit": "next_quarter_segment_growth_rank", "transformed": "forward_component_turnover_order"},
        family_names={"explicit": "segment_growth", "transformed": "component_turnover_change"}, unit="growth_percent",
        prompt="Rank the six reportable segments by next-quarter year-over-year revenue growth; rank 1 is highest.",
        license_text=LICENSE, source_name="SEC EDGAR inline XBRL filings", rows=rows,
    )
    print("proxy-09-segment-growth-rank", len(rows))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--snapshot", type=Path, default=Path("proxy-benchmark/sources/proxy-09-segments-2023.json"))
    parser.add_argument("--units", type=Path, default=Path("proxy-benchmark/units"))
    args = parser.parse_args()
    if args.raw_dir:
        build_snapshot(args.raw_dir, args.snapshot)
    build(args.snapshot, args.units)


if __name__ == "__main__":
    main()
