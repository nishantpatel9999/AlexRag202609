from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from alexrag.schemas.sources import CONFLICT_LABELS, SourceType


class Citation(BaseModel):
    """Retrieved evidence Risk can map. Timestamps are required for go-decisions."""

    source_id: str
    source_type: SourceType
    chunk_id: str
    excerpt: str
    timestamp: datetime | None = None
    path: str | None = None
    author: str | None = None


class Proposal(BaseModel):
    """Setup/Risk decision object. Exec may run only when abstain is false and mode is paper."""

    proposal_id: str
    decision_clock: datetime
    mode: Literal["paper"] = "paper"
    tickers: list[str] = Field(default_factory=list)
    regime: str = "unknown"
    size_ner_pct: float = 0.0
    confidence: float = 0.0
    abstain: bool = True
    abstain_reason: str | None = "uninitialized"
    citations: list[Citation] = Field(default_factory=list)
    thesis: str = ""
    setup_summary: str = ""
    risk_notes: list[str] = Field(default_factory=list)
    hard_limits_snapshot: dict[str, Any] = Field(default_factory=dict)
    retrieval_confidence: float = 0.0
    fill_intent_id: str | None = None
    # First-class corpus conflict labels (see docs/CORPUS.md). Empty in MVP agents.
    conflict_labels: list[str] = Field(
        default_factory=list,
        description="Subset of " + ",".join(CONFLICT_LABELS),
    )
