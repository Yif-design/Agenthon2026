#!/usr/bin/env python3
"""Screen whether deterministic peer statistics carry cross-sectional outcome signal."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def binary_metrics(pairs: list[tuple[int, int]]) -> dict[str, float | int]:
    accuracy = sum(pred == actual for pred, actual in pairs) / len(pairs)
    f1s = []
    for label in (-1, 1):
        tp = sum(pred == label and actual == label for pred, actual in pairs)
        fp = sum(pred == label and actual != label for pred, actual in pairs)
        fn = sum(pred != label and actual == label for pred, actual in pairs)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return {"rows": len(pairs), "accuracy": accuracy, "macro_f1": statistics.fmean(f1s)}


def cpi_screen(document: dict[str, Any], years: set[str]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in document["rows"]:
        if row["ref_month"][:4] in years:
            groups[row["ref_month"]].append(row)
    raw_pairs: list[tuple[int, int]] = []
    peer_pairs: list[tuple[int, int]] = []
    covered = 0
    mad_zero = 0
    for rows in groups.values():
        values = [float(row["known_mom_pct"][-1]) for row in rows if row.get("known_mom_pct")]
        if len(values) != len(rows) or not values:
            continue
        median = statistics.median(values)
        mad = statistics.median(abs(value - median) for value in values)
        mad_zero += mad == 0
        for row, value in zip(rows, values):
            actual = sign(float(row["target_mom_pct"]))
            if actual == 0:
                continue
            raw_pairs.append((sign(value) or -1, actual))
            peer_pairs.append((sign(value - median) or -1, actual))
            covered += 1
    return {
        "groups": len(groups),
        "eligible_rows": sum(len(rows) for rows in groups.values()),
        "computed_rows": covered,
        "computed_rate": covered / max(1, sum(len(rows) for rows in groups.values())),
        "mad_zero_groups": mad_zero,
        "raw_sign": binary_metrics(raw_pairs),
        "peer_centered_sign": binary_metrics(peer_pairs),
    }


def ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / 2.0
        for index in order[start:end]:
            result[index] = rank
        start = end
    return result


def correlation(left: list[float], right: list[float]) -> float:
    lmean, rmean = statistics.fmean(left), statistics.fmean(right)
    numerator = sum((x - lmean) * (y - rmean) for x, y in zip(left, right))
    lnorm = sum((x - lmean) ** 2 for x in left) ** 0.5
    rnorm = sum((y - rmean) ** 2 for y in right) ** 0.5
    return numerator / (lnorm * rnorm) if lnorm and rnorm else 0.0


def cot_screen(document: dict[str, Any], years: set[str]) -> dict[str, Any]:
    raw_scores = []
    percentile_scores = []
    z_scores = []
    rows = 0
    mad_zero = 0
    for group in document["groups"]:
        if group["start_date"][:4] not in years:
            continue
        values = [float(row["trailing_4wk_net_change_pct_oi"]) for row in group["rows"]]
        actual = [float(row["target_5wk_change_pct_start_oi"]) for row in group["rows"]]
        median = statistics.median(values)
        mad = statistics.median(abs(value - median) for value in values)
        mad_zero += mad == 0
        percentiles = ranks(values)
        robust_z = [(value - median) / (1.4826 * mad) if mad else 0.0 for value in values]
        actual_ranks = ranks(actual)
        raw_scores.append(correlation(ranks(values), actual_ranks))
        percentile_scores.append(correlation(ranks(percentiles), actual_ranks))
        z_scores.append(correlation(ranks(robust_z), actual_ranks))
        rows += len(values)
    return {
        "groups": len(raw_scores),
        "rows": rows,
        "computed_rate": 1.0 if rows else 0.0,
        "mad_zero_groups": mad_zero,
        "raw_mean_spearman": statistics.fmean(raw_scores),
        "percentile_mean_spearman": statistics.fmean(percentile_scores),
        "robust_z_mean_spearman": statistics.fmean(z_scores),
        "rank_order_changed_by_percentile": any(abs(a - b) > 1e-12 for a, b in zip(raw_scores, percentile_scores)),
        "rank_order_changed_by_robust_z": any(abs(a - b) > 1e-12 for a, b in zip(raw_scores, z_scores)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    paths = {
        "cpi": args.dataset_root / "cpi/components_2015_2023.json",
        "cpi_confirmation": args.dataset_root / "cpi/components_2024_2025_confirmation.json",
        "cot": args.dataset_root / "cot/legacy10_2015_2023.json",
    }
    docs = {name: json.loads(path.read_text()) for name, path in paths.items()}
    periods = {
        "development": {
            "cpi": cpi_screen(docs["cpi"], {"2021"}),
            "cot": cot_screen(docs["cot"], {"2021"}),
        },
        "test": {
            "cpi": cpi_screen(docs["cpi"], {"2022"}),
            "cot": cot_screen(docs["cot"], {"2022"}),
        },
        "confirmation": {
            "cpi": cpi_screen(docs["cpi_confirmation"], {"2024", "2025"}),
            "cot": cot_screen(docs["cot"], {"2023"}),
        },
    }
    cpi_pass = all(
        periods[name]["cpi"]["peer_centered_sign"][metric] > periods[name]["cpi"]["raw_sign"][metric]
        for name in ("test", "confirmation") for metric in ("accuracy", "macro_f1")
    )
    coverage_pass = all(
        domain["computed_rate"] >= 0.95
        for period in periods.values() for domain in period.values()
    )
    cot_noninferior = all(
        period["cot"]["percentile_mean_spearman"] >= period["cot"]["raw_mean_spearman"] - 1e-12
        and period["cot"]["robust_z_mean_spearman"] >= period["cot"]["raw_mean_spearman"] - 1e-12
        for period in periods.values()
    )
    advance = cpi_pass and coverage_pass and cot_noninferior
    report = {
        "schema_version": 1,
        "experiment": "cross_section_stats_screen_v1",
        "date": "2026-09-30",
        "baseline_git_commit": "4276ededb7ab5dfc8e8425ba22c96ccc8a2f4550",
        "hypothesis": "Peer median, MAD, robust z-score and percentile expose useful full-roster context for unknown classification and ranking beyond the row-local raw scalar.",
        "scope": "L3 cross-sectional statistics preflight",
        "dataset_sha256": {name: sha256(path) for name, path in paths.items()},
        "time_splits": {
            "development": {"cpi": ["2021"], "cot": ["2021"]},
            "test": {"cpi": ["2022"], "cot": ["2022"]},
            "confirmation": {"cpi": ["2024", "2025"], "cot": ["2023"]},
        },
        "periods": periods,
        "gates": {
            "cpi_test_and_confirmation_accuracy_and_macro_f1_strictly_improve": cpi_pass,
            "cot_spearman_noninferior": cot_noninferior,
            "computed_rate_at_least_0_95": coverage_pass,
        },
        "decision_rule": "Advance to a remote model A/B only if peer-centered CPI accuracy and macro-F1 strictly improve on both test and confirmation, COT Spearman is noninferior in every split, and at least 95% of rows are computable.",
        "decision": "advance_to_remote_model_ab" if advance else "reject_before_prompt_change",
        "interpretation_guard": "Statistics are diagnostic input facts. This screen uses simple mappings only to test whether they contain incremental outcome signal; it does not authorize production to map a percentile or z-score directly to a forecast direction.",
        "model_api_calls": 0,
        "local_llm_run": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"gates": report["gates"], "decision": report["decision"], "periods": periods}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
