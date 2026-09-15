"""Paper simulator using fill model M0.

M0 = mark-to-next-available fixture bar/mid with 0bps scar. This is a labeled
fixture mark, not invented Alex slippage. No live path.
"""

from __future__ import annotations

from alexrag.marketdata.fixture_bars import FixtureBar, next_available_bar
from alexrag.schemas.fill_intent import FillIntent
from alexrag.schemas.paper_fill import (
    M0_SCAR_LABEL,
    PaperFill,
    make_paper_fill,
)


def simulate_m0(intent: FillIntent, bars: list[FixtureBar]) -> PaperFill:
    clock = intent.decision_clock
    if clock is None:
        raise RuntimeError("M0 requires decision_clock on FillIntent")

    if intent.abstain:
        return make_paper_fill(
            intent=intent,
            status="skipped",
            venue="paper_sim",
            fill_ts=clock,
            qty_filled=0.0,
            qty_left=intent.qty or 0.0,
            skip_reason=intent.abstain_reason or "intent_abstain",
            scar_label=M0_SCAR_LABEL,
            notes=["M0 skipped; not filled"],
        )

    bar = next_available_bar(bars, intent.ticker, clock)
    if bar is None:
        return make_paper_fill(
            intent=intent,
            status="skipped",
            venue="paper_sim",
            fill_ts=clock,
            qty_filled=0.0,
            qty_left=intent.qty or 0.0,
            skip_reason="no_next_fixture_bar",
            scar_label=M0_SCAR_LABEL,
            notes=["M0 no next-available fixture bar/mid; skipped ≠ filled"],
        )

    qty = intent.qty or 0.0
    return make_paper_fill(
        intent=intent,
        status="acked",
        venue="paper_sim",
        fill_ts=bar.ts,
        fill_px=bar.mid,
        qty_filled=qty,
        qty_left=0.0,
        scar_label=M0_SCAR_LABEL,
        notes=[
            "M0 mark-to-next-available fixture mid",
            "scar_bps=0 labeled fixture_mid_not_alex_slippage",
        ],
    )


class PaperSimBroker:
    """Offline paper_sim venue. Marks M0 against fixture bars only."""

    name = "paper_sim"

    def submit_paper(self, intent: FillIntent, bars: list[FixtureBar] | None = None) -> PaperFill:
        if intent.mode != "paper":
            raise RuntimeError("PaperSimBroker rejects non-paper intents")
        return simulate_m0(intent, bars or [])
