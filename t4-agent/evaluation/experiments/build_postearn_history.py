#!/usr/bin/env python3
"""Build historical after-close earnings abnormal returns from free public data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TICKERS = ("AAPL", "AMZN", "META")


def announcement_rows(path: Path) -> list[dict[str, str]]:
    usable = "\n".join(line for line in path.read_text(encoding="utf-8-sig").splitlines() if not line.startswith("#"))
    rows = []
    seen = set()
    for row in csv.DictReader(io.StringIO(usable)):
        key = (row["ticker"], row["announcement_date"])
        if (
            row["ticker"] in TICKERS
            and "2018-01-01" <= row["announcement_date"] <= "2023-12-31"
            and row["session"] == "after_close"
            and row["date_uncertain"] == "no"
            and key not in seen
        ):
            seen.add(key)
            rows.append(row)
    return sorted(rows, key=lambda row: (row["announcement_date"], row["ticker"]))


def unix(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())


def prices(symbol: str, cache: Path) -> dict[str, float]:
    path = cache / f"{symbol}.json"
    if not path.exists():
        query = urlencode({
            "period1": unix("2017-12-01"),
            "period2": unix("2024-03-01"),
            "interval": "1d",
            "events": "div,splits",
        })
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}"
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 Agenthon research"})
        with urlopen(request, timeout=30) as response:
            content = response.read()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    result = json.loads(path.read_text())["chart"]["result"][0]
    adjusted = result["indicators"]["adjclose"][0]["adjclose"]
    output = {}
    for stamp, value in zip(result["timestamp"], adjusted):
        if value is not None:
            output[datetime.fromtimestamp(stamp, timezone.utc).date().isoformat()] = float(value)
    return output


def next_session(series: dict[str, float], day: str) -> str | None:
    return next((item for item in sorted(series) if item > day), None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--announcements", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source_rows = announcement_rows(args.announcements)
    market = {symbol: prices(symbol, args.cache) for symbol in (*TICKERS, "SPY")}
    events = []
    for row in source_rows:
        ticker = row["ticker"]
        start = row["announcement_date"]
        end = next_session(market[ticker], start)
        if start not in market[ticker] or start not in market["SPY"] or end is None or end not in market["SPY"]:
            continue
        company_return = 100.0 * (market[ticker][end] / market[ticker][start] - 1.0)
        benchmark_return = 100.0 * (market["SPY"][end] / market["SPY"][start] - 1.0)
        abnormal = company_return - benchmark_return
        label = "positive_reaction" if abnormal > 1.0 else "negative_reaction" if abnormal < -1.0 else "flat"
        events.append({
            "ticker": ticker,
            "announcement_date": start,
            "resolution_date": end,
            "label": label,
            "abnormal_return_pct": abnormal,
            "company_return_pct": company_return,
            "benchmark_return_pct": benchmark_return,
            "accession": row["accession"],
            "sec_url": row["sec_url"],
            "session": row["session"],
        })
    document = {
        "built_at": date.today().isoformat(),
        "announcement_source": "https://quant500.com/api/descarga/anuncios.csv",
        "announcement_source_sha256": hashlib.sha256(args.announcements.read_bytes()).hexdigest(),
        "announcement_license": "CC0 1.0",
        "price_source": "https://query1.finance.yahoo.com/v8/finance/chart/",
        "definition": "adjusted-close return from after-close announcement date to next session minus SPY over the same dates",
        "tickers": list(TICKERS),
        "event_count": len(events),
        "events": events,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps({"source_rows": len(source_rows), "events": len(events)}, indent=2))


if __name__ == "__main__":
    main()
