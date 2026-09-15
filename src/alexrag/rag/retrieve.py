from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from alexrag.config import PRECEDENCE_DEFAULT
from alexrag.eval.cutoff import sealed_ok
from alexrag.rag.chunking import Chunk
from alexrag.rag.index import InMemoryIndex
from alexrag.schemas.sources import DEFAULT_DISCORD_TZ

_TOK = re.compile(r"[a-z0-9$]+")


def lexical_overlap(query: str, text: str) -> float:
    q = {t for t in _TOK.findall(query.lower()) if len(t) > 1}
    if not q:
        return 0.0
    t = set(_TOK.findall((text or "").lower()))
    return len(q & t) / len(q)

PRECEDENCE_RANK = {name: i for i, name in enumerate(PRECEDENCE_DEFAULT)}


class RetrievalHit(BaseModel):
    chunk: Chunk
    score: float
    rank: int


class RetrievalResult(BaseModel):
    query: str
    hits: list[RetrievalHit] = Field(default_factory=list)
    confidence: float = 0.0
    stale: bool = False
    newest_timestamp: datetime | None = None
    notes: list[str] = Field(default_factory=list)

    def as_citations(self) -> list[dict[str, Any]]:
        return [
            {
                "source_id": h.chunk.source_id,
                "source_type": h.chunk.source_type,
                "chunk_id": h.chunk.chunk_id,
                "excerpt": h.chunk.text[:400],
                "timestamp": h.chunk.timestamp,
                "path": h.chunk.path,
                "author": h.chunk.author,
            }
            for h in self.hits
        ]


def _newest(chunks: list[Chunk]) -> datetime | None:
    stamps = [c.timestamp for c in chunks if c.timestamp is not None]
    if not stamps:
        return None
    aware = []
    for ts in stamps:
        if ts.tzinfo is None:
            aware.append(ts.replace(tzinfo=ZoneInfo(DEFAULT_DISCORD_TZ)))
        else:
            aware.append(ts)
    return max(aware)


def retrieve_with_precedence(
    index: InMemoryIndex,
    query: str,
    *,
    top_k: int = 8,
    precedence: list[str] | tuple[str, ...] = PRECEDENCE_DEFAULT,
    per_source: int | None = None,
    before: datetime | None = None,
) -> RetrievalResult:
    """Fill slots by corpus precedence: fills > journal > gameplan > report > gitbook.

    If ``before`` is set (decision_ts), only chunks with timestamp < before are used
    (sealed chronological cutoff). Missing timestamps are excluded.
    """

    if not index.chunks:
        return RetrievalResult(query=query, confidence=0.0, notes=["empty_index"])

    q_vec = index.provider.embed([query])[0]
    from alexrag.rag.embeddings import cosine

    by_source: dict[str, list[tuple[Chunk, float]]] = {name: [] for name in precedence}
    other: list[tuple[Chunk, float]] = []
    skipped_unsealed = 0
    for chunk, vec in zip(index.chunks, index.vectors, strict=True):
        if before is not None and not sealed_ok(chunk.timestamp, before):
            skipped_unsealed += 1
            continue
        score = cosine(q_vec, vec) + 0.25 * lexical_overlap(query, chunk.text)
        if chunk.source_type in by_source:
            by_source[chunk.source_type].append((chunk, score))
        else:
            other.append((chunk, score))
    for name in by_source:
        by_source[name].sort(key=lambda item: item[1], reverse=True)

    budget = per_source or max(1, top_k // max(1, len(precedence)))
    selected: list[tuple[Chunk, float]] = []
    seen: set[str] = set()
    for name in precedence:
        for chunk, score in by_source.get(name, [])[:budget]:
            if chunk.chunk_id in seen:
                continue
            selected.append((chunk, score))
            seen.add(chunk.chunk_id)
            if len(selected) >= top_k:
                break
        if len(selected) >= top_k:
            break
    if len(selected) < top_k:
        rest = []
        for name in precedence:
            rest.extend(by_source.get(name, [])[budget:])
        rest.extend(other)
        rest.sort(key=lambda item: item[1], reverse=True)
        for chunk, score in rest:
            if chunk.chunk_id in seen:
                continue
            selected.append((chunk, score))
            seen.add(chunk.chunk_id)
            if len(selected) >= top_k:
                break

    hits = [
        RetrievalHit(chunk=chunk, score=score, rank=i)
        for i, (chunk, score) in enumerate(selected)
    ]
    confidence = max((h.score for h in hits), default=0.0)
    # Blend in coverage: at least one high-precedence source
    if hits and hits[0].chunk.source_type == "trade_log":
        confidence = min(1.0, confidence + 0.05)
    newest = _newest([h.chunk for h in hits])
    notes = []
    if before is not None:
        notes.append("sealed_cutoff")
        if skipped_unsealed:
            notes.append(f"skipped_unsealed={skipped_unsealed}")
    return RetrievalResult(
        query=query,
        hits=hits,
        confidence=max(0.0, min(1.0, confidence)),
        newest_timestamp=newest,
        notes=notes,
    )
