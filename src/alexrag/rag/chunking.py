from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SOURCE_TYPES = ("trade_log", "journal", "report", "gitbook")
SourceType = Literal["trade_log", "journal", "report", "gitbook"]


class Chunk(BaseModel):
    chunk_id: str
    text: str
    source_type: SourceType
    source_id: str
    timestamp: datetime | None = None
    author: str | None = None
    path: str | None = None
    tags: list[str] = Field(default_factory=list)


_SPLIT = re.compile(r"\n{2,}")


def chunk_text(
    text: str,
    *,
    source_id: str,
    source_type: SourceType,
    timestamp: datetime | None = None,
    author: str | None = None,
    path: str | None = None,
    extra_tags: list[str] | None = None,
    max_chars: int = 800,
    overlap: int = 80,
) -> list[Chunk]:
    """Paragraph-aware char chunks with metadata tags. No model calls."""

    text = (text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in _SPLIT.split(text) if p.strip()]
    if not parts:
        parts = [text]
    windows: list[str] = []
    for part in parts:
        if len(part) <= max_chars:
            windows.append(part)
            continue
        start = 0
        while start < len(part):
            end = min(len(part), start + max_chars)
            windows.append(part[start:end])
            if end == len(part):
                break
            start = max(0, end - overlap)
    chunks: list[Chunk] = []
    tags = list(extra_tags or [])
    if source_type not in tags:
        tags.append(source_type)
    for i, window in enumerate(windows):
        digest = hashlib.sha256(f"{source_id}:{i}:{window[:64]}".encode()).hexdigest()[:12]
        chunks.append(
            Chunk(
                chunk_id=f"{source_id}:{i}:{digest}",
                text=window,
                source_type=source_type,
                source_id=source_id,
                timestamp=timestamp,
                author=author,
                path=path,
                tags=tags,
            )
        )
    return chunks
