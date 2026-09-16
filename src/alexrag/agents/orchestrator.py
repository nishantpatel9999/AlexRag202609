from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from alexrag.agents.audit_hooks import apply_promotion_hooks
from alexrag.agents.audit_log import AuditLog
from alexrag.agents.auditor import AuditorAgent
from alexrag.agents.exec_agent import ExecAgent
from alexrag.agents.regime import RegimeAgent
from alexrag.agents.risk import RiskAgent
from alexrag.agents.setup import SetupAgent
from alexrag.config import ROOT, Settings
from alexrag.eval.cutoff import aware
from alexrag.eval.metrics import paper_run_diagnostics
from alexrag.marketdata.fixture_bars import load_fixture_bars
from alexrag.rag.index import InMemoryIndex
from alexrag.rag.retrieve import retrieve_with_precedence
from alexrag.schemas.fill_intent import FillIntent
from alexrag.schemas.paper_fill import PaperFill
from alexrag.schemas.proposal import Proposal
from alexrag.schemas.reasons import AbstainReason
from alexrag.schemas.sources import DEFAULT_DISCORD_TZ


class PaperDayResult:
    def __init__(
        self,
        proposal: Proposal,
        fill: FillIntent | None,
        audit: AuditLog,
        receipt: PaperFill | None = None,
        diagnostics: dict | None = None,
    ) -> None:
        self.proposal = proposal
        self.fill = fill
        self.audit = audit
        self.receipt = receipt
        self.diagnostics = diagnostics or {}

    def proposal_json(self) -> str:
        return self.proposal.model_dump_json(indent=2)


def _aware(dt: datetime) -> datetime:
    return aware(dt)


def run_paper_day(
    settings: Settings,
    index: InMemoryIndex,
    *,
    query: str = "trend day trade log fill ticker playbook regime setup",
    decision_clock: datetime | None = None,
    audit_path: Path | None = None,
    dry_run: bool = True,
    replay_case_id: str | None = None,
) -> PaperDayResult:
    """Regime→Setup→Risk→Exec (paper_sim fill model / alpaca stub)→Auditor. No network. No live path."""

    clock = aware(decision_clock or datetime.now(ZoneInfo(DEFAULT_DISCORD_TZ)))
    proposal_id = str(uuid.uuid4())
    path = Path(audit_path) if audit_path is not None else Path(settings.paths.audit_log)
    audit = AuditLog(path)
    proposal = Proposal(
        proposal_id=proposal_id,
        decision_clock=clock,
        mode="paper",
        abstain=True,
        abstain_reason=AbstainReason.PIPELINE_START,
        hard_limits_snapshot=settings.hard_limits_snapshot(),
        replay_case_id=replay_case_id,
    )
    diagnostics = paper_run_diagnostics(
        settings.paper_book.sessions,
        settings.paper_book.decisions + 1,
        min_sessions=settings.paper_gates.min_sessions,
        min_decisions=settings.paper_gates.min_decisions,
    )

    def finish(reason: AbstainReason | None = None) -> PaperDayResult:
        if reason:
            proposal.abstain = True
            proposal.abstain_reason = reason
            proposal.size_ner_pct = 0.0
        hooks = apply_promotion_hooks(proposal)
        audit.emit(
            kind="paper_day_complete",
            actor="orchestrator",
            proposal_id=proposal.proposal_id,
            payload={
                "abstain": proposal.abstain,
                "reason": None if proposal.abstain_reason is None else str(proposal.abstain_reason),
                "dry_run": dry_run,
                "citation_faithfulness": hooks["citation_faithfulness"],
                "hindsight": hooks["hindsight"],
                "replay_case_id": hooks["replay_case_id"],
                **diagnostics,
            },
        )
        return PaperDayResult(proposal, None, audit, None, diagnostics)

    audit.emit(
        kind="paper_day_start",
        actor="orchestrator",
        proposal_id=proposal_id,
        payload={"query": query, "dry_run": dry_run, "kill_switch": settings.kill_switch},
        ts=clock,
    )

    if settings.mode != "paper":
        return finish(AbstainReason.NON_PAPER_MODE)

    if not audit.available:
        proposal.risk_notes.append(audit.error or "missing_audit")
        return finish(AbstainReason.MISSING_AUDIT)

    if settings.kill_switch:
        return finish(AbstainReason.KILL_SWITCH_FAIL)

    retrieved = retrieve_with_precedence(
        index,
        query,
        top_k=settings.retrieval.top_k,
        precedence=settings.retrieval.precedence,
        before=clock,
    )
    audit.emit(
        kind="retrieved",
        actor="rag",
        proposal_id=proposal_id,
        payload={
            "confidence": retrieved.confidence,
            "hit_count": len(retrieved.hits),
            "sources": [h.chunk.source_type for h in retrieved.hits],
            "newest_timestamp": retrieved.newest_timestamp.isoformat()
            if retrieved.newest_timestamp
            else None,
        },
    )

    if not retrieved.hits:
        return finish(AbstainReason.EMPTY_RETRIEVAL)

    newest = retrieved.newest_timestamp
    if newest is None:
        return finish(AbstainReason.STALE_FEED)
    age = clock - _aware(newest)
    if age > timedelta(hours=settings.retrieval.stale_after_hours):
        proposal.risk_notes.append(f"feed_age_hours={age.total_seconds()/3600:.2f}")
        return finish(AbstainReason.STALE_FEED)

    if retrieved.confidence < settings.retrieval.min_confidence:
        proposal.retrieval_confidence = retrieved.confidence
        proposal.confidence = retrieved.confidence
        return finish(AbstainReason.LOW_RETRIEVAL_CONFIDENCE)

    proposal.regime = RegimeAgent().run(retrieved, audit, proposal_id)
    proposal = SetupAgent().run(retrieved, proposal=proposal, audit=audit)
    proposal = RiskAgent().run(proposal, settings, audit)
    bars = []
    if settings.paper.bars_path:
        bars_path = Path(settings.paper.bars_path)
        if not bars_path.is_absolute():
            bars_path = ROOT / bars_path
        bars = load_fixture_bars(bars_path)
    fill, receipt = ExecAgent().run(proposal, audit, settings=settings, bars=bars)
    proposal = AuditorAgent().run(proposal, audit, fill, receipt)
    hooks = apply_promotion_hooks(
        proposal,
        fill_ts=None if receipt is None or not receipt.filled else receipt.fill_ts,
    )
    audit.emit(
        kind="paper_day_complete",
        actor="orchestrator",
        proposal_id=proposal.proposal_id,
        payload={
            "abstain": proposal.abstain,
            "reason": None if proposal.abstain_reason is None else str(proposal.abstain_reason),
            "dry_run": dry_run,
            "receipt_status": None if receipt is None else receipt.status,
            "receipt_filled": None if receipt is None else receipt.filled,
            "citation_faithfulness": hooks["citation_faithfulness"],
            "hindsight": hooks["hindsight"],
            "replay_case_id": hooks["replay_case_id"],
            **diagnostics,
        },
    )
    return PaperDayResult(proposal, fill, audit, receipt, diagnostics)
