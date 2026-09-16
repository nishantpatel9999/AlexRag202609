from __future__ import annotations

from alexrag.rag.chunking import Chunk
from alexrag.rag.embeddings import EmbeddingProvider, cosine, get_provider


class InMemoryIndex:
    """In-memory vector index for tests and dry-run. Not a production store."""

    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        self.provider = provider or get_provider("fake")
        self.chunks: list[Chunk] = []
        self.vectors: list[list[float]] = []

    def add(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        vecs = self.provider.embed([c.text for c in chunks])
        self.chunks.extend(chunks)
        self.vectors.extend(vecs)

    def similarity_search(self, query: str, k: int = 8) -> list[tuple[Chunk, float]]:
        if not self.chunks:
            return []
        q = self.provider.embed([query])[0]
        scored = [(chunk, cosine(q, vec)) for chunk, vec in zip(self.chunks, self.vectors, strict=True)]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:k]
