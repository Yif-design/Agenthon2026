"""Shared deterministic writer for materialized proxy question pairs."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rank(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    order = sorted(rows, key=lambda row: (-float(row[key]), row["entity_id"]))
    return {row["entity_id"]: index + 1 for index, row in enumerate(order)}


def materialize_pair(
    *, root: Path, snapshot_path: Path, question_id: str, origin: str,
    cutoff: str, resolution: str, split: str, target_type: str,
    target_names: dict[str, str], family_names: dict[str, str], unit: str,
    prompt: str, license_text: str, source_name: str, rows: list[dict[str, Any]],
    labels: list[str] | None = None,
) -> None:
    snapshot = json.loads(snapshot_path.read_text())
    for variant in ("explicit", "transformed"):
        ordered = rows if variant == "explicit" else list(reversed(rows))
        unit_id = f"{question_id}-{origin}-{variant}"
        directory = root / unit_id
        if directory.exists():
            shutil.rmtree(directory)
        (directory / "corpus").mkdir(parents=True)
        entities = []
        for row in ordered:
            entities.append({
                "entity_id": row["entity_id"], "name": row["name"],
                "corpus_ref": f"corpus/{row['entity_id']}.json", **row[variant],
            })
            dump(directory / "corpus" / f"{row['entity_id']}.json", {
                "doc_id": f"PROXY_{question_id}_{row['entity_id']}_{variant}",
                "doc_date": cutoff, "entities": [row["entity_id"]],
                "source": source_name, "license": license_text,
                "text": row[f"corpus_{variant}"],
            })
        target = {"type": target_type, "name": target_names[variant], "unit": unit}
        if labels:
            target["labels"] = labels
        dump(directory / "task.json", {
            "task_id": unit_id, "schema_version": "3", "family": family_names[variant],
            "target": target, "prompt": prompt, "cutoff_date": cutoff,
            "resolution_date": resolution, "interval_level": 0.9,
            "schema_variant": variant, "entities": entities,
        })
        params = [
            "faithfulness_threshold = 0.80", "interval_level = 0.90",
            f'target_type = "{target_type}"',
        ]
        if target_type == "classification":
            params.append("interval_leg = false")
            params.append("labels = [" + ", ".join(json.dumps(x) for x in labels or []) + "]")
        params.extend(("composite_weights = [0.7, 0.3]", "tau_citation = 0.5"))
        (directory / "card.toml").write_text(f'''schema_version = "2.0"

[task]
id = "{unit_id}"
track = "analysis"
title = "{question_id} ({variant})"
split = "{split}"
family = "{family_names[variant]}"
target_type = "{target_type}"
cutoff_date = "{cutoff}"
resolution_date = "{resolution}"

[provenance]
license = "{license_text}"
data_source = "{source_name}"
data_cutoff = "{cutoff}"
redistributable = true
manifest = "manifest.json"

[scoring]
verifier = "t4.faithful_analysis"
metric = "analysis_composite"
admissibility_gates = ["g0_integrity", "g1_schema", "g2_cutoff_resource", "g3_domain_semantics"]

[scoring.params]
{chr(10).join(params)}

[agent]
timeout_sec = 600.0
''')
        ranks = _rank(ordered, "naive_point") if target_type == "ranking" else {}
        predictions = []
        for row in ordered:
            point, half = float(row["naive_point"]), float(row["naive_half"])
            pred = {
                "entity_id": row["entity_id"], "point_forecast": point,
                "interval": {"lo": point - half, "hi": point + half, "level": 0.9},
                "claims": [{"doc_id": f"PROXY_{question_id}_{row['entity_id']}_{variant}",
                            "span_start": 0, "span_end": 1, "claim": f"{source_name} source."}],
            }
            if target_type == "classification":
                pred["label"] = row["naive_label"]
            if target_type == "ranking":
                pred["rank"] = ranks[row["entity_id"]]
            predictions.append(pred)
        dump(directory / "reference/naive_answer.json", {
            "task_id": unit_id, "schema_version": "3", "target_type": target_type,
            "entity_predictions": predictions, "notes": {"baseline_id": "declared-cutoff-rule"},
        })
        outcome_key = "true_label" if target_type == "classification" else "y"
        dump(directory / "reference/outcome.json", {
            "task_id": unit_id,
            "outcomes": [{"entity_id": row["entity_id"], outcome_key: row["truth"]} for row in ordered],
        })
        dump(directory / "provenance.json", {
            "question_id": question_id, "variant": variant, "split": split,
            "source_snapshot": str(snapshot_path), "source_snapshot_sha256": sha256(snapshot_path),
            "download_date": snapshot["retrieved_at"], "cutoff_date": cutoff,
            "resolution_date": resolution, "license": license_text,
            "generator": snapshot["generator"], "generator_version": "1.0.0",
            "raw_sources": snapshot.get("raw_sources", []),
        })
        files = []
        for path in sorted(p for p in directory.rglob("*") if p.is_file() and p.name != "manifest.json"):
            files.append({"path": path.relative_to(directory).as_posix(),
                          "bytes": path.stat().st_size, "sha256": sha256(path)})
        dump(directory / "manifest.json", {"manifest_version": "1.0", "unit_id": unit_id, "files": files})
