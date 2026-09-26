from __future__ import annotations

from typing import Any
import math

from .retrieve import IndexedCorpus, allowed_document_ids
from .taskio import Task


def validate_answer(answer: dict[str, Any], task: Task, corpus: IndexedCorpus) -> list[str]:
    errors: list[str] = []
    if answer.get("task_id") != task.task_id:
        errors.append("task_id mismatch")
    if answer.get("target_type") != task.target_type:
        errors.append("target_type mismatch")
    preds = answer.get("entity_predictions")
    if not isinstance(preds, list):
        return ["entity_predictions missing"]
    expected = [str(e.get("entity_id", "")) for e in task.entities]
    entity_by_id = {str(e.get("entity_id", "")): e for e in task.entities}
    got = [str(p.get("entity_id", "")) for p in preds if isinstance(p, dict)]
    if sorted(got) != sorted(expected):
        errors.append(f"roster mismatch expected={expected} got={got}")
    if task.target_type == "ranking":
        ranks = [p.get("rank") for p in preds if isinstance(p, dict) and "rank" in p]
        if ranks and sorted(ranks) != list(range(1, len(expected) + 1)):
            errors.append("ranking rank field is not a full permutation")
    for pred in preds:
        if not isinstance(pred, dict):
            errors.append("prediction is not object")
            continue
        eid = pred.get("entity_id", "<missing>")
        interval = pred.get("interval")
        if not isinstance(interval, dict):
            errors.append(f"{eid}: interval missing")
        else:
            lo, hi = interval.get("lo"), interval.get("hi")
            if interval.get("level") != task.interval_level:
                errors.append(f"{eid}: interval level mismatch")
            if not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)):
                errors.append(f"{eid}: interval lo/hi missing")
            elif not math.isfinite(float(lo)) or not math.isfinite(float(hi)) or lo > hi:
                errors.append(f"{eid}: interval is not finite and ordered")
            elif isinstance(pred.get("point_forecast"), (int, float)) and not lo <= pred["point_forecast"] <= hi:
                errors.append(f"{eid}: interval does not contain point forecast")
        claims = pred.get("claims")
        if not isinstance(claims, list) or not claims:
            errors.append(f"{eid}: claims missing")
        else:
            allowed = allowed_document_ids(task, entity_by_id.get(str(eid), {}), corpus)
            for claim in claims:
                if not isinstance(claim, dict):
                    errors.append(f"{eid}: malformed claim")
                    continue
                doc_id = str(claim.get("doc_id") or "")
                text = corpus.doc_texts.get(doc_id)
                start, end = claim.get("span_start"), claim.get("span_end")
                if text is None:
                    errors.append(f"{eid}: unresolved doc_id {doc_id}")
                elif doc_id not in allowed:
                    errors.append(f"{eid}: citation doc_id is outside entity scope: {doc_id}")
                elif not isinstance(start, int) or not isinstance(end, int) or not (0 <= start < end <= len(text)):
                    errors.append(f"{eid}: invalid span for {doc_id}")
                elif not text[start:end].strip():
                    errors.append(f"{eid}: empty citation span for {doc_id}")
        if task.target_type == "classification" and pred.get("label") not in task.labels:
            errors.append(f"{eid}: invalid label {pred.get('label')}")
        if task.target_type in ("regression", "ranking") and not isinstance(pred.get("point_forecast"), (int, float)):
            errors.append(f"{eid}: point_forecast missing")
        elif isinstance(pred.get("point_forecast"), (int, float)) and not math.isfinite(float(pred["point_forecast"])):
            errors.append(f"{eid}: point_forecast is not finite")
    return errors
