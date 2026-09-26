#!/usr/bin/env python3
"""Build a cutoff-safe FOMC inter-meeting yield dataset from official sources."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

FED = "https://www.federalreserve.gov"
TENORS = {"UST2Y": "2 Yr", "UST3Y": "3 Yr", "UST5Y": "5 Yr", "UST7Y": "7 Yr", "UST10Y": "10 Yr", "UST30Y": "30 Yr"}
CACHE_DIR: Path | None = None


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def fetch(url: str) -> str:
    cache_path = CACHE_DIR / f"{hashlib.sha256(url.encode()).hexdigest()}.html" if CACHE_DIR else None
    if cache_path and cache_path.exists():
        return cache_path.read_text()
    request = Request(url, headers={"User-Agent": "Agenthon research dataset builder; public official data"})
    with urlopen(request, timeout=30) as response:
        content = response.read().decode("utf-8", "replace")
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(content)
    return content


def visible_text(raw_html: str) -> str:
    parser = TextParser()
    parser.feed(raw_html)
    return " ".join(" ".join(parser.parts).split())


def statement_links() -> list[str]:
    links: set[str] = set()
    pattern = re.compile(r"href=[\"']([^\"']+)[\"'][^>]*>\s*Statement\s*</a>", re.I)
    for year in range(2000, 2021):
        page = f"{FED}/monetarypolicy/fomchistorical{year}.htm"
        links.update(urljoin(page, item) for item in pattern.findall(fetch(page)))

    page = f"{FED}/newsevents/pressreleases/2021-press-fomc.htm"
    raw = fetch(page)
    for href, label in re.findall(r"href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", raw, re.I | re.S):
        if "fomc statement" in visible_text(label).lower():
            links.add(urljoin(page, html.unescape(href)))
    return sorted(links, key=statement_date)


def statement_date(url: str) -> date:
    matches = re.findall(r"(20\d{6})", url)
    if not matches:
        raise ValueError(f"no YYYYMMDD date in {url}")
    return datetime.strptime(matches[-1], "%Y%m%d").date()


def number(text: str) -> float:
    text = text.strip().replace("−", "-").replace("–", "-").replace("‑", "-")
    if re.fullmatch(r"\d+\s+\d+/\d+", text):
        whole, fraction = text.split(None, 1)
        numerator, denominator = fraction.split("/", 1)
        return float(whole) + float(numerator) / float(denominator)
    if re.fullmatch(r"\d+-\d+/\d+", text):
        whole, fraction = text.split("-", 1)
        numerator, denominator = fraction.split("/", 1)
        return float(whole) + float(numerator) / float(denominator)
    if re.fullmatch(r"\d+/\d+", text):
        numerator, denominator = text.split("/", 1)
        return float(numerator) / float(denominator)
    return float(text)


def target_midpoint(text: str) -> float | None:
    normalized = text.replace("−", "-").replace("–", "-").replace("‑", "-")
    value = r"(?:\d+(?:\.\d+)?(?:[- ]\d+/\d+)?|\d+/\d+)"
    ranges = [
        rf"target range for the federal funds rate(?:\s+by\s+(?:\d+|{value})\s+(?:basis points|percentage point))?[,\s]+(?:at|to|of)\s+({value})\s+(?:percent\s+)?to\s+({value})\s+percent",
        rf"target range of\s+({value})\s+(?:percent\s+)?to\s+({value})\s+percent for the federal funds rate",
        rf"({value})\s+(?:percent\s+)?to\s+({value})\s+percent target range for the federal funds rate",
        rf"federal funds rate (?:in|at) a target range of\s+({value})\s+(?:percent\s+)?to\s+({value})\s+percent",
    ]
    for pattern in ranges:
        match = re.search(pattern, normalized, re.I)
        if match:
            return (number(match.group(1)) + number(match.group(2))) / 2.0
    singles = [
        rf"target for the federal funds rate(?:\s+(?:by\s+)?\d+\s+basis points)?\s+(?:unchanged\s+)?(?:at|to)\s+({value})\s+percent",
        rf"federal funds rate target(?:\s+(?:by\s+)?\d+\s+basis points)?\s+(?:at|to)\s+({value})\s+percent",
    ]
    for pattern in singles:
        match = re.search(pattern, normalized, re.I)
        if match:
            return number(match.group(1))
    return None


def treasury_rows(folder: Path) -> dict[date, dict[str, float]]:
    rows: dict[date, dict[str, float]] = {}
    for path in sorted(folder.glob("*.csv")):
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                day = datetime.strptime(row["Date"], "%m/%d/%Y").date()
                try:
                    rows[day] = {entity: float(row[column]) for entity, column in TENORS.items()}
                except (KeyError, TypeError, ValueError):
                    continue
    return rows


def next_after(days: list[date], value: date) -> date | None:
    return next((day for day in days if day > value), None)


def last_before(days: list[date], value: date) -> date | None:
    return next((day for day in reversed(days) if day < value), None)


def main() -> None:
    global CACHE_DIR
    parser = argparse.ArgumentParser()
    parser.add_argument("--treasury", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()
    CACHE_DIR = args.cache

    statements = []
    for url in statement_links():
        raw = fetch(url)
        text = visible_text(raw)
        statements.append({
            "date": statement_date(url),
            "url": url,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "target_midpoint_pct": target_midpoint(text),
        })

    rates = treasury_rows(args.treasury)
    days = sorted(rates)
    events = []
    previous_midpoint: float | None = None
    for index, current in enumerate(statements[:-1]):
        midpoint = current["target_midpoint_pct"]
        if midpoint is None:
            continue
        direction = 0 if previous_midpoint is None else (1 if midpoint > previous_midpoint else -1 if midpoint < previous_midpoint else 0)
        previous_midpoint = midpoint
        following = statements[index + 1]
        start = next_after(days, current["date"])
        end = last_before(days, following["date"])
        if start is None or end is None or end <= start:
            continue
        events.append({
            "decision_date": current["date"].isoformat(),
            "next_decision_date": following["date"].isoformat(),
            "start_date": start.isoformat(),
            "resolution_date": end.isoformat(),
            "statement_url": current["url"],
            "statement_text_sha256": current["text_sha256"],
            "target_midpoint_pct": midpoint,
            "policy_direction": direction,
            "start_yields_pct": rates[start],
            "yield_changes_bps": {entity: round((rates[end][entity] - rates[start][entity]) * 100.0, 10) for entity in TENORS},
        })

    missing = [item["date"].isoformat() for item in statements if item["target_midpoint_pct"] is None]
    document = {
        "source": "Federal Reserve policy statements and U.S. Treasury daily par-yield CSVs",
        "built_at": date.today().isoformat(),
        "statement_count": len(statements),
        "event_count": len(events),
        "missing_target_dates": missing,
        "events": events,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps({"statements": len(statements), "events": len(events), "missing_target_dates": missing}, indent=2))


if __name__ == "__main__":
    main()
