from __future__ import annotations

from alexrag.agents.audit_log import AuditLog
from alexrag.schemas.fill_intent import FillIntent
from alexrag.schemas.paper_fill import PaperFill
from alexrag.schemas.proposal import Proposal


class AuditorAgent:
    """Checks that a decision is fully audit-logged and citations are timestamped."""

    name = "auditor"

    def run(
        self,
        proposal: Proposal,
        audit: AuditLog,
        fill: FillIntent | None,
        receipt: PaperFill | None = None,
    ) -> Proposal:
        problems: list[str] = []
        if not audit.available:
            problems.append(audit.error or "missing_audit")
        required = {"regime_classified", "setup_built", "exec_paper_fill"}
        kinds = {e.kind for e in audit.events if e.proposal_id == proposal.proposal_id}
        missing = sorted(required - kinds)
        if missing:
            problems.append(f"missing_audit_events:{','.join(missing)}")
        if not proposal.citations:
            problems.append("no_citations")
        if fill and fill.mode != "paper":
            problems.append("non_paper_fill")
        if fill and not fill.abstain:
            if not fill.ticker or fill.side is None or fill.qty is None or fill.notional <= 0:
                problems.append("go_intent_incomplete")
            if fill.decision_clock is None:
                problems.append("go_intent_missing_clock")
        if receipt:
            if receipt.status == "stubbed" and receipt.filled:
                problems.append("stubbed_marked_filled")
            if receipt.intent_id and fill and receipt.intent_id != fill.intent_id:
                problems.append("receipt_intent_mismatch")
            if receipt.proposal_id != proposal.proposal_id:
                problems.append("receipt_proposal_mismatch")
            if fill and not fill.abstain and receipt.status == "acked":
                if fill.qty is not None and receipt.qty_filled != fill.qty:
                    problems.append("acked_qty_mismatch")

        if problems:
            proposal.abstain = True
            proposal.abstain_reason = problems[0]
            proposal.risk_notes = list(proposal.risk_notes) + problems
            proposal.size_ner_pct = 0.0
            proposal.fill_intent_id = None

        audit.emit(
            kind="auditor_complete",
            actor="auditor",
            proposal_id=proposal.proposal_id,
            payload={
                "abstain": proposal.abstain,
                "reason": proposal.abstain_reason,
                "problems": problems,
                "fill_intent_id": proposal.fill_intent_id,
                "receipt_status": None if receipt is None else receipt.status,
                "receipt_filled": None if receipt is None else receipt.filled,
            },
        )
        return proposal
