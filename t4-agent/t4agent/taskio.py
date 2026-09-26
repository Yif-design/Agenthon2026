from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Task:
    raw: dict[str, Any]
    task_id: str
    schema_version: str
    target: dict[str, Any]
    target_type: str
    labels: list[str]
    entities: list[dict[str, Any]]
    cutoff_date: str
    interval_level: float
    prompt: str
    family: str


def load_task(path: str | Path) -> Task:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    target = raw.get("target") or {}
    target_type = str(target.get("type") or raw.get("target_type") or "classification")
    labels = [str(x) for x in target.get("labels", [])]
    return Task(
        raw=raw,
        task_id=str(raw.get("task_id") or raw.get("id") or ""),
        schema_version=str(raw.get("schema_version") or "3"),
        target=target,
        target_type=target_type,
        labels=labels,
        entities=list(raw.get("entities") or raw.get("rows") or []),
        cutoff_date=str(raw.get("cutoff_date") or ""),
        interval_level=float(raw.get("interval_level") or 0.90),
        prompt=str(raw.get("prompt") or ""),
        family=str(raw.get("family") or ""),
    )


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=out.parent, prefix=f".{out.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, out)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
