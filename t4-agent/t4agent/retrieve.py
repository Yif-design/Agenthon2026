from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from .family_specs import task_family_spec

TOKEN_RE = re.compile(r"\$?[A-Za-z0-9_]+(?:\.[0-9]+)?%?(?:-[A-Za-z0-9_]+)*")
SCHEMA_PART_RE = re.compile(r"[A-Za-z]+|[0-9]+")
MAX_SCHEMA_QUERY_PARTS = 8
MAX_PROMPT_QUERY_CHARS = 512
MAX_PROMPT_QUERY_TERMS = 24
GENERIC_RUBRIC = "results outlook growth risk change forecast target evidence"
RUBRIC_BY_FAMILY = {
    "eps_consensus": "eps earnings revenue margin guidance diluted net income per share",
    "eps_yoy": "eps earnings revenue margin guidance diluted net income per share",
    "bank_eps": "eps earnings revenue margin guidance diluted net income per share",
    "credit": "liquidity debt default bankruptcy covenant going concern rating maturity",
    "rates": "fomc inflation labor market unemployment fed funds policy yield curve",
    "cpi": "cpi inflation shelter energy food services goods month over month",
    "auction": "auction bid cover indirect direct dealer demand tail offering amount",
    "positioning": "commitments traders net position open interest managed money futures",
    "macro_revision": "revision estimate preliminary durable goods shipments inventories retail sales",
    "reaction": "earnings guidance revenue margin outlook surprise market reaction",
    "generic": GENERIC_RUBRIC,
}
SCHEMA_NOISE_PARTS = {
    "forecast",
    "family",
    "generic",
    "metric",
    "opaque",
    "target",
    "task",
    "unknown",
    "unseen",
}
PROMPT_QUERY_STOPWORDS = SCHEMA_NOISE_PARTS | {
    "allowed",
    "and",
    "based",
    "classification",
    "determine",
    "each",
    "entities",
    "entity",
    "estimate",
    "for",
    "from",
    "future",
    "into",
    "label",
    "labels",
    "next",
    "output",
    "percent",
    "percentage",
    "predict",
    "ranking",
    "regression",
    "return",
    "score",
    "the",
    "their",
    "this",
    "using",
    "value",
    "values",
    "whether",
    "with",
}


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    doc_date: str | None
    span_start: int
    span_end: int
    text: str


@dataclass(frozen=True)
class IndexedCorpus:
    chunks: list[Chunk]
    doc_texts: dict[str, str]
    doc_dates: dict[str, str | None]
    doc_paths: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float


def tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(text)]


def _date_ok(doc_date: str | None, cutoff: str) -> bool:
    if not cutoff:
        return True
    if not doc_date:
        return False
    try:
        return date.fromisoformat(doc_date[:10]) <= date.fromisoformat(cutoff[:10])
    except ValueError:
        return False


def _date_ordinal(doc_date: str | None) -> int:
    try:
        return date.fromisoformat(str(doc_date)[:10]).toordinal()
    except ValueError:
        return 0


def _score_order(item: ScoredChunk) -> tuple[float, int, str, int]:
    """Prefer recent cutoff-safe evidence only when BM25 scores are exactly equal."""
    return (-item.score, -_date_ordinal(item.chunk.doc_date), item.chunk.doc_id, item.chunk.span_start)


def _fallback_order(item: ScoredChunk) -> int:
    """Use recency for zero-score fallbacks while preserving corpus order for equal dates."""
    return -_date_ordinal(item.chunk.doc_date)


def _span_texts(doc: dict) -> list[str]:
    if isinstance(doc.get("text"), str):
        return [doc["text"]]
    spans = doc.get("spans")
    if isinstance(spans, list):
        return [str(x.get("text", "")) for x in spans if isinstance(x, dict)]
    return []


def build_index(corpus_dir: str | Path, cutoff_date: str) -> IndexedCorpus:
    corpus_root = Path(corpus_dir)
    resolved_root = corpus_root.resolve()
    chunks: list[Chunk] = []
    doc_texts: dict[str, str] = {}
    doc_dates: dict[str, str | None] = {}
    doc_paths: dict[str, str] = {}
    for path in sorted(corpus_root.rglob("*.json")):
        if path.name == "manifest.json":
            continue
        try:
            resolved_path = path.resolve(strict=True)
            resolved_path.relative_to(resolved_root)
        except (FileNotFoundError, ValueError) as exc:
            raise ValueError(f"corpus document escapes corpus root: {path}") from exc
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc_id = str(doc.get("doc_id") or path.stem)
        if doc_id in doc_paths:
            raise ValueError(f"duplicate corpus doc_id: {doc_id}")
        doc_date = doc.get("doc_date")
        if not _date_ok(str(doc_date) if doc_date else None, cutoff_date):
            continue
        parts = _span_texts(doc)
        offset = 0
        for text in parts:
            if text.strip():
                chunks.extend(_chunks_for_text(doc_id, str(doc_date) if doc_date else None, text, offset))
            offset += len(text) + 1
        doc_texts[doc_id] = " ".join(parts)
        doc_dates[doc_id] = str(doc_date) if doc_date else None
        doc_paths[doc_id] = path.relative_to(corpus_root).as_posix()
    return IndexedCorpus(chunks, doc_texts, doc_dates, doc_paths)


def _chunks_for_text(doc_id: str, doc_date: str | None, text: str, base_offset: int) -> list[Chunk]:
    if len(text) <= 2400:
        return [Chunk(doc_id, doc_date, base_offset, base_offset + len(text), text)]
    out: list[Chunk] = []
    start = 0
    while start < len(text):
        end = min(start + 2200, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n", start + 1200, end), text.rfind(". ", start + 1200, end))
            if boundary > start:
                end = boundary + 1
        piece = text[start:end]
        if piece.strip():
            out.append(Chunk(doc_id, doc_date, base_offset + start, base_offset + end, piece))
        if end >= len(text):
            break
        start = max(start + 1, end - 250)
    return out


class BM25:
    def __init__(self, chunks: list[Chunk], tokenizer: Callable[[str], list[str]] | None = None):
        self.chunks = chunks
        self.tokenizer = tokenizer or tokenize
        self.tokens = [self.tokenizer(c.text) for c in chunks]
        self.lengths = [len(t) for t in self.tokens]
        self.avg_len = sum(self.lengths) / max(len(self.lengths), 1)
        df: dict[str, int] = defaultdict(int)
        for toks in self.tokens:
            for tok in set(toks):
                df[tok] += 1
        n = max(len(chunks), 1)
        self.idf = {tok: math.log(1 + (n - count + 0.5) / (count + 0.5)) for tok, count in df.items()}
        self.tfs = [Counter(toks) for toks in self.tokens]

    def search(
        self, query: str, top_k: int = 8, allowed_doc_ids: set[str] | None = None
    ) -> list[ScoredChunk]:
        q = self.tokenizer(query)
        if not q:
            candidates = [c for c in self.chunks if allowed_doc_ids is None or c.doc_id in allowed_doc_ids]
            return sorted((ScoredChunk(c, 0.0) for c in candidates), key=_fallback_order)[:top_k]
        scores: list[ScoredChunk] = []
        k1, b = 1.5, 0.75
        for chunk, tf, length in zip(self.chunks, self.tfs, self.lengths, strict=True):
            if allowed_doc_ids is not None and chunk.doc_id not in allowed_doc_ids:
                continue
            score = 0.0
            for tok in q:
                freq = tf.get(tok, 0)
                if not freq:
                    continue
                denom = freq + k1 * (1 - b + b * length / max(self.avg_len, 1.0))
                score += self.idf.get(tok, 0.0) * freq * (k1 + 1) / denom
            if score > 0:
                scores.append(ScoredChunk(chunk, score))
        scores.sort(key=_score_order)
        if scores:
            return scores[:top_k]
        candidates = [c for c in self.chunks if allowed_doc_ids is None or c.doc_id in allowed_doc_ids]
        return sorted((ScoredChunk(c, 0.0) for c in candidates), key=_fallback_order)[:top_k]


def allowed_document_ids(task: object, entity: dict, corpus: IndexedCorpus) -> set[str]:
    """Return the hard document scope for one roster entity before lexical retrieval."""
    all_ids = _corpus_ref_document_ids(entity.get("corpus_ref"), corpus)
    target = getattr(task, "target", {}) or {}
    routed_family = task_family_spec(
        str(getattr(task, "family", "")),
        str(target.get("name", "")),
        str(getattr(task, "target_type", target.get("type", ""))),
        list(getattr(task, "entities", ()) or ()),
    ).key
    cik = "".join(ch for ch in str(entity.get("cik") or "") if ch.isdigit()).zfill(10)
    if cik.strip("0"):
        scoped = {doc_id for doc_id in all_ids if cik in doc_id}
        if scoped:
            return scoped
    if routed_family == "macro_revision":
        series_id = str(entity.get("series_id") or "").upper()
        scoped = {doc_id for doc_id in all_ids if series_id and series_id in doc_id.upper()}
        if series_id == "PAYEMS":
            scoped |= {doc_id for doc_id in all_ids if "CES_PRELIM_BENCHMARK" in doc_id.upper()}
        return scoped or all_ids
    if routed_family == "auction":
        tenor_text = str(entity.get("tenor") or "").upper()
        digits = "".join(ch for ch in tenor_text if ch.isdigit())
        tenor = f"{digits}Y" if digits else tenor_text.replace("-", "").replace(" ", "")
        scoped = {
            doc_id
            for doc_id in all_ids
            if "TDIRECT_UPCOMING" in doc_id.upper()
            or ("TDIRECT_AUCTIONS" in doc_id.upper() and tenor in doc_id.upper().replace("-", "").replace("_", ""))
        }
        return scoped or all_ids
    if routed_family == "positioning":
        entity_id = str(entity.get("entity_id") or "").upper()
        scoped = {
            doc_id
            for doc_id in all_ids
            if entity_id in doc_id.upper()
            or "COT_METHODOLOGY" in doc_id.upper()
            or "MKT_SNAPSHOT" in doc_id.upper()
        }
        return scoped or all_ids
    if routed_family == "cpi":
        return {
            doc_id
            for doc_id in all_ids
            if any(token in doc_id.upper() for token in ("CPI", "GASREG", "EIA"))
        } or all_ids
    if routed_family == "rates":
        return {
            doc_id
            for doc_id in all_ids
            if any(token in doc_id.upper() for token in ("FOMC", "RATES_SNAPSHOT"))
        } or all_ids
    return all_ids


def _corpus_ref_document_ids(corpus_ref: object, corpus: IndexedCorpus) -> set[str]:
    """Resolve a task-relative corpus pointer without allowing it to escape the corpus root."""
    all_ids = set(corpus.doc_texts)
    if corpus_ref is None:
        return all_ids
    if not isinstance(corpus_ref, str) or not corpus_ref.strip():
        raise ValueError("corpus_ref must be a non-empty relative path")
    raw = corpus_ref.strip()
    if "\\" in raw or raw.startswith("/"):
        raise ValueError(f"unsafe corpus_ref: {corpus_ref!r}")
    parts = [part for part in raw.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError(f"unsafe corpus_ref: {corpus_ref!r}")
    if parts and parts[0] == "corpus":
        parts = parts[1:]
    if not parts:
        return all_ids
    if not corpus.doc_paths:
        return set()
    prefix = tuple(parts)
    scoped: set[str] = set()
    for doc_id, relative_path in corpus.doc_paths.items():
        path_parts = tuple(part for part in relative_path.split("/") if part)
        if path_parts == prefix or path_parts[: len(prefix)] == prefix:
            scoped.add(doc_id)
    return scoped


def scoped_corpus(corpus: IndexedCorpus, allowed_doc_ids: set[str]) -> IndexedCorpus:
    return IndexedCorpus(
        chunks=[chunk for chunk in corpus.chunks if chunk.doc_id in allowed_doc_ids],
        doc_texts={doc_id: text for doc_id, text in corpus.doc_texts.items() if doc_id in allowed_doc_ids},
        doc_dates={doc_id: value for doc_id, value in corpus.doc_dates.items() if doc_id in allowed_doc_ids},
        doc_paths={doc_id: value for doc_id, value in corpus.doc_paths.items() if doc_id in allowed_doc_ids},
    )


def query_for(task: object, entity: dict, include_all_scalar_fields: bool = False) -> str:
    parts: list[str] = []
    has_semantic_schema_terms = False
    standard_keys = (
        "entity_id",
        "name",
        "sector",
        "industry",
        "series_id",
        "series_name",
        "asset_class",
        "tenor",
        "description",
    )
    for key in standard_keys:
        val = entity.get(key)
        if val is not None:
            parts.append(str(val))
    if include_all_scalar_fields:
        for key, value in entity.items():
            if (
                key in standard_keys
                or key == "corpus_ref"
                or value is None
                or isinstance(value, (dict, list, tuple, set))
                or (isinstance(value, float) and not math.isfinite(value))
            ):
                continue
            key_text, expanded = _schema_query_text(str(key))
            parts.append(key_text)
            has_semantic_schema_terms = has_semantic_schema_terms or expanded
            if isinstance(value, str):
                parts.append(value[:1000])
            elif isinstance(value, (bool, int, float)):
                parts.append(str(value))
    target = getattr(task, "target", {}) or {}
    target_name = str(target.get("name", ""))
    family = str(getattr(task, "family", ""))
    if include_all_scalar_fields:
        target_text, target_expanded = _schema_query_text(target_name)
        family_text, family_expanded = _schema_query_text(family)
        parts.extend((target_text, family_text))
        has_semantic_schema_terms = has_semantic_schema_terms or target_expanded or family_expanded
    else:
        parts.extend((target_name, family))
    routed_family = task_family_spec(
        family,
        target_name,
        str(getattr(task, "target_type", target.get("type", ""))),
        list(getattr(task, "entities", ()) or ()),
    ).key
    prompt_terms: list[str] = []
    if include_all_scalar_fields and routed_family == "generic" and not has_semantic_schema_terms:
        prompt_terms = _prompt_query_terms(str(getattr(task, "prompt", "")))
        if prompt_terms:
            parts.append(" ".join(prompt_terms))
    keywords = rubric_keywords(family, target_name, routed_family=routed_family)
    if not (
        include_all_scalar_fields
        and (has_semantic_schema_terms or prompt_terms)
        and keywords == GENERIC_RUBRIC
    ):
        parts.append(keywords)
    return " ".join(parts)


def _schema_query_text(value: str) -> tuple[str, bool]:
    """Keep the exact identifier and add bounded components when at least two are semantic."""
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).replace("_", " ").replace("-", " ")
    components = SCHEMA_PART_RE.findall(separated)[:MAX_SCHEMA_QUERY_PARTS]
    meaningful = [
        part
        for part in components
        if part.isalpha() and len(part) >= 2 and part.lower() not in SCHEMA_NOISE_PARTS
    ]
    expanded = len(meaningful) >= 2 and tokenize(value) != [part.lower() for part in components]
    return (f"{value} {' '.join(components)}", True) if expanded else (value, False)


def _prompt_query_terms(prompt: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for raw in SCHEMA_PART_RE.findall(prompt[:MAX_PROMPT_QUERY_CHARS]):
        term = raw.lower()
        if len(term) < 3 or term in PROMPT_QUERY_STOPWORDS or term in seen:
            continue
        terms.append(term)
        seen.add(term)
        if len(terms) >= MAX_PROMPT_QUERY_TERMS:
            break
    return terms if len(terms) >= 2 else []


def rubric_keywords(family: str, target_name: str, *, routed_family: str | None = None) -> str:
    if routed_family is not None:
        return RUBRIC_BY_FAMILY.get(routed_family, GENERIC_RUBRIC)
    text = f"{family} {target_name}".lower()
    if "eps" in text:
        return "eps earnings revenue margin guidance diluted net income per share"
    if "credit" in text:
        return "liquidity debt default bankruptcy covenant going concern rating maturity"
    if "yield" in text or "curve" in text or "rate" in text:
        return "fomc inflation labor market unemployment fed funds policy yield curve"
    if "cpi" in text:
        return "cpi inflation shelter energy food services goods month over month"
    if "auction" in text or "bid_to_cover" in text:
        return "auction bid cover indirect direct dealer demand tail offering amount"
    if "position" in text or "cot" in text:
        return "commitments traders net position open interest managed money futures"
    if "revision" in text:
        return "revision estimate preliminary durable goods shipments inventories retail sales"
    if "reaction" in text:
        return "earnings guidance revenue margin outlook surprise market reaction"
    return GENERIC_RUBRIC
