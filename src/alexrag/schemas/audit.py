from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """Append-only audit record. Missing audit sink is fail-closed (abstain)."""

    event_id: str
    ts: datetime
    kind: str
    actor: Literal[
        "orchestrator",
        "regime",
        "setup",
        "risk",
        "exec",
        "auditor",
        "ingest",
        "rag",
        "broker",
        "notify",
    ]
    proposal_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
