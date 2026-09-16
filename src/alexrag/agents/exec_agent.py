from __future__ import annotations

import uuid
from typing import Literal

from alexrag.agents.audit_log import AuditLog
from alexrag.agents.fill_map import proposal_to_intent
from alexrag.broker.alpaca_paper import AlpacaPaperBroker
from alexrag.broker.fill_models import resolve_fill_model
from alexrag.config import Settings
from alexrag.marketdata.fixture_bars import FixtureBar, next_available_mid
from alexrag.schemas.fill_intent import FillIntent
from alexrag.schemas.paper_fill import DEFAULT_FILL_MODEL, PaperFill, canonicalize_fill_model
from alexrag.schemas.proposal import Proposal

FillVenue = Literal["paper_sim", "alpaca_paper"]


class ExecAgent:
    """Paper execution. Maps a cleared Proposal to FillIntent, then paper_sim or alpaca stub.

    Fill model is selected from settings (``m1_realistic_v0`` default; M0 kept for
    regression). There is no live trading path. Stubbed alpaca receipts are not fills.
    Selecting m1 does not unlock paper.
    """

    name = "exec"

    def __init__(self, broker: AlpacaPaperBroker | None = None) -> None:
        self.broker = broker or AlpacaPaperBroker()

    def run(
        self,
        proposal: Proposal,
        audit: AuditLog,
        *,
        settings: Settings | None = None,
        bars: list[FixtureBar] | None = None,
        venue: FillVenue | None = None,
        intent_id: str | None = None,
    ) -> tuple[FillIntent, PaperFill]:
        if proposal.mode != "paper":
            raise RuntimeError("exec refused non-paper mode")

        paper_nav = settings.paper.nav if settings is not None else 0.0
        max_notional = settings.max_notional_dollars() if settings is not None else 0.0
        chosen: FillVenue = venue or (
            settings.paper.venue if settings is not None else "paper_sim"
        )
        bars = list(bars or [])
        ticker = proposal.tickers[0] if proposal.tickers else None
        fallback_mid = (
            next_available_mid(bars, ticker, proposal.decision_clock)
            if ticker and not proposal.abstain
            else None
        )
        intent = proposal_to_intent(
            proposal,
            paper_nav=paper_nav,
            max_notional=max_notional,
            fallback_ref_px=fallback_mid,
            intent_id=intent_id or str(uuid.uuid4()),
        )
        audit.emit(
            kind="exec_intent_mapped",
            actor="exec",
            proposal_id=proposal.proposal_id,
            payload={
                "intent_id": intent.intent_id,
                "abstain": intent.abstain,
                "reason": intent.abstain_reason,
                "ticker": intent.ticker,
                "side": intent.side,
                "notional": intent.notional,
                "qty": intent.qty,
                "venue": chosen,
            },
        )

        if proposal.abstain:
            audit.emit(
                kind="exec_skipped_abstain",
                actor="exec",
                proposal_id=proposal.proposal_id,
                payload={"reason": proposal.abstain_reason, "intent_id": intent.intent_id},
            )

        fill_model = canonicalize_fill_model(
            settings.paper.fill_model if settings is not None else DEFAULT_FILL_MODEL
        )
        if chosen == "alpaca_paper":
            receipt = self.broker.submit_paper(intent, fill_model=fill_model)
        else:
            receipt = resolve_fill_model(fill_model).simulate(intent, bars)

        proposal.fill_intent_id = intent.intent_id
        audit.emit(
            kind="exec_paper_fill",
            actor="exec",
            proposal_id=proposal.proposal_id,
            payload={
                "intent_id": intent.intent_id,
                "status": receipt.status,
                "filled": receipt.filled,
                "venue": receipt.venue,
                "fill_model": receipt.fill_model,
                "scar_bps": receipt.scar_bps,
                "qty_filled": receipt.qty_filled,
            },
        )
        return intent, receipt
