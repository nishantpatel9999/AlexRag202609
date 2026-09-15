from __future__ import annotations

from typer.testing import CliRunner

from alexrag.cli import app

runner = CliRunner()


def test_cli_ingest_and_paper_day(fixtures_dir, tmp_path) -> None:
    html = fixtures_dir / "discord" / "sample.html"
    out_jsonl = tmp_path / "d.jsonl"
    ingest = runner.invoke(app, ["ingest-discord", str(html), "--out", str(out_jsonl)])
    assert ingest.exit_code == 0, ingest.output
    assert "wrote 2 messages" in ingest.output

    gb_out = tmp_path / "g.jsonl"
    gb = runner.invoke(
        app,
        ["ingest-gitbook", "--path", str(fixtures_dir / "gitbook"), "--out", str(gb_out)],
    )
    assert gb.exit_code == 0, gb.output

    proposal_path = tmp_path / "proposal.json"
    audit = tmp_path / "audit.jsonl"
    result = runner.invoke(
        app,
        [
            "run-paper-day",
            "--dry-run",
            "--fixtures",
            str(fixtures_dir),
            "--out",
            str(proposal_path),
            "--audit-log",
            str(audit),
        ],
    )
    assert result.exit_code == 0, result.output
    text = proposal_path.read_text(encoding="utf-8")
    assert '"mode": "paper"' in text
    assert '"abstain"' in text
    assert '"decision_clock"' in text
    assert audit.is_file()
