# Runbook — Mac Studio vs npsecondbrain

Paper-only MVP. Do not point this stack at live brokerage endpoints.

## Roles

| Host | Role |
| --- | --- |
| **Mac Studio** | Future local models (vision caption, embeddings). Cursor **API for Cursor** (Standard Agents) listening on **:8794**. Heavy GPU/NPU work stays here. |
| **npsecondbrain (VPS)** | Orchestrator, Discord HTML ingest (large exports), GitBook snapshot path, `run-paper-day`, audit JSONL. Tunnel **VPS :8791 → Mac :8794** for Cursor API bridge. |

Secrets stay in local `.env` on the host that needs them. **Never commit secrets.** Use `.env.example` as the template.

## VPS: Cursor API bridge (when using Hermes / custom provider)

On npsecondbrain, provider `custom:cursor-api` should already be:

- `base_url`: `http://127.0.0.1:8791/v1`
- `key_env`: `CURSOR_API_KEY`

Health depends on Mac “API for Cursor” running with a valid Cursor API key.

Working model switch (examples):

```text
/model name:composer-2.5 --provider custom:cursor-api
/model name:composer-2.5-fast --provider custom:cursor-api
/model name:grok-4.5 --provider custom:cursor-api
/model name:grok-4.5-fast --provider custom:cursor-api
```

This runbook does not require the bridge for **offline unit tests** or `run-paper-day --dry-run` on fixtures (fake embeddings, no network).

## One-time setup (either host)

```bash
uv sync --extra dev
cp .env.example .env   # then edit locally; do not commit
```

`.env` defaults to `ALEXRAG_MODE=paper` and `ALEXRAG_KILL_SWITCH=false`.

## Ingest a Discord export

DiscordChatExporter HTML can be hundreds of MB. Run ingest on **npsecondbrain** (disk), not inside a tiny agent workspace:

```bash
uv run alexrag ingest-discord /path/to/export.html --out data/ingest/discord.jsonl --source-type journal
uv run alexrag ingest-discord /path/to/trade-log.html --out data/ingest/trade_log.jsonl --source-type trade_log
```

GitBook/playbook snapshot (configurable path):

```bash
uv run alexrag ingest-gitbook --path /path/to/gitbook-snapshot --out data/ingest/gitbook.jsonl
# or ALEXRAG_GITBOOK_PATH=/path/to/gitbook-snapshot
```

## Paper day dry run (fixtures, no network)

```bash
uv run alexrag run-paper-day --dry-run --fixtures tests/fixtures --out /tmp/proposal.json
```

Default decision clock on dry-run is the **latest fixture timestamp** so historical sample HTML is not auto-marked stale. To test fail-closed staleness, pass `--as-of` in the future.

## Kill switch

```bash
ALEXRAG_KILL_SWITCH=true uv run alexrag run-paper-day --dry-run --fixtures tests/fixtures
```

Expect `abstain=true` and `abstain_reason=kill_switch`. Exec must not run.

## Hard limits

Operator-set in config/env: `max_notional`, `max_positions`, `max_daily_loss`, `max_portfolio_dd`. Defaults of `0` fail-closed (no go-decision). These are not model-suggested sizes.

## What not to run

- Anything that would set `ALEXRAG_MODE=live` (config will reject it).
- Real Alpaca/Discord/TradingView clients — stubs only; TODOs are in code.
- Committing `.env`, paper keys, or Discord tokens.

## Tests

```bash
uv run pytest
```

Must pass offline.
