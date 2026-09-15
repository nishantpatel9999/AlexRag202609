from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FillIntent(BaseModel):
    """Paper-only order intent. Live routing is not implemented."""

    intent_id: str
    proposal_id: str
    mode: Literal["paper"] = "paper"
    ticker: str | None = None
    side: Literal["buy", "sell"] | None = None
    notional: float = 0.0
    qty: float | None = None
    size_ner_pct: float = 0.0
    abstain: bool = True
    abstain_reason: str | None = None
    notes: list[str] = Field(default_factory=list)
