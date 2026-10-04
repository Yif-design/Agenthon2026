#!/usr/bin/env python3
"""Evaluate Wang-inspired rolling selection on frozen project history panels."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.rolling_origin import (  # noqa: E402
    CANDIDATES,
    ForecastRow,
    Observation,
    run_rolling_origin,
    score_rows,
)

REPORT = ROOT / "evaluation/reports/rolling-origin-reference-screen-v1.json"
REFERENCE = Path("/Users/joezhou/PycharmProject/Agenthon2026-references/wang-a32950d")


def parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def load_json(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def observation(
    family: str,
    event_id: str,
    entity_id: str,
    origin: str,
    resolution: str,
    target: float,
    kind: str,
    season: int,
    **features: Any,
) -> Observation:
    return Observation(
        family=family,
        event_id=event_id,
        entity_id=entity_id,
        origin_date=parse_date(origin),
        resolution_date=parse_date(resolution),
        target=float(target),
        target_kind=kind,
        season_period=season,
        features=features,
    )


def auction_rows() -> list[Observation]:
    document = load_json("evaluation/datasets/auction/nominal_coupon_2010_2024-10-31.json")
    return [
        observation(
            "auction_bid_to_cover",
            f"auction:{row['auction_date']}",
            row["tenor"],
            row["announcement_date"],
            row["auction_date"],
            row["bid_to_cover_ratio"],
            "level",
            12,
            production_rule="auction_recent6",
        )
        for row in document["data"]
    ]


def cot_rows() -> list[Observation]:
    document = load_json("evaluation/datasets/cot/legacy10_2015_2023.json")
    rows = []
    for group in document["groups"]:
        for row in group["rows"]:
            rows.append(observation(
                "cot_5wk_change",
                f"cot:{group['start_date']}",
                row["entity_id"],
                group["start_date"],
                group["resolution_date"],
                row["target_5wk_change_pct_start_oi"],
                "change",
                52,
                production_rule="cot_positioning",
                current=row["current_net_pct_oi"],
                trailing_change=row["trailing_4wk_net_change_pct_oi"],
            ))
    return rows


def cpi_rows() -> list[Observation]:
    rows = []
    for relative in (
        "evaluation/datasets/cpi/components_2015_2023.json",
        "evaluation/datasets/cpi/components_2024_2025_confirmation.json",
    ):
        for row in load_json(relative)["rows"]:
            rows.append(observation(
                "cpi_component_mom",
                f"cpi:{row['ref_month']}",
                row["entity_id"],
                row["cutoff_vintage"],
                row["resolution_vintage"],
                row["target_mom_pct"],
                "change",
                12,
                production_rule="cpi_component",
                known_values=row["known_mom_pct"],
            ))
    return rows


def eps_rows() -> list[Observation]:
    document = load_json("evaluation/datasets/eps_yoy/quarterly_diluted_eps_2015_2025.json")
    return [
        observation(
            "quarterly_diluted_eps",
            f"eps:{row['ticker']}:{row['target_end']}",
            row["ticker"],
            row["prior_filed"],
            row["target_filed"],
            row["target_eps"],
            "level",
            4,
            production_rule="eps_directionless",
            prior_eps=row["target_filing_comparable_prior_eps"],
        )
        for row in document["rows"]
    ]


def fomc_rows() -> list[Observation]:
    rows = []
    for relative in (
        "evaluation/datasets/fomc/events_2000_2021.json",
        "evaluation/datasets/fomc/events_2022_2026.json",
    ):
        for event in load_json(relative)["events"]:
            for entity_id, target in event["yield_changes_bps"].items():
                rows.append(observation(
                    "fomc_yield_change",
                    f"fomc:{event['decision_date']}",
                    entity_id,
                    event["decision_date"],
                    event["resolution_date"],
                    target,
                    "change",
                    8,
                    production_rule="fomc_no_signal",
                ))
    return rows


def macro_revision_rows() -> list[Observation]:
    document = load_json("evaluation/datasets/macro_revision/alfred_monthend_2014_2024.json")
    return [
        observation(
            "macro_revision",
            f"revision:{row['cutoff_vintage']}:{row['ref_month']}",
            f"{row['series_id']}:age{row['revision_age']}",
            row["cutoff_vintage"],
            row["resolution_vintage"],
            row["target_change"],
            "change",
            12,
            production_rule="macro_revision",
            history_changes=row["all_history_changes"],
        )
        for row in document["rows"]
    ]


def postearn_rows() -> list[Observation]:
    rows = []
    for relative in (
        "evaluation/datasets/postearn/panel100_2018_2023.json",
        "evaluation/datasets/postearn/panel88_confirmation_2024_2025.json",
        "evaluation/datasets/postearn/panel88_confirmation_2026_ytd.json",
    ):
        for event in load_json(relative)["events"]:
            rows.append(observation(
                "postearn_abnormal_return",
                f"postearn:{event['announcement_date']}",
                event["ticker"],
                event["announcement_date"],
                event["resolution_date"],
                event["abnormal_return_pct"],
                "change",
                4,
                production_rule="reaction_no_signal",
            ))
    # An event can appear in both a historical and later rebuild.  Preserve one
    # economic observation rather than overweighting a duplicated source row.
    unique = {(row.family, row.entity_id, row.origin_date): row for row in rows}
    return list(unique.values())


def source_manifest() -> list[dict[str, Any]]:
    relatives = [
        "evaluation/datasets/auction/nominal_coupon_2010_2024-10-31.json",
        "evaluation/datasets/cot/legacy10_2015_2023.json",
        "evaluation/datasets/cpi/components_2015_2023.json",
        "evaluation/datasets/cpi/components_2024_2025_confirmation.json",
        "evaluation/datasets/eps_yoy/quarterly_diluted_eps_2015_2025.json",
        "evaluation/datasets/fomc/events_2000_2021.json",
        "evaluation/datasets/fomc/events_2022_2026.json",
        "evaluation/datasets/macro_revision/alfred_monthend_2014_2024.json",
        "evaluation/datasets/postearn/panel100_2018_2023.json",
        "evaluation/datasets/postearn/panel88_confirmation_2024_2025.json",
        "evaluation/datasets/postearn/panel88_confirmation_2026_ytd.json",
    ]
    result = []
    for relative in relatives:
        payload = (ROOT / relative).read_bytes()
        result.append({"path": relative, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)})
    return result


def pair_audit() -> dict[str, Any]:
    suite = load_json("evaluation/benchmark_suite.json")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for unit in suite["units"]:
        if unit.get("variant") in {"explicit", "transformed"}:
            groups[unit["event_id"]].append(unit)
    failures = []
    for event_id, units in groups.items():
        variants = {unit["variant"] for unit in units}
        splits = {unit["split"] for unit in units}
        weights = sum(float(unit["event_weight"]) for unit in units)
        if variants != {"explicit", "transformed"} or len(splits) != 1 or abs(weights - 1.0) > 1e-12:
            failures.append(event_id)
    return {
        "paired_events": len(groups),
        "failures": failures,
        "passed": not failures,
        "rolling_panel_policy": "one normalized forecast per economic observation; schema variants cannot alter origin, split, selector, or outcome",
    }


def metrics(rows: list[ForecastRow]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for family in sorted({row.family for row in rows}):
        family_rows = [row for row in rows if row.family == family]
        kind = "level" if family in {"auction_bid_to_cover", "quarterly_diluted_eps"} else "change"
        naive = "persistence" if kind == "level" else "zero"
        result[family] = {
            split: {
                candidate: score_rows(
                    [row for row in family_rows if row.split == split], candidate, naive
                )
                for candidate in (*CANDIDATES, "wang_selector")
            }
            for split in ("development", "time_forward_test", "confirmation")
        }
    return result


def aggregate(metrics_by_family: dict[str, Any], split: str, candidate: str) -> dict[str, float | int]:
    values = [family[split][candidate] for family in metrics_by_family.values() if family[split][candidate]["rows"]]
    return {
        "families": len(values),
        "mean_predictive_quality": statistics.fmean(float(value["predictive_quality"]) for value in values),
        "median_predictive_quality": statistics.median(float(value["predictive_quality"]) for value in values),
        "mean_interval_score": statistics.fmean(float(value["mean_interval_score"]) for value in values),
        "mean_interval_quality": statistics.fmean(float(value["interval_quality"]) for value in values),
        "mean_composite": statistics.fmean(float(value["composite"]) for value in values),
        "mean_interval_coverage": statistics.fmean(float(value["interval_coverage"]) for value in values),
    }


def leave_one_family_out(metrics_by_family: dict[str, Any]) -> dict[str, Any]:
    """Choose one fixed rule on other families' development slices, then hold one out."""
    candidates = tuple(name for name in CANDIDATES if name != "production_prior")
    output = {}
    families = sorted(metrics_by_family)
    for held_out in families:
        training = [name for name in families if name != held_out]
        scores = {
            candidate: statistics.fmean(
                float(metrics_by_family[name]["development"][candidate]["predictive_quality"])
                for name in training
            )
            for candidate in candidates
        }
        selected = max(candidates, key=lambda candidate: (scores[candidate], candidate))
        output[held_out] = {
            "selected_without_family": selected,
            "other_family_development_quality": scores[selected],
            "held_out_time_forward": metrics_by_family[held_out]["time_forward_test"][selected],
            "held_out_confirmation": metrics_by_family[held_out]["confirmation"][selected],
        }
    return output


def per_origin(rows: list[ForecastRow]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, date], list[ForecastRow]] = defaultdict(list)
    for row in rows:
        groups[(row.family, row.origin_date)].append(row)
    output = []
    for (family, origin), values in sorted(groups.items(), key=lambda item: (item[0][1], item[0][0])):
        output.append({
            "family": family,
            "origin": origin.isoformat(),
            "split": values[0].split,
            "rows": len(values),
            "resolution_max": max(row.resolution_date for row in values).isoformat(),
            "history_rows_min": min(row.history_count for row in values),
            "latest_training_resolution": max(
                (row.latest_training_resolution for row in values if row.latest_training_resolution is not None),
                default=None,
            ).isoformat() if any(row.latest_training_resolution for row in values) else None,
            "selected_models": dict(sorted(Counter(row.selected_model for row in values).items())),
            "mae": {
                candidate: statistics.fmean(abs(row.actual - row.predictions[candidate]) for row in values)
                for candidate in (*CANDIDATES, "wang_selector")
            },
        })
    return output


def reference_evidence() -> dict[str, Any]:
    active = json.loads((REFERENCE / "ACTIVE_BASELINE.json").read_text())
    files = {}
    for name in ("s12_numerics.py", "s13_numerics.py", "s14_numerics.py", "s15_numerics.py", "s15_calibration.py", "s16_numerics.py", "s16_calibration.py"):
        payload = (REFERENCE / name).read_bytes()
        files[name] = hashlib.sha256(payload).hexdigest()
    return {
        "repository": "https://github.com/wangzgui/agenthon-t4-baseline-2026",
        "snapshot_upstream_commit": "a32950da279905956269c1a60a9141988849e99d",
        "active_baseline_record": active,
        "interpretation": (
            "ACTIVE_BASELINE binds reported 0.4793 to S1.6/source commit af764681; "
            "S1.7 is recorded as rejected at 0.4787. Later S1.8/S1.9 files are research candidates, "
            "not evidence that they produced the active score."
        ),
        "mechanism_reimplemented": (
            "cutoff-only dated examples; recent-change and deviation ridge features; zero, momentum, "
            "anti-momentum, reversion and ridge candidates; held-out pre-cutoff model selection; "
            "5 percent improvement rail; residual-based intervals"
        ),
        "file_sha256": files,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()

    observations = (
        auction_rows() + cot_rows() + cpi_rows() + eps_rows() + fomc_rows()
        + macro_revision_rows() + postearn_rows()
    )
    keys = [(row.family, row.event_id, row.entity_id, row.origin_date) for row in observations]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate normalized observation key")
    rows = run_rolling_origin(observations)
    family_metrics = metrics(rows)
    comparisons = {
        split: {
            candidate: aggregate(family_metrics, split, candidate)
            for candidate in (*CANDIDATES, "wang_selector")
        }
        for split in ("development", "time_forward_test", "confirmation")
    }
    leakage_violations = [
        row for row in rows
        if row.latest_training_resolution is not None and row.latest_training_resolution >= row.origin_date
    ]
    family_improvements = {}
    for family, values in family_metrics.items():
        family_improvements[family] = {
            split: (
                float(values[split]["wang_selector"]["predictive_quality"])
                - float(values[split]["production_prior"]["predictive_quality"])
            )
            for split in ("time_forward_test", "confirmation")
        }
    gates = {
        "at_least_two_independent_families": len(family_metrics) >= 2,
        "strict_cutoff_no_leakage": not leakage_violations,
        "development_time_forward_confirmation_present": all(
            values[split]["wang_selector"]["origins"] > 0
            for values in family_metrics.values()
            for split in ("development", "time_forward_test", "confirmation")
        ),
        "schema_pairs_share_event_split_weight": pair_audit()["passed"],
        "deterministic_no_model_calls": True,
    }
    hypothesis = {
        "time_forward_selector_minus_production": (
            float(comparisons["time_forward_test"]["wang_selector"]["mean_predictive_quality"])
            - float(comparisons["time_forward_test"]["production_prior"]["mean_predictive_quality"])
        ),
        "confirmation_selector_minus_production": (
            float(comparisons["confirmation"]["wang_selector"]["mean_predictive_quality"])
            - float(comparisons["confirmation"]["production_prior"]["mean_predictive_quality"])
        ),
        "families_improved_both_forward_splits": sum(
            result["time_forward_test"] > 0 and result["confirmation"] > 0
            for result in family_improvements.values()
        ),
    }
    hypothesis["passed"] = bool(
        hypothesis["time_forward_selector_minus_production"] > 0
        and hypothesis["confirmation_selector_minus_production"] > 0
        and hypothesis["families_improved_both_forward_splits"] >= 2
    )
    report = {
        "schema_version": 1,
        "experiment": "rolling-origin-reference-screen-v1",
        "created_date": date.today().isoformat(),
        "scope": "evaluation_only_no_production_change",
        "hypothesis": (
            "A Wang-style cutoff-safe rolling candidate selector improves event/family-macro "
            "naive-relative predictive quality over the current production prior on multiple "
            "independent regression families without schema-variant-dependent selection."
        ),
        "pre_registered_in": "/Users/joezhou/Desktop/goal.txt",
        "reference": reference_evidence(),
        "sources": source_manifest(),
        "normalization": {
            "families": len(family_metrics),
            "observations": len(observations),
            "event_origins": len({(row.family, row.origin_date) for row in observations}),
            "availability_rule": "training resolution_date < forecast origin_date",
            "split_rule": "within-family chronological 60/20/20 by whole origin group",
            "naive_rule": "persistence for level targets; zero for change targets",
            "interval_rule": "prior-origin absolute residual q90; pre-origin scale fallback before enough residuals",
        },
        "schema_pair_audit": pair_audit(),
        "leakage_audit": {
            "violations": len(leakage_violations),
            "passed": not leakage_violations,
            "same_origin_outcomes_excluded": True,
            "future_outcome_mutation_test": "tests/test_rolling_origin.py",
            "revision_caveat": "ALFRED and CPI builders record actual vintage aliases; source caveats remain in frozen dataset metadata.",
        },
        "comparisons": comparisons,
        "family_metrics": family_metrics,
        "family_selector_minus_production": family_improvements,
        "leave_one_family_out": leave_one_family_out(family_metrics),
        "hypothesis_result": hypothesis,
        "infrastructure_gates": gates,
        "infrastructure_decision": "accept_evaluation_infrastructure" if all(gates.values()) else "reject",
        "production_decision": (
            "defer_requires_separate_adoption_round"
            if hypothesis["passed"] else "reject_selector_no_production_change"
        ),
        "per_origin": per_origin(rows),
        "model_api_calls": 0,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "observations": len(observations),
        "families": len(family_metrics),
        "infrastructure_decision": report["infrastructure_decision"],
        "hypothesis_result": hypothesis,
        "report": str(args.out),
    }
    print(json.dumps(summary, indent=2))
    if report["infrastructure_decision"] == "reject":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
