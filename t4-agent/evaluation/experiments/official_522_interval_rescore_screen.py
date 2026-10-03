#!/usr/bin/env python3
"""Audit accepted interval policies with the official scorer 5.2.2 loss.

This is a read-only screen.  It holds each family's point forecasts fixed and
compares the current interval rule with its immediate predecessor on forward
test and confirmation periods.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable, Iterable


PROJECT = Path(__file__).resolve().parents[2]
EXPERIMENTS = PROJECT / "evaluation" / "experiments"
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
if str(EXPERIMENTS) not in sys.path:
    sys.path.insert(0, str(EXPERIMENTS))

import generic_interval_scale as generic  # noqa: E402


TARGET_LEVEL = 0.90
PENALTY = 2.0 / (1.0 - TARGET_LEVEL)
TENORS = ("UST2Y", "UST3Y", "UST5Y", "UST7Y", "UST10Y", "UST30Y")
SENSITIVITY = {"UST2Y": 1.0, "UST3Y": 0.8, "UST5Y": 0.8, "UST7Y": 0.6, "UST10Y": 0.6, "UST30Y": 0.4}
PUBLIC_FOMC_DATES = {"2022-07-27", "2024-09-18"}


Observation = tuple[float, float, float]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def interval_score(point: float, actual: float, half: float) -> float:
    lo, hi = point - half, point + half
    return 2.0 * half + PENALTY * max(lo - actual, 0.0) + PENALTY * max(actual - hi, 0.0)


def metrics(rows: Iterable[Observation]) -> dict[str, float | int]:
    values = list(rows)
    if not values:
        return {"rows": 0, "mean_interval_score": float("nan"), "mean_full_width": float("nan"), "coverage": float("nan")}
    return {
        "rows": len(values),
        "mean_interval_score": statistics.fmean(interval_score(point, actual, half) for point, actual, half in values),
        "mean_full_width": statistics.fmean(2.0 * half for _, _, half in values),
        "coverage": statistics.fmean(point - half <= actual <= point + half for point, actual, half in values),
    }


def comparison(current: list[Observation], predecessor: list[Observation]) -> dict:
    if len(current) != len(predecessor):
        raise ValueError("current and predecessor row counts differ")
    current_metrics, predecessor_metrics = metrics(current), metrics(predecessor)
    return {
        "current": current_metrics,
        "predecessor": predecessor_metrics,
        "current_minus_predecessor_mean_interval_score": (
            float(current_metrics["mean_interval_score"]) - float(predecessor_metrics["mean_interval_score"])
        ),
    }


def family_result(description: str, test: dict, confirmation: dict) -> dict:
    worse_test = test["current_minus_predecessor_mean_interval_score"] > 0.0
    worse_confirmation = confirmation["current_minus_predecessor_mean_interval_score"] > 0.0
    return {
        "policy_comparison": description,
        "test": test,
        "confirmation": confirmation,
        "current_worse_on_test": worse_test,
        "current_worse_on_confirmation": worse_confirmation,
        "decision": "rollback_candidate" if worse_test and worse_confirmation else "no_rollback_signal",
    }


def eps_rows(rows: list[dict], years: set[str], scale: float, floor: float) -> list[Observation]:
    result = []
    for row in rows:
        if row["target_end"][:4] not in years:
            continue
        prior = float(row["prior_eps"])
        point = prior - max(0.05 * abs(prior), 0.01)
        result.append((point, float(row["target_eps"]), max(floor, scale * abs(prior))))
    return result


def cpi_rows(rows: list[dict], years: set[str], floor: float, multiplier: float) -> list[Observation]:
    result = []
    for row in rows:
        if row["ref_month"][:4] not in years:
            continue
        history = [float(value) for value in row["known_mom_pct"]]
        point = 0.7 * history[-1] + 0.3 * statistics.median(history[-3:])
        half = max(floor, multiplier * statistics.pstdev(history[-9:]))
        result.append((point, float(row["target_mom_pct"]), half))
    return result


def cot_rows(groups: list[dict], years: set[str], current: bool) -> list[Observation]:
    result = []
    for group in groups:
        if group["start_date"][:4] not in years:
            continue
        for row in group["rows"]:
            point = -0.2 * float(row["current_net_pct_oi"])
            half = 11.3 if current else max(4.0, 1.65 * float(row["history_pstdev_pct_oi"]))
            result.append((point, float(row["target_5wk_change_pct_start_oi"]), half))
    return result


def auction_samples(document: dict) -> list[dict]:
    by_tenor: dict[str, list[dict]] = defaultdict(list)
    for row in document["data"]:
        by_tenor[row["tenor"]].append(row)
    samples = []
    for tenor, rows in sorted(by_tenor.items()):
        rows.sort(key=lambda row: row["auction_date"])
        for index, target in enumerate(rows):
            history = rows[:index]
            if len(history) < 6:
                continue
            recent = [float(row["bid_to_cover_ratio"]) for row in history[-6:]]
            samples.append({
                "year": target["auction_date"][:4],
                "point": statistics.fmean(recent),
                "actual": float(target["bid_to_cover_ratio"]),
                "pstdev": statistics.pstdev(recent),
            })
    return samples


def auction_rows(samples: list[dict], years: set[str], multiplier: float) -> list[Observation]:
    return [
        (row["point"], row["actual"], max(0.15, multiplier * row["pstdev"]))
        for row in samples
        if row["year"] in years
    ]


def postearn_rows(events: list[dict], half: float) -> list[Observation]:
    return [(0.0, float(event["abnormal_return_pct"]), half) for event in events]


def fomc_rows(events: list[dict], years: set[str], half: float) -> list[Observation]:
    result = []
    for event in events:
        if event["decision_date"][:4] not in years or event["decision_date"] in PUBLIC_FOMC_DATES:
            continue
        for tenor in TENORS:
            point = 15.0 * float(event["policy_direction"]) * SENSITIVITY[tenor]
            result.append((point, float(event["yield_changes_bps"][tenor]), half))
    return result


def generic_comparison(rows: list[Observation]) -> dict:
    current = [(point, actual, 2.0 * half) for point, half, actual in rows]
    predecessor = [(point, actual, half) for point, half, actual in rows]
    return comparison(current, predecessor)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, default=PROJECT / "evaluation" / "datasets")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline-commit", required=True)
    args = parser.parse_args()
    paths = {
        "eps": args.dataset_root / "eps_yoy/quarterly_diluted_eps_2015_2025.json",
        "cpi": args.dataset_root / "cpi/components_2015_2023.json",
        "cpi_confirmation": args.dataset_root / "cpi/components_2024_2025_confirmation.json",
        "cot": args.dataset_root / "cot/legacy10_2015_2023.json",
        "auction": args.dataset_root / "auction/nominal_coupon_2010_2024-10-31.json",
        "postearn": args.dataset_root / "postearn/panel100_2018_2023.json",
        "postearn_confirmation": args.dataset_root / "postearn/panel88_confirmation_2024_2025.json",
        "fomc": args.dataset_root / "fomc/events_2022_2026.json",
        "macro": args.dataset_root / "macro_revision/alfred_monthend_2014_2024.json",
    }
    data = {name: load(path) for name, path in paths.items()}
    auction = auction_samples(data["auction"])

    families = {
        "eps_yoy": family_result(
            "current max(2.75, 1.15*abs(prior EPS)) vs predecessor max(0.03, 0.15*abs(prior EPS)); fixed no-signal point",
            comparison(eps_rows(data["eps"]["rows"], {"2022", "2023"}, 1.15, 2.75), eps_rows(data["eps"]["rows"], {"2022", "2023"}, 0.15, 0.03)),
            comparison(eps_rows(data["eps"]["rows"], {"2024", "2025"}, 1.15, 2.75), eps_rows(data["eps"]["rows"], {"2024", "2025"}, 0.15, 0.03)),
        ),
        "cpi": family_result(
            "current 0.75 floor vs predecessor 0.35 floor; fixed 1.65 multiplier and current_mix point",
            comparison(cpi_rows(data["cpi"]["rows"], {"2022", "2023"}, 0.75, 1.65), cpi_rows(data["cpi"]["rows"], {"2022", "2023"}, 0.35, 1.65)),
            comparison(cpi_rows(data["cpi_confirmation"]["rows"], {"2024", "2025"}, 0.75, 1.65), cpi_rows(data["cpi_confirmation"]["rows"], {"2024", "2025"}, 0.35, 1.65)),
        ),
        "cot": family_result(
            "current fixed 11.3 pct-oi half-width vs predecessor dynamic max(4,1.65*history pstdev); fixed mean-reversion point",
            comparison(cot_rows(data["cot"]["groups"], {"2022"}, True), cot_rows(data["cot"]["groups"], {"2022"}, False)),
            comparison(cot_rows(data["cot"]["groups"], {"2023"}, True), cot_rows(data["cot"]["groups"], {"2023"}, False)),
        ),
        "auction": family_result(
            "current 2.5*recent pstdev vs predecessor 1.65*recent pstdev, both floor 0.15; fixed mean6 point",
            comparison(auction_rows(auction, {"2022", "2023"}, 2.5), auction_rows(auction, {"2022", "2023"}, 1.65)),
            comparison(auction_rows(auction, {"2024"}, 2.5), auction_rows(auction, {"2024"}, 1.65)),
        ),
        "postearn": family_result(
            "current 8.3 percentage-point half-width vs predecessor 2.5; fixed zero abnormal-return point",
            comparison(postearn_rows([e for e in data["postearn"]["events"] if e["announcement_date"][:4] in {"2022", "2023"}], 8.3), postearn_rows([e for e in data["postearn"]["events"] if e["announcement_date"][:4] in {"2022", "2023"}], 2.5)),
            comparison(postearn_rows(data["postearn_confirmation"]["events"], 8.3), postearn_rows(data["postearn_confirmation"]["events"], 2.5)),
        ),
    }

    generic_test = {
        "cpi": generic.cpi_rows(data["cpi"], {"2022", "2023"}),
        "cot": generic.cot_rows(data["cot"], {"2022"}),
        "macro_revision": generic.macro_rows(data["macro"], {"2021", "2022"}),
    }
    generic_confirmation = {
        "cpi": generic.cpi_rows(data["cpi_confirmation"], {"2024", "2025"}),
        "cot": generic.cot_rows(data["cot"], {"2023"}),
        "macro_revision": generic.macro_rows(data["macro"], {"2023"}),
    }
    generic_domains = {
        name: family_result(
            "current generic final half-width scale 2.0 vs predecessor 1.0; fixed generic point and base interval",
            generic_comparison(generic_test[name]),
            generic_comparison(generic_confirmation[name]),
        )
        for name in generic_test
    }

    fomc_control = family_result(
        "unchanged production half-width 50 bps compared with itself; negative-control integrity check",
        comparison(fomc_rows(data["fomc"]["events"], {"2024", "2025"}, 50.0), fomc_rows(data["fomc"]["events"], {"2024", "2025"}, 50.0)),
        comparison(fomc_rows(data["fomc"]["events"], {"2026"}, 50.0), fomc_rows(data["fomc"]["events"], {"2026"}, 50.0)),
    )
    rollback = [name for name, result in families.items() if result["decision"] == "rollback_candidate"]
    rollback += [f"generic/{name}" for name, result in generic_domains.items() if result["decision"] == "rollback_candidate"]
    report = {
        "schema_version": 1,
        "experiment": "official_522_interval_rescore_screen_v1",
        "baseline_git_commit": args.baseline_commit,
        "official_scorer_version": "5.2.2",
        "official_interval_score": "(hi-lo) + 20*max(lo-actual,0) + 20*max(actual-hi,0) at level 0.90",
        "hypothesis": "At least one coverage-selected accepted interval is worse than its predecessor on both forward test and confirmation mean official interval score.",
        "isolation_policy": "Hold point forecasts fixed within each comparison; change only interval half-width.",
        "decision_rule": "Flag a rollback candidate only when current mean interval score is strictly higher on both test and confirmation. This screen does not mutate production.",
        "dataset_sha256": {name: sha256(path) for name, path in paths.items()},
        "families": families,
        "generic_domains": generic_domains,
        "fomc_unchanged_control": fomc_control,
        "rollback_candidates": rollback,
        "hypothesis_supported": bool(rollback),
        "decision": "proceed_one_candidate_at_a_time" if rollback else "no_production_change",
        "production_change": "none",
        "model_api": {"requests": 0, "input_tokens": 0, "output_tokens": 0},
        "local_llm_run": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"rollback_candidates": rollback, "families": {name: value["decision"] for name, value in families.items()}, "generic_domains": {name: value["decision"] for name, value in generic_domains.items()}}, indent=2))


if __name__ == "__main__":
    main()
