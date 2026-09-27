#!/usr/bin/env python3
"""Build recent FOMC inter-meeting outcomes from official public sources."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

FED = "https://www.federalreserve.gov"
POLICY_ACTIONS_URL = f"{FED}/monetarypolicy/openmarket.htm"
TREASURY_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve&"
    "field_tdr_date_value={year}&page&_format=csv"
)
TENORS = {"UST2Y": "2 Yr", "UST3Y": "3 Yr", "UST5Y": "5 Yr", "UST7Y": "7 Yr", "UST10Y": "10 Yr", "UST30Y": "30 Yr"}


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def visible_text(raw_html: str) -> str:
    parser = TextParser()
    parser.feed(raw_html)
    return " ".join(" ".join(parser.parts).split())


def fetch(url: str, cache: Path) -> str:
    path = cache / f"{hashlib.sha256(url.encode()).hexdigest()}.html"
    if path.exists():
        return path.read_text(errors="replace")
    request = Request(url, headers={"User-Agent": "Agenthon research dataset builder; public official data"})
    with urlopen(request, timeout=60) as response:
        content = response.read().decode("utf-8-sig", "replace")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return content


def decision_dates(cache: Path, start_year: int, end_year: int) -> list[date]:
    decisions: set[date] = set()
    for year in range(start_year, end_year + 1):
        page = f"{FED}/newsevents/pressreleases/{year}-press-fomc.htm"
        raw = fetch(page, cache)
        for href, label in re.findall(r"href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", raw, re.I | re.S):
            if "fomc statement" not in visible_text(label).lower():
                continue
            match = re.search(r"monetary(20\d{6})a\.htm", urljoin(page, html.unescape(href)))
            if match:
                decisions.add(datetime.strptime(match.group(1), "%Y%m%d").date())
    return sorted(decisions)


def policy_changes(cache: Path, start_year: int, end_year: int) -> dict[date, float]:
    raw = fetch(POLICY_ACTIONS_URL, cache)
    actions: dict[date, float] = {}
    for year in range(start_year, end_year + 1):
        match = re.search(
            rf'<a id="{year}".*?<h4>{year}</h4>(.*?)(?:Back to year navigation)',
            raw,
            re.I | re.S,
        )
        if not match:
            continue
        for table_row in re.findall(r"<tr>(.*?)</tr>", match.group(1), re.I | re.S):
            cells = [visible_text(item).strip() for item in re.findall(r"<td[^>]*>(.*?)</td>", table_row, re.I | re.S)]
            if len(cells) < 4:
                continue
            try:
                effective = datetime.strptime(f"{cells[0]} {year}", "%B %d %Y").date()
                actions[effective] = float(cells[1]) - float(cells[2])
            except ValueError:
                continue
    return actions


def treasury_rows(folder: Path) -> tuple[dict[date, dict[str, float]], dict[str, str]]:
    rates: dict[date, dict[str, float]] = {}
    checksums: dict[str, str] = {}
    for path in sorted(folder.glob("*.csv")):
        raw = path.read_bytes()
        checksums[path.name] = hashlib.sha256(raw).hexdigest()
        for row in csv.DictReader(raw.decode("utf-8-sig").splitlines()):
            try:
                observed = datetime.strptime(row["Date"], "%m/%d/%Y").date()
                rates[observed] = {entity: float(row[column]) for entity, column in TENORS.items()}
            except (KeyError, TypeError, ValueError):
                continue
    return rates, checksums


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--treasury", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--start-year", type=int, default=2022)
    parser.add_argument("--end-year", type=int, default=2026)
    args = parser.parse_args()

    decisions = decision_dates(args.cache, args.start_year, args.end_year)
    actions = policy_changes(args.cache, args.start_year, args.end_year)
    rates, checksums = treasury_rows(args.treasury)
    days = sorted(rates)
    events = []
    for index, decision in enumerate(decisions[:-1]):
        if not args.start_year <= decision.year <= args.end_year:
            continue
        next_decision = decisions[index + 1]
        start = next((day for day in days if day > decision), None)
        resolution = next((day for day in reversed(days) if day < next_decision), None)
        if start is None or resolution is None or resolution <= start:
            continue
        policy_change = actions.get(decision + timedelta(days=1), 0.0)
        events.append({
            "decision_date": decision.isoformat(),
            "next_decision_date": next_decision.isoformat(),
            "start_date": start.isoformat(),
            "resolution_date": resolution.isoformat(),
            "policy_change_bps": policy_change,
            "policy_direction": 1 if policy_change > 0 else -1 if policy_change < 0 else 0,
            "start_yields_pct": rates[start],
            "yield_changes_bps": {
                entity: round((rates[resolution][entity] - rates[start][entity]) * 100.0, 10)
                for entity in TENORS
            },
        })
    report = {
        "source": "Federal Reserve FOMC annual indexes and policy-actions table; U.S. Treasury daily par-yield CSVs",
        "license": "Public domain (U.S. government works)",
        "source_urls": {
            "fomc_index_template": f"{FED}/newsevents/pressreleases/{{year}}-press-fomc.htm",
            "policy_actions": POLICY_ACTIONS_URL,
            "treasury_template": TREASURY_URL,
        },
        "built_at": date.today().isoformat(),
        "start_year": args.start_year,
        "end_year": args.end_year,
        "treasury_file_sha256": checksums,
        "event_count": len(events),
        "events": events,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"event_count": len(events), "first": events[0]["decision_date"], "last": events[-1]["decision_date"]}, indent=2))


if __name__ == "__main__":
    main()
