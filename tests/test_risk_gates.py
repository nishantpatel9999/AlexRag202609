from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from alexrag.agents.audit_log import AuditLog
from alexrag.agents.risk import RiskAgent
from alexrag.config import Settings, load_settings
from alexrag.eval.gates import evaluate_promotion_readiness
from alexrag.eval.metrics import PaperMetrics, paper_run_diagnostics, paper_window_met
from alexrag.schemas.proposal import Citation, Proposal
from alexrag.schemas.reasons import REQUIRED_ABSTAIN_REASONS, AbstainReason


def _clock() -> datetime:
    return datetime(2026, 9, 15, 18, 15, tzinfo=timezone.utc)


def _go_proposal(**kwargs) -> Proposal:
    clock = _clock()
    data = dict(
        proposal_id="p-risk",
        decision_clock=clock,
        tickers=["NVDA"],
        regime="trend_day",
        size_ner_pct=0.25,
        confidence=0.7,
        abstain=False,
        abstain_reason=None,
        citations=[
            Citation(
                source_id="tl",
                source_type="trade_log",
                chunk_id="c1",
                excerpt="Trade log: filled $NVDA long. Size NER 0.25%.",
                timestamp=datetime(2026, 9, 15, 18, 10, tzinfo=timezone.utc),
            )
        ],
    )
    data.update(kwargs)
    return Proposal.model_validate(data)


def _cleared_settings(**book) -> Settings:
    return load_settings(
        overrides={
            "paper": {"nav": 100000.0},
            "paper_book": {
                "daily_loss": 0.0,
                "portfolio_dd": 0.0,
                **book,
            },
        }
    )


def test_required_abstain_reasons_are_explicit() -> None:
    names = {r.value for r in AbstainReason}
    for required in REQUIRED_ABSTAIN_REASONS:
        assert required.value in names
    for must in (
        "stale_feed",
        "missing_audit",
        "daily_loss_breach",
        "portfolio_dd_breach",
        "kill_switch_fail",
        "unexplained_order",
    ):
        assert must in names


def test_risk_enforces_daily_loss_and_portfolio_dd(tmp_path: Path) -> None:
    audit = AuditLog(tmp_path / "a.jsonl")
    loss = RiskAgent().run(
        _go_proposal(),
        _cleared_settings(daily_loss=10000.0),
        audit,
    )
    assert loss.abstain is True
    assert loss.abstain_reason == AbstainReason.DAILY_LOSS_BREACH

    dd = RiskAgent().run(
        _go_proposal(proposal_id="p-dd"),
        _cleared_settings(portfolio_dd=0.25),
        AuditLog(tmp_path / "b.jsonl"),
    )
    assert dd.abstain is True
    assert dd.abstain_reason == AbstainReason.PORTFOLIO_DD_BREACH


def test_risk_stale_feed_vs_decision_clock(tmp_path: Path) -> None:
    proposal = _go_proposal(
        decision_clock=datetime(2026, 9, 17, 18, 15, tzinfo=timezone.utc),
    )
    settings = _cleared_settings()
    assert settings.retrieval.stale_after_hours == 36
    out = RiskAgent().run(proposal, settings, AuditLog(tmp_path / "s.jsonl"))
    assert out.abstain is True
    assert out.abstain_reason == AbstainReason.STALE_FEED


def test_risk_kill_switch_fail(tmp_path: Path) -> None:
    settings = _cleared_settings()
    settings.kill_switch = True
    out = RiskAgent().run(_go_proposal(), settings, AuditLog(tmp_path / "k.jsonl"))
    assert out.abstain_reason == AbstainReason.KILL_SWITCH_FAIL


def test_risk_unexplained_order_without_side(tmp_path: Path) -> None:
    proposal = _go_proposal(
        citations=[
            Citation(
                source_id="tl",
                source_type="trade_log",
                chunk_id="c1",
                excerpt="Tape notes $NVDA. Size NER 0.25%. No side.",
                timestamp=datetime(2026, 9, 15, 18, 10, tzinfo=timezone.utc),
            )
        ]
    )
    out = RiskAgent().run(proposal, _cleared_settings(), AuditLog(tmp_path / "u.jsonl"))
    assert out.abstain is True
    assert out.abstain_reason == AbstainReason.UNEXPLAINED_ORDER


def test_risk_nav_zero_is_unconfigured(tmp_path: Path) -> None:
    settings = load_settings()
    assert settings.paper.nav == 0.0
    out = RiskAgent().run(_go_proposal(), settings, AuditLog(tmp_path / "z.jsonl"))
    assert out.abstain is True
    assert out.abstain_reason == AbstainReason.HARD_LIMITS_UNCONFIGURED


def test_risk_daily_loss_below_ten_percent_clears(tmp_path: Path) -> None:
    out = RiskAgent().run(
        _go_proposal(),
        _cleared_settings(daily_loss=9999.0, portfolio_dd=0.249),
        AuditLog(tmp_path / "under.jsonl"),
    )
    assert out.abstain is False
    out = RiskAgent().run(
        _go_proposal(),
        _cleared_settings(daily_loss=1.0, portfolio_dd=0.001),
        AuditLog(tmp_path / "ok.jsonl"),
    )
    assert out.abstain is False
    assert out.abstain_reason is None


def test_paper_counters_are_diagnostics_not_hard_floor() -> None:
    assert paper_window_met(60, 0) is True
    assert paper_window_met(0, 100) is True
    assert paper_window_met(59, 99) is False
    diag = paper_run_diagnostics(3, 12, min_sessions=60, min_decisions=100)
    assert diag["counters_are_diagnostics"] is True
    assert diag["paper_window_hard_floor"] is False
    assert diag["calendar_promotes"] is False
    assert diag["meets_legacy_session_or_decision_threshold"] is False

    ready = evaluate_promotion_readiness(
        PaperMetrics(
            sessions=3,
            decisions=12,
            abstain_count=4,
            cited_decisions=12,
            timestamped_citation_decisions=12,
        ),
        load_settings(),
    )
    assert ready["live_allowed"] is False
    assert ready["paper_window_hard_floor"] is False
    assert ready["calendar_promotes"] is False
    assert ready["fidelity_gates_required"] is True
    assert "2 weeks" in ready["nishant_override"]
    assert ready["metrics"]["sessions_decisions_role"] == "diagnostic"
