from __future__ import annotations

import re
from typing import Any

from ..retrieve import IndexedCorpus
from ..taskio import Task
from .common import ModelOutput, interval, number


_PAIR_PATTERNS = (
    re.compile(
        r"diluted earnings per common share was\s*\$?\s*([0-9]+(?:\.[0-9]+)?)"
        r".{0,180}?compared with\s*\$?\s*([0-9]+(?:\.[0-9]+)?)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\$?\s*([0-9]+(?:\.[0-9]+)?)\s+per diluted common share"
        r".{0,180}?compared with.{0,100}?\$?\s*([0-9]+(?:\.[0-9]+)?)\s+per diluted common share",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\$?\s*([0-9]+(?:\.[0-9]+)?)\s+per diluted share"
        r".{0,180}?compared to\s*\$?\s*([0-9]+(?:\.[0-9]+)?)\s+per diluted share",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"diluted earnings per common share\s*\(EPS\)\s*of\s*\$?\s*([0-9]+(?:\.[0-9]+)?)"
        r".{0,180}?diluted EPS of\s*\$?\s*([0-9]+(?:\.[0-9]+)?)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"Earnings per common share\s+Basic\s+\$?\s*[0-9]+(?:\.[0-9]+)?\s+\$?\s*[0-9]+(?:\.[0-9]+)?"
        r".{0,100}?Diluted\s+\$?\s*([0-9]+(?:\.[0-9]+)?)\s+\$?\s*([0-9]+(?:\.[0-9]+)?)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"Diluted\s+Income from continuing operations\s+\$?\s*([0-9]+(?:\.[0-9]+)?)\s+\$?\s*([0-9]+(?:\.[0-9]+)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"Diluted earnings per share\s+\$?\s*([0-9]+(?:\.[0-9]+)?)\s+\$?\s*([0-9]+(?:\.[0-9]+)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"Per common share information\s+Earnings.{0,160}?Diluted earnings\s+\$?\s*([0-9]+(?:\.[0-9]+)?)\s+\$?\s*([0-9]+(?:\.[0-9]+)?)",
        re.IGNORECASE | re.DOTALL,
    ),
)

_THREE_COLUMN_PATTERN = re.compile(
    r"(?:Per Common Share.{0,160}?Diluted|Diluted earnings per common share)\s+\$?\s*"
    r"([0-9]+(?:\.[0-9]+)?)\s+\$?\s*([0-9]+(?:\.[0-9]+)?)\s+\$?\s*([0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE | re.DOTALL,
)


def extract_parameters(
    entity: dict[str, Any], corpus: IndexedCorpus
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """Extract the latest quarter and same-quarter-prior-year GAAP diluted EPS pair."""
    cik = str(entity.get("cik") or "").zfill(10)
    candidates = [
        (doc_id, text)
        for doc_id, text in corpus.doc_texts.items()
        if (cik and cik in doc_id) and ("10Q" in doc_id.upper() or "10-Q" in text[:1000].upper())
    ]
    for doc_id, text in candidates:
        pair = _find_pair(text)
        if pair is None:
            continue
        current, prior, quote = pair
        claim = (
            f"The filing reports latest-quarter GAAP diluted EPS of {current:g} "
            f"and same-quarter prior-year diluted EPS of {prior:g}."
        )
        evidence = {"doc_id": doc_id, "quote": quote, "claim": claim}
        return {
            "latest_reported_eps": current,
            "latest_reported_prior_year_eps": prior,
        }, [evidence]
    return {}, []


def _find_pair(text: str) -> tuple[float, float, str] | None:
    for pattern in _PAIR_PATTERNS:
        match = pattern.search(text)
        if match:
            return float(match.group(1)), float(match.group(2)), match.group(0)
    for match in _THREE_COLUMN_PATTERN.finditer(text):
        context = text[max(0, match.start() - 350) : match.start()]
        if "March 31" in context:
            return float(match.group(1)), float(match.group(3)), match.group(0)
    return None


def solve(
    task: Task,
    entity: dict[str, Any],
    signals: dict[str, int],
    parameters: dict[str, float | None],
    corpus: IndexedCorpus,
    row_index: int,
    row_count: int,
) -> ModelOutput:
    target_prior = number(entity.get("prior_year_q_eps")) or 0.0
    latest = parameters.get("latest_reported_eps")
    latest_prior = parameters.get("latest_reported_prior_year_eps")
    if latest is None or latest_prior is None or abs(target_prior) < 1e-9:
        point = 0.0
        return ModelOutput(point, None, interval(point, task.interval_level, 60.0), "missing_eps_zero_growth")
    recent_delta = latest - latest_prior
    forecast_eps = target_prior + recent_delta
    point = (forecast_eps - target_prior) / abs(target_prior) * 100.0
    half = max(20.0, abs(point) * 0.75)
    return ModelOutput(
        point,
        None,
        interval(point, task.interval_level, half),
        "seasonal_eps_delta_persistence",
        derivation={
            "target_prior_eps": target_prior,
            "latest_reported_eps": latest,
            "latest_reported_prior_year_eps": latest_prior,
            "recent_yoy_delta": recent_delta,
            "forecast_target_eps": forecast_eps,
        },
    )
