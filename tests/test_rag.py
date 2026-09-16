from __future__ import annotations

from datetime import datetime, timezone

from alexrag.rag.chunking import chunk_text
from alexrag.rag.embeddings import FakeEmbeddingProvider
from alexrag.rag.index import InMemoryIndex
from alexrag.rag.retrieve import retrieve_with_precedence


def test_chunking_and_tags() -> None:
    chunks = chunk_text(
        "alpha\n\nbeta " * 50,
        source_id="doc1",
        source_type="journal",
        timestamp=datetime(2026, 9, 15, tzinfo=timezone.utc),
        extra_tags=["session"],
        max_chars=40,
    )
    assert chunks
    assert all("journal" in c.tags for c in chunks)
    assert all(c.source_type == "journal" for c in chunks)


def test_fake_embeddings_are_deterministic() -> None:
    p = FakeEmbeddingProvider(dim=16)
    a = p.embed(["trend day $NVDA"])
    b = p.embed(["trend day $NVDA"])
    assert a == b
    assert len(a[0]) == 16


def test_precedence_prefers_trade_log() -> None:
    index = InMemoryIndex(FakeEmbeddingProvider(dim=32))
    ts = datetime(2026, 9, 15, 18, 0, tzinfo=timezone.utc)
    index.add(
        chunk_text(
            "Playbook: wait for reclaim on trend day.",
            source_id="gb",
            source_type="gitbook",
            timestamp=ts,
        )
    )
    index.add(
        chunk_text(
            "Journal: trend day notes.",
            source_id="j",
            source_type="journal",
            timestamp=ts,
        )
    )
    index.add(
        chunk_text(
            "Morning gameplan: wait, no trade unless reclaim.",
            source_id="gp",
            source_type="gameplan",
            timestamp=ts,
        )
    )
    index.add(
        chunk_text(
            "Trade log: filled $NVDA long on trend day.",
            source_id="tl",
            source_type="trade_log",
            timestamp=ts,
        )
    )
    index.add(
        chunk_text(
            "pf-update: account NAV snapshot, not a fill.",
            source_id="pf",
            source_type="pf_update",
            timestamp=ts,
        )
    )
    result = retrieve_with_precedence(index, "NVDA trend day fill", top_k=8)
    assert result.hits
    assert result.hits[0].chunk.source_type == "trade_log"
    types = [h.chunk.source_type for h in result.hits]
    assert types.index("trade_log") < types.index("journal")
    assert types.index("journal") < types.index("gameplan")
    assert types.index("gameplan") < types.index("gitbook")
    assert types.index("trade_log") < types.index("pf_update")
    assert types.index("pf_update") < types.index("gitbook")


def test_sealed_cutoff_excludes_at_or_after_decision() -> None:
    index = InMemoryIndex(FakeEmbeddingProvider(dim=32))
    before = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    index.add(
        chunk_text(
            "Trade log: filled $NVDA long on trend day.",
            source_id="tl-early",
            source_type="trade_log",
            timestamp=datetime(2026, 9, 15, 11, 0, tzinfo=timezone.utc),
        )
    )
    index.add(
        chunk_text(
            "Trade log: later fill $NVDA.",
            source_id="tl-late",
            source_type="trade_log",
            timestamp=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
        )
    )
    result = retrieve_with_precedence(index, "NVDA fill", top_k=8, before=before)
    ids = [h.chunk.source_id for h in result.hits]
    assert "tl-early" in ids
    assert "tl-late" not in ids
    assert "sealed_cutoff" in result.notes
