"""Build an in-memory RAG index from ingested JSONL / fixture folders. Offline only."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from alexrag.config import Settings
from alexrag.ingest.discord_html import ingest_discord_html, iter_discord_html
from alexrag.ingest.gitbook import iter_gitbook_snapshot
from alexrag.rag.chunking import chunk_text
from alexrag.rag.embeddings import get_provider
from alexrag.rag.index import InMemoryIndex
from alexrag.schemas.message import IngestedMessage
from alexrag.vision_caption.stub import caption_paths

SOURCE_FILES = {
    "trade_log": "trade_log.jsonl",
    "journal": "journal.jsonl",
    "report": "report.jsonl",
    "gitbook": "gitbook.jsonl",
}


def load_jsonl_messages(path: Path, default_source: str | None = None) -> list[IngestedMessage]:
    messages: list[IngestedMessage] = []
    if not path.exists():
        return messages
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if default_source and "source_type" not in data:
                data["source_type"] = default_source
            messages.append(IngestedMessage.model_validate(data))
    return messages


def messages_to_index(messages: list[IngestedMessage], settings: Settings) -> InMemoryIndex:
    provider = get_provider(settings.embedding.provider, dim=settings.embedding.dim)
    index = InMemoryIndex(provider=provider)
    for msg in messages:
        captions = msg.captions or caption_paths(msg.attachment_paths)
        extra = ""
        if captions:
            extra = "\n" + "\n".join(captions)
        chunks = chunk_text(
            (msg.text or "") + extra,
            source_id=msg.id,
            source_type=msg.source_type,
            timestamp=msg.ts,
            author=msg.author,
            path=msg.path,
            extra_tags=[msg.source_type],
        )
        index.add(chunks)
    return index


def newest_timestamp(messages: list[IngestedMessage]) -> datetime | None:
    stamps = []
    for msg in messages:
        if msg.ts is None:
            continue
        ts = msg.ts if msg.ts.tzinfo else msg.ts.replace(tzinfo=timezone.utc)
        stamps.append(ts)
    return max(stamps) if stamps else None


def load_fixture_messages(fixtures: Path) -> list[IngestedMessage]:
    """Load tests/fixtures layout: discord HTML, gitbook dir, optional corpus JSONL."""

    fixtures = Path(fixtures)
    messages: list[IngestedMessage] = []

    discord_html = fixtures / "discord" / "sample.html"
    if discord_html.exists():
        messages.extend(iter_discord_html(discord_html, source_type="journal"))

    trade_html = fixtures / "discord" / "trade_log.html"
    if trade_html.exists():
        messages.extend(iter_discord_html(trade_html, source_type="trade_log"))

    gitbook_dir = fixtures / "gitbook"
    if gitbook_dir.exists():
        messages.extend(iter_gitbook_snapshot(gitbook_dir, source_type="gitbook"))

    corpus = fixtures / "corpus"
    if corpus.exists():
        for source_type, name in SOURCE_FILES.items():
            messages.extend(load_jsonl_messages(corpus / name, default_source=source_type))

    for html in fixtures.glob("*.html"):
        messages.extend(iter_discord_html(html, source_type="journal"))

    return messages


def ingest_discord_cli(html: Path, out: Path, source_type: str = "journal") -> int:
    return ingest_discord_html(html, out, source_type=source_type)
