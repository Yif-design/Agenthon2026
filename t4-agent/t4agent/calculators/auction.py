from __future__ import annotations

import re
from statistics import pstdev
from typing import Any

from ..retrieve import IndexedCorpus
from ..taskio import Task
from .common import ModelOutput, artifact_available, clip, interval, number


INTERVAL_PSTDEV_MULTIPLIER = 1.65
ARTIFACT_AVAILABLE_DATE = "2022-01-01"


def solve(
    task: Task,
    entity: dict[str, Any],
    signals: dict[str, int],
    parameters: dict[str, float | None],
    corpus: IndexedCorpus,
    row_index: int,
    row_count: int,
) -> ModelOutput:
    values, evidence = _history(corpus, str(entity.get("tenor") or ""))
    calibrated = False
    multiplier: float | None = None
    if values:
        recent = values[-6:]
        baseline = sum(recent) / len(recent)
        calibrated = artifact_available(task.cutoff_date, ARTIFACT_AVAILABLE_DATE)
        trend = 0.0 if len(values) < 3 else clip((values[-1] - values[-3]) / 2.0, -0.08, 0.08)
        point = baseline if calibrated else baseline + trend
        multiplier = INTERVAL_PSTDEV_MULTIPLIER if calibrated else 1.65
        half = max(
            0.15,
            multiplier * pstdev(recent) if len(recent) > 1 else 0.0,
        )
        if calibrated:
            evidence = _prefer_verified_recent_mean_summary(corpus, evidence, baseline)
    else:
        point, half = 2.5, 0.8
    return ModelOutput(
        point,
        None,
        interval(point, task.interval_level, half),
        "same_tenor_recent_history",
        evidence=evidence,
        derivation={
            "recent_values": values[-6:],
            "forecast": point,
            "interval_pstdev_multiplier": multiplier,
            "calibrated_artifact_available": calibrated,
            "artifact_available_date": ARTIFACT_AVAILABLE_DATE,
        },
    )


def _history(corpus: IndexedCorpus, tenor: str) -> tuple[list[float], list[dict[str, Any]]]:
    wanted = tenor.lower().replace("-", "")
    for doc_id, text in corpus.doc_texts.items():
        first = text.splitlines()[0].lower().replace("-", "") if text else ""
        if wanted not in first or "auction" not in first:
            continue
        values: list[float] = []
        used_lines: list[str] = []
        for line in text.splitlines():
            if not re.match(r"^\d{4}-\d{2}-\d{2}\s*\|", line):
                continue
            cells = [part.strip() for part in line.split("|")]
            if len(cells) > 4:
                value = number(cells[4])
                if value is not None:
                    values.append(value)
                    used_lines.append(line)
        if values:
            quote = "\n".join(used_lines[-6:])
            evidence = [{
                "doc_id": doc_id,
                "quote": quote,
                "claim": f"The frozen TreasuryDirect table reports the recent {tenor} bid-to-cover history used by the forecast.",
                "name": "same_tenor_history",
                "value": values[-6:],
            }] if quote in text else []
            return values, evidence
    return [], []


def _prefer_verified_recent_mean_summary(
    corpus: IndexedCorpus,
    evidence: list[dict[str, Any]],
    baseline: float,
) -> list[dict[str, Any]]:
    """Prefer a concise corpus summary only after reproducing its statistic from raw rows."""
    if not evidence:
        return evidence
    doc_id = str(evidence[0].get("doc_id") or "")
    text = corpus.doc_texts.get(doc_id, "")
    for line in text.splitlines():
        match = re.search(
            r"average over the six most recent auctions is\s*([0-9]+(?:\.[0-9]+)?)",
            line,
            flags=re.IGNORECASE,
        )
        if match is None:
            continue
        reported = number(match.group(1))
        if reported is None or abs(reported - baseline) > 0.001:
            continue
        preferred = dict(evidence[0])
        preferred["quote"] = line
        preferred["claim"] = (
            "The frozen TreasuryDirect summary reports the verified recent-six "
            "bid-to-cover average used by the forecast."
        )
        return [preferred]
    return evidence
