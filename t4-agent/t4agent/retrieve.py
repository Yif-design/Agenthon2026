from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

TOKEN_RE = re.compile(r"[A-Za-z0-9_.$%-]+")


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


def _span_texts(doc: dict) -> list[str]:
    if isinstance(doc.get("text"), str):
        return [doc["text"]]
    spans = doc.get("spans")
    if isinstance(spans, list):
        return [str(x.get("text", "")) for x in spans if isinstance(x, dict)]
    return []


def build_index(corpus_dir: str | Path, cutoff_date: str) -> IndexedCorpus:
    chunks: list[Chunk] = []
    doc_texts: dict[str, str] = {}
    doc_dates: dict[str, str | None] = {}
    for path in sorted(Path(corpus_dir).glob("*.json")):
        if path.name == "manifest.json":
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc_id = str(doc.get("doc_id") or path.stem)
        doc_date = doc.get("doc_date")
        if not _date_ok(str(doc_date) if doc_date else None, cutoff_date):
            continue
        parts = _span_texts(doc)
        offset = 0
        for text in parts:
            if text.strip():
                chunks.append(Chunk(doc_id, str(doc_date) if doc_date else None, offset, offset + len(text), text))
            offset += len(text) + 1
        doc_texts[doc_id] = " ".join(parts)
        doc_dates[doc_id] = str(doc_date) if doc_date else None
    return IndexedCorpus(chunks, doc_texts, doc_dates)


class BM25:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.tokens = [tokenize(c.text) for c in chunks]
        self.lengths = [len(t) for t in self.tokens]
        self.avg_len = sum(self.lengths) / max(len(self.lengths), 1)
        df: dict[str, int] = defaultdict(int)
        for toks in self.tokens:
            for tok in set(toks):
                df[tok] += 1
        n = max(len(chunks), 1)
        self.idf = {tok: math.log(1 + (n - count + 0.5) / (count + 0.5)) for tok, count in df.items()}
        self.tfs = [Counter(toks) for toks in self.tokens]

    def search(self, query: str, top_k: int = 8) -> list[ScoredChunk]:
        q = tokenize(query)
        if not q:
            return [ScoredChunk(c, 0.0) for c in self.chunks[:top_k]]
        scores: list[ScoredChunk] = []
        k1, b = 1.5, 0.75
        for chunk, tf, length in zip(self.chunks, self.tfs, self.lengths, strict=True):
            score = 0.0
            for tok in q:
                freq = tf.get(tok, 0)
                if not freq:
                    continue
                denom = freq + k1 * (1 - b + b * length / max(self.avg_len, 1.0))
                score += self.idf.get(tok, 0.0) * freq * (k1 + 1) / denom
            if score > 0:
                scores.append(ScoredChunk(chunk, score))
        scores.sort(key=lambda x: (-x.score, x.chunk.doc_id, x.chunk.span_start))
        return scores[:top_k] or [ScoredChunk(c, 0.0) for c in self.chunks[:top_k]]


def query_for(task: object, entity: dict) -> str:
    parts: list[str] = []
    for key in ("entity_id", "name", "sector", "industry", "series_id", "series_name", "asset_class", "tenor", "description"):
        val = entity.get(key)
        if val is not None:
            parts.append(str(val))
    target = getattr(task, "target", {}) or {}
    parts.append(str(target.get("name", "")))
    parts.append(str(getattr(task, "family", "")))
    parts.append(str(getattr(task, "prompt", ""))[:400])
    parts.append(rubric_keywords(str(getattr(task, "family", "")), str(target.get("name", ""))))
    return " ".join(parts)


def rubric_keywords(family: str, target_name: str) -> str:
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
    return "results outlook growth risk change forecast target evidence"
