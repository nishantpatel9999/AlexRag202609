"""Alpaca paper broker stub. Live trading is not implemented and must not be added here."""

from __future__ import annotations

from alexrag.schemas.fill_intent import FillIntent


class AlpacaPaperBroker:
    """TODO: real Alpaca paper API (keys via env, never git). Paper endpoint only."""

    name = "alpaca_paper_stub"

    def submit_paper(self, intent: FillIntent) -> dict:
        if intent.mode != "paper":
            raise RuntimeError("AlpacaPaperBroker rejects non-paper intents")
        return {
            "status": "stubbed",
            "submitted": False,
            "broker": self.name,
            "note": "TODO: real Alpaca paper submit; no network in MVP",
            "intent_id": intent.intent_id,
        }
