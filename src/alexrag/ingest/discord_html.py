"""DiscordChatExporter-style HTML → JSONL ingest (streaming / large-file friendly).

Corpus notes (see docs/CORPUS.md):
- Operator Mac HTML (equity-trades, alex-journal, prime-report, pf-update ~1428)
  is NOT ingested in MVP — fixtures only. focuslist-ideas is out of MVP.
- pf-update is portfolio/state only, not fills ground truth (equity-trades remains #1).
- Follow-on messages often omit <time datetime>; timestamps inherit across
  messages AND message groups from the last seen datetime.
- Current DiscordChatExporter HTML may use title= on chatlog__timestamp /
  chatlog__short-timestamp instead of <time datetime>.
- Naive timestamps are America/Los_Angeles; ingest is labeled **PT**.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

from alexrag.schemas.message import IngestedMessage
from alexrag.schemas.sources import DEFAULT_DISCORD_TZ

CHUNK_SIZE = 64 * 1024
DISCORD_TZ = ZoneInfo(DEFAULT_DISCORD_TZ)


def parse_ts(value: str | None) -> datetime | None:
    """Parse ISO datetime or DiscordChatExporter title strings.

    Real exporter HTML often uses:
      title="Monday, October 3, 2022 6:37\u202fAM"
    on chatlog__timestamp / chatlog__short-timestamp (no <time datetime>).
    Naive values are America/Los_Angeles (PT).
    """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    # Normalize narrow/no-break spaces common in exporter titles.
    for ch in (" ", " ", " "):
        text = text.replace(ch, " ")
    text = " ".join(text.split())
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        dt = None
    if dt is None:
        for fmt in (
            "%A, %B %d, %Y %I:%M %p",
            "%A, %B %d, %Y %H:%M",
            "%m/%d/%Y %I:%M %p",
            "%m/%d/%Y %H:%M",
        ):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=DISCORD_TZ)
    return dt


def _has_class(class_attr: str | None, token: str) -> bool:
    if not class_attr:
        return False
    return token in class_attr.split()


class DiscordHTMLParser(HTMLParser):
    """Incremental parser for DiscordChatExporter HTML exports.

    `_carry_ts` survives message groups so follow-on / next-group messages
    without a datetime inherit the last seen timestamp.
    """

    def __init__(self, on_message: Callable[[dict], None]) -> None:
        super().__init__(convert_charrefs=True)
        self._on_message = on_message
        self._msg: dict | None = None
        self._author_depth = 0
        self._text_depth = 0
        self._attach_depth = 0
        self._author_buf: list[str] = []
        self._text_buf: list[str] = []
        self._carry_ts: str | None = None

    def _emit(self) -> None:
        if not self._msg:
            return
        text = " ".join("".join(self._text_buf).split())
        author = " ".join("".join(self._author_buf).split())
        raw_ts = self._msg.get("ts")
        inherited = False
        if not raw_ts and self._carry_ts:
            raw_ts = self._carry_ts
            inherited = True
        elif raw_ts:
            self._carry_ts = raw_ts
        rec = {
            "id": self._msg.get("id") or "",
            "ts": raw_ts,
            "ts_inherited": inherited,
            "author": author,
            "text": text,
            "attachment_paths": list(self._msg.get("attachment_paths") or []),
        }
        if rec["id"] or rec["text"] or rec["attachment_paths"]:
            self._on_message(rec)
        self._msg = None
        self._author_buf = []
        self._text_buf = []
        self._author_depth = 0
        self._text_depth = 0
        self._attach_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k: v for k, v in attrs}
        classes = ad.get("class") or ""
        if (
            _has_class(classes, "chatlog__message-container")
            or ad.get("data-message-id")
            or (tag == "div" and (ad.get("id") or "").startswith("chatlog__message-container-"))
        ):
            self._emit()
            msg_id = ad.get("data-message-id") or ""
            raw_id = ad.get("id") or ""
            if not msg_id and raw_id.startswith("chatlog__message-container-"):
                msg_id = raw_id.removeprefix("chatlog__message-container-")
            self._msg = {"id": msg_id, "ts": None, "attachment_paths": []}
            self._author_buf = []
            self._text_buf = []

        if self._msg is None:
            return

        if _has_class(classes, "chatlog__author"):
            self._author_depth = 1
        elif self._author_depth:
            self._author_depth += 1

        if _has_class(classes, "chatlog__content") or _has_class(
            classes, "chatlog__markdown-preserve"
        ):
            if self._text_depth == 0:
                self._text_depth = 1
            else:
                self._text_depth += 1
        elif self._text_depth:
            self._text_depth += 1

        if _has_class(classes, "chatlog__attachment"):
            self._attach_depth = 1
        elif self._attach_depth:
            self._attach_depth += 1

        if tag == "time" and ad.get("datetime"):
            self._msg["ts"] = ad.get("datetime")

        # DiscordChatExporter (current): timestamps live in title= on
        # chatlog__timestamp / chatlog__short-timestamp, not <time datetime>.
        if ad.get("title") and (
            _has_class(classes, "chatlog__timestamp")
            or _has_class(classes, "chatlog__short-timestamp")
        ):
            self._msg["ts"] = ad.get("title")

        if self._attach_depth and tag in {"a", "img"}:
            src = ad.get("href") or ad.get("src")
            if src and src not in self._msg["attachment_paths"]:
                self._msg["attachment_paths"].append(src)

    def handle_endtag(self, tag: str) -> None:
        if self._author_depth:
            self._author_depth -= 1
        if self._text_depth:
            self._text_depth -= 1
        if self._attach_depth:
            self._attach_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._msg is None:
            return
        if self._author_depth:
            self._author_buf.append(data)
        if self._text_depth:
            self._text_buf.append(data)

    def close(self) -> None:
        self._emit()
        super().close()


def _resolve_attachments(html_path: Path, paths: list[str]) -> list[str]:
    resolved: list[str] = []
    root = html_path.parent
    for raw in paths:
        if raw.startswith(("http://", "https://", "data:")):
            # Record path only; never fetch.
            resolved.append(raw)
            continue
        resolved.append(str((root / raw).resolve()))
    return resolved


def iter_discord_html(
    html_path: Path,
    *,
    source_type: str = "journal",
    chunk_size: int = CHUNK_SIZE,
) -> Iterator[IngestedMessage]:
    """Stream messages from a DiscordChatExporter HTML file without slurping it.

    Do not point this at Mac corpus trees in MVP; fixtures only.
    """

    html_path = Path(html_path)
    pending: list[IngestedMessage] = []

    def on_message(raw: dict) -> None:
        pending.append(
            IngestedMessage(
                id=raw["id"] or f"anon-{len(pending)+1}",
                ts=parse_ts(raw.get("ts")),
                ts_inherited=bool(raw.get("ts_inherited")),
                author=raw.get("author") or "",
                text=raw.get("text") or "",
                attachment_paths=_resolve_attachments(html_path, raw.get("attachment_paths") or []),
                source_type=source_type,  # type: ignore[arg-type]
                path=str(html_path),
                tz_label="PT",
            )
        )

    parser = DiscordHTMLParser(on_message)
    with html_path.open("r", encoding="utf-8") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            parser.feed(chunk)
            while pending:
                yield pending.pop(0)
    parser.close()
    while pending:
        yield pending.pop(0)


def ingest_discord_html(
    html_path: Path,
    out_path: Path,
    *,
    source_type: str = "journal",
    chunk_size: int = CHUNK_SIZE,
) -> int:
    """Write JSONL (id, ts, author, text, attachment_paths, tz_label=PT). Returns message count."""

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", encoding="utf-8") as out:
        for msg in iter_discord_html(html_path, source_type=source_type, chunk_size=chunk_size):
            line = json.dumps(msg.model_dump(mode="json"), ensure_ascii=False)
            out.write(line + "\n")
            count += 1
    return count
