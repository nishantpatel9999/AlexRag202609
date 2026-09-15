"""GitBook / playbook snapshot ingest stub (configurable local path)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Iterator

from alexrag.schemas.message import IngestedMessage

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".html", ".htm"}


def _file_id(path: Path) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    return f"gitbook-{digest}"


def iter_gitbook_snapshot(root: Path, *, source_type: str = "gitbook") -> Iterator[IngestedMessage]:
    """Walk a local GitBook/playbook snapshot. No GitBook API / network."""

    root = Path(root)
    if not root.exists():
        return
    if root.is_file():
        files = [root]
    else:
        files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES)
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        yield IngestedMessage(
            id=_file_id(path),
            ts=mtime,
            author="gitbook",
            text=text.strip(),
            attachment_paths=[],
            source_type=source_type,  # type: ignore[arg-type]
            path=str(path),
        )


def ingest_gitbook_snapshot(root: Path, out_path: Path, *, source_type: str = "gitbook") -> int:
    """TODO: replace with GitBook export sync when the snapshot pipeline is wired."""

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", encoding="utf-8") as out:
        for msg in iter_gitbook_snapshot(root, source_type=source_type):
            out.write(json.dumps(msg.model_dump(mode="json"), ensure_ascii=False) + "\n")
            count += 1
    return count
