#!/usr/bin/env python3
"""Combine separately-run NLI members using the official per-citation mean."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def _combine_case(reports: list[dict], first: dict) -> dict:
    keys = ("unit_id", "answer_sha256", "tau_citation", "faithfulness_threshold")
    first_case_id = first.get("case_id", first["unit_id"])
    for report in reports[1:]:
        if report.get("case_id", report["unit_id"]) != first_case_id or any(
            report[key] != first[key] for key in keys
        ):
            raise ValueError("member reports do not describe the same scoring input")

    predictions = []
    for rows in zip(*(report["predictions"] for report in reports), strict=True):
        entity_id = rows[0]["entity_id"]
        hypothesis = rows[0]["hypothesis"]
        if any(row["entity_id"] != entity_id or row["hypothesis"] != hypothesis for row in rows):
            raise ValueError("member prediction rows are not aligned")
        scores = [float(row["score"]) for row in rows]
        ensemble_score = statistics.fmean(scores)
        predictions.append(
            {
                "entity_id": entity_id,
                "hypothesis": hypothesis,
                "member_scores": scores,
                "ensemble_score": ensemble_score,
                "supported": ensemble_score >= float(first["tau_citation"]),
            }
        )
    faithfulness = statistics.fmean([float(row["supported"]) for row in predictions])
    return {
        "case_id": first_case_id,
        "unit_id": first["unit_id"],
        "answer_sha256": first["answer_sha256"],
        "tau_citation": first["tau_citation"],
        "faithfulness_threshold": first["faithfulness_threshold"],
        "faithfulness": faithfulness,
        "gate_pass": faithfulness >= float(first["faithfulness_threshold"]),
        "predictions": predictions,
    }


def main() -> None:
    args = parse_args()
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.reports]
    first = reports[0]
    if len({report["model_id"] for report in reports}) != len(reports):
        raise ValueError("NLI model ids must be distinct")

    common = {
        "model_ids": [report["model_id"] for report in reports],
        "model_revisions": {report["model_id"]: report["model_revision"] for report in reports},
        "member_runtimes": {report["model_id"]: report["runtime"] for report in reports},
        "aggregation": "Arithmetic mean of member two-way entailment scores before tau threshold.",
        "aggregation_scope": "Exact for these reports because run_nli_member requires one citation per entity.",
    }
    versions = {int(report.get("schema_version", 1)) for report in reports}
    if versions == {1}:
        result = {"schema_version": 1, **common, **_combine_case(reports, first)}
    elif versions == {2}:
        case_counts = {len(report["cases"]) for report in reports}
        if len(case_counts) != 1:
            raise ValueError("suite reports have different case counts")
        cases = [
            _combine_case(list(rows), rows[0])
            for rows in zip(*(report["cases"] for report in reports), strict=True)
        ]
        result = {
            "schema_version": 2,
            **common,
            "case_count": len(cases),
            "all_gates_pass": all(case["gate_pass"] for case in cases),
            "cases": cases,
        }
    else:
        raise ValueError("cannot combine mixed or unsupported report schema versions")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if result["schema_version"] == 1:
        summary = {"faithfulness": result["faithfulness"], "gate_pass": result["gate_pass"]}
    else:
        summary = {
            "all_gates_pass": result["all_gates_pass"],
            "faithfulness": [
                {
                    "case_id": case["case_id"],
                    "unit_id": case["unit_id"],
                    "value": case["faithfulness"],
                }
                for case in result["cases"]
            ],
        }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
