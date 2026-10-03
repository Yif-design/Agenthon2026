#!/usr/bin/env python3
"""Build aligned five-week COT positioning targets from the official CFTC API."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
MARKETS = {
    "CORN_CBT": "002602",
    "ES_SP500": "13874A",
    "EURO_FX": "099741",
    "GOLD_CMX": "088691",
    "JPY_CME": "097741",
    "NATGAS_NYMEX": "023651",
    "SILVER_CMX": "084691",
    "UST_10Y": "043602",
    "UST_2Y": "042601",
    "WTI_NYMEX": "067651",
}


def fetch(cache: Path) -> list[dict]:
    if not cache.exists():
        codes = ",".join(f"'{code}'" for code in MARKETS.values())
        query = urlencode({
            "$select": "report_date_as_yyyy_mm_dd,cftc_contract_market_code,market_and_exchange_names,open_interest_all,noncomm_positions_long_all,noncomm_positions_short_all",
            "$where": f"cftc_contract_market_code in({codes}) AND report_date_as_yyyy_mm_dd between '2015-01-01T00:00:00.000' and '2023-12-31T00:00:00.000'",
            "$order": "report_date_as_yyyy_mm_dd,cftc_contract_market_code",
            "$limit": 50000,
        })
        request = Request(f"{API}?{query}", headers={"User-Agent": "Agenthon research"})
        with urlopen(request, timeout=60) as response:
            content = response.read()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(content)
    return json.loads(cache.read_text())


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    raw = fetch(args.cache)
    reverse = {code: entity for entity, code in MARKETS.items()}
    series: dict[str, dict[date, dict]] = {entity: {} for entity in MARKETS}
    for row in raw:
        entity = reverse.get(row["cftc_contract_market_code"])
        if entity is None:
            continue
        day = datetime.fromisoformat(row["report_date_as_yyyy_mm_dd"].replace("Z", "+00:00")).date()
        oi = float(row["open_interest_all"])
        net = float(row["noncomm_positions_long_all"]) - float(row["noncomm_positions_short_all"])
        series[entity][day] = {"open_interest": oi, "net": net, "net_pct_oi": 100.0 * net / oi}

    common_dates = sorted(set.intersection(*(set(values) for values in series.values())))
    groups = []
    for start in common_dates:
        prior = start - timedelta(days=28)
        end = start + timedelta(days=35)
        if prior not in common_dates or end not in common_dates:
            continue
        rows = []
        for entity in MARKETS:
            current = series[entity][start]
            earlier = series[entity][prior]
            future = series[entity][end]
            history = [series[entity][day]["net_pct_oi"] for day in common_dates if start - timedelta(days=175) <= day <= start]
            trailing = 100.0 * (current["net"] - earlier["net"]) / current["open_interest"]
            truth = 100.0 * (future["net"] - current["net"]) / current["open_interest"]
            crowd_cutoff = percentile([abs(value) for value in history], 0.90)
            rows.append({
                "entity_id": entity,
                "cftc_contract_market_code": MARKETS[entity],
                "current_net_pct_oi": current["net_pct_oi"],
                "trailing_4wk_net_change_pct_oi": trailing,
                "history_pstdev_pct_oi": statistics.pstdev(history) if len(history) > 1 else 0.0,
                "crowded": abs(current["net_pct_oi"]) >= crowd_cutoff,
                "target_5wk_change_pct_start_oi": truth,
            })
        groups.append({"start_date": start.isoformat(), "resolution_date": end.isoformat(), "rows": rows})

    document = {
        "built_at": date.today().isoformat(),
        "source": API,
        "raw_sha256": hashlib.sha256(args.cache.read_bytes()).hexdigest(),
        "market_codes": MARKETS,
        "target": "(noncommercial net at t+5 weeks - net at t) / open interest at t * 100",
        "group_count": len(groups),
        "groups": groups,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps({"raw_rows": len(raw), "groups": len(groups)}, indent=2))


if __name__ == "__main__":
    main()
