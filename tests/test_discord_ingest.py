from __future__ import annotations

from pathlib import Path

from alexrag.ingest.discord_html import ingest_discord_html, iter_discord_html


def test_discord_html_extracts_fields(fixtures_dir: Path, tmp_path: Path) -> None:
    html = fixtures_dir / "discord" / "sample.html"
    messages = list(iter_discord_html(html))
    assert len(messages) == 2
    first, second = messages
    assert first.id == "1001"
    assert first.author == "Alex"
    assert first.ts is not None
    assert first.ts.year == 2026
    assert "trend day" in first.text.lower()
    assert first.attachment_paths == []
    assert second.id == "1002"
    assert second.attachment_paths
    assert second.attachment_paths[0].endswith("attachments/sample.png")
    assert Path(second.attachment_paths[0]).is_file()


def test_discord_ingest_writes_jsonl(fixtures_dir: Path, tmp_path: Path) -> None:
    html = fixtures_dir / "discord" / "sample.html"
    out = tmp_path / "discord.jsonl"
    count = ingest_discord_html(html, out)
    assert count == 2
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert '"id": "1001"' in lines[0]
    assert "attachment_paths" in lines[1]


def test_discord_ingest_is_chunked_not_read_text(fixtures_dir: Path, tmp_path: Path, monkeypatch) -> None:
    html = fixtures_dir / "discord" / "sample.html"
    out = tmp_path / "discord.jsonl"

    def boom(*_args, **_kwargs):
        raise AssertionError("ingest must not Path.read_text the whole HTML file")

    monkeypatch.setattr(Path, "read_text", boom)
    count = ingest_discord_html(html, out, chunk_size=128)
    assert count == 2


def test_trade_log_html(fixtures_dir: Path) -> None:
    html = fixtures_dir / "discord" / "trade_log.html"
    messages = list(iter_discord_html(html, source_type="trade_log"))
    assert len(messages) == 1
    assert messages[0].source_type == "trade_log"
    assert "$NVDA" in messages[0].text
