"""Alpaca paper broker stub. Live trading is not implemented and must not be added here."""

from __future__ import annotations

from datetime import datetime, timezone

from alexrag import envutil
from alexrag.schemas.fill_intent import FillIntent
from alexrag.schemas.paper_fill import (
    DEFAULT_FILL_MODEL,
    STUBBED_SCAR_LABEL,
    PaperFill,
    canonicalize_fill_model,
    make_paper_fill,
)

ALPACA_KEY_ID_ENV = "ALPACA_API_KEY_ID"
ALPACA_SECRET_KEY_ENV = "ALPACA_API_SECRET_KEY"


def alpaca_paper_credentials_present() -> bool:
    """True when both paper key env vars are set. Does not return or store secrets."""

    return (
        envutil.get_str(ALPACA_KEY_ID_ENV) is not None
        and envutil.get_str(ALPACA_SECRET_KEY_ENV) is not None
    )


class AlpacaPaperBroker:
    """TODO: real Alpaca paper API (keys via env, never git). Paper endpoint only.

    Without network, submits are ``stubbed``. Stubbed is not filled. Live trading
    is not implemented.
    """

    name = "alpaca_paper_stub"

    def submit_paper(
        self,
        intent: FillIntent,
        fill_model: str | None = None,
    ) -> PaperFill:
        if intent.mode != "paper":
            raise RuntimeError("AlpacaPaperBroker rejects non-paper intents")
        model = canonicalize_fill_model(fill_model or DEFAULT_FILL_MODEL)
        clock = intent.decision_clock or datetime.now(timezone.utc)
        if intent.abstain:
            return make_paper_fill(
                intent=intent,
                status="skipped",
                venue="alpaca_paper",
                fill_ts=clock,
                qty_filled=0.0,
                skip_reason=intent.abstain_reason or "intent_abstain",
                fill_model=model,
                scar_bps=0.0,
                scar_label=STUBBED_SCAR_LABEL,
                notes=["alpaca_paper skipped abstain intent; not submitted"],
            )
        keys_present = alpaca_paper_credentials_present()
        skip_reason = (
            "alpaca_paper_stub_no_network" if keys_present else "alpaca_paper_no_keys"
        )
        return make_paper_fill(
            intent=intent,
            status="stubbed",
            venue="alpaca_paper",
            fill_ts=clock,
            fill_px=None,
            qty_filled=0.0,
            qty_left=intent.qty or 0.0,
            skip_reason=skip_reason,
            fill_model=model,
            scar_bps=0.0,
            scar_label=STUBBED_SCAR_LABEL,
            notes=[
                "TODO: real Alpaca paper submit; no network in MVP",
                "stubbed ≠ filled",
                "paper only; ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY env, never git",
            ],
        )
