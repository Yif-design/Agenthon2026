#!/usr/bin/env python3
"""Build a cutoff-safe nominal coupon auction history from official Treasury data."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import urllib.parse
from datetime import date
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"
TENORS = {"2-Year", "3-Year", "5-Year", "7-Year", "10-Year", "20-Year", "30-Year"}
END_DATE = "2024-10-31"
FIELDS = [
    "cusip",
    "security_type",
    "security_term",
    "auction_date",
    "issue_date",
    "announcemt_date",
    "bid_to_cover_ratio",
    "offering_amt",
    "original_security_term",
    "reopening",
    "total_accepted",
    "total_tendered",
    "indirect_bidder_accepted",
    "direct_bidder_accepted",
    "primary_dealer_accepted",
    "floating_rate",
    "inflation_index_security",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache",
        type=Path,
        default=PROJECT / "evaluation/cache/auction/official_2010_2024-10-31.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT / "evaluation/datasets/auction/nominal_coupon_2010_2024-10-31.json",
    )
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args()


def number(value: object) -> float | None:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return out


def fetch(cache: Path, refresh: bool) -> dict:
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    params = {
        "fields": ",".join(FIELDS),
        "filter": f"auction_date:gte:2010-01-01,auction_date:lte:{END_DATE},security_type:in:(Note,Bond)",
        "page[size]": "10000",
    }
    url = API + "?" + urllib.parse.urlencode(params, safe=":,()")
    response = subprocess.run(
        [
            "curl",
            "--fail",
            "--location",
            "--silent",
            "--show-error",
            "--max-time",
            "90",
            "--user-agent",
            "Agenthon2026-research/1.0",
            url,
        ],
        check=True,
        capture_output=True,
    )
    payload = json.loads(response.stdout)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def normalize(payload: dict) -> dict:
    raw_rows = payload.get("data")
    if not isinstance(raw_rows, list):
        raise ValueError("Treasury response has no data list")
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    total_count = int(meta.get("total-count", len(raw_rows)))
    total_pages = int(meta.get("total-pages", 1))
    if total_count != len(raw_rows) or total_pages != 1:
        raise ValueError(
            f"incomplete Treasury response: rows={len(raw_rows)} total-count={total_count} "
            f"total-pages={total_pages}"
        )
    rows = []
    skips: dict[str, int] = {}

    def skip(reason: str) -> None:
        skips[reason] = skips.get(reason, 0) + 1

    for raw in raw_rows:
        if raw.get("floating_rate") == "Yes" or raw.get("inflation_index_security") == "Yes":
            skip("floating_or_inflation_indexed")
            continue
        tenor = raw.get("original_security_term") or raw.get("security_term")
        if tenor not in TENORS:
            skip("non_target_tenor")
            continue
        auction_date = str(raw.get("auction_date") or "")
        announcement_date = str(raw.get("announcemt_date") or "")
        try:
            if date.fromisoformat(announcement_date) > date.fromisoformat(auction_date):
                skip("announcement_after_auction")
                continue
        except ValueError:
            skip("bad_date")
            continue
        btc = number(raw.get("bid_to_cover_ratio"))
        accepted = number(raw.get("total_accepted"))
        tendered = number(raw.get("total_tendered"))
        offering = number(raw.get("offering_amt"))
        if btc is None or accepted in (None, 0.0) or tendered is None or offering is None:
            skip("missing_required_result")
            continue
        simple_total_ratio = tendered / accepted
        indirect = number(raw.get("indirect_bidder_accepted"))
        direct = number(raw.get("direct_bidder_accepted"))
        dealer = number(raw.get("primary_dealer_accepted"))
        rows.append(
            {
                "auction_date": auction_date,
                "announcement_date": announcement_date,
                "cusip": raw.get("cusip"),
                "tenor": tenor,
                "security_term_at_auction": raw.get("security_term"),
                "reopening": raw.get("reopening") == "Yes",
                "offering_amount_usd_bn": offering / 1_000_000_000,
                "bid_to_cover_ratio": btc,
                "total_tendered_to_total_accepted": simple_total_ratio,
                "difference_from_reported_ratio": simple_total_ratio - btc,
                "total_tendered_usd_bn": tendered / 1_000_000_000,
                "total_accepted_usd_bn": accepted / 1_000_000_000,
                "indirect_accepted_share": None if indirect is None else indirect / accepted,
                "direct_accepted_share": None if direct is None else direct / accepted,
                "primary_dealer_accepted_share": None if dealer is None else dealer / accepted,
            }
        )
    rows.sort(key=lambda row: (row["auction_date"], row["tenor"], row["cusip"] or ""))
    counts = {tenor: sum(row["tenor"] == tenor for row in rows) for tenor in sorted(TENORS)}
    return {
        "schema_version": 1,
        "source": "U.S. Treasury Fiscal Data Auctions Query",
        "source_endpoint": API,
        "source_page": "https://www.treasurydirect.gov/auctions/auction-query/",
        "source_retrieved_date": "2026-09-27",
        "source_response_rows": len(raw_rows),
        "source_payload_sha256": hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "license_note": "Official U.S. government auction records; source and retrieval date disclosed.",
        "raw_filter": f"2010-01-01 through {END_DATE}; Note/Bond",
        "future_information_check": (
            "For each forecast row, comparison features use only earlier auction outcomes plus the "
            "target auction's pre-auction announcement fields. Current-auction result fields are outcomes only."
        ),
        "rows": len(rows),
        "counts_by_tenor": counts,
        "skipped": skips,
        "data": rows,
    }


def main() -> None:
    args = parse_args()
    result = normalize(fetch(args.cache, args.refresh))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rows": result["rows"], "counts_by_tenor": result["counts_by_tenor"], "skipped": result["skipped"]}, indent=2))


if __name__ == "__main__":
    main()
