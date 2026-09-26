#!/usr/bin/env python3
"""Fit cutoff-safe 35-trading-day Treasury interval widths.

The script deliberately has no access to the 2022/2024 public-unit outcomes. It fits widths on
2000-2016 origins and selects one quantile on 2017-2021 origins. Public units are evaluated only
after this report is written and its checksum is recorded.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import date, datetime
from pathlib import Path

TENORS = {
    "UST2Y": "2 Yr",
    "UST3Y": "3 Yr",
    "UST5Y": "5 Yr",
    "UST7Y": "7 Yr",
    "UST10Y": "10 Yr",
    "UST30Y": "30 Yr",
}
CANDIDATE_QUANTILES = (0.80, 0.85, 0.90, 0.925, 0.95, 0.975, 0.99, 0.995)
HORIZON_TRADING_DAYS = 35
ORIGIN_STEP = 5
TRAIN_END = date(2016, 12, 31)
DEV_START = date(2017, 1, 1)
DEV_END = date(2021, 12, 31)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("empty quantile input")
    position = (len(ordered) - 1) * q
    lo = math.floor(position)
    hi = math.ceil(position)
    if lo == hi:
        return ordered[lo]
    weight = position - lo
    return ordered[lo] * (1 - weight) + ordered[hi] * weight


def load_series(root: Path) -> tuple[dict[str, list[tuple[date, float]]], dict[str, str]]:
    series: dict[str, dict[date, float]] = {entity: {} for entity in TENORS}
    checksums: dict[str, str] = {}
    paths = sorted(root.glob("*.csv"))
    if len(paths) != 22:
        raise ValueError(f"expected 22 annual Treasury files, found {len(paths)}")
    for path in paths:
        raw = path.read_bytes()
        checksums[path.name] = hashlib.sha256(raw).hexdigest()
        for row in csv.DictReader(raw.decode("utf-8-sig").splitlines()):
            observed = datetime.strptime(row["Date"], "%m/%d/%Y").date()
            for entity, column in TENORS.items():
                value = (row.get(column) or "").strip()
                if value:
                    series[entity][observed] = float(value)
    return {entity: sorted(values.items()) for entity, values in series.items()}, checksums


def changes(values: list[tuple[date, float]]) -> tuple[list[float], list[float]]:
    train: list[float] = []
    dev: list[float] = []
    last = len(values) - HORIZON_TRADING_DAYS
    for index in range(0, last, ORIGIN_STEP):
        origin_date, origin_value = values[index]
        _, future_value = values[index + HORIZON_TRADING_DAYS]
        move_bps = (future_value - origin_value) * 100.0
        if origin_date <= TRAIN_END:
            train.append(move_bps)
        elif DEV_START <= origin_date <= DEV_END:
            dev.append(move_bps)
    return train, dev


def main() -> None:
    args = parse_args()
    loaded, checksums = load_series(args.data)
    samples = {entity: changes(values) for entity, values in loaded.items()}
    battery = []
    for q in CANDIDATE_QUANTILES:
        widths = {
            entity: quantile([abs(value) for value in train], q)
            for entity, (train, _dev) in samples.items()
        }
        hits = total = 0
        by_tenor = {}
        for entity, (_train, dev) in samples.items():
            entity_hits = sum(abs(value) <= widths[entity] for value in dev)
            hits += entity_hits
            total += len(dev)
            by_tenor[entity] = entity_hits / len(dev)
        coverage = hits / total
        battery.append({
            "quantile": q,
            "dev_coverage": coverage,
            "dev_calibration_loss": abs(coverage - 0.90),
            "widths_bps": widths,
            "dev_coverage_by_tenor": by_tenor,
        })
    selected = min(
        battery,
        key=lambda item: (item["dev_calibration_loss"], sum(item["widths_bps"].values())),
    )
    report = {
        "schema_version": 1,
        "artifact": "fomc_35td_interval_v1",
        "source": "U.S. Treasury daily par yield curve rates",
        "source_url_template": (
            "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
            "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve&"
            "field_tdr_date_value={year}&page&_format=csv"
        ),
        "fit_period": "2000-01-01/2016-12-31",
        "selection_period": "2017-01-01/2021-12-31",
        "holdout_not_read": ["t4-fomc-curve-20220728", "t4-fomc-curve-20240918"],
        "horizon_trading_days": HORIZON_TRADING_DAYS,
        "origin_step_trading_days": ORIGIN_STEP,
        "sample_counts": {
            entity: {"train": len(train), "dev": len(dev)}
            for entity, (train, dev) in samples.items()
        },
        "annual_file_sha256": checksums,
        "candidate_battery": battery,
        "selected": selected,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"sample_counts": report["sample_counts"], "selected": selected}, indent=2))


if __name__ == "__main__":
    main()
