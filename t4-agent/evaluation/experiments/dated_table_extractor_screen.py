#!/usr/bin/env python3
"""Pre-registered screen for a strict generic dated-table persistence baseline."""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import fmean

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from t4agent.retrieve import IndexedCorpus  # noqa: E402
from t4agent.tables import extract_generic_table_baseline, parse_dated_tables  # noqa: E402
from t4agent.taskio import Task  # noqa: E402


REPORT = ROOT / "evaluation/reports/generic-dated-table-extractor-v1.json"


def task(target_name: str, unit: str, cutoff: str) -> Task:
    raw = {"target": {"name": target_name, "type": "regression", "unit": unit}}
    return Task(raw, "transformed-generic", "3", raw["target"], "regression", [], [], cutoff, 0.9, "", "unknown")


def extract(table: str, target_name: str, unit: str, cutoff: str) -> float | None:
    corpus = IndexedCorpus([], {"history": table}, {"history": cutoff})
    result = extract_generic_table_baseline(task(target_name, unit, cutoff), {"entity_id": "X"}, corpus)
    return result.value if result else None


def safety_cases() -> dict[str, bool]:
    def close(value: float | None, expected: float) -> bool:
        return value is not None and math.isclose(value, expected, abs_tol=1e-12)

    valid = "date | metric_ratio\n2024-01-01 | 2.5\n2024-02-01 | 2.7"
    return {
        "valid_level": extract(valid, "metric_ratio", "ratio", "2024-02-15") == 2.7,
        "valid_markdown": extract("| date | metric_ratio |\n| --- | --- |\n| 2024-01-01 | 2.5 |", "metric_ratio", "ratio", "2024-01-31") == 2.5,
        "future_stopped": extract(valid, "metric_ratio", "ratio", "2024-01-15") == 2.5,
        "duplicate_date_rejected": extract("date | metric_ratio\n2024-01-01 | 2.5\n2024-01-01 | 2.7", "metric_ratio", "ratio", "2024-02-15") is None,
        "reverse_date_rejected": extract("date | metric_ratio\n2024-02-01 | 2.5\n2024-01-01 | 2.7", "metric_ratio", "ratio", "2024-02-15") is None,
        "missing_rejected": extract("date | metric_ratio\n2024-01-01 | --\n2024-02-01 | 2.7", "metric_ratio", "ratio", "2024-02-15") is None,
        "partial_number_rejected": extract("date | metric_ratio\n2024-01-01 | 2.5x", "metric_ratio", "ratio", "2024-02-15") is None,
        "duplicate_column_rejected": extract("date | metric_ratio | METRIC_RATIO\n2024-01-01 | 2.5 | 2.7", "metric_ratio", "ratio", "2024-02-15") is None,
        "wrong_column_rejected": extract("date | other_ratio\n2024-01-01 | 2.5", "metric_ratio", "ratio", "2024-02-15") is None,
        "unit_mismatch_rejected": extract("date | metric_pct\n2024-01-01 | 2.5", "metric_pct", "basis_points", "2024-02-15") is None,
        "unknown_unit_rejected": extract("date | metric\n2024-01-01 | 2.5", "metric", "", "2024-02-15") is None,
        "malformed_boundary_not_crossed": extract("date | metric_ratio\n2024-01-01 | 2.5\nbroken\n2024-02-01 | 99", "metric_ratio", "ratio", "2024-02-15") == 2.5,
        "blank_boundary_not_crossed": extract("date | metric_ratio\n2024-01-01 | 2.5\n\n2024-02-01 | 99", "metric_ratio", "ratio", "2024-02-15") == 2.5,
        "change_delta": close(extract("date | rate_pct\n2024-01-01 | 4.10\n2024-02-01 | 4.02", "rate_pct_change", "percent", "2024-02-15"), -0.08),
        "percent_to_bps": close(extract("date | rate_pct\n2024-01-01 | 4.10\n2024-02-01 | 4.02", "rate_pct_change_bps", "basis_points", "2024-02-15"), -8.0),
        "growth_abstains": extract("date | revenue_usd\n2024-01-01 | 100\n2024-02-01 | 120", "revenue_growth_pct", "percent", "2024-02-15") is None,
        "parser_no_table_on_invalid_cutoff": not parse_dated_tables(valid, "not-a-date"),
    }


def metrics(rows: list[tuple[str, float, float]]) -> dict[str, dict[str, float | int]]:
    result = {}
    for split in ("test", "confirmation"):
        selected = [(prediction, actual) for name, prediction, actual in rows if name == split]
        baseline = fmean(abs(actual) for _, actual in selected)
        candidate = fmean(abs(prediction - actual) for prediction, actual in selected)
        result[split] = {
            "rows": len(selected),
            "baseline_zero_mae": baseline,
            "candidate_persistence_mae": candidate,
            "relative_mae_improvement": (baseline - candidate) / baseline if baseline else 0.0,
        }
    return result


def auction_rows() -> list[tuple[str, float, float]]:
    data = json.loads((ROOT / "evaluation/datasets/auction/nominal_coupon_2010_2024-10-31.json").read_text())["data"]
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in data:
        groups[row["tenor"]].append(row)
    output = []
    for values in groups.values():
        values.sort(key=lambda item: item["auction_date"])
        history: list[dict] = []
        for row in values:
            year = int(row["auction_date"][:4])
            split = "test" if 2020 <= year <= 2021 else "confirmation" if year >= 2022 else "development"
            if history and split != "development":
                table = "date | bid_to_cover_ratio\n" + "\n".join(
                    f"{item['auction_date']} | {item['bid_to_cover_ratio']}" for item in history[-12:]
                )
                prediction = extract(table, "bid_to_cover_ratio", "ratio", history[-1]["auction_date"])
                if prediction is not None:
                    output.append((split, prediction, float(row["bid_to_cover_ratio"])))
            history.append(row)
    return output


def eps_rows() -> list[tuple[str, float, float]]:
    data = json.loads((ROOT / "evaluation/datasets/eps_yoy/quarterly_diluted_eps_2015_2025.json").read_text())["rows"]
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in data:
        groups[row["ticker"]].append(row)
    output = []
    for values in groups.values():
        values.sort(key=lambda item: item["target_end"])
        history: list[dict] = []
        for row in values:
            year = int(row["target_end"][:4])
            split = "test" if 2020 <= year <= 2021 else "confirmation" if year >= 2022 else "development"
            if history and split != "development":
                table = "date | diluted_eps_usd_per_share\n" + "\n".join(
                    f"{item['target_end']} | {item['target_eps']}" for item in history[-12:]
                )
                prediction = extract(table, "diluted_eps_usd_per_share", "usd per share", history[-1]["target_end"])
                if prediction is not None:
                    output.append((split, prediction, float(row["target_eps"])))
            history.append(row)
    return output


def main() -> None:
    safety = safety_cases()
    datasets = {"auction_bid_to_cover": metrics(auction_rows()), "quarterly_diluted_eps": metrics(eps_rows())}
    no_reversal = all(
        values[split]["candidate_persistence_mae"] <= values[split]["baseline_zero_mae"]
        for values in datasets.values()
        for split in ("test", "confirmation")
    )
    report = {
        "experiment": "generic_dated_table_extractor_v1",
        "layer": "L2 unknown-family deterministic extraction",
        "hypothesis": "An exact target-matched cutoff-safe dated-table persistence baseline improves unknown numeric tasks over the current zero fallback without affecting known families or model requests.",
        "pre_registered_rule": "For a level target with one exact target/series column and a confirmed unit, use the latest valid pre-cutoff observation; for unambiguous change/delta targets use the latest difference; otherwise abstain.",
        "source_reuse": "Frozen project datasets; this screen performs no network access and does not change the source files.",
        "splits": {"test": "2020-2021", "confirmation": "2022 through each frozen dataset end"},
        "safety": {"passed": sum(safety.values()), "total": len(safety), "cases": safety},
        "datasets": datasets,
        "gates": {
            "all_synthetic_safety": all(safety.values()),
            "two_independent_datasets": len(datasets) >= 2,
            "test_and_confirmation_no_reversal": no_reversal,
            "no_model_calls": True,
            "production_path_unchanged_during_screen": True,
        },
    }
    report["decision"] = "pass_to_faithfulness_gate" if all(report["gates"].values()) else "reject"
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"decision": report["decision"], "safety": report["safety"], "datasets": datasets}, indent=2))
    if report["decision"] == "reject":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
