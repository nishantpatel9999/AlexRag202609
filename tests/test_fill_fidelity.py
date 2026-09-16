from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from alexrag.agents.fill_map import proposal_to_intent
from alexrag.broker.fill_models import (
    M1_DEFAULT_SCAR_BPS,
    RealisticFillModel,
    resolve_fill_model,
    simulate_fill,
)
from alexrag.broker.paper_sim import simulate_m0
from alexrag.config import ROOT, load_settings
from alexrag.eval.fill_m0 import load_m0_cases, score_m0_pack
from alexrag.eval.fill_m1 import load_m1_cases, score_m1_pack
from alexrag.marketdata.fixture_bars import FixtureBar
from alexrag.schemas.fill_intent import FillIntent
from alexrag.schemas.paper_fill import (
    FILL_MODEL_M0,
    FILL_MODEL_M1,
    M0_SCAR_LABEL,
    M1_SCAR_LABEL,
    FillReceipt,
    PaperFill,
)
from alexrag.schemas.proposal import Citation, Proposal


def _go_intent() -> FillIntent:
    clock = datetime(2026, 9, 15, 18, 15, tzinfo=timezone.utc)
    return FillIntent(
        intent_id="i",
        proposal_id="p",
        mode="paper",
        ticker="NVDA",
        side="buy",
        order_type="market",
        notional=250.0,
        qty=2.0,
        size_ner_pct=0.25,
        decision_clock=clock,
        abstain=False,
    )


def test_default_yaml_fail_closed_zero_nav() -> None:
    settings = load_settings(load_env_file=False)
    assert settings.hard_limits.max_notional_pct == 1.5
    assert settings.hard_limits.max_positions == 15
    assert settings.hard_limits.max_daily_loss_pct == 0.10
    assert settings.hard_limits.max_portfolio_dd == 0.25
    assert settings.paper.nav == 0.0
    assert settings.max_notional_dollars() == 0.0
    assert settings.hard_limits_ready() is False
    assert settings.paper.fill_model == FILL_MODEL_M1


def test_fixture_yaml_operator_limits_derive_dollars() -> None:
    settings = load_settings(
        config_path=ROOT / "config" / "fixture.yaml", load_env_file=False
    )
    assert settings.hard_limits.max_notional_pct == 1.5
    assert settings.hard_limits.max_positions == 15
    assert settings.hard_limits.max_daily_loss_pct == 0.10
    assert settings.hard_limits.max_portfolio_dd == 0.25
    assert settings.hard_limits.notional_breach_policy == "pro_rata_trim_for_new_entry"
    assert settings.paper.nav == 100000.0
    assert settings.max_notional_dollars() == 150000.0
    assert settings.max_daily_loss_dollars() == 10000.0
    assert settings.hard_limits_ready() is True
    assert settings.paper.fill_model == FILL_MODEL_M1
    assert settings.paper.venue == "paper_sim"
    assert settings.paper.bars_path == "tests/fixtures/m0/bars.json"


def test_fill_model_env_selects_m0(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALEXRAG_FILL_MODEL", "m0_fixture_mid_0bps")
    settings = load_settings(load_env_file=False)
    assert settings.paper.fill_model == FILL_MODEL_M0
    monkeypatch.setenv("ALEXRAG_FILL_MODEL", "M0")
    settings = load_settings(load_env_file=False)
    assert settings.paper.fill_model == FILL_MODEL_M0
    monkeypatch.setenv("ALEXRAG_FILL_MODEL", "m1_realistic_v0")
    settings = load_settings(load_env_file=False)
    assert settings.paper.fill_model == FILL_MODEL_M1


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


def test_paper_fill_m1_requires_nonzero_proxy_scar() -> None:
    clock = datetime(2026, 9, 15, 18, 16, tzinfo=timezone.utc)
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
            fill_model=FILL_MODEL_M1,
            scar_bps=0.0,
            scar_label=M1_SCAR_LABEL,
        )
    with pytest.raises(ValidationError):
        PaperFill(
            fill_ts=clock,
            fill_px=125.075,
            qty_filled=2.0,
            qty_left=0.0,
            status="acked",
            venue="paper_sim",
            latency_ms=0.0,
            intent_id="i",
            proposal_id="p",
            filled=True,
            fill_model=FILL_MODEL_M1,
            scar_bps=6.0,
            scar_label=M0_SCAR_LABEL,
        )
    receipt = PaperFill(
        fill_ts=clock,
        fill_px=125.075,
        qty_filled=2.0,
        qty_left=0.0,
        status="acked",
        venue="paper_sim",
        latency_ms=0.0,
        intent_id="i",
        proposal_id="p",
        filled=True,
        fill_model=FILL_MODEL_M1,
        scar_bps=M1_DEFAULT_SCAR_BPS,
        scar_label=M1_SCAR_LABEL,
    )
    assert receipt.scar_bps != 0
    assert receipt.scar_label == M1_SCAR_LABEL
    assert receipt.fill_model == FILL_MODEL_M1


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


def test_simulate_m0_and_m1_both() -> None:
    intent = _go_intent()
    bars = [
        FixtureBar(ts=datetime(2026, 9, 15, 18, 16, tzinfo=timezone.utc), ticker="NVDA", mid=125.0)
    ]
    m0 = simulate_m0(intent, bars)
    assert m0.fill_model == FILL_MODEL_M0
    assert m0.fill_px == 125.0
    assert m0.scar_bps == 0
    assert m0.scar_label == M0_SCAR_LABEL
    m1 = simulate_fill(intent, bars, FILL_MODEL_M1)
    assert m1.fill_model == FILL_MODEL_M1
    assert m1.scar_bps == M1_DEFAULT_SCAR_BPS
    assert m1.scar_label == M1_SCAR_LABEL
    assert m1.fill_px == pytest.approx(125.075)
    assert m1.fill_px != m0.fill_px
    sell = intent.model_copy(update={"side": "sell"})
    m1_sell = simulate_fill(sell, bars, FILL_MODEL_M1)
    assert m1_sell.fill_px == pytest.approx(124.925)
    opened = [
        FixtureBar(
            ts=datetime(2026, 9, 15, 18, 16, tzinfo=timezone.utc),
            ticker="NVDA",
            mid=125.0,
            open=126.0,
        )
    ]
    m1_open = RealisticFillModel().simulate(intent, opened)
    assert m1_open.fill_px == pytest.approx(126.0756)
    assert resolve_fill_model("M0").id == FILL_MODEL_M0
    assert resolve_fill_model(None).id == FILL_MODEL_M1


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
    assert acked.expected_fill.fill_model == FILL_MODEL_M0
    assert acked.expected_fill.scar_bps == 0
    assert acked.expected_fill.scar_label == M0_SCAR_LABEL
    summary = score_m0_pack(cases, tmp_path / "m0-audit")
    assert summary["pnl_scored"] is False
    assert summary["n_cases"] == len(cases)
    failed = [c for c in summary["cases"] if not c["passed"]]
    assert failed == [], failed
    assert summary["n_passed"] == len(cases)


def test_m1_sealed_replay_pack(tmp_path: Path) -> None:
    cases = load_m1_cases()
    ids = {c.case_id for c in cases}
    assert ids >= {
        "m1_acked_long",
        "m1_acked_next_open",
        "m1_abstain_skipped",
        "m1_stubbed_alpaca",
        "m1_no_bar_skipped",
    }
    assert len(cases) == 5
    statuses = {c.expected_fill.status for c in cases}
    assert "skipped" in statuses
    assert "stubbed" in statuses
    assert "acked" in statuses
    stubbed = next(c for c in cases if c.expected_fill.status == "stubbed")
    acked = next(c for c in cases if c.expected_fill.status == "acked")
    assert stubbed.expected_fill.filled is False
    assert stubbed.expected_fill.qty_filled == 0
    assert stubbed.expected_fill.scar_label == "stubbed_not_filled"
    assert acked.expected_fill.filled is True
    assert acked.expected_fill.fill_model == FILL_MODEL_M1
    assert acked.expected_fill.scar_bps != 0
    assert acked.expected_fill.scar_label == M1_SCAR_LABEL
    assert acked.expected_fill.scar_label != M0_SCAR_LABEL
    summary = score_m1_pack(cases, tmp_path / "m1-audit")
    assert summary["pnl_scored"] is False
    assert summary["paper_authority"] is False
    assert summary["capital"] == 0
    assert summary["unlocks_paper"] is False
    assert summary["fill_model"] == FILL_MODEL_M1
    assert summary["n_cases"] == len(cases)
    failed = [c for c in summary["cases"] if not c["passed"]]
    assert failed == [], failed
    assert summary["n_passed"] == len(cases)
