from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from alexrag.agents.orchestrator import run_paper_day
from alexrag.config import load_settings
from alexrag.eval.metrics import paper_window_met
from alexrag.pipeline import load_fixture_messages, messages_to_index, newest_timestamp
from alexrag.schemas.proposal import Proposal


def _index(fixtures_dir: Path, settings):
    messages = load_fixture_messages(fixtures_dir)
    return messages_to_index(messages, settings), messages


def test_run_paper_day_emits_audited_proposal(fixtures_dir: Path, tmp_path: Path) -> None:
    settings = load_settings(overrides={"kill_switch": False})
    index, messages = _index(fixtures_dir, settings)
    clock = newest_timestamp(messages)
    audit = tmp_path / "audit" / "events.jsonl"
    result = run_paper_day(settings, index, decision_clock=clock, audit_path=audit, dry_run=True)
    proposal = result.proposal
    assert isinstance(proposal, Proposal)
    assert proposal.mode == "paper"
    assert proposal.decision_clock is not None
    assert isinstance(proposal.abstain, bool)
    assert proposal.citations or proposal.abstain
    dumped = proposal.model_dump()
    assert "size_ner_pct" in dumped
    assert "regime" in dumped
    assert "tickers" in dumped
    assert "confidence" in dumped
    assert audit.is_file()
    lines = audit.read_text(encoding="utf-8").strip().splitlines()
    assert lines
    assert any("paper_day_start" in line for line in lines)
    assert any("paper_day_complete" in line for line in lines)
    complete = [line for line in lines if "paper_day_complete" in line][-1]
    assert "citation_faithfulness" in complete
    assert "hindsight" in complete
    assert "replay_case_id" in complete
    assert "counters_are_diagnostics" in complete


def test_kill_switch_abstains(fixtures_dir: Path, tmp_path: Path) -> None:
    settings = load_settings(overrides={"kill_switch": True})
    index, messages = _index(fixtures_dir, settings)
    result = run_paper_day(
        settings,
        index,
        decision_clock=newest_timestamp(messages),
        audit_path=tmp_path / "a.jsonl",
    )
    assert result.proposal.abstain is True
    assert result.proposal.abstain_reason == "kill_switch_fail"
    assert result.fill is None


def test_stale_feed_abstains(fixtures_dir: Path, tmp_path: Path) -> None:
    settings = load_settings(overrides={"retrieval": {"stale_after_hours": 1}})
    index, messages = _index(fixtures_dir, settings)
    future = newest_timestamp(messages) + timedelta(days=7)
    result = run_paper_day(
        settings,
        index,
        decision_clock=future,
        audit_path=tmp_path / "a.jsonl",
    )
    assert result.proposal.abstain is True
    assert result.proposal.abstain_reason == "stale_feed"


def test_low_confidence_abstains(fixtures_dir: Path, tmp_path: Path) -> None:
    settings = load_settings(overrides={"retrieval": {"min_confidence": 1.01}})
    index, messages = _index(fixtures_dir, settings)
    result = run_paper_day(
        settings,
        index,
        decision_clock=newest_timestamp(messages),
        audit_path=tmp_path / "a.jsonl",
    )
    assert result.proposal.abstain is True
    assert result.proposal.abstain_reason == "low_retrieval_confidence"


def test_missing_audit_abstains(fixtures_dir: Path, tmp_path: Path) -> None:
    blocker = tmp_path / "notdir"
    blocker.write_text("x", encoding="utf-8")
    settings = load_settings()
    index, messages = _index(fixtures_dir, settings)
    result = run_paper_day(
        settings,
        index,
        decision_clock=newest_timestamp(messages),
        audit_path=blocker / "events.jsonl",
    )
    assert result.proposal.abstain is True
    assert result.proposal.abstain_reason == "missing_audit"


def test_hard_limits_present_and_block_when_nav_zero(
    fixtures_dir: Path, tmp_path: Path
) -> None:
    settings = load_settings()
    assert settings.hard_limits.max_notional_pct == 1.5
    assert settings.hard_limits.max_positions == 15
    assert settings.hard_limits.max_daily_loss_pct == 0.10
    assert settings.hard_limits.max_portfolio_dd == 0.25
    assert settings.hard_limits.notional_breach_policy == "pro_rata_trim_for_new_entry"
    assert settings.paper.nav == 0.0
    assert settings.max_notional_dollars() == 0.0
    assert settings.max_daily_loss_dollars() == 0.0
    index, messages = _index(fixtures_dir, settings)
    result = run_paper_day(
        settings,
        index,
        decision_clock=newest_timestamp(messages),
        audit_path=tmp_path / "a.jsonl",
    )
    snap = result.proposal.hard_limits_snapshot
    assert snap["max_notional_pct"] == 1.5
    assert snap["max_positions"] == 15
    assert snap["max_daily_loss_pct"] == 0.10
    assert snap["max_portfolio_dd"] == 0.25
    assert snap["max_notional"] == 0.0
    assert snap["max_daily_loss"] == 0.0
    assert snap["paper_equity"] == 0.0
    assert snap["notional_breach_policy"] == "pro_rata_trim_for_new_entry"
    # Operator pcts are locked; nav 0 still fail-closes dollar derivation.
    assert result.proposal.abstain is True


def test_configured_limits_can_clear_risk(fixtures_dir: Path, tmp_path: Path) -> None:
    settings = load_settings(
        overrides={
            "paper": {"nav": 100000.0},
        }
    )
    index, messages = _index(fixtures_dir, settings)
    result = run_paper_day(
        settings,
        index,
        decision_clock=newest_timestamp(messages),
        audit_path=tmp_path / "a.jsonl",
    )
    assert result.proposal.tickers == ["NVDA"]
    assert result.proposal.regime in {"trend", "trend_day"}
    if not result.proposal.abstain:
        assert result.fill is not None
        assert result.fill.mode == "paper"


def test_fixture_config_exercises_m0_exec(fixtures_dir: Path, tmp_path: Path) -> None:
    from datetime import timezone

    from alexrag.config import ROOT

    settings = load_settings(config_path=ROOT / "config" / "fixture.yaml")
    index, _messages = _index(fixtures_dir, settings)
    clock = datetime(2026, 9, 15, 18, 15, tzinfo=timezone.utc)
    result = run_paper_day(
        settings,
        index,
        decision_clock=clock,
        audit_path=tmp_path / "m0.jsonl",
    )
    assert settings.max_notional_dollars() == 150000.0
    assert result.proposal.abstain is False
    assert result.fill is not None
    assert result.fill.abstain is False
    assert result.fill.ticker == "NVDA"
    assert result.fill.side == "buy"
    assert result.fill.notional == 250.0
    assert result.fill.qty == 2.0
    assert result.receipt is not None
    assert result.receipt.status == "acked"
    assert result.receipt.filled is True
    assert result.receipt.venue == "paper_sim"
    assert result.receipt.scar_bps == 0
    assert result.receipt.fill_px == 125.0
    assert result.receipt.qty_filled == 2.0


def test_paper_window_is_or_not_calendar() -> None:
    assert paper_window_met(60, 0) is True
    assert paper_window_met(0, 100) is True
    assert paper_window_met(59, 99) is False
