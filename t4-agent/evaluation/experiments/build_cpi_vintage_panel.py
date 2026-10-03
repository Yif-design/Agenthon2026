#!/usr/bin/env python3
"""Build cutoff-safe monthly CPI component samples from ALFRED vintages."""

from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import io
import json
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

API = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
SERIES = {
    "CPI_ALLITEMS": "CPIAUCSL",
    "CPI_APPAREL": "CPIAPPSL",
    "CPI_CORE": "CPILFESL",
    "CPI_ENERGY": "CPIENGSL",
    "CPI_FOOD": "CPIUFDSL",
    "CPI_GASOLINE": "CUSR0000SETB01",
    "CPI_MEDICAL": "CPIMEDSL",
    "CPI_NEWVEH": "CUSR0000SETA01",
    "CPI_SHELTER": "CUSR0000SAH1",
    "CPI_TRANSPSVC": "CUSR0000SAS4",
    "CPI_USEDCARS": "CUSR0000SETA02",
}


def month_shift(year: int, month: int, offset: int) -> tuple[int, int]:
    index = year * 12 + month - 1 + offset
    return index // 12, index % 12 + 1


def month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}-01"


def parse_month(value: str) -> tuple[int, int]:
    year, month = (int(part) for part in value.split("-"))
    if not 1 <= month <= 12:
        raise argparse.ArgumentTypeError("month must be YYYY-MM")
    return year, month


def vintages(start: tuple[int, int], end_ref: tuple[int, int]) -> list[str]:
    result = []
    year, month = start
    end = month_shift(*end_ref, 1)
    while (year, month) <= end:
        result.append(month_end(year, month))
        year, month = month_shift(year, month, 1)
    return result


def month_end(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def fetch_one(cache: Path, series_id: str, vintage: str, observation_end: str) -> Path:
    target = cache / series_id / f"{vintage}.csv"
    year, month, day = (int(part) for part in vintage.split("-"))
    day20 = cache / series_id / f"{year:04d}-{month:02d}-20.csv"
    audited_alias = (
        series_id == "CUSR0000SETA02"
        and day != 20
        and (2022, 1) <= (year, month) <= (2024, 1)
    )
    if audited_alias:
        # Official archive URLs show every release in this audited span occurred by day 14.
        # The day-20 and month-end information sets are therefore equivalent.
        if not day20.exists():
            fetch_one(cache, series_id, f"{year:04d}-{month:02d}-20", observation_end)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(day20, target)
        return target
    if target.exists():
        return target
    query = urlencode({
        "id": series_id,
        "cosd": "2013-01-01",
        "coed": observation_end,
        "vintage_date": vintage,
    })
    url = f"{API}?{query}"
    error = None
    for attempt in range(4):
        try:
            completed = subprocess.run(
                ["curl", "--fail", "--location", "--silent", "--show-error", "--max-time", "30", url],
                check=True,
                capture_output=True,
                timeout=35,
            )
            content = completed.stdout
            if not content.startswith(b"observation_date,"):
                raise ValueError("ALFRED response is not a CSV series")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            return target
        except Exception as exc:  # pragma: no cover - network retry
            error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed {series_id} at {vintage}: {error}")


def load(path: Path) -> dict[str, float]:
    rows = csv.DictReader(io.StringIO(path.read_text()))
    value_column = next(name for name in rows.fieldnames or [] if name != "observation_date")
    result = {}
    for row in rows:
        raw = row[value_column]
        if raw not in ("", "."):
            result[row["observation_date"]] = float(raw)
    return result


def changes(snapshot: dict[str, float], end_year: int, end_month: int, count: int) -> list[float]:
    result = []
    for offset in range(-count + 1, 1):
        year, month = month_shift(end_year, end_month, offset)
        prior_year, prior_month = month_shift(year, month, -1)
        current = snapshot.get(month_key(year, month))
        prior = snapshot.get(month_key(prior_year, prior_month))
        if current is not None and prior not in (None, 0.0):
            result.append(100.0 * (current / prior - 1.0))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--start-ref", type=parse_month, default=parse_month("2015-01"))
    parser.add_argument("--end-ref", type=parse_month, default=parse_month("2023-12"))
    args = parser.parse_args()

    requested_vintages = vintages(args.start_ref, args.end_ref)
    observation_end = month_key(*args.end_ref)
    jobs = [(series_id, vintage) for series_id in SERIES.values() for vintage in requested_vintages]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_one, args.cache, *job, observation_end): job for job in jobs}
        for future in as_completed(futures):
            future.result()

    snapshots = {
        (series_id, vintage): load(args.cache / series_id / f"{vintage}.csv")
        for series_id, vintage in jobs
    }
    rows = []
    year, month = args.start_ref
    while (year, month) <= args.end_ref:
        prior_vintage = month_end(year, month)
        release_year, release_month = month_shift(year, month, 1)
        target_vintage = month_end(release_year, release_month)
        for entity_id, series_id in SERIES.items():
            known = snapshots[(series_id, prior_vintage)]
            resolved = snapshots[(series_id, target_vintage)]
            history = changes(known, *month_shift(year, month, -1), 12)
            target_changes = changes(resolved, year, month, 1)
            if len(history) < 9 or not target_changes:
                continue
            rows.append({
                "ref_month": f"{year:04d}-{month:02d}",
                "cutoff_vintage": prior_vintage,
                "resolution_vintage": target_vintage,
                "entity_id": entity_id,
                "series_id": series_id,
                "known_mom_pct": history,
                "target_mom_pct": target_changes[-1],
            })
        year, month = month_shift(year, month, 1)

    raw_hash = hashlib.sha256()
    vintage_aliases = []
    for path in sorted(args.cache / series_id / f"{vintage}.csv" for series_id, vintage in jobs):
        raw_hash.update(path.relative_to(args.cache).as_posix().encode())
        raw_hash.update(path.read_bytes())
        header = path.read_text().splitlines()[0]
        actual_vintage = header.rsplit("_", 1)[-1]
        requested_vintage = path.stem.replace("-", "")
        if actual_vintage != requested_vintage:
            vintage_aliases.append({
                "series_id": path.parent.name,
                "requested_vintage": path.stem,
                "actual_vintage": f"{actual_vintage[:4]}-{actual_vintage[4:6]}-{actual_vintage[6:]}",
                "basis": "BLS archive shows the CPI release occurred by day 14; no intervening release.",
            })
    document = {
        "built_at": date.today().isoformat(),
        "source": API,
        "source_note": "Each target uses month-end ALFRED vintages immediately before and after its release.",
        "reference_month_range": [
            f"{args.start_ref[0]:04d}-{args.start_ref[1]:02d}",
            f"{args.end_ref[0]:04d}-{args.end_ref[1]:02d}",
        ],
        "raw_cache_sha256": raw_hash.hexdigest(),
        "equivalent_vintage_aliases": vintage_aliases,
        "series": SERIES,
        "row_count": len(rows),
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps({"downloads": len(jobs), "rows": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
