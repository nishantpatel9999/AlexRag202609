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
        abstain_reason="uninitialized",
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
        "conflict_labels",
        "citation_faithfulness",
        "hindsight",
        "replay_case_id",
    ):
        assert key in dumped
    p2 = p.model_copy(update={"conflict_labels": ["no_trade_plan_then_entry"]})
    assert p2.conflict_labels == ["no_trade_plan_then_entry"]


def test_fill_intent_paper_only() -> None:
    FillIntent(intent_id="i", proposal_id="p", mode="paper")
    with pytest.raises(ValidationError):
        FillIntent(intent_id="i", proposal_id="p", mode="live")  # type: ignore[arg-type]


def test_paper_fill_acked_roundtrip() -> None:
    from alexrag.schemas.paper_fill import PaperFill

    clock = datetime(2026, 9, 15, 18, 16, tzinfo=timezone.utc)
    fill = PaperFill(
        fill_ts=clock,
        fill_px=125.0,
        qty_filled=2.0,
        qty_left=0.0,
        status="acked",
        venue="paper_sim",
        latency_ms=60000.0,
        intent_id="i",
        proposal_id="p",
        filled=True,
        scar_bps=0.0,
    )
    assert fill.filled is True
    assert fill.status != "stubbed"


def test_settings_reject_live_mode() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"mode": "live"})


def test_settings_lock_inferhub_llm() -> None:
    s = Settings.model_validate({})
    assert s.llm.provider == "inferhub"
    assert s.llm.model == "cbcn/GLM-5.3-flash"
    assert s.llm.base_url == "https://api.inferhub.dev/v1"
    assert s.llm.inferhub_provider == "cbcn"
    with pytest.raises(ValidationError):
        Settings.model_validate({"llm": {"model": "other"}})
    with pytest.raises(ValidationError):
        Settings.model_validate({"llm": {"provider": "openai"}})
    with pytest.raises(ValidationError):
        Settings.model_validate({"llm": {"model": "other/GLM-5.3-flash"}})
