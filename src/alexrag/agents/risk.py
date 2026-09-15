from __future__ import annotations

from alexrag.agents.audit_log import AuditLog
from alexrag.config import Settings
from alexrag.schemas.proposal import Proposal


class RiskAgent:
    """Fail-closed risk mapper. Does not invent limits or indicator numbers."""

    name = "risk"

    def run(self, proposal: Proposal, settings: Settings, audit: AuditLog) -> Proposal:
        notes: list[str] = []
        proposal.hard_limits_snapshot = settings.hard_limits_snapshot()
        proposal.mode = "paper"

        def abstain(reason: str, extra: str | None = None) -> Proposal:
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
                payload={"reason": reason, "notes": notes},
            )
            return proposal

        if settings.kill_switch:
            notes.append("kill_switch engaged")
            return abstain("kill_switch")

        if not settings.fail_closed:
            notes.append("fail_closed=false is ignored in MVP; fail-closed is mandatory")

        if not proposal.citations:
            return abstain("no_citations")

        missing_ts = [c.chunk_id for c in proposal.citations if c.timestamp is None]
        if missing_ts:
            notes.append(f"citations_missing_timestamps:{len(missing_ts)}")
            return abstain("citations_missing_timestamps")

        if proposal.confidence < settings.retrieval.min_confidence:
            notes.append(
                f"confidence {proposal.confidence:.3f} < min {settings.retrieval.min_confidence}"
            )
            return abstain("low_retrieval_confidence")

        if not proposal.tickers:
            return abstain("no_tickers_in_citations")

        if proposal.regime == "unknown":
            notes.append("regime unknown from citations")
            return abstain("unknown_regime")

        limits = settings.hard_limits
        if limits.max_notional <= 0 or limits.max_positions <= 0:
            notes.append("hard limits unconfigured (max_notional/max_positions <= 0)")
            return abstain("hard_limits_unconfigured")

        if proposal.size_ner_pct < 0:
            return abstain("invalid_size")

        if proposal.size_ner_pct > 0:
            # Size is copied from citations; still blocked until operator limits allow paper size.
            notes.append("positive size requires configured hard limits; exec remains paper stub")

        proposal.abstain = False
        proposal.abstain_reason = None
        proposal.risk_notes = notes or ["risk_cleared_paper_stub"]
        audit.emit(
            kind="risk_cleared",
            actor="risk",
            proposal_id=proposal.proposal_id,
            payload={"size_ner_pct": proposal.size_ner_pct, "tickers": proposal.tickers},
        )
        return proposal
