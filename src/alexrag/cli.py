from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from alexrag.config import load_settings
from alexrag.agents.orchestrator import run_paper_day
from alexrag.eval.harness import DEFAULT_PACK, load_golden_pack, score_pack
from alexrag.ingest.discord_html import ingest_discord_html
from alexrag.ingest.gitbook import ingest_gitbook_snapshot
from alexrag.pipeline import load_fixture_messages, messages_to_index, newest_timestamp

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("ingest-discord")
def ingest_discord(
    html: Path = typer.Argument(..., exists=True, readable=True, help="DiscordChatExporter HTML"),
    out: Path = typer.Option(..., "--out", "-o", help="JSONL output path"),
    source_type: str = typer.Option("journal", help="trade_log|journal|report|gitbook"),
) -> None:
    """Stream Discord HTML to JSONL (id, ts, author, text, attachment_paths)."""

    count = ingest_discord_html(html, out, source_type=source_type)
    typer.echo(f"wrote {count} messages to {out}")


@app.command("ingest-gitbook")
def ingest_gitbook(
    path: Optional[Path] = typer.Option(None, "--path", help="GitBook/playbook snapshot directory"),
    out: Path = typer.Option(..., "--out", "-o", help="JSONL output path"),
) -> None:
    """Ingest fixture/doctrine markdown. Not a GitBook mirror; see docs/CORPUS.md."""

    settings = load_settings()
    root = path or Path(settings.paths.gitbook_snapshot)
    count = ingest_gitbook_snapshot(root, out)
    typer.echo(f"wrote {count} documents from {root} to {out}")


@app.command("run-paper-day")
def run_paper_day_cmd(
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run"),
    fixtures: Path = typer.Option(Path("tests/fixtures"), help="Fixture directory"),
    out: Optional[Path] = typer.Option(None, "--out", help="Write Proposal JSON here"),
    audit_log: Optional[Path] = typer.Option(None, help="Audit JSONL path"),
    query: str = typer.Option(
        "trend day trade log fill ticker playbook regime setup"
    ),
    as_of: Optional[str] = typer.Option(
        None, help="Decision clock ISO-8601. Default on dry-run: latest fixture timestamp."
    ),
    config: Optional[Path] = typer.Option(None, help="YAML config path"),
) -> None:
    """Run Regime→Setup→Risk→Exec paper stub→Auditor on local fixtures. No network."""

    settings = load_settings(config)
    messages = load_fixture_messages(fixtures)
    if not messages:
        raise typer.BadParameter(f"no fixture messages found under {fixtures}")
    index = messages_to_index(messages, settings)
    if as_of:
        clock = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    else:
        clock = newest_timestamp(messages)
    audit_path = audit_log or Path(settings.paths.audit_log)
    result = run_paper_day(
        settings,
        index,
        query=query,
        decision_clock=clock,
        audit_path=audit_path,
        dry_run=dry_run,
    )
    payload = result.proposal_json()
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")
        typer.echo(f"wrote proposal to {out}")
    typer.echo(payload)


@app.command("eval-golden")
def eval_golden(
    pack: Path = typer.Option(DEFAULT_PACK, "--pack", help="eval/golden_cases_v0.json"),
) -> None:
    """Load V0 golden cases and score offline (no P&L, no network)."""

    loaded = load_golden_pack(pack)
    summary = score_pack(loaded)
    typer.echo(
        f"loaded {summary['n_cases']} cases version={summary['version']} "
        f"scored={summary['n_scored']} passed={summary['n_passed']} pnl={summary['pnl_scored']}"
    )


if __name__ == "__main__":
    app()
