from __future__ import annotations

from datetime import timedelta

from alexrag.agents.audit_log import AuditLog
from alexrag.agents.extract import extract_side
from alexrag.config import Settings
from alexrag.eval.cutoff import aware, sealed_ok
from alexrag.schemas.proposal import Proposal
from alexrag.schemas.reasons import AbstainReason


def _sealed_text(proposal: Proposal) -> str:
    return "\n".join(
        c.excerpt for c in proposal.citations if sealed_ok(c.timestamp, proposal.decision_clock)
    )


def _newest_citation_ts(proposal: Proposal):
    stamps = [aware(c.timestamp) for c in proposal.citations if c.timestamp is not None]
    return max(stamps) if stamps else None


class RiskAgent:
    """Fail-closed risk mapper. Enforces hard limits vs paper book; does not invent numbers."""

    name = "risk"

    def run(self, proposal: Proposal, settings: Settings, audit: AuditLog) -> Proposal:
        notes: list[str] = []
        proposal.hard_limits_snapshot = settings.hard_limits_snapshot()
        proposal.mode = "paper"

        def abstain(reason: AbstainReason, extra: str | None = None) -> Proposal:
            proposal.abstain = True
            proposal.abstain_reason = reason
            if extra:
                notes.append(extra)
            proposal.risk_notes = notes
            proposal.size_ner_pct = 0.0
            audit.emit(
                kind="risk_abstain",
                actor="risk",
                proposal_id=proposal.proposal_id,
                payload={"reason": str(reason), "notes": notes},
            )
            return proposal

        if settings.kill_switch:
            notes.append("kill_switch engaged")
            return abstain(AbstainReason.KILL_SWITCH_FAIL)

        if not settings.fail_closed:
            notes.append("fail_closed=false is ignored in MVP; fail-closed is mandatory")

        if not proposal.citations:
            return abstain(AbstainReason.NO_CITATIONS)

        missing_ts = [c.chunk_id for c in proposal.citations if c.timestamp is None]
        if missing_ts:
            notes.append(f"citations_missing_timestamps:{len(missing_ts)}")
            return abstain(AbstainReason.CITATIONS_MISSING_TIMESTAMPS)

        newest = _newest_citation_ts(proposal)
        if newest is None:
            return abstain(AbstainReason.STALE_FEED, "newest citation timestamp missing")
        age = aware(proposal.decision_clock) - newest
        stale_after = timedelta(hours=settings.retrieval.stale_after_hours)
        if age > stale_after:
            notes.append(f"feed_age_hours={age.total_seconds()/3600:.2f}")
            return abstain(AbstainReason.STALE_FEED)

        if proposal.confidence < settings.retrieval.min_confidence:
            notes.append(
                f"confidence {proposal.confidence:.3f} < min {settings.retrieval.min_confidence}"
            )
            return abstain(AbstainReason.LOW_RETRIEVAL_CONFIDENCE)

        if not proposal.tickers:
            return abstain(AbstainReason.NO_TICKERS_IN_CITATIONS)

        if proposal.regime == "unknown":
            notes.append("regime unknown from citations")
            return abstain(AbstainReason.UNKNOWN_REGIME)

        limits = settings.hard_limits
        if (
            limits.max_notional <= 0
            or limits.max_positions <= 0
            or limits.max_daily_loss <= 0
            or limits.max_portfolio_dd <= 0
        ):
            notes.append("hard limits unconfigured (notional/positions/daily_loss/dd <= 0)")
            return abstain(AbstainReason.HARD_LIMITS_UNCONFIGURED)

        book = settings.paper_book
        if book.daily_loss >= limits.max_daily_loss:
            notes.append(
                f"paper daily_loss={book.daily_loss} >= max_daily_loss={limits.max_daily_loss}"
            )
            return abstain(AbstainReason.DAILY_LOSS_BREACH)
        if book.portfolio_dd >= limits.max_portfolio_dd:
            notes.append(
                f"paper portfolio_dd={book.portfolio_dd} >= max_portfolio_dd={limits.max_portfolio_dd}"
            )
            return abstain(AbstainReason.PORTFOLIO_DD_BREACH)

        if proposal.size_ner_pct < 0:
            return abstain(AbstainReason.INVALID_SIZE)

        if extract_side(_sealed_text(proposal)) is None:
            notes.append("sealed citations do not evidence side; order would be unexplained")
            return abstain(AbstainReason.UNEXPLAINED_ORDER)

        if proposal.size_ner_pct > 0:
            notes.append("positive size mapped under configured hard limits")

        proposal.abstain = False
        proposal.abstain_reason = None
        proposal.risk_notes = notes or ["risk_cleared"]
        audit.emit(
            kind="risk_cleared",
            actor="risk",
            proposal_id=proposal.proposal_id,
            payload={"size_ner_pct": proposal.size_ner_pct, "tickers": proposal.tickers},
        )
        return proposal
