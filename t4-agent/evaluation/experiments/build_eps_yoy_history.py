#!/usr/bin/env python3
"""Build a cutoff-auditable quarterly diluted-EPS year-over-year panel.

The source is the SEC Company Concept API.  Only standard us-gaap diluted EPS
facts from approximately one-quarter 10-Q contexts are eligible.  Comparative
facts are repeated in later filings, so the builder keeps the earliest filing
for each reporting period and records both filing dates used by every pair.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any


TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
CONCEPT_URL = (
    "https://data.sec.gov/api/xbrl/companyconcept/"
    "CIK{cik:010d}/us-gaap/EarningsPerShareDiluted.json"
)


def download(url: str, path: Path, user_agent: str) -> bytes:
    if path.exists():
        return path.read_bytes()
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return payload


def span_days(row: dict[str, Any]) -> int:
    return (date.fromisoformat(row["end"]) - date.fromisoformat(row["start"])).days


def quarter_facts(document: dict[str, Any]) -> list[dict[str, Any]]:
    units = document.get("units", {}).get("USD/shares", [])
    eligible_rows = []
    for row in units:
        try:
            eligible = (
                row.get("form") in {"10-Q", "10-Q/A"}
                and 60 <= span_days(row) <= 120
                and isinstance(row.get("val"), (int, float))
                and all(row.get(field) for field in ("start", "end", "filed", "accn"))
            )
        except (KeyError, TypeError, ValueError):
            eligible = False
        if not eligible:
            continue
        eligible_rows.append(row)
    return eligible_rows


def original_quarters(eligible_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    periods: dict[tuple[str, str], dict[str, Any]] = {}
    for row in eligible_rows:
        key = (row["start"], row["end"])
        order = (row["filed"], row.get("form") != "10-Q", row["accn"])
        incumbent = periods.get(key)
        if incumbent is None:
            periods[key] = row
        else:
            incumbent_order = (
                incumbent["filed"],
                incumbent.get("form") != "10-Q",
                incumbent["accn"],
            )
            if order < incumbent_order:
                periods[key] = row
    return sorted(periods.values(), key=lambda row: (row["end"], row["filed"]))


def pair_quarters(
    ticker: str,
    cik: int,
    quarters: list[dict[str, Any]],
    all_facts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    pairs = []
    audit = {"missing_target_comparator": 0, "recast_or_split_mismatch": 0, "near_zero_prior": 0}
    for index, target in enumerate(quarters):
        target_year = date.fromisoformat(target["end"]).year
        if not 2015 <= target_year <= 2025:
            continue
        candidates = []
        for prior in quarters[:index]:
            gap = (date.fromisoformat(target["end"]) - date.fromisoformat(prior["end"])).days
            if 330 <= gap <= 400 and prior["filed"] < target["start"]:
                candidates.append((abs(gap - 365), prior["end"], prior))
        if not candidates:
            continue
        prior = min(candidates, key=lambda item: (item[0], item[1]))[2]
        prior_eps = float(prior["val"])
        target_eps = float(target["val"])
        comparators = [
            float(row["val"])
            for row in all_facts
            if row["accn"] == target["accn"]
            and row["start"] == prior["start"]
            and row["end"] == prior["end"]
        ]
        if not comparators:
            audit["missing_target_comparator"] += 1
            continue
        comparator = min(comparators, key=lambda value: abs(value - prior_eps))
        comparability_tolerance = max(0.01, 0.01 * abs(prior_eps))
        if abs(comparator - prior_eps) > comparability_tolerance:
            # Stock splits and retrospective accounting changes can make the original
            # prior EPS incomparable with the target-period basis.  Exclude rather
            # than calibrating interval width on a unit mismatch.
            audit["recast_or_split_mismatch"] += 1
            continue
        # The relative-width model is undefined around zero.  This is a cutoff-safe
        # feature filter because prior EPS was public before the target quarter.
        if abs(prior_eps) < 0.05:
            audit["near_zero_prior"] += 1
            continue
        pairs.append({
            "ticker": ticker,
            "cik": f"{cik:010d}",
            "prior_start": prior["start"],
            "prior_end": prior["end"],
            "prior_filed": prior["filed"],
            "prior_accession": prior["accn"],
            "prior_eps": prior_eps,
            "target_start": target["start"],
            "target_end": target["end"],
            "target_filed": target["filed"],
            "target_accession": target["accn"],
            "target_eps": target_eps,
            "target_filing_comparable_prior_eps": comparator,
            "comparability_tolerance": comparability_tolerance,
            "source_url": CONCEPT_URL.format(cik=cik),
        })
    return pairs, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--user-agent", required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)

    universe = json.loads(args.universe.read_text())
    tickers = sorted({row["ticker"].upper() for row in universe["events"]})
    ticker_payload = download(TICKER_MAP_URL, args.cache / "company_tickers.json", args.user_agent)
    ticker_rows = json.loads(ticker_payload)
    ticker_map = {row["ticker"].upper(): row for row in ticker_rows.values()}
    missing_tickers = sorted(set(tickers) - set(ticker_map))

    def fetch(ticker: str) -> tuple[str, str | None]:
        cik = int(ticker_map[ticker]["cik_str"])
        try:
            download(
                CONCEPT_URL.format(cik=cik),
                args.cache / f"{ticker}.json",
                args.user_agent,
            )
            return ticker, None
        except Exception as exc:  # noqa: BLE001 - every source failure is recorded
            return ticker, f"{type(exc).__name__}: {str(exc)[:200]}"

    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 6))) as executor:
        for ticker, error in executor.map(fetch, [t for t in tickers if t in ticker_map]):
            if error:
                failures[ticker] = error
            time.sleep(0.03)

    rows = []
    source_hashes = {}
    company_counts = {}
    for ticker in tickers:
        if ticker not in ticker_map or ticker in failures:
            continue
        cik = int(ticker_map[ticker]["cik_str"])
        path = args.cache / f"{ticker}.json"
        payload = path.read_bytes()
        source_hashes[ticker] = hashlib.sha256(payload).hexdigest()
        facts = quarter_facts(json.loads(payload))
        quarters = original_quarters(facts)
        pairs, audit = pair_quarters(ticker, cik, quarters, facts)
        company_counts[ticker] = {
            "eligible_quarters": len(quarters),
            "pairs": len(pairs),
            **audit,
        }
        rows.extend(pairs)

    rows.sort(key=lambda row: (row["target_end"], row["ticker"]))
    document = {
        "built_at": date.today().isoformat(),
        "source": "SEC EDGAR Company Concept API, us-gaap:EarningsPerShareDiluted",
        "source_documentation": "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
        "ticker_map_url": TICKER_MAP_URL,
        "ticker_map_sha256": hashlib.sha256(ticker_payload).hexdigest(),
        "universe_file": str(args.universe),
        "universe_sha256": hashlib.sha256(args.universe.read_bytes()).hexdigest(),
        "selection": (
            "All ticker-resolvable companies in the pre-existing post-earnings panel; standard "
            "diluted-EPS 10-Q facts with 60-120 day contexts; earliest filing per period; same-company "
            "period pairs 330-400 days apart; prior filed before target start; abs(prior EPS) >= 0.05"
            "; target filing must repeat prior-period EPS within max(0.01, 1%) of its original value"
        ),
        "years": [2015, 2025],
        "tickers_requested": len(tickers),
        "tickers_built": len(company_counts),
        "missing_tickers": missing_tickers,
        "download_failures": dict(sorted(failures.items())),
        "source_sha256_by_ticker": dict(sorted(source_hashes.items())),
        "company_counts": dict(sorted(company_counts.items())),
        "row_count": len(rows),
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps({
        "tickers_requested": len(tickers),
        "tickers_built": len(company_counts),
        "failures": len(failures),
        "rows": len(rows),
    }, indent=2))


if __name__ == "__main__":
    main()
