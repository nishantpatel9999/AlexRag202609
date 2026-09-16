# Runbook — Mac Studio vs npsecondbrain

Paper-only MVP. Do not point this stack at live brokerage endpoints.

## Roles

| Host | Role |
| --- | --- |
| **Mac Studio** | Future local models (vision caption, embeddings). Cursor **API for Cursor** (Standard Agents) listening on **:8794**. Heavy GPU/NPU work stays here. |
| **npsecondbrain (VPS)** | Orchestrator, Discord HTML ingest of **fixtures** (large Mac exports later), paper loop, audit JSONL. Tunnel **VPS :8791 → Mac :8794** for Cursor API bridge. |

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

GitBook/playbook snapshot stub:

```bash
uv run alexrag ingest-gitbook --path tests/fixtures/gitbook --out /tmp/gitbook.jsonl
# Fixture only. No local GitBook mirror. Doctrine = live GitBook +
# PRIMETRADING_RULEBOOK_DISTILLATION.md + PrimeTrading_Ebook.pdf (docs/CORPUS.md).
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

Expect `abstain=true` and `abstain_reason=kill_switch_fail`. Exec must not run.

## Hard limits

Nishant-locked operator values (config/env):

| Limit | Value | Runtime dollars |
| --- | --- | --- |
| `max_positions` | 15 | n/a |
| `max_daily_loss_pct` | 10% of equity | `paper.nav * 0.10` |
| `max_portfolio_dd` | 25% of equity | compared as a fraction against `paper_book.portfolio_dd` |
| `max_notional_pct` | 150% of paper equity | `paper.nav * 1.5` |
| `notional_breach_policy` | `pro_rata_trim_for_new_entry` | If a new entry/buy would push **gross** notional above 150% of equity, **pro-rata trim all open positions** enough to make room for the new size, then enter. The new entry is not shrunk to leftover room. See `docs/RISK_GATES.md`. |

`paper.nav` defaults to `0` (cannot derive dollars → `hard_limits_unconfigured`). Risk enforces daily loss and portfolio DD against `paper_book`. These are not model-suggested sizes. `sessions`/`decisions` are diagnostics, not a hard floor (`docs/RISK_GATES.md`). Offline Exec replay uses `config/fixture.yaml` (same pcts + `paper.nav`); default fill model is `m1_realistic_v0` (`docs/FILL_FIDELITY_M1.md`) and does not unlock paper. Legacy M0: `docs/FILL_FIDELITY_M0.md`.

## LLM (always-on)

Inferhub host: `https://api.inferhub.dev/v1` (`INFERHUB_BASE_URL`). **LLM_PROVIDER=inferhub**. **Upstream `INFERHUB_PROVIDER=cbcn` only** — do not route to any other Inferhub upstream. Model id: **`cbcn/glm-5.3-flash`** (`LLM_MODEL`, provider prefix; accepts `cbcn/GLM-5.3-flash` case-insensitively and normalizes). Client: `alexrag.llm.inferhub.InferhubClient` POSTs OpenAI-compatible `{base_url}/chat/completions` (request body always includes `provider=cbcn`, canonical `model=cbcn/glm-5.3-flash`, `temperature=0.1`, `max_tokens=8192`, and `response_format={"type":"json_object"}`; HTTP 400 on the format field retries without it). Secret via `INFERHUB_API_KEY` env only — never in git, never logged. Without a key the client returns a local stub (no HTTP). Decision-model emit: `alexrag emit-model-predictions` (default `--dry-run` for offline CI) then `alexrag score-model`. Live emit needs the key on the operator Mac (`--no-dry-run`). **Next live `run_id`: `inferhub-cbcn-v5-gc29`.** Capital 0; does not unlock paper; does not claim CLEAR. See `docs/DECISION_QUALITY_V5_GC29_SCAR.md`.

**GC-29 scar rule:** same-morning sealed no-trade / no-focuslist language beats stale (older-than-1-day / older-than-same-session) ticker alerts. Emitter fail-closed `abstain` with `conflict_no_trade_plan_vs_stale_setup` unless there is contemporaneous enter evidence. Do not peek GT / banned fills. GC-15 stays honest thin abstain. v4 quality pack stands; this is a paper-block scar close (match may dip if GC-29 was a stale-alert enter PASS). Paper still KILL until Risk drills.

## Alpaca (paper only)

Env: `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY` (operator key pair #2 — do not hardcode). Broker remains a stub (no network); `stubbed ≠ filled`. Live endpoints are not implemented.

## What not to run

- Anything that would set `ALEXRAG_MODE=live` (config will reject it).
- Alpaca/Discord/TradingView live clients — still stubs; TODOs are in code.
- `emit-model-predictions --no-dry-run` without `INFERHUB_API_KEY` on the operator Mac.
- Committing `.env`, Inferhub/Alpaca paper keys, or Discord tokens.

## Tests

```bash
uv run pytest
```

Must pass offline.
