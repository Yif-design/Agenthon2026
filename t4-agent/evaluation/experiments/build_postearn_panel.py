#!/usr/bin/env python3
"""Build a deterministic 100-company earnings-reaction calibration panel."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from build_postearn_history import next_session, prices


def rows_and_tickers(path: Path, size: int) -> tuple[list[dict[str, str]], list[str]]:
    usable = "\n".join(line for line in path.read_text(encoding="utf-8-sig").splitlines() if not line.startswith("#"))
    rows = []
    seen = set()
    for row in csv.DictReader(io.StringIO(usable)):
        key = (row["ticker"], row["announcement_date"])
        if (
            "2018-01-01" <= row["announcement_date"] <= "2023-12-31"
            and row["session"] == "after_close"
            and row["date_uncertain"] == "no"
            and key not in seen
        ):
            seen.add(key)
            rows.append(row)
    counts = Counter(row["ticker"] for row in rows)
    eligible = sorted(ticker for ticker, count in counts.items() if 23 <= count <= 25)
    selected = eligible[:size]
    return [row for row in rows if row["ticker"] in selected], selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--announcements", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--companies", type=int, default=100)
    args = parser.parse_args()
    source_rows, selected = rows_and_tickers(args.announcements, args.companies)

    market = {"SPY": prices("SPY", args.cache)}
    failures = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(prices, ticker, args.cache): ticker for ticker in selected}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                market[ticker] = future.result()
            except Exception as exc:  # noqa: BLE001 - dataset records every failed symbol
                failures[ticker] = f"{type(exc).__name__}: {str(exc)[:160]}"

    events = []
    for row in sorted(source_rows, key=lambda item: (item["announcement_date"], item["ticker"])):
        ticker = row["ticker"]
        if ticker not in market:
            continue
        start = row["announcement_date"]
        end = next_session(market[ticker], start)
        if start not in market[ticker] or start not in market["SPY"] or end is None or end not in market["SPY"]:
            continue
        company_return = 100.0 * (market[ticker][end] / market[ticker][start] - 1.0)
        benchmark_return = 100.0 * (market["SPY"][end] / market["SPY"][start] - 1.0)
        abnormal = company_return - benchmark_return
        events.append({
            "ticker": ticker,
            "announcement_date": start,
            "resolution_date": end,
            "label": "positive_reaction" if abnormal > 1.0 else "negative_reaction" if abnormal < -1.0 else "flat",
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
        "selection": "Alphabetical first 100 tickers among companies with 23-25 unique reliable after-close rows in 2018-2023; selection does not inspect returns",
        "selected_tickers": selected,
        "price_failures": dict(sorted(failures.items())),
        "event_count": len(events),
        "events": events,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps({"selected": len(selected), "failures": len(failures), "events": len(events)}, indent=2))


if __name__ == "__main__":
    main()
