#!/usr/bin/env python3
"""Build an untouched 2024-2025 earnings-reaction confirmation panel."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def unix(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())


def prices(symbol: str, cache: Path) -> dict[str, float]:
    path = cache / f"{symbol}.json"
    if not path.exists():
        query = urlencode(
            {
                "period1": unix("2023-12-01"),
                "period2": unix("2026-02-15"),
                "interval": "1d",
                "events": "div,splits",
            }
        )
        request = Request(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}",
            headers={"User-Agent": "Mozilla/5.0 Agenthon research"},
        )
        with urlopen(request, timeout=30) as response:
            content = response.read()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    result = json.loads(path.read_text())["chart"]["result"][0]
    adjusted = result["indicators"]["adjclose"][0]["adjclose"]
    return {
        datetime.fromtimestamp(stamp, timezone.utc).date().isoformat(): float(value)
        for stamp, value in zip(result["timestamp"], adjusted)
        if value is not None
    }


def next_session(series: dict[str, float], day: str) -> str | None:
    return next((item for item in sorted(series) if item > day), None)


def announcements(path: Path, tickers: set[str]) -> list[dict[str, str]]:
    usable = "\n".join(
        line for line in path.read_text(encoding="utf-8-sig").splitlines() if not line.startswith("#")
    )
    rows = []
    seen = set()
    for row in csv.DictReader(io.StringIO(usable)):
        key = (row["ticker"], row["announcement_date"])
        if (
            row["ticker"] in tickers
            and "2024-01-01" <= row["announcement_date"] <= "2025-12-31"
            and row["session"] == "after_close"
            and row["date_uncertain"] == "no"
            and key not in seen
        ):
            seen.add(key)
            rows.append(row)
    return sorted(rows, key=lambda item: (item["announcement_date"], item["ticker"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--announcements", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    history = json.loads(args.history.read_text())
    tickers = set(history["selected_tickers"])
    source_rows = announcements(args.announcements, tickers)
    market: dict[str, dict[str, float]] = {}
    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(prices, ticker, args.cache): ticker for ticker in sorted(tickers | {"SPY"})}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                market[ticker] = future.result()
            except Exception as exc:  # pragma: no cover - network result is recorded
                failures[ticker] = f"{type(exc).__name__}: {str(exc)[:160]}"

    events = []
    spy = market.get("SPY", {})
    for row in source_rows:
        ticker = row["ticker"]
        series = market.get(ticker)
        if not series:
            continue
        start = row["announcement_date"]
        end = next_session(series, start)
        if start not in series or start not in spy or end is None or end not in spy:
            continue
        company_return = 100.0 * (series[end] / series[start] - 1.0)
        benchmark_return = 100.0 * (spy[end] / spy[start] - 1.0)
        abnormal = company_return - benchmark_return
        events.append(
            {
                "ticker": ticker,
                "announcement_date": start,
                "resolution_date": end,
                "label": (
                    "positive_reaction"
                    if abnormal > 1.0
                    else "negative_reaction"
                    if abnormal < -1.0
                    else "flat"
                ),
                "abnormal_return_pct": abnormal,
                "company_return_pct": company_return,
                "benchmark_return_pct": benchmark_return,
                "accession": row["accession"],
                "sec_url": row["sec_url"],
                "session": row["session"],
            }
        )

    raw_hash = hashlib.sha256()
    for path in sorted(args.cache.glob("*.json")):
        raw_hash.update(path.name.encode())
        raw_hash.update(path.read_bytes())
    document = {
        "built_at": date.today().isoformat(),
        "history_universe_sha256": hashlib.sha256(args.history.read_bytes()).hexdigest(),
        "announcement_source": "https://quant500.com/api/descarga/anuncios.csv",
        "announcement_source_sha256": hashlib.sha256(args.announcements.read_bytes()).hexdigest(),
        "announcement_license": "CC0 1.0",
        "price_source": "https://query1.finance.yahoo.com/v8/finance/chart/",
        "selection": "The 88 ticker-resolvable companies fixed by the 2018-2023 panel before confirmation outcomes were inspected.",
        "requested_tickers": sorted(tickers),
        "price_failures": dict(sorted(failures.items())),
        "raw_price_cache_sha256": raw_hash.hexdigest(),
        "event_count": len(events),
        "events": events,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps({"source_rows": len(source_rows), "events": len(events), "failures": len(failures)}, indent=2))


if __name__ == "__main__":
    main()
