"""Extractors that only copy evidence already present in retrieved text.

Do not invent trading indicator numbers.
"""

from __future__ import annotations

import re

from alexrag.rag.retrieve import RetrievalResult

TICKER_RE = re.compile(r"\$([A-Z]{1,5})\b")
NER_RE = re.compile(r"(?i)(?:ner\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%|(\d+(?:\.\d+)?)\s*%\s*ner)")
SIDE_RE = re.compile(r"(?i)\b(long|buy|short|sell)\b")
LIMIT_RE = re.compile(r"(?i)\blimit\b\s*(?:px|price|@|:|=)?\s*(\d+(?:\.\d+)?)")
INVALIDATION_NUM_RE = re.compile(
    r"(?i)\binvalidation\b\s*(?:at|below|above|:|=)\s*(\d+(?:\.\d+)?)"
)
INVALIDATION_TEXT_RE = re.compile(r"(?i)\binvalidation\s*:\s*([^\n.]{1,80})")

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


def extract_side(text: str) -> str | None:
    match = SIDE_RE.search(text or "")
    if not match:
        return None
    word = match.group(1).lower()
    if word in {"long", "buy"}:
        return "buy"
    return "sell"


def extract_limit_px(text: str) -> float | None:
    match = LIMIT_RE.search(text or "")
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def extract_invalidation(text: str) -> str | None:
    text = text or ""
    numbered = INVALIDATION_NUM_RE.search(text)
    if numbered:
        return numbered.group(1)
    prose = INVALIDATION_TEXT_RE.search(text)
    if not prose:
        return None
    snippet = prose.group(1).strip()
    return snippet or None


def combined_text(result: RetrievalResult) -> str:
    return "\n".join(h.chunk.text for h in result.hits)
