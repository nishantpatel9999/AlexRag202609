from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class FillIntent(BaseModel):
    """Paper-only order intent. Live routing is not implemented.

    When ``abstain`` is false, Exec must populate ticker, side, order_type,
    notional>0, qty>0, and a copy of ``proposal.decision_clock``. Limit and
    invalidation are copied only when present in sealed citations.
    """

    intent_id: str
    proposal_id: str
    mode: Literal["paper"] = "paper"
    ticker: str | None = None
    side: Literal["buy", "sell"] | None = None
    order_type: Literal["market", "limit"] | None = None
    limit_px: float | None = None
    invalidation: str | None = None
    notional: float = 0.0
    qty: float | None = None
    size_ner_pct: float = 0.0
    decision_clock: datetime | None = None
    ref_px: float | None = None
    ref_px_source: str | None = None
    abstain: bool = True
    abstain_reason: str | None = None
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _go_intent_complete(self) -> FillIntent:
        if self.abstain:
            return self
        problems: list[str] = []
        if not self.ticker:
            problems.append("ticker")
        if self.side is None:
            problems.append("side")
        if self.order_type is None:
            problems.append("order_type")
        if self.notional <= 0:
            problems.append("notional")
        if self.qty is None or self.qty <= 0:
            problems.append("qty")
        if self.decision_clock is None:
            problems.append("decision_clock")
        if problems:
            raise ValueError(
                "abstain=false requires " + ", ".join(problems) + "; Exec must not leave holes"
            )
        if self.limit_px is None and self.order_type == "limit":
            raise ValueError("limit order_type requires limit_px from sealed citations")
        if self.limit_px is not None and self.order_type != "limit":
            raise ValueError("limit_px present requires order_type=limit")
        return self
