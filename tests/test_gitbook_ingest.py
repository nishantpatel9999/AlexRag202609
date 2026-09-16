from __future__ import annotations

from pathlib import Path

from alexrag.ingest.gitbook import ingest_gitbook_snapshot, iter_gitbook_snapshot


def test_gitbook_snapshot_ingest(fixtures_dir: Path, tmp_path: Path) -> None:
    root = fixtures_dir / "gitbook"
    docs = list(iter_gitbook_snapshot(root))
    assert len(docs) == 1
    assert docs[0].source_type == "gitbook"
    assert "kill switch" in docs[0].text.lower()
    out = tmp_path / "gitbook.jsonl"
    assert ingest_gitbook_snapshot(root, out) == 1
    assert out.read_text(encoding="utf-8").strip()
