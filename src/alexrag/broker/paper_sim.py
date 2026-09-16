"""Paper simulator. Selects M0 (legacy 0bps mid) or m1_realistic_v0.

M0 = mark-to-next-available fixture bar/mid with 0bps scar. Labeled fixture
mark, not invented Alex slippage.

m1_realistic_v0 = next-bar open or mid ± half-spread + impact stub with a
non-zero documented scar. Not Alex-calibrated. Does not unlock paper.

No live path.
"""

from __future__ import annotations

from alexrag.broker.fill_models import (
    DEFAULT_FILL_MODEL,
    resolve_fill_model,
    simulate_fill,
)
from alexrag.marketdata.fixture_bars import FixtureBar
from alexrag.schemas.fill_intent import FillIntent
from alexrag.schemas.paper_fill import PaperFill, canonicalize_fill_model


def simulate_m0(intent: FillIntent, bars: list[FixtureBar]) -> PaperFill:
    """Legacy M0 path. Kept for sealed regression fixtures."""

    return resolve_fill_model("m0_fixture_mid_0bps").simulate(intent, bars)


class PaperSimBroker:
    """Offline paper_sim venue. Marks against fixture bars only."""

    name = "paper_sim"

    def __init__(self, fill_model: str | None = None) -> None:
        self.fill_model = canonicalize_fill_model(fill_model or DEFAULT_FILL_MODEL)

    def submit_paper(
        self,
        intent: FillIntent,
        bars: list[FixtureBar] | None = None,
        fill_model: str | None = None,
    ) -> PaperFill:
        if intent.mode != "paper":
            raise RuntimeError("PaperSimBroker rejects non-paper intents")
        model = canonicalize_fill_model(fill_model or self.fill_model)
        return simulate_fill(intent, bars or [], model)
