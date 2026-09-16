from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from alexrag.schemas.audit import AuditEvent


class AuditLog:
    """Append-only JSONL audit sink. Failure to write is fail-closed."""

    def __init__(self, path: Path | None) -> None:
        self.path = Path(path) if path else None
        self.events: list[AuditEvent] = []
        self.available = False
        self.error: str | None = None
        if self.path is None:
            self.error = "missing_audit_path"
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8"):
                pass
            self.available = True
        except OSError as exc:
            self.error = f"audit_open_failed:{exc}"
            self.available = False

    def emit(
        self,
        *,
        kind: str,
        actor: str,
        proposal_id: str | None = None,
        payload: dict | None = None,
        ts: datetime | None = None,
    ) -> AuditEvent | None:
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            ts=ts or datetime.now(timezone.utc),
            kind=kind,
            actor=actor,  # type: ignore[arg-type]
            proposal_id=proposal_id,
            payload=payload or {},
        )
        if not self.available or self.path is None:
            self.error = self.error or "missing_audit"
            return None
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(event.model_dump_json() + "\n")
                fh.flush()
        except OSError as exc:
            self.available = False
            self.error = f"audit_write_failed:{exc}"
            return None
        self.events.append(event)
        return event


def dump_json(obj, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")
