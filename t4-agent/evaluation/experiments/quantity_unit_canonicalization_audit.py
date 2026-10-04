#!/usr/bin/env python3
"""Audit general quantity/unit canonicalization without selecting forecasts.

The runtime-shaped canonicalizer sees one task at a time.  It emits only
quantities whose source field or corpus-table header declares a recognized
unit, converts them once to the target unit, assigns a generic semantic role,
and records provenance.  Pair comparison is strictly an offline invariance
audit and is never available to canonicalization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "evaluation/benchmark_suite.json"
REPORT = ROOT / "evaluation/reports/quantity-unit-canonicalization-audit-v1.json"

TOKEN = re.compile(r"[A-Za-z]+|\d+")
NUMBER = re.compile(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

PERCENT_TARGETS = {
    "percent",
    "growth_percent",
    "annualized_percent",
    "percent_return",
    "percent_of_revenue",
    "percent_of_start_open_interest",
    "percent_of_total_accepted",
}

UNIT_ALIASES = {
    "pct": "percent",
    "percent": "percent",
    "percentage": "percent",
    "fraction": "fraction",
    "bp": "basis_points",
    "bps": "basis_points",
    "basispoints": "basis_points",
    "mmbbl": "million_barrels",
    "bcf": "billion_cubic_feet",
    "mmcf": "million_cubic_feet",
    "kb": "thousand_barrels",
}

CONVERSION_FACTORS = {
    ("fraction", "percent"): 100.0,
    ("fraction", "percentage_points"): 100.0,
    ("fraction", "basis_points"): 10_000.0,
    ("percent", "fraction"): 0.01,
    ("percent", "percent"): 1.0,
    ("percent", "percentage_points"): 1.0,
    ("percent", "basis_points"): 100.0,
    ("percentage_points", "percentage_points"): 1.0,
    ("percentage_points", "percent"): 1.0,
    ("basis_points", "basis_points"): 1.0,
    ("basis_points", "percent"): 0.01,
    ("basis_points", "fraction"): 0.0001,
    ("million_barrels", "million_barrels"): 1.0,
    ("million_barrels", "thousand_barrels"): 1000.0,
    ("thousand_barrels", "million_barrels"): 0.001,
    ("billion_cubic_feet", "billion_cubic_feet"): 1.0,
    ("billion_cubic_feet", "million_cubic_feet"): 1000.0,
    ("million_cubic_feet", "billion_cubic_feet"): 0.001,
}

UNIT_NOISE = {
    "pct", "percent", "percentage", "fraction", "bp", "bps", "basis", "points",
    "mmbbl", "million", "millions", "barrel", "barrels", "kb", "bcf", "mmcf",
    "billion", "cubic", "feet",
}

METADATA = {
    "id", "cik", "code", "key", "number", "ordinal", "index", "month", "months",
    "year", "years", "day", "days", "maturity", "padd", "scale", "threshold",
}


def tokens(value: str) -> set[str]:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value)).replace("_", " ").replace("-", " ")
    return {part.lower() for part in TOKEN.findall(separated)}


def target_unit(target: dict[str, Any]) -> str | None:
    raw = str(target.get("unit") or "").lower()
    if raw in PERCENT_TARGETS:
        return "percent"
    if raw == "basis_points":
        return "basis_points"
    if raw == "percentage_points":
        return "percentage_points"
    if raw == "million_barrels_change":
        return "million_barrels"
    if raw == "billion_cubic_feet_change":
        return "billion_cubic_feet"
    return None


def source_unit(field: str) -> str | None:
    field_tokens = tokens(field)
    if {"percentage", "points"} <= field_tokens:
        return "percentage_points"
    if {"million", "barrels"} <= field_tokens:
        return "million_barrels"
    if {"thousand", "barrels"} <= field_tokens:
        return "thousand_barrels"
    if {"billion", "cubic", "feet"} <= field_tokens:
        return "billion_cubic_feet"
    if {"million", "cubic", "feet"} <= field_tokens:
        return "million_cubic_feet"
    candidates = {UNIT_ALIASES[token] for token in field_tokens if token in UNIT_ALIASES}
    return next(iter(candidates)) if len(candidates) == 1 else None


def semantic_role(field: str) -> str:
    raw_tokens = tokens(field)
    field_tokens = raw_tokens - UNIT_NOISE
    metric = bool(raw_tokens & {"ratio", "margin", "intensity", "share", "volatility", "sigma", "metric", "fraction"})
    recent = bool(field_tokens & {"latest", "last", "recent", "trailing", "current", "terminal", "short", "one", "period", "observed", "published", "lagged"})
    baseline = bool(field_tokens & {"baseline", "base", "prior", "reference"})
    if field_tokens & {"seasonal", "norm"}:
        return "seasonal_reference"
    if field_tokens & {"change", "delta", "flow", "drift", "move", "shift", "return", "growth"}:
        return "recent_change" if recent else "change"
    if metric:
        if baseline:
            return "baseline_metric"
        return "recent_metric" if recent else "metric"
    if baseline:
        return "baseline_level"
    if recent:
        return "recent_level"
    return "level"


def convert_once(value: float, original_unit: str, canonical_unit: str) -> float | None:
    factor = CONVERSION_FACTORS.get((original_unit, canonical_unit))
    result = value * factor if factor is not None else None
    return result if result is not None and math.isfinite(result) else None


def canonicalize_entity(target: dict[str, Any], entity: dict[str, Any]) -> dict[str, Any]:
    canonical_unit = target_unit(target)
    emitted = []
    abstained = []
    for field in sorted(entity):
        value = entity[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            continue
        original_unit = source_unit(field)
        field_tokens = tokens(field)
        if canonical_unit is None:
            reason = "target_has_no_supported_numeric_unit"
        elif original_unit is None:
            reason = "source_unit_not_explicit"
        elif field_tokens <= METADATA | UNIT_NOISE:
            reason = "numeric_metadata"
        else:
            canonical_value = convert_once(float(value), original_unit, canonical_unit)
            if canonical_value is not None:
                emitted.append({
                    "source_kind": "entity_field",
                    "source_field": field,
                    "original_value": float(value),
                    "original_unit": original_unit,
                    "canonical_value": canonical_value,
                    "canonical_unit": canonical_unit,
                    "semantic_role": semantic_role(field),
                    "conversion_factor": CONVERSION_FACTORS[(original_unit, canonical_unit)],
                })
                continue
            reason = "unit_incompatible_with_target"
        abstained.append({
            "source_kind": "entity_field",
            "source_field": field,
            "original_value": float(value),
            "inferred_unit": original_unit,
            "reason": reason,
        })
    return {
        "entity_id": str(entity.get("entity_id")),
        "canonical_target_unit": canonical_unit,
        "quantities": emitted,
        "abstentions": abstained,
    }


def _table_lines(text: str) -> list[tuple[int, str]]:
    result = []
    offset = 0
    for line in text.splitlines(keepends=True):
        result.append((offset, line.rstrip("\r\n")))
        offset += len(line)
    return result


def canonicalize_corpus(target: dict[str, Any], corpus_dir: Path, entity_id: str) -> list[dict[str, Any]]:
    """Emit the latest dated compatible values from simple pipe tables."""
    canonical_unit = target_unit(target)
    if canonical_unit is None:
        return []
    emitted = []
    for path in sorted(corpus_dir.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if entity_id not in {str(value) for value in document.get("entities", [])}:
            continue
        text = str(document.get("text") or "")
        lines = _table_lines(text)
        for index, (header_offset, header_line) in enumerate(lines):
            if "|" not in header_line:
                continue
            headers = [cell.strip() for cell in header_line.split("|")]
            if len(headers) < 2:
                continue
            compatible = [(column, name, source_unit(name)) for column, name in enumerate(headers[1:], 1)]
            compatible = [item for item in compatible if item[2] and convert_once(1.0, item[2], canonical_unit) is not None]
            if not compatible:
                continue
            rows = []
            for row_offset, row_line in lines[index + 1:]:
                cells = [cell.strip() for cell in row_line.split("|")]
                if len(cells) != len(headers) or not DATE.fullmatch(cells[0]):
                    if rows:
                        break
                    continue
                rows.append((cells[0], row_offset, row_line, cells))
            if not rows:
                continue
            period, row_offset, row_line, cells = max(rows, key=lambda row: row[0])
            cursor = 0
            for column, name, original_unit in compatible:
                raw = cells[column].replace(",", "")
                if not NUMBER.fullmatch(raw):
                    continue
                value = float(raw)
                canonical_value = convert_once(value, original_unit, canonical_unit)
                if canonical_value is None:
                    continue
                cell_start = row_line.find(cells[column], cursor)
                cursor = max(cursor, cell_start + len(cells[column]))
                emitted.append({
                    "source_kind": "corpus_table",
                    "doc_id": str(document.get("doc_id")),
                    "span_start": row_offset + cell_start,
                    "span_end": row_offset + cell_start + len(cells[column]),
                    "period": period,
                    "source_field": name,
                    "original_value": value,
                    "original_unit": original_unit,
                    "canonical_value": canonical_value,
                    "canonical_unit": canonical_unit,
                    "semantic_role": semantic_role(name),
                    "conversion_factor": CONVERSION_FACTORS[(original_unit, canonical_unit)],
                })
            break
    return sorted(emitted, key=lambda row: (row["doc_id"], row["source_field"], row["period"]))


def canonicalize_unit(unit: Path) -> dict[str, Any]:
    task_path = unit / "task.json"
    task = json.loads(task_path.read_text(encoding="utf-8"))
    rows = []
    for entity in sorted(task["entities"], key=lambda row: str(row["entity_id"])):
        item = canonicalize_entity(task["target"], entity)
        item["corpus_quantities"] = canonicalize_corpus(
            task["target"], unit / "corpus", str(entity["entity_id"])
        )
        rows.append(item)
    return {
        "unit": unit.name,
        "task_sha256": hashlib.sha256(task_path.read_bytes()).hexdigest(),
        "corpus_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((unit / "corpus").glob("*.json"))
        },
        "target": task["target"],
        "target_kind": target_kind(task["target"]),
        "rows": rows,
    }


def target_kind(target: dict[str, Any]) -> str:
    if target.get("type") == "classification":
        return "categorical"
    target_tokens = tokens(" ".join(str(target.get(key) or "") for key in ("name", "definition")))
    if target_tokens & {"change", "delta", "revision", "move", "return", "growth", "drift", "shift"}:
        return "change"
    if target_tokens & {"ratio", "share", "margin", "intensity", "volatility", "sigma"}:
        return "ratio_or_metric"
    return "level"


def _quantity_signature(row: dict[str, Any]) -> tuple[str, str, float]:
    return row["semantic_role"], row["canonical_unit"], float(row["canonical_value"])


def close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-9)


def compare_pair(event: str, explicit: dict[str, Any], transformed: dict[str, Any]) -> dict[str, Any]:
    left = {row["entity_id"]: row for row in explicit["rows"]}
    right = {row["entity_id"]: row for row in transformed["rows"]}
    entity_results = []
    for entity_id in sorted(set(left) | set(right)):
        if entity_id not in left or entity_id not in right:
            entity_results.append({"entity_id": entity_id, "status": "roster_mismatch", "matches": []})
            continue
        matches = []
        conflicts = []
        ambiguous = []
        used = set()
        for a in left[entity_id]["quantities"]:
            comparable = [
                (index, b) for index, b in enumerate(right[entity_id]["quantities"])
                if index not in used
                and a["semantic_role"] == b["semantic_role"]
                and a["canonical_unit"] == b["canonical_unit"]
            ]
            for index, b in enumerate(right[entity_id]["quantities"]):
                if index in used:
                    continue
                if a["semantic_role"] == b["semantic_role"] and a["canonical_unit"] == b["canonical_unit"] and close(float(a["canonical_value"]), float(b["canonical_value"])):
                    used.add(index)
                    matches.append({
                        "semantic_role": a["semantic_role"],
                        "canonical_unit": a["canonical_unit"],
                        "canonical_value": a["canonical_value"],
                        "explicit_field": a["source_field"],
                        "transformed_field": b["source_field"],
                    })
                    break
            else:
                if comparable:
                    conflicts.append({
                        "semantic_role": a["semantic_role"],
                        "canonical_unit": a["canonical_unit"],
                        "explicit_field": a["source_field"],
                        "explicit_value": a["canonical_value"],
                        "transformed_candidates": [
                            {"field": b["source_field"], "value": b["canonical_value"]}
                            for _, b in comparable
                        ],
                    })
                else:
                    ambiguous.append({
                        "side": "explicit",
                        "source_field": a["source_field"],
                        "semantic_role": a["semantic_role"],
                        "canonical_unit": a["canonical_unit"],
                    })
        for index, b in enumerate(right[entity_id]["quantities"]):
            if index in used:
                continue
            comparable_left = [
                a for a in left[entity_id]["quantities"]
                if a["semantic_role"] == b["semantic_role"]
                and a["canonical_unit"] == b["canonical_unit"]
            ]
            if not comparable_left:
                ambiguous.append({
                    "side": "transformed",
                    "source_field": b["source_field"],
                    "semantic_role": b["semantic_role"],
                    "canonical_unit": b["canonical_unit"],
                })
        entity_results.append({
            "entity_id": entity_id,
            "status": "matched" if matches else "abstained_or_unmatched",
            "matches": matches,
            "conflicts": conflicts,
            "ambiguous": ambiguous,
            "explicit_emitted": len(left[entity_id]["quantities"]),
            "transformed_emitted": len(right[entity_id]["quantities"]),
            "explicit_abstained": len(left[entity_id]["abstentions"]),
            "transformed_abstained": len(right[entity_id]["abstentions"]),
            "corpus_equal": left[entity_id]["corpus_quantities"] == right[entity_id]["corpus_quantities"],
        })
    return {
        "event": event,
        "explicit_unit": explicit["unit"],
        "transformed_unit": transformed["unit"],
        "target_kinds": [explicit["target_kind"], transformed["target_kind"]],
        "entities": entity_results,
        "matched_entities": sum(row["status"] == "matched" for row in entity_results),
        "abstained_or_unmatched_entities": sum(row["status"] == "abstained_or_unmatched" for row in entity_results),
        "roster_mismatches": sum(row["status"] == "roster_mismatch" for row in entity_results),
        "corpus_equal_entities": sum(row.get("corpus_equal", False) for row in entity_results),
        "matched": sum(len(row.get("matches", [])) for row in entity_results),
        "abstained": sum(
            row.get("explicit_abstained", 0) + row.get("transformed_abstained", 0)
            for row in entity_results
        ),
        "ambiguous": sum(len(row.get("ambiguous", [])) for row in entity_results),
        "conflict": sum(len(row.get("conflicts", [])) for row in entity_results),
    }


def git_revision() -> str | None:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT.parent, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def audit() -> dict[str, Any]:
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    pairs: dict[str, dict[str, Path]] = {}
    for row in suite["units"]:
        if row["cohort"] == "proxy":
            pairs.setdefault(row["event_id"], {})[row["variant"]] = ROOT / row["path"]
    results = []
    permutation_failures = []
    provenance_failures = []
    accounting_failures = []
    implicit_selection_failures = []
    for event, paths in sorted(pairs.items()):
        canonical = {}
        for variant in ("explicit", "transformed"):
            canonical[variant] = canonicalize_unit(paths[variant])
            task = json.loads((paths[variant] / "task.json").read_text(encoding="utf-8"))
            reversed_task = dict(task)
            reversed_task["entities"] = [dict(reversed(list(entity.items()))) for entity in reversed(task["entities"])]
            normal = [canonicalize_entity(task["target"], entity) for entity in sorted(task["entities"], key=lambda row: str(row["entity_id"]))]
            permuted = [canonicalize_entity(task["target"], entity) for entity in sorted(reversed_task["entities"], key=lambda row: str(row["entity_id"]))]
            if normal != permuted:
                permutation_failures.append(f"{event}:{variant}")
            for row in canonical[variant]["rows"]:
                task_entity = next(
                    entity for entity in task["entities"]
                    if str(entity["entity_id"]) == row["entity_id"]
                )
                numeric_fields = {
                    key for key, value in task_entity.items()
                    if not isinstance(value, bool)
                    and isinstance(value, (int, float))
                    and math.isfinite(float(value))
                }
                accounted = {
                    quantity["source_field"] for quantity in row["quantities"]
                } | {
                    abstention["source_field"] for abstention in row["abstentions"]
                }
                if accounted != numeric_fields or len(row["quantities"]) + len(row["abstentions"]) != len(numeric_fields):
                    accounting_failures.append(f"{event}:{variant}:{row['entity_id']}")
                if any(key in row for key in ("selected", "selected_field", "point_forecast", "candidate")):
                    implicit_selection_failures.append(f"{event}:{variant}:{row['entity_id']}")
                for quantity in row["quantities"] + row["corpus_quantities"]:
                    required = {"source_kind", "source_field", "original_value", "original_unit", "canonical_value", "canonical_unit", "semantic_role", "conversion_factor"}
                    if not required <= set(quantity):
                        provenance_failures.append(f"{event}:{variant}:{row['entity_id']}")
        result = compare_pair(event, canonical["explicit"], canonical["transformed"])
        result["canonical_units"] = canonical
        results.append(result)
    required_events = {
        "proxy-04-capex-intensity",
        "proxy-16-crude-inventory-change",
        "proxy-17-natural-gas-storage-change",
    }
    required_pair_matches = {
        event: next((row for row in results if row["event"] == event), None)
        for event in required_events
    }
    numeric_events_with_matches = sum(row["matched_entities"] > 0 for row in results)
    roundtrip_cases = []
    for original, canonical, value in (
        ("fraction", "percent", 0.03125),
        ("percent", "basis_points", 2.5),
        ("thousand_barrels", "million_barrels", 569.0),
        ("million_cubic_feet", "billion_cubic_feet", 3000.0),
    ):
        converted = convert_once(value, original, canonical)
        reverse = CONVERSION_FACTORS.get((canonical, original))
        roundtrip_cases.append({
            "original_unit": original,
            "canonical_unit": canonical,
            "original_value": value,
            "canonical_value": converted,
            "roundtrip_ok": reverse is not None and converted is not None and close(converted * reverse, value),
            "converted_once_ok": converted is not None and convert_once(converted, canonical, canonical) == converted,
        })
    gates = {
        "all_20_pairs_runnable": len(results) == 20 and all(row["roster_mismatches"] == 0 for row in results),
        "row_and_field_permutation_invariant": not permutation_failures,
        "unit_roundtrip_and_convert_once": all(row["roundtrip_ok"] and row["converted_once_ok"] for row in roundtrip_cases),
        "all_emitted_quantities_have_provenance": not provenance_failures,
        "all_numeric_fields_accounted_without_selection": (
            not accounting_failures and not implicit_selection_failures
        ),
        "at_least_10_events_have_schema_invariant_entity_quantities": numeric_events_with_matches >= 10,
        "capex_crude_gas_all_entities_match": all(
            row is not None
            and row["matched_entities"] == len(row["entities"])
            and row["conflict"] == 0
            for row in required_pair_matches.values()
        ),
    }
    return {
        "schema_version": 1,
        "experiment": "quantity_unit_canonicalization_audit_v1",
        "scope": "evaluation_only_representation_audit_no_forecast_selection_no_production_change",
        "baseline_git_commit": git_revision(),
        "hypothesis": (
            "A target-derived unit registry and generic semantic roles can canonicalize explicit numeric fields "
            "once, abstain on ambiguous scalars, and make equivalent schemas stable without task-specific rules."
        ),
        "reference": {
            "repository": "https://github.com/wangzgui/agenthon-t4-baseline-2026",
            "active_version": "s1.6",
            "mechanisms": ["quantity semantics", "canonical units", "checked numerical facts"],
        },
        "registry": {
            "target_units": sorted(PERCENT_TARGETS | {"basis_points", "percentage_points", "million_barrels_change", "billion_cubic_feet_change"}),
            "source_units": sorted(set(UNIT_ALIASES.values()) | {"percentage_points", "million_barrels", "thousand_barrels", "billion_cubic_feet", "million_cubic_feet"}),
            "conversion_factors": {f"{left}->{right}": factor for (left, right), factor in sorted(CONVERSION_FACTORS.items())},
        },
        "pairs": len(results),
        "results": results,
        "roundtrip_cases": roundtrip_cases,
        "permutation_failures": permutation_failures,
        "provenance_failures": provenance_failures,
        "accounting_failures": accounting_failures,
        "implicit_selection_failures": implicit_selection_failures,
        "events_with_schema_invariant_entity_quantities": numeric_events_with_matches,
        "required_pair_matches": required_pair_matches,
        "gates": gates,
        "decision": "pass_to_model_ab_design" if all(gates.values()) else "reject_no_production_change",
        "model_api_calls": 0,
        "local_llm_run": False,
        "limitations": [
            "Field-name unit parsing is intentionally conservative and does not infer units from magnitude.",
            "Pair agreement tests representation invariance, not predictive quality.",
            "Latest corpus-table facts cover simple dated pipe tables and abstain on other prose/table shapes.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()
    report = audit()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "decision": report["decision"],
        "pairs": report["pairs"],
        "gates": report["gates"],
        "permutation_failures": report["permutation_failures"],
        "provenance_failures": report["provenance_failures"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
