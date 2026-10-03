#!/usr/bin/env python3
"""Build a cutoff-safe monthly ALFRED revision panel for the public macro families.

The panel uses month-end snapshots.  A sample contains only revisions visible at
the cutoff snapshot; its outcome is the change visible in the next month-end
snapshot.  This is deliberately an experiment artifact, not runtime code.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import io
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from urllib.parse import urlencode


API = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
SERIES = ("DGORDER", "HOUST", "INDPRO", "PAYEMS", "PI", "RSAFS")


def month_shift(year: int, month: int, offset: int) -> tuple[int, int]:
    index = year * 12 + month - 1 + offset
    return index // 12, index % 12 + 1


def month_end(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def snapshot_dates(start_year: int, end_year: int) -> list[str]:
    return [
        month_end(year, month)
        for year in range(start_year, end_year + 1)
        for month in range(1, 13)
    ]


def month_index(value: str) -> int:
    year, month = (int(part) for part in value[:7].split("-"))
    return year * 12 + month - 1


def fetch_one(cache: Path, series_id: str, vintage: str) -> Path:
    target = cache / series_id / f"{vintage}.csv"
    if target.exists():
        return target
    query = urlencode(
        {
            "id": series_id,
            "cosd": "2012-01-01",
            "coed": "2024-12-01",
            "vintage_date": vintage,
        }
    )
    error: Exception | None = None
    for attempt in range(5):
        try:
            completed = subprocess.run(
                [
                    "curl",
                    "--fail",
                    "--location",
                    "--silent",
                    "--show-error",
                    "--max-time",
                    "30",
                    f"{API}?{query}",
                ],
                check=True,
                capture_output=True,
                timeout=35,
            )
            if not completed.stdout.startswith(b"observation_date,"):
                raise ValueError("ALFRED response is not a CSV series")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(completed.stdout)
            return target
        except Exception as exc:  # pragma: no cover - network retry
            error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed {series_id} at {vintage}: {error}")


def load(path: Path) -> dict[str, float]:
    rows = csv.DictReader(io.StringIO(path.read_text()))
    value_column = next(name for name in rows.fieldnames or [] if name != "observation_date")
    return {
        row["observation_date"]: float(row[value_column])
        for row in rows
        if row[value_column] not in ("", ".")
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--start-year", type=int, default=2014)
    parser.add_argument("--end-year", type=int, default=2024)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()

    vintages = snapshot_dates(args.start_year, args.end_year)
    jobs = [(series_id, vintage) for series_id in SERIES for vintage in vintages]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_one, args.cache, *job): job for job in jobs}
        for future in as_completed(futures):
            future.result()

    snapshots = {
        (series_id, vintage): load(args.cache / series_id / f"{vintage}.csv")
        for series_id, vintage in jobs
    }
    rows: list[dict[str, object]] = []
    for series_id in SERIES:
        first_seen: dict[str, int] = {}
        transitions: list[dict[str, object]] = []
        for index, vintage in enumerate(vintages[:-1]):
            current = snapshots[(series_id, vintage)]
            following = snapshots[(series_id, vintages[index + 1])]
            for ref_month, current_value in current.items():
                first_seen.setdefault(ref_month, index)
                next_value = following.get(ref_month)
                if next_value is None or next_value == current_value:
                    continue
                # Public frozen tables show only the recent release window, not
                # decades of observations changed by annual benchmark updates.
                ref_lag = month_index(vintage) - month_index(ref_month)
                if not 0 <= ref_lag <= 8:
                    continue
                age = index - first_seen[ref_month]
                transitions.append(
                    {
                        "cutoff_index": index,
                        "ref_month": ref_month[:7],
                        "revision_age": age,
                        "change": next_value - current_value,
                    }
                )

        for transition in transitions:
            cutoff_index = int(transition["cutoff_index"])
            history = [
                prior
                for prior in transitions
                if int(prior["cutoff_index"]) < cutoff_index
                and cutoff_index - int(prior["cutoff_index"]) <= 8
            ]
            if len(history) < 4:
                continue
            age_history = [
                float(prior["change"])
                for prior in history
                if prior["revision_age"] == transition["revision_age"]
            ]
            all_history = [float(prior["change"]) for prior in history]
            rows.append(
                {
                    "series_id": series_id,
                    "cutoff_vintage": vintages[cutoff_index],
                    "resolution_vintage": vintages[cutoff_index + 1],
                    "ref_month": transition["ref_month"],
                    "revision_age": transition["revision_age"],
                    "all_history_changes": all_history,
                    "age_history_changes": age_history,
                    "target_change": transition["change"],
                }
            )

    raw_hash = hashlib.sha256()
    actual_vintages: dict[str, str] = {}
    for series_id, vintage in jobs:
        path = args.cache / series_id / f"{vintage}.csv"
        raw_hash.update(path.relative_to(args.cache).as_posix().encode())
        raw_hash.update(path.read_bytes())
        actual_vintages[f"{series_id}/{vintage}"] = path.read_text().splitlines()[0].rsplit("_", 1)[-1]

    document = {
        "built_at": date.today().isoformat(),
        "source": API,
        "method": "Consecutive month-end ALFRED snapshots; each row predicts the next snapshot revision using only earlier transitions.",
        "caveat": "Month-end snapshots may combine multiple releases in a month and are an offline model-selection proxy, not an exact release-calendar reconstruction.",
        "series": list(SERIES),
        "requested_vintage_range": [vintages[0], vintages[-1]],
        "raw_cache_sha256": raw_hash.hexdigest(),
        "actual_vintage_headers_sha256": hashlib.sha256(
            json.dumps(actual_vintages, sort_keys=True).encode()
        ).hexdigest(),
        "row_count": len(rows),
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps({"downloads": len(jobs), "rows": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
