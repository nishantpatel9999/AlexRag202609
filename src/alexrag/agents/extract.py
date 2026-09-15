"""Extractors that only copy evidence already present in retrieved text.

Do not invent trading indicator numbers.
"""

from __future__ import annotations

import re

from alexrag.rag.retrieve import RetrievalResult

TICKER_RE = re.compile(r"\$([A-Z]{1,5})\b")
NER_RE = re.compile(r"(?i)(?:ner\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%|(\d+(?:\.\d+)?)\s*%\s*ner)")

# Qualitative labels only — used if the word already appears in citations.
REGIME_LABELS = (
    "trend day",
    "trend",
    "range",
    "chop",
    "squeeze",
    "inside day",
    "unknown",
)


def extract_tickers(text: str) -> list[str]:
    found: list[str] = []
    for match in TICKER_RE.finditer(text or ""):
        sym = match.group(1)
        if sym not in found:
            found.append(sym)
    return found


def extract_size_ner_pct(text: str) -> float | None:
    match = NER_RE.search(text or "")
    if not match:
        return None
    raw = match.group(1) or match.group(2)
    try:
        return float(raw)
    except ValueError:
        return None


def extract_regime(text: str) -> str:
    lowered = (text or "").lower()
    for label in REGIME_LABELS:
        if label != "unknown" and label in lowered:
            return label.replace(" ", "_")
    return "unknown"


def combined_text(result: RetrievalResult) -> str:
    return "\n".join(h.chunk.text for h in result.hits)
