from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from alexrag.config import load_settings
from alexrag.agents.orchestrator import run_paper_day
from alexrag.eval.harness import DEFAULT_PACK, load_golden_pack, score_pack
from alexrag.eval.model_emit import DEFAULT_OUT_ROOT, emit_model_predictions
from alexrag.eval.model_lock import DEFAULT_FROZEN_PACK, DEFAULT_LOCK_PATH
from alexrag.eval.model_scorer import KillScarError, run_score_model
from alexrag.llm.inferhub import InferhubClient, inferhub_key_present
from alexrag.ingest.discord_html import ingest_discord_html
from alexrag.ingest.gitbook import ingest_gitbook_snapshot
from alexrag.pipeline import load_fixture_messages, messages_to_index, newest_timestamp

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("ingest-discord")
def ingest_discord(
    html: Path = typer.Argument(..., exists=True, readable=True, help="DiscordChatExporter HTML"),
    out: Path = typer.Option(..., "--out", "-o", help="JSONL output path"),
    source_type: str = typer.Option(
        "journal", help="trade_log|journal|gameplan|report|pf_update|gitbook"
    ),
) -> None:
    """Stream Discord HTML to JSONL (id, ts, author, text, attachment_paths). Timestamps labeled PT."""

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


@app.command("emit-model-predictions")
def emit_model_predictions_cmd(
    ingest: Path = typer.Option(
        Path("data/ingest"),
        "--ingest",
        help="MVP JSONL dir (equity-trades.jsonl, alex-journal.jsonl, …).",
    ),
    frozen: Path = typer.Option(DEFAULT_FROZEN_PACK, "--frozen", exists=True, readable=True),
    lock: Path = typer.Option(DEFAULT_LOCK_PATH, "--lock", exists=True, readable=True),
    out: Path = typer.Option(DEFAULT_OUT_ROOT, "--out", help="Audit root; writes <run_id>/predictions.jsonl"),
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--no-dry-run",
        help="Skip Inferhub; write abstain predictions with model_id=dry_run_abstain.",
    ),
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Immutable audit run id"),
    max_messages: int = typer.Option(32, "--max-messages", help="Max sealed context messages per case"),
) -> None:
    """Emit sealed-cutoff MODEL_EVAL_LOCK_V0 predictions.jsonl. Capital 0; no paper unlock.

    Loads the frozen Golden-48 pack + lock, applies eligible_filter over MVP ingest
    (excludes banned_same_day_ids), never injects target_action / GT fill bodies,
    and writes one JSON object per case_id. Default --dry-run is offline CI.
    Live Inferhub (--no-dry-run) needs INFERHUB_API_KEY (Mac); never logged.
    """

    if not dry_run and not inferhub_key_present():
        typer.echo(
            "INFERHUB_API_KEY is required for --no-dry-run (set on Mac; never commit). "
            "Use --dry-run for offline abstain predictions.",
            err=True,
        )
        raise typer.Exit(code=2)

    ingest_dir: Path | None = ingest if ingest.exists() else None
    client = None if dry_run else InferhubClient()
    try:
        run = emit_model_predictions(
            ingest_dir=ingest_dir,
            frozen_path=frozen,
            lock_path=lock,
            out_root=out,
            dry_run=dry_run,
            run_id=run_id,
            max_messages=max_messages,
            client=client,
        )
    except FileExistsError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    pred_path = Path(run.out_dir) / "predictions.jsonl"
    typer.echo(
        f"run_id={run.meta.run_id} cases={run.meta.n_cases} abstain={run.meta.n_abstain} "
        f"model_id={run.meta.model_id} dry_run={dry_run} "
        f"paper_authority=false capital=0 wrote={pred_path}"
    )


@app.command("score-model")
def score_model(
    predictions: Path = typer.Option(..., "--predictions", exists=True, readable=True),
    ingest: Path = typer.Option(
        Path("data/ingest"),
        "--ingest",
        help="MVP JSONL dir (equity-trades.jsonl, alex-journal.jsonl, …). Optional for scoring.",
    ),
    frozen: Path = typer.Option(DEFAULT_FROZEN_PACK, "--frozen", exists=True, readable=True),
    lock: Path = typer.Option(DEFAULT_LOCK_PATH, "--lock", exists=True, readable=True),
    out: Path = typer.Option(Path("results/model_eval_runs"), "--out", help="Audit root"),
) -> None:
    """Score a predictions JSONL against MODEL_EVAL_LOCK_V0. Offline; capital 0; no LLM."""

    ingest_dir: Path | None = ingest if ingest.exists() else None
    try:
        run = run_score_model(
            predictions_path=predictions,
            ingest_dir=ingest_dir,
            frozen_path=frozen,
            lock_path=lock,
            out_root=out,
        )
    except KillScarError as exc:
        dest = exc.run.out_dir if exc.run is not None else ""
        typer.echo(
            f"KILL_SCAR run_valid=false paper_authority=false capital=0 hits={exc.hits} wrote={dest}",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    s = run.summary
    typer.echo(
        f"run_id={run.run_id} cases={s.n_cases} scored={s.n_scored} "
        f"pass={s.n_pass} fail={s.n_fail} ambiguous={s.n_ambiguous} "
        f"cfp={s.cfp_count} no_trade_p={s.no_trade_precision} no_trade_r={s.no_trade_recall} "
        f"run_valid={s.run_valid} paper_authority=false capital=0 pnl={s.pnl_scored} "
        f"wrote={run.out_dir}"
    )


if __name__ == "__main__":
    app()
