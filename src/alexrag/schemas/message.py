from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class IngestedMessage(BaseModel):
    """Normalized Discord / GitBook / journal record written as JSONL."""

    id: str
    ts: datetime | None = None
    author: str = ""
    text: str = ""
    attachment_paths: list[str] = Field(default_factory=list)
    source_type: Literal["trade_log", "journal", "report", "gitbook"] = "journal"
    path: str | None = None
    captions: list[str] = Field(default_factory=list)
