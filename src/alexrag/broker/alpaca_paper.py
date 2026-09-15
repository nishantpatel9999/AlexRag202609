"""Alpaca paper broker stub. Live trading is not implemented and must not be added here."""

from __future__ import annotations

from datetime import datetime, timezone

from alexrag.schemas.fill_intent import FillIntent
from alexrag.schemas.paper_fill import STUBBED_SCAR_LABEL, PaperFill, make_paper_fill


class AlpacaPaperBroker:
    """TODO: real Alpaca paper API (keys via env, never git). Paper endpoint only.

    Without keys / network, submits are ``stubbed``. Stubbed is not filled.
    """

    name = "alpaca_paper_stub"

    def submit_paper(self, intent: FillIntent) -> PaperFill:
        if intent.mode != "paper":
            raise RuntimeError("AlpacaPaperBroker rejects non-paper intents")
        clock = intent.decision_clock or datetime.now(timezone.utc)
        if intent.abstain:
            return make_paper_fill(
                intent=intent,
                status="skipped",
                venue="alpaca_paper",
                fill_ts=clock,
                qty_filled=0.0,
                skip_reason=intent.abstain_reason or "intent_abstain",
                scar_label=STUBBED_SCAR_LABEL,
                notes=["alpaca_paper skipped abstain intent; not submitted"],
            )
        return make_paper_fill(
            intent=intent,
            status="stubbed",
            venue="alpaca_paper",
            fill_ts=clock,
            fill_px=None,
            qty_filled=0.0,
            qty_left=intent.qty or 0.0,
            skip_reason="alpaca_paper_no_keys",
            scar_label=STUBBED_SCAR_LABEL,
            notes=[
                "TODO: real Alpaca paper submit; no network in MVP",
                "stubbed ≠ filled",
            ],
        )
