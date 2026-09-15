from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from alexrag.schemas.sources import SourceType


class IngestedMessage(BaseModel):
    """Normalized Discord / doctrine / journal record written as JSONL."""

    id: str
    ts: datetime | None = None
    author: str = ""
    text: str = ""
    attachment_paths: list[str] = Field(default_factory=list)
    source_type: SourceType = "journal"
    path: str | None = None
    captions: list[str] = Field(default_factory=list)
    # DiscordChatExporter omits datetime on follow-on messages; inherit last seen ts.
    ts_inherited: bool = False
