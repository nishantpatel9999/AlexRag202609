"""Offline fixture bars for paper_sim M0. No live market data."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from alexrag.eval.cutoff import aware


class FixtureBar(BaseModel):
    ts: datetime
    ticker: str
    mid: float


def load_fixture_bars(path: Path) -> list[FixtureBar]:
    path = Path(path)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "bars" in raw:
        raw = raw["bars"]
    if not isinstance(raw, list):
        raise ValueError(f"fixture bars at {path} must be a list or {{bars: [...]}}")
    return [FixtureBar.model_validate(item) for item in raw]


def next_available_bar(
    bars: list[FixtureBar],
    ticker: str | None,
    after: datetime,
) -> FixtureBar | None:
    """First bar with ts strictly after ``after`` for ``ticker``. Past bars are not marks."""

    if not ticker:
        return None
    want = ticker.upper()
    eligible = [
        bar
        for bar in bars
        if bar.ticker.upper() == want and bar.mid > 0 and aware(bar.ts) > aware(after)
    ]
    if not eligible:
        return None
    eligible.sort(key=lambda b: aware(b.ts))
    return eligible[0]


def next_available_mid(
    bars: list[FixtureBar],
    ticker: str | None,
    after: datetime,
) -> float | None:
    bar = next_available_bar(bars, ticker, after)
    return None if bar is None else bar.mid
