#!/usr/bin/env python3
"""Dependency-free Track 4 5.2.2 metric proxy for local resolved units."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any


def ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    result = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        average = (cursor + 1 + end) / 2.0
        for index in order[cursor:end]:
            result[index] = average
        cursor = end
    return result


def spearman(left: list[float], right: list[float]) -> float:
    a, b = ranks(left), ranks(right)
    am, bm = statistics.fmean(a), statistics.fmean(b)
    numerator = sum((x - am) * (y - bm) for x, y in zip(a, b, strict=True))
    denominator = math.sqrt(sum((x - am) ** 2 for x in a) * sum((y - bm) ** 2 for y in b))
    return numerator / denominator if denominator else 0.0


def interval_score(rows: list[dict[str, Any]], truth: list[float], level: float) -> float:
    alpha = 1.0 - level
    costs = []
    for row, y in zip(rows, truth, strict=True):
        lo, hi = float(row["interval"]["lo"]), float(row["interval"]["hi"])
        cost = hi - lo
        if y < lo:
            cost += 2.0 / alpha * (lo - y)
        if y > hi:
            cost += 2.0 / alpha * (y - hi)
        costs.append(cost)
    return statistics.fmean(costs)


def aligned(unit: Path, answer_path: Path) -> tuple[list[str], list[dict[str, Any]], list[Any], str]:
    task = json.loads((unit / "task.json").read_text())
    answer = json.loads(answer_path.read_text())
    outcome = json.loads((unit / "reference/outcome.json").read_text())
    ids = [row["entity_id"] for row in task["entities"]]
    predictions = {row["entity_id"]: row for row in answer["entity_predictions"]}
    target_type = str(task["target"]["type"])
    if target_type == "classification":
        outcomes = {row["entity_id"]: str(row["true_label"]) for row in outcome["outcomes"]}
    else:
        outcomes = {row["entity_id"]: float(row["y"]) for row in outcome["outcomes"]}
    if set(predictions) != set(ids) or set(outcomes) != set(ids) or len(predictions) != len(ids):
        raise ValueError("answer/outcome roster differs from task roster")
    rows = [predictions[entity_id] for entity_id in ids]
    truth = [outcomes[entity_id] for entity_id in ids]
    for row in rows:
        point = float(row["point_forecast"])
        lo, hi, level = (float(row["interval"][key]) for key in ("lo", "hi", "level"))
        if not all(math.isfinite(value) for value in (point, lo, hi, level)) or lo > point or point > hi or level != 0.9:
            raise ValueError("invalid point or interval")
    if target_type == "classification":
        labels = set(task["target"].get("labels", []))
        if not labels or any(row.get("label") not in labels for row in rows):
            raise ValueError("classification answer carries an unknown label")
    return ids, rows, truth, target_type


def anchored_quality(raw: float, anchor: float) -> float:
    if raw >= anchor:
        return 1.0 if anchor >= 1.0 - 1e-12 else 0.5 + 0.5 * (raw - anchor) / (1.0 - anchor)
    return 0.5 * raw / anchor if anchor > 0 else 0.5


def score(unit: Path, answer_path: Path) -> dict[str, Any]:
    _, rows, truth, target_type = aligned(unit, answer_path)
    _, naive, _, naive_type = aligned(unit, unit / "reference/naive_answer.json")
    if naive_type != target_type:
        raise ValueError("naive target type differs from task")
    points = [float(row["point_forecast"]) for row in rows]
    naive_points = [float(row["point_forecast"]) for row in naive]
    metric_parts: dict[str, Any]
    if target_type == "classification":
        raw = statistics.fmean(row["label"] == label for row, label in zip(rows, truth, strict=True))
        naive_raw = statistics.fmean(row["label"] == label for row, label in zip(naive, truth, strict=True))
        anchor = naive_raw
        predictive = anchored_quality(raw, anchor)
        metric_parts = {"raw_accuracy": raw, "naive_accuracy": naive_raw}
        return {
            "unit": unit.name, **metric_parts,
            "raw_predictive_quality": raw, "naive_predictive_quality": naive_raw,
            "predictive_anchor": anchor, "predictive_quality": predictive,
            "interval_coverage": None, "interval_score": None,
            "naive_interval_score": None, "raw_interval_quality": None,
            "interval_quality": None,
            "composite_before_claim_penalty": predictive,
            "claim_penalty_evaluated": False,
        }
    if target_type == "ranking":
        rho = spearman(points, truth)
        naive_rho = spearman(naive_points, truth)
        raw = (rho + 1.0) / 2.0
        naive_raw = (naive_rho + 1.0) / 2.0
        anchor = max(0.5, naive_raw)
        predictive = anchored_quality(raw, anchor)
        # Preserve the historical proxy report's exact floating-point serialization.
        metric_parts = {"raw_spearman": 2.0 * raw - 1.0}
    elif target_type == "regression":
        own_mae = statistics.fmean(abs(point - y) for point, y in zip(points, truth, strict=True))
        naive_mae = statistics.fmean(abs(point - y) for point, y in zip(naive_points, truth, strict=True))
        predictive = naive_mae / (naive_mae + own_mae) if naive_mae + own_mae > 0 else 0.5
        raw = predictive
        naive_raw = 0.5
        anchor = None
        metric_parts = {"target_type": target_type, "mae": own_mae, "naive_mae": naive_mae}
    else:
        raise ValueError(f"unsupported proxy target type: {target_type}")
    own_is = interval_score(rows, truth, 0.9)
    naive_is = interval_score(naive, truth, 0.9)
    raw_iq = naive_is / (naive_is + own_is)
    interval_quality = min(raw_iq, max(0.5, predictive))
    coverage = statistics.fmean(
        float(row["interval"]["lo"]) <= y <= float(row["interval"]["hi"])
        for row, y in zip(rows, truth, strict=True)
    )
    return {
        "unit": unit.name, **metric_parts,
        "raw_predictive_quality": raw, "naive_predictive_quality": naive_raw,
        "predictive_anchor": anchor, "predictive_quality": predictive,
        "interval_coverage": coverage, "interval_score": own_is,
        "naive_interval_score": naive_is, "raw_interval_quality": raw_iq,
        "interval_quality": interval_quality,
        "composite_before_claim_penalty": 0.7 * predictive + 0.3 * interval_quality,
        "claim_penalty_evaluated": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit", type=Path, required=True)
    parser.add_argument("--answer", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = score(args.unit, args.answer)
    payload = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload)
    print(payload, end="")


if __name__ == "__main__":
    main()
