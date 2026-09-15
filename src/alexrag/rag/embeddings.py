"""Embedding provider interface. MVP ships a deterministic in-memory fake."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9$%._-]+", re.I)


class EmbeddingProvider(Protocol):
    name: str

    def dim(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbeddingProvider:
    """Hash bag-of-tokens embeddings for offline tests. No network.

    TODO: replace with a local embedding model on Mac Studio.
    """

    name = "fake"

    def __init__(self, dim: int = 32) -> None:
        self._dim = dim

    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for tok in _TOKEN.findall(text.lower()):
            digest = hashlib.sha256(tok.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:2], "big") % self._dim
            sign = 1.0 if digest[2] % 2 == 0 else -1.0
            vec[idx] += sign
        return _l2(vec)


def _l2(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


def get_provider(name: str = "fake", dim: int = 32) -> EmbeddingProvider:
    if name != "fake":
        raise ValueError(
            f"embedding provider {name!r} is not available offline; use fake "
            "(TODO: local embeddings on Mac Studio)"
        )
    return FakeEmbeddingProvider(dim=dim)
