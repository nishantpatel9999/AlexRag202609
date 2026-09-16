"""Sealed MVP corpus: eligible_filter over ingest JSONL, excluding banned ids.

No Mac ingest required — tests ship tiny JSONL under tests/fixtures/.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from alexrag.eval.cutoff import aware, parse_ts, sealed_ok
from alexrag.eval.frozen_pack import FrozenCase
from alexrag.eval.model_lock import MVP_CHANNELS, MVP_JSONL_NAMES
from alexrag.schemas.sources import CHANNEL_TO_SOURCE, SourceType


class CorpusMessage(BaseModel):
    """One MVP ingest row with channel attached. Safe for retrieval context."""

    model_config = ConfigDict(extra="forbid")

    message_id: str
    channel: str
    ts: datetime | None = None
    text: str = ""
    author: str = ""
    source_type: SourceType = "journal"
    ts_inherited: bool = False


class SealedCorpus:
    """MVP JSONL index. Apply per-case eligible_filter; never return banned ids."""

    def __init__(self, messages: Iterable[CorpusMessage]):
        self.messages = list(messages)
        self.by_id: dict[str, CorpusMessage] = {m.message_id: m for m in self.messages}

    def eligible_for(self, case: FrozenCase) -> list[CorpusMessage]:
        channels = set(case.eligible_filter.channels)
        banned = set(case.banned_same_day_ids)
        tz_name = case.eligible_filter.tz
        cutoff = aware(case.eligible_filter.ts_lt, tz_name)
        selected: list[CorpusMessage] = []
        for msg in self.messages:
            if msg.channel not in channels:
                continue
            if msg.message_id in banned:
                continue
            if msg.ts is None:
                continue
            ts = aware(msg.ts, tz_name)
            if not sealed_ok(ts, cutoff):
                continue
            selected.append(msg)
        selected.sort(key=lambda m: (aware(m.ts, tz_name), m.message_id))
        return selected

    def lookup(self, message_id: str) -> CorpusMessage | None:
        return self.by_id.get(message_id)


def _row_to_message(data: dict, channel: str) -> CorpusMessage | None:
    message_id = data.get("id") or data.get("message_id")
    if not message_id:
        return None
    source = data.get("source_type") or CHANNEL_TO_SOURCE.get(channel, "journal")
    return CorpusMessage(
        message_id=str(message_id),
        channel=channel,
        ts=parse_ts(data.get("ts")),
        text=str(data.get("text") or ""),
        author=str(data.get("author") or ""),
        source_type=source,
        ts_inherited=bool(data.get("ts_inherited") or False),
    )


def load_mvp_ingest(ingest_dir: Path | None) -> SealedCorpus:
    """Load equity-trades / alex-journal / prime-report / pf-update JSONL.

    Missing files are skipped (tests ship a subset). focuslist-ideas is never loaded.
    """

    messages: list[CorpusMessage] = []
    if ingest_dir is None:
        return SealedCorpus(messages)
    root = Path(ingest_dir)
    if not root.exists():
        return SealedCorpus(messages)
    for channel in MVP_CHANNELS:
        path = root / MVP_JSONL_NAMES[channel]
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if not isinstance(data, dict):
                    continue
                msg = _row_to_message(data, channel)
                if msg is not None:
                    messages.append(msg)
    return SealedCorpus(messages)


def eligible_messages(case: FrozenCase, corpus: SealedCorpus) -> list[CorpusMessage]:
    """Eligible retrieval rows: channel ∈ filter, ts < ts_lt, id ∉ banned_same_day_ids."""

    return corpus.eligible_for(case)
