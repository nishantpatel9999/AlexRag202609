"""Labeled paper fill models. Offline / sealed fixtures only. No live path.

Modes:
- ``m0_fixture_mid_0bps`` (alias ``M0``): next fixture mid, 0bps scar labeled
  ``fixture_mid_0bps_not_alex_slippage``. Legacy regression.
- ``m1_realistic_v0``: next-bar open or mid ± half-spread proxy + impact stub.
  Non-zero scar labeled ``proxy_half_spread_not_alex_slippage``. Not
  Alex-calibrated slippage. Does not unlock paper.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from alexrag.marketdata.fixture_bars import FixtureBar, next_available_bar
from alexrag.schemas.fill_intent import FillIntent
from alexrag.schemas.paper_fill import (
    DEFAULT_FILL_MODEL,
    FILL_MODEL_M0,
    FILL_MODEL_M1,
    M0_SCAR_LABEL,
    M1_SCAR_LABEL,
    PaperFill,
    canonicalize_fill_model,
    make_paper_fill,
)

# Documented M1 proxy — not a measured quote and not Alex slippage.
M1_HALF_SPREAD_BPS = 5.0
M1_IMPACT_STUB_BPS = 1.0
M1_DEFAULT_SCAR_BPS = M1_HALF_SPREAD_BPS + M1_IMPACT_STUB_BPS  # 6.0


def apply_adverse_scar(mark_px: float, side: str, scar_bps: float) -> float:
    """Buy pays up; sell receives down. ``scar_bps`` is a documented proxy."""

    sign = 1.0 if side == "buy" else -1.0
    return mark_px * (1.0 + sign * scar_bps / 10_000.0)


class FillModel(ABC):
    """Paper FillIntent → PaperFill. Never submits live."""

    id: str

    @abstractmethod
    def simulate(self, intent: FillIntent, bars: list[FixtureBar]) -> PaperFill:
        raise NotImplementedError


class M0FixtureMidFillModel(FillModel):
    """Legacy mark-to-next-available fixture mid with a labeled 0bps scar."""

    id = FILL_MODEL_M0

    def simulate(self, intent: FillIntent, bars: list[FixtureBar]) -> PaperFill:
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
                fill_model=self.id,
                scar_bps=0.0,
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
                fill_model=self.id,
                scar_bps=0.0,
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
            fill_model=self.id,
            scar_bps=0.0,
            scar_label=M0_SCAR_LABEL,
            notes=[
                "M0 mark-to-next-available fixture mid",
                "scar_bps=0 labeled fixture_mid_0bps_not_alex_slippage",
            ],
        )


class RealisticFillModel(FillModel):
    """m1_realistic_v0: next-bar open or mid ± half-spread + impact stub.

    Scar is a documented proxy, not Alex-calibrated slippage. Sealed/offline.
    """

    id = FILL_MODEL_M1
    half_spread_bps: float = M1_HALF_SPREAD_BPS
    impact_stub_bps: float = M1_IMPACT_STUB_BPS
    scar_label: str = M1_SCAR_LABEL

    def scar_bps_for(self, bar: FixtureBar) -> float:
        if bar.spread_bps is not None and bar.spread_bps > 0:
            half = bar.spread_bps / 2.0
        else:
            half = self.half_spread_bps
        scar = half + self.impact_stub_bps
        if scar <= 0:
            raise RuntimeError("m1_realistic_v0 scar_bps must be non-zero")
        return scar

    def mark_px(self, bar: FixtureBar) -> tuple[float, str]:
        if bar.open is not None and bar.open > 0:
            return bar.open, "next_bar_open"
        return bar.mid, "next_bar_mid"

    def fill_px_for(self, bar: FixtureBar, side: str) -> tuple[float, float, str]:
        mark, mark_src = self.mark_px(bar)
        scar = self.scar_bps_for(bar)
        return apply_adverse_scar(mark, side, scar), scar, mark_src

    def simulate(self, intent: FillIntent, bars: list[FixtureBar]) -> PaperFill:
        clock = intent.decision_clock
        if clock is None:
            raise RuntimeError("m1_realistic_v0 requires decision_clock on FillIntent")

        if intent.abstain:
            return make_paper_fill(
                intent=intent,
                status="skipped",
                venue="paper_sim",
                fill_ts=clock,
                qty_filled=0.0,
                qty_left=intent.qty or 0.0,
                skip_reason=intent.abstain_reason or "intent_abstain",
                fill_model=self.id,
                scar_bps=0.0,
                scar_label=self.scar_label,
                notes=["m1_realistic_v0 skipped; not filled"],
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
                fill_model=self.id,
                scar_bps=0.0,
                scar_label=self.scar_label,
                notes=["m1_realistic_v0 no next-available fixture bar; skipped ≠ filled"],
            )

        side = intent.side or "buy"
        fill_px, scar_bps, mark_src = self.fill_px_for(bar, side)
        qty = intent.qty or 0.0
        return make_paper_fill(
            intent=intent,
            status="acked",
            venue="paper_sim",
            fill_ts=bar.ts,
            fill_px=fill_px,
            qty_filled=qty,
            qty_left=0.0,
            fill_model=self.id,
            scar_bps=scar_bps,
            scar_label=self.scar_label,
            notes=[
                f"m1_realistic_v0 mark={mark_src} then half-spread+impact stub",
                f"scar_bps={scar_bps} labeled {self.scar_label}",
                "not Alex-calibrated slippage; does not unlock paper",
            ],
        )


_MODELS: dict[str, FillModel] = {
    FILL_MODEL_M0: M0FixtureMidFillModel(),
    FILL_MODEL_M1: RealisticFillModel(),
}


def resolve_fill_model(name: str | None = None) -> FillModel:
    canonical = canonicalize_fill_model(name or DEFAULT_FILL_MODEL)
    return _MODELS[canonical]


def simulate_fill(
    intent: FillIntent,
    bars: list[FixtureBar],
    fill_model: str | None = None,
) -> PaperFill:
    return resolve_fill_model(fill_model).simulate(intent, bars)
