from __future__ import annotations

import uuid

from alexrag.agents.audit_log import AuditLog
from alexrag.broker.alpaca_paper import AlpacaPaperBroker
from alexrag.schemas.fill_intent import FillIntent
from alexrag.schemas.proposal import Proposal


class ExecAgent:
    """Paper execution stub. There is no live trading path in this module."""

    name = "exec"

    def __init__(self, broker: AlpacaPaperBroker | None = None) -> None:
        self.broker = broker or AlpacaPaperBroker()

    def run(self, proposal: Proposal, audit: AuditLog) -> FillIntent | None:
        if proposal.abstain:
            audit.emit(
                kind="exec_skipped_abstain",
                actor="exec",
                proposal_id=proposal.proposal_id,
                payload={"reason": proposal.abstain_reason},
            )
            return None
        if proposal.mode != "paper":
            raise RuntimeError("exec refused non-paper mode")
        intent = FillIntent(
            intent_id=str(uuid.uuid4()),
            proposal_id=proposal.proposal_id,
            mode="paper",
            ticker=proposal.tickers[0] if proposal.tickers else None,
            side=None,
            notional=0.0,
            size_ner_pct=proposal.size_ner_pct,
            abstain=False,
            notes=["paper stub; order not sent"],
        )
        result = self.broker.submit_paper(intent)
        intent.notes.append(result.get("note", "stub"))
        proposal.fill_intent_id = intent.intent_id
        audit.emit(
            kind="exec_paper_stub",
            actor="exec",
            proposal_id=proposal.proposal_id,
            payload={"intent_id": intent.intent_id, "broker": result},
        )
        return intent
