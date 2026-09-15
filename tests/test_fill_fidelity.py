from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from alexrag.agents.fill_map import proposal_to_intent
from alexrag.config import ROOT, load_settings
from alexrag.eval.fill_m0 import load_m0_cases, score_m0_pack
from alexrag.schemas.fill_intent import FillIntent
from alexrag.schemas.paper_fill import FillReceipt, PaperFill
from alexrag.schemas.proposal import Citation, Proposal


def test_default_yaml_fail_closed_zero_limits() -> None:
    settings = load_settings()
    assert settings.hard_limits.max_notional == 0.0
    assert settings.hard_limits.max_positions == 0
    assert settings.paper.nav == 0.0


def test_fixture_yaml_nonzero_operator_limits() -> None:
    settings = load_settings(config_path=ROOT / "config" / "fixture.yaml")
    assert settings.hard_limits.max_notional == 1000.0
    assert settings.hard_limits.max_positions == 1
    assert settings.hard_limits.max_daily_loss == 50.0
    assert settings.hard_limits.max_portfolio_dd == 0.02
    assert settings.paper.nav == 100000.0
    assert settings.paper.fill_model == "M0"
    assert settings.paper.venue == "paper_sim"
    assert settings.paper.bars_path == "tests/fixtures/m0/bars.json"


def test_go_intent_rejects_holes() -> None:
    clock = datetime(2026, 9, 15, 18, 15, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        FillIntent(
            intent_id="i",
            proposal_id="p",
            mode="paper",
            abstain=False,
            ticker=None,
            side=None,
            notional=0.0,
            qty=None,
            decision_clock=clock,
        )


def test_paper_fill_stubbed_is_not_filled() -> None:
    clock = datetime(2026, 9, 15, 18, 15, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        PaperFill(
            fill_ts=clock,
            fill_px=125.0,
            qty_filled=2.0,
            qty_left=0.0,
            status="stubbed",
            venue="alpaca_paper",
            latency_ms=0.0,
            intent_id="i",
            proposal_id="p",
            filled=True,
            scar_bps=0.0,
        )
    receipt = FillReceipt(
        fill_ts=clock,
        fill_px=None,
        qty_filled=0.0,
        qty_left=2.0,
        status="stubbed",
        venue="alpaca_paper",
        latency_ms=0.0,
        intent_id="i",
        proposal_id="p",
        filled=False,
        scar_bps=0.0,
        scar_label="stubbed_not_filled",
    )
    assert receipt.filled is False
    assert receipt.status == "stubbed"


def test_paper_fill_rejects_nonzero_scar() -> None:
    clock = datetime(2026, 9, 15, 18, 15, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        PaperFill(
            fill_ts=clock,
            fill_px=125.0,
            qty_filled=2.0,
            qty_left=0.0,
            status="acked",
            venue="paper_sim",
            latency_ms=0.0,
            intent_id="i",
            proposal_id="p",
            filled=True,
            scar_bps=1.5,
        )


def test_unsealed_limit_is_not_copied() -> None:
    clock = datetime(2026, 9, 15, 18, 15, tzinfo=timezone.utc)
    proposal = Proposal(
        proposal_id="p",
        decision_clock=clock,
        tickers=["NVDA"],
        regime="trend_day",
        size_ner_pct=0.25,
        confidence=0.7,
        abstain=False,
        abstain_reason=None,
        citations=[
            Citation(
                source_id="late",
                source_type="trade_log",
                chunk_id="late",
                excerpt="filled $NVDA long limit 50. Invalidation: 40.",
                timestamp=datetime(2026, 9, 15, 19, 0, tzinfo=timezone.utc),
            ),
            Citation(
                source_id="ok",
                source_type="trade_log",
                chunk_id="ok",
                excerpt="filled $NVDA long. Size NER 0.25%.",
                timestamp=datetime(2026, 9, 15, 18, 10, tzinfo=timezone.utc),
            ),
        ],
    )
    intent = proposal_to_intent(
        proposal,
        paper_nav=100000.0,
        max_notional=1000.0,
        fallback_ref_px=125.0,
        intent_id="i",
    )
    assert intent.abstain is False
    assert intent.limit_px is None
    assert intent.invalidation is None
    assert intent.order_type == "market"
    assert intent.side == "buy"
    assert intent.notional == 250.0
    assert intent.qty == 2.0


def test_m0_sealed_replay_pack(tmp_path: Path) -> None:
    cases = load_m0_cases()
    ids = {c.case_id for c in cases}
    assert ids >= {
        "m0_acked_long",
        "m0_abstain_skipped",
        "m0_stubbed_alpaca",
        "m0_no_bar_skipped",
        "m0_limit_citation",
    }
    assert 3 <= len(cases) <= 5
    statuses = {c.expected_fill.status for c in cases}
    assert "skipped" in statuses
    assert "stubbed" in statuses
    assert "acked" in statuses
    stubbed = next(c for c in cases if c.expected_fill.status == "stubbed")
    acked = next(c for c in cases if c.expected_fill.status == "acked")
    assert stubbed.expected_fill.filled is False
    assert acked.expected_fill.filled is True
    assert stubbed.expected_fill.qty_filled == 0
    summary = score_m0_pack(cases, tmp_path / "m0-audit")
    assert summary["pnl_scored"] is False
    assert summary["n_cases"] == len(cases)
    failed = [c for c in summary["cases"] if not c["passed"]]
    assert failed == [], failed
    assert summary["n_passed"] == len(cases)
