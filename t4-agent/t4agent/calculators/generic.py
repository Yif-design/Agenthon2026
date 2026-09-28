from __future__ import annotations

import re
from typing import Any

from ..calc import interval_for, select_default_point
from ..retrieve import IndexedCorpus
from ..taskio import Task
from .common import ModelOutput


GENERIC_NUMERIC_INTERVAL_SCALE = 2.0


def solve(
    task: Task,
    entity: dict[str, Any],
    signals: dict[str, int],
    parameters: dict[str, float | None],
    corpus: IndexedCorpus,
    row_index: int,
    row_count: int,
) -> ModelOutput:
    name = str(task.target.get("name", ""))
    baseline, baseline_field, baseline_reason = select_default_point(
        task.target_type,
        name,
        entity,
        row_index,
        row_count,
    )
    signal = signals.get("directional_signal", 0)
    point = baseline
    if task.target_type in {"regression", "ranking"} and signal:
        baseline_interval = interval_for(baseline, name, task.interval_level)
        scale = (baseline_interval["hi"] - baseline_interval["lo"]) / 6.0
        point = baseline + signal * scale
    label = _label(signal, task.labels, task.prompt, name)
    method = "generic_evidence_adjusted" if signal else "generic_baseline"
    final_interval = interval_for(point, name, task.interval_level)
    if task.target_type in {"regression", "ranking"}:
        half = (final_interval["hi"] - final_interval["lo"]) / 2.0
        final_interval = {
            "level": final_interval["level"],
            "lo": point - GENERIC_NUMERIC_INTERVAL_SCALE * half,
            "hi": point + GENERIC_NUMERIC_INTERVAL_SCALE * half,
        }
    return ModelOutput(
        point,
        label,
        final_interval,
        method,
        derivation={
            "baseline": baseline,
            "baseline_field": baseline_field,
            "baseline_reason": baseline_reason,
            "directional_signal": signal,
        },
    )


ROLE_KEYWORDS = {
    "positive": (
        "up", "positive", "yes", "beat", "upgrade", "expand", "high", "higher", "increase",
        "increases", "increased", "increasing", "rise", "rises", "rising", "rose", "improve",
        "improves", "improved", "improving", "gain", "gains", "gained", "climb", "climbs",
        "pass", "approved", "approve", "met", "satisfied", "compliant",
    ),
    "neutral": (
        "flat", "neutral", "unchanged", "inline", "no_change", "stable", "steady", "same",
        "hold", "medium",
    ),
    "negative": (
        "down", "negative", "no", "miss", "downgrade", "contract", "low", "lower", "decrease",
        "decreases", "decreased", "decreasing", "fall", "falls", "falling", "fell", "decline",
        "declines", "declined", "deteriorate", "deteriorates", "deteriorated", "worsen", "worsens",
        "worsening", "loss", "drop", "drops", "dropped", "fail", "failed", "rejected", "reject",
    ),
}
EVENT_TARGET_TOKENS = {"risk", "event", "default", "failure", "breach", "bankruptcy"}
TOKEN_RE = re.compile(r"[a-z0-9]+")


def _label(signal: int, labels: list[str], prompt: str = "", target_name: str = "") -> str | None:
    if not labels:
        return None
    roles = infer_label_roles(labels, prompt, target_name)
    role = "positive" if signal > 0 else "negative" if signal < 0 else "neutral"
    if role in roles:
        return roles[role]
    return _legacy_label(signal, labels)


def infer_label_roles(labels: list[str], prompt: str, target_name: str) -> dict[str, str]:
    """Map arbitrary allowed labels to signal roles using bounded task-schema text."""
    roles: dict[str, str] = {}
    assigned: set[str] = set()
    for label in labels:
        role = _intrinsic_role(label, target_name)
        if role is not None and role not in roles:
            roles[role] = label
            assigned.add(label)
    bounded_prompt = prompt[:8000].lower()
    for label in labels:
        if label in assigned:
            continue
        clause = _label_clause(bounded_prompt, label)
        role = _clause_role(clause)
        if role is not None and role not in roles:
            roles[role] = label
            assigned.add(label)
    return roles


def _intrinsic_role(label: str, target_name: str) -> str | None:
    tokens = set(TOKEN_RE.findall(label.lower()))
    target_tokens = set(TOKEN_RE.findall(target_name.lower()))
    if tokens & {"not", "no", "without"} and target_tokens & EVENT_TARGET_TOKENS:
        return "negative"
    if target_tokens & EVENT_TARGET_TOKENS and tokens & target_tokens:
        return "positive"
    for role in ("neutral", "positive", "negative"):
        if tokens & set(ROLE_KEYWORDS[role]):
            return role
    if label.lower() == "credit_event":
        return "positive"
    if label.lower() == "no_event":
        return "negative"
    return None


def _label_clause(prompt: str, label: str) -> str:
    parts = TOKEN_RE.findall(label.lower())
    if not parts:
        return ""
    pattern = r"(?<![a-z0-9])" + r"[_\s-]+".join(map(re.escape, parts)) + r"(?![a-z0-9])"
    match = re.search(pattern, prompt)
    if match is None:
        return ""
    tail = prompt[match.end() : match.end() + 160]
    boundary = re.search(r"[,;.\n]", tail)
    return tail[: boundary.start()] if boundary is not None else tail


def _clause_role(clause: str) -> str | None:
    tokens = set(TOKEN_RE.findall(clause))
    scores = {role: len(tokens & set(keywords)) for role, keywords in ROLE_KEYWORDS.items()}
    best = max(scores.values(), default=0)
    winners = [role for role, score in scores.items() if score == best and score > 0]
    return winners[0] if len(winners) == 1 else None


def _legacy_label(signal: int, labels: list[str]) -> str:
    if signal == 0:
        for candidate in ("flat", "neutral", "unchanged", "inline", "no_change"):
            for label in labels:
                if candidate in label.lower():
                    return label
        return labels[0]
    positive = ("up", "positive", "yes", "beat", "credit_event")
    negative = ("down", "negative", "no", "miss", "no_event")
    candidates = positive if signal > 0 else negative
    for candidate in candidates:
        for label in labels:
            if candidate in label.lower():
                return label
    return labels[0]
