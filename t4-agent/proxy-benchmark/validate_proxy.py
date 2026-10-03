#!/usr/bin/env python3
"""Validate reproducibility, cutoff, roster, and variant invariants for proxy units."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_unit(unit: Path) -> list[str]:
    errors: list[str] = []
    task = json.loads((unit / "task.json").read_text())
    outcome = json.loads((unit / "reference/outcome.json").read_text())
    naive = json.loads((unit / "reference/naive_answer.json").read_text())
    manifest = json.loads((unit / "manifest.json").read_text())
    ids = [row.get("entity_id") for row in task.get("entities", [])]
    if len(ids) != len(set(ids)) or not ids:
        errors.append("task roster is empty or duplicated")
    for label, rows in (("outcome", outcome.get("outcomes", [])), ("naive", naive.get("entity_predictions", []))):
        if {row.get("entity_id") for row in rows} != set(ids) or len(rows) != len(ids):
            errors.append(f"{label} roster differs from task")
    forbidden = {"truth", "target_5wk_change_pct_start_oi", "next_report_change", "outcome"}
    for row in task.get("entities", []):
        if forbidden.intersection(row):
            errors.append(f"visible row leaks outcome-like field for {row.get('entity_id')}")
    cutoff = str(task.get("cutoff_date", ""))
    docs = list((unit / "corpus").glob("*.json"))
    if len(docs) != len(ids):
        errors.append("corpus does not contain exactly one document per entity")
    for path in docs:
        doc = json.loads(path.read_text())
        if str(doc.get("doc_date", "")) > cutoff:
            errors.append(f"post-cutoff document: {path.name}")
        if not isinstance(doc.get("text"), str) or not doc["text"]:
            errors.append(f"empty corpus text: {path.name}")
    for entry in manifest.get("files", []):
        path = unit / entry["path"]
        if not path.is_file() or sha256(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            errors.append(f"manifest mismatch: {entry['path']}")
    return errors


def compare_variants(explicit: Path, transformed: Path) -> list[str]:
    errors: list[str] = []
    left = json.loads((explicit / "reference/outcome.json").read_text())["outcomes"]
    right = json.loads((transformed / "reference/outcome.json").read_text())["outcomes"]
    lmap = {row["entity_id"]: row["y"] for row in left}
    rmap = {row["entity_id"]: row["y"] for row in right}
    if lmap != rmap:
        errors.append("schema variants have different resolved outcomes")
    ln = json.loads((explicit / "reference/naive_answer.json").read_text())["entity_predictions"]
    rn = json.loads((transformed / "reference/naive_answer.json").read_text())["entity_predictions"]
    def project(rows):
        return {row["entity_id"]: (row["point_forecast"], row["interval"]) for row in rows}
    if project(ln) != project(rn):
        errors.append("schema variants have different naive forecasts")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units", type=Path, default=Path("proxy-benchmark/units"))
    args = parser.parse_args()
    explicit = args.units / "proxy-18-cot-positioning-rank-20230926-explicit"
    transformed = args.units / "proxy-18-cot-positioning-rank-20230926-transformed"
    errors = validate_unit(explicit) + validate_unit(transformed) + compare_variants(explicit, transformed)
    print(json.dumps({"units": 2, "errors": errors, "passed": not errors}, indent=2))
    raise SystemExit(bool(errors))


if __name__ == "__main__":
    main()
