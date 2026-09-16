from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from zoneinfo import ZoneInfo

from alexrag.schemas.fill_intent import FillIntent
from alexrag.schemas.sources import DEFAULT_DISCORD_TZ

FillStatus = Literal["acked", "partial", "rejected", "skipped", "stubbed"]
FillVenue = Literal["paper_sim", "alpaca_paper"]
FillModel = Literal["m0_fixture_mid_0bps", "m1_realistic_v0"]

FILL_MODEL_M0 = "m0_fixture_mid_0bps"
FILL_MODEL_M0_ALIAS = "M0"
FILL_MODEL_M1 = "m1_realistic_v0"
DEFAULT_FILL_MODEL = FILL_MODEL_M1

# M0 is mark-to-next-available fixture bar/mid. This label is not Alex slippage.
M0_SCAR_LABEL = "fixture_mid_0bps_not_alex_slippage"
# M1 documented proxy (half-spread + impact stub). Not Alex-calibrated slippage.
M1_SCAR_LABEL = "proxy_half_spread_not_alex_slippage"
STUBBED_SCAR_LABEL = "stubbed_not_filled"


def canonicalize_fill_model(value: str) -> FillModel:
    raw = (value or "").strip()
    if raw in {FILL_MODEL_M0_ALIAS, FILL_MODEL_M0}:
        return FILL_MODEL_M0
    if raw == FILL_MODEL_M1:
        return FILL_MODEL_M1
    raise ValueError(
        "unknown fill_model "
        f"{value!r}; expected m0_fixture_mid_0bps, M0, or m1_realistic_v0"
    )


def is_m0_fill_model(value: str) -> bool:
    return canonicalize_fill_model(value) == FILL_MODEL_M0


def _aware(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=ZoneInfo(DEFAULT_DISCORD_TZ))
    return ts


class PaperFill(BaseModel):
    """Paper fill / receipt. ``stubbed`` is not a fill (filled=False, qty_filled=0)."""

    fill_ts: datetime
    fill_px: float | None = None
    qty_filled: float = 0.0
    qty_left: float = 0.0
    status: FillStatus
    venue: FillVenue
    latency_ms: float = 0.0
    intent_id: str
    proposal_id: str
    filled: bool = False
    fill_model: FillModel = FILL_MODEL_M0
    scar_bps: float = 0.0
    scar_label: str = M0_SCAR_LABEL
    skip_reason: str | None = None
    notes: list[str] = Field(default_factory=list)

    @field_validator("fill_model", mode="before")
    @classmethod
    def _canon_fill_model(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("fill_model must be a string")
        return canonicalize_fill_model(value)

    @model_validator(mode="after")
    def _status_vs_filled(self) -> PaperFill:
        if self.status in {"stubbed", "skipped", "rejected"}:
            if self.filled:
                raise ValueError(f"{self.status} is not filled")
            if self.qty_filled != 0:
                raise ValueError(f"{self.status} requires qty_filled=0")
        if self.status == "acked":
            if not self.filled:
                raise ValueError("acked must have filled=True")
            if self.qty_filled <= 0:
                raise ValueError("acked requires qty_filled>0")
            if self.fill_px is None:
                raise ValueError("acked requires fill_px")
        if self.status == "partial":
            if self.qty_filled <= 0:
                raise ValueError("partial requires qty_filled>0")
            if not self.filled:
                raise ValueError("partial with qty_filled>0 is filled")
            if self.fill_px is None:
                raise ValueError("partial requires fill_px")

        if is_m0_fill_model(self.fill_model):
            if self.scar_bps != 0:
                raise ValueError("M0 scar_bps must be 0; do not invent Alex slippage")
        elif self.status in {"acked", "partial"}:
            if self.scar_bps == 0:
                raise ValueError(
                    "m1_realistic_v0 filled receipts cannot claim 0bps fixture mid"
                )
            if self.scar_label == M0_SCAR_LABEL:
                raise ValueError(
                    "m1_realistic_v0 must not use fixture_mid_0bps_not_alex_slippage"
                )
            if self.scar_label != M1_SCAR_LABEL:
                raise ValueError(
                    f"m1_realistic_v0 filled scar_label must be {M1_SCAR_LABEL}"
                )
        return self


FillReceipt = PaperFill


def latency_ms_vs_clock(fill_ts: datetime, decision_clock: datetime | None) -> float:
    if decision_clock is None:
        return 0.0
    return (_aware(fill_ts) - _aware(decision_clock)).total_seconds() * 1000.0


def make_paper_fill(
    *,
    intent: FillIntent,
    status: FillStatus,
    venue: FillVenue,
    fill_ts: datetime,
    fill_px: float | None = None,
    qty_filled: float = 0.0,
    qty_left: float | None = None,
    skip_reason: str | None = None,
    fill_model: str = FILL_MODEL_M0,
    scar_bps: float = 0.0,
    scar_label: str = M0_SCAR_LABEL,
    notes: list[str] | None = None,
) -> PaperFill:
    filled = status in {"acked", "partial"} and qty_filled > 0
    left = (intent.qty or 0.0) - qty_filled if qty_left is None else qty_left
    clock = intent.decision_clock or fill_ts
    return PaperFill(
        fill_ts=fill_ts,
        fill_px=fill_px,
        qty_filled=qty_filled,
        qty_left=max(0.0, left),
        status=status,
        venue=venue,
        latency_ms=latency_ms_vs_clock(fill_ts, clock),
        intent_id=intent.intent_id,
        proposal_id=intent.proposal_id,
        filled=filled,
        fill_model=canonicalize_fill_model(fill_model),
        scar_bps=scar_bps,
        scar_label=scar_label,
        skip_reason=skip_reason,
        notes=list(notes or []),
    )
