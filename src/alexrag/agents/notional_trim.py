"""Pro-rata trim math for paper gross-notional cap. No broker, no network, no live path.

Nishant lock: ``notional_breach_policy=pro_rata_trim_for_new_entry``.

If a new entry/buy would push **gross** notional above ``max_notional_pct`` of
equity (locked 150%), scale every open position by the same factor until there
is room for the **requested** new size, then enter. The new entry is not
shrunk to leftover room. It is clipped only when it alone exceeds the cap
(existing book flattened to 0).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import copysign
from typing import Sequence

from alexrag.config import NOTIONAL_BREACH_POLICY, OPERATOR_MAX_NOTIONAL_PCT


@dataclass(frozen=True)
class TrimmedPosition:
    ticker: str
    notional_before: float
    notional_after: float

    @property
    def trimmed_notional(self) -> float:
        return abs(self.notional_before) - abs(self.notional_after)


@dataclass(frozen=True)
class ProRataTrimPlan:
    policy: str
    equity: float
    max_notional_pct: float
    max_gross_notional: float
    current_gross: float
    requested_new_notional: float
    entered_notional: float
    overflow: float
    scale_existing: float
    positions: tuple[TrimmedPosition, ...]
    new_clipped_to_cap: bool
    ready: bool

    @property
    def resulting_gross(self) -> float:
        return sum(abs(p.notional_after) for p in self.positions) + self.entered_notional

    @property
    def trimmed(self) -> bool:
        return any(p.trimmed_notional > 0 for p in self.positions)


def _as_pair(item: object) -> tuple[str, float]:
    if isinstance(item, tuple) and len(item) == 2:
        ticker, notional = item
        return str(ticker), float(notional)
    ticker = getattr(item, "ticker", None)
    notional = getattr(item, "notional", None)
    if ticker is None or notional is None:
        raise TypeError(f"open position must be (ticker, notional) or have those attributes: {item!r}")
    return str(ticker), float(notional)


def pro_rata_trim_for_new_entry(
    open_positions: Sequence[object],
    new_notional: float,
    *,
    equity: float,
    max_notional_pct: float = OPERATOR_MAX_NOTIONAL_PCT,
) -> ProRataTrimPlan:
    """Return a deterministic trim plan. Pure function; does not mutate a book."""

    pairs = [_as_pair(p) for p in open_positions]
    current_gross = sum(abs(n) for _, n in pairs)
    requested = max(0.0, float(new_notional))
    ready = equity > 0 and max_notional_pct > 0
    max_gross = (equity * max_notional_pct) if ready else 0.0

    if not ready:
        unchanged = tuple(
            TrimmedPosition(ticker=t, notional_before=n, notional_after=n) for t, n in pairs
        )
        return ProRataTrimPlan(
            policy=NOTIONAL_BREACH_POLICY,
            equity=equity,
            max_notional_pct=max_notional_pct,
            max_gross_notional=0.0,
            current_gross=current_gross,
            requested_new_notional=requested,
            entered_notional=0.0,
            overflow=current_gross + requested,
            scale_existing=1.0,
            positions=unchanged,
            new_clipped_to_cap=False,
            ready=False,
        )

    entered = min(requested, max_gross)
    new_clipped = entered < requested
    projected = current_gross + entered
    overflow = max(0.0, projected - max_gross)
    target_existing = max(0.0, max_gross - entered)

    if current_gross <= 0 or overflow <= 0:
        scale = 1.0
        trimmed = tuple(
            TrimmedPosition(ticker=t, notional_before=n, notional_after=n) for t, n in pairs
        )
    else:
        scale = target_existing / current_gross
        allocated_gross = 0.0
        built: list[TrimmedPosition] = []
        last = len(pairs) - 1
        for i, (ticker, signed) in enumerate(pairs):
            gross = abs(signed)
            if i == last:
                after_gross = max(0.0, target_existing - allocated_gross)
            else:
                after_gross = gross * scale
                allocated_gross += after_gross
            if signed == 0:
                after_signed = 0.0
            else:
                after_signed = copysign(after_gross, signed)
            built.append(
                TrimmedPosition(
                    ticker=ticker,
                    notional_before=signed,
                    notional_after=after_signed,
                )
            )
        trimmed = tuple(built)

    return ProRataTrimPlan(
        policy=NOTIONAL_BREACH_POLICY,
        equity=equity,
        max_notional_pct=max_notional_pct,
        max_gross_notional=max_gross,
        current_gross=current_gross,
        requested_new_notional=requested,
        entered_notional=entered,
        overflow=overflow,
        scale_existing=scale,
        positions=trimmed,
        new_clipped_to_cap=new_clipped,
        ready=True,
    )
