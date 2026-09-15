from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from alexrag.config import Settings
from alexrag.schemas.fill_intent import FillIntent
from alexrag.schemas.proposal import Citation, Proposal


def test_proposal_has_risk_mappable_fields() -> None:
    clock = datetime(2026, 9, 15, 18, 0, tzinfo=timezone.utc)
    p = Proposal(
        proposal_id="p1",
        decision_clock=clock,
        tickers=["NVDA"],
        regime="trend_day",
        size_ner_pct=0.25,
        confidence=0.7,
        abstain=True,
        abstain_reason="test",
        citations=[
            Citation(
                source_id="tl",
                source_type="trade_log",
                chunk_id="c1",
                excerpt="filled $NVDA",
                timestamp=clock,
            )
        ],
    )
    dumped = p.model_dump()
    for key in (
        "citations",
        "abstain",
        "abstain_reason",
        "confidence",
        "size_ner_pct",
        "regime",
        "tickers",
        "decision_clock",
    ):
        assert key in dumped


def test_fill_intent_paper_only() -> None:
    FillIntent(intent_id="i", proposal_id="p", mode="paper")
    with pytest.raises(ValidationError):
        FillIntent(intent_id="i", proposal_id="p", mode="live")  # type: ignore[arg-type]


def test_settings_reject_live_mode() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"mode": "live"})
