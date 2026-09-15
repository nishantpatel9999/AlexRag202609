"""Sealed chronological cutoff and post-fill enter-evidence ban.

See docs/EVAL_SPEC_V0.md. Naive timestamps are America/Los_Angeles.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from alexrag.schemas.sources import DEFAULT_DISCORD_TZ

ENTER_BANNED_SOURCES = frozenset({"journal", "gameplan", "report", "gitbook"})


def aware(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=ZoneInfo(DEFAULT_DISCORD_TZ))
    return ts


def sealed_ok(timestamp: datetime | None, decision_ts: datetime | None) -> bool:
    """True iff evidence timestamp is strictly before decision_ts."""

    if timestamp is None or decision_ts is None:
        return False
    return aware(timestamp) < aware(decision_ts)


def enter_evidence_illegal(
    *,
    timestamp: datetime | None,
    source_type: str,
    decision_ts: datetime | None,
    fill_ts: datetime | None = None,
) -> bool:
    """Post-fill (or not sealed) rationalization cannot justify enter."""

    cutoff = fill_ts or decision_ts
    if not sealed_ok(timestamp, cutoff):
        return True
    if source_type in ENTER_BANNED_SOURCES and fill_ts is not None:
        if timestamp is not None and aware(timestamp) >= aware(fill_ts):
            return True
    return False
