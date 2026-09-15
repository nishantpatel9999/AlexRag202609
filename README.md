# AlexRag202609

RAG + multi-agent system that reasons like Alex (Prime Trading). **MVP scaffold is paper-only.** There is no live trading path and no go-live date — promotion is gate-driven (`docs/RISK_GATES.md`).

Locked spec: [`docs/SDD_MVP.md`](docs/SDD_MVP.md). Also see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/RUNBOOK.md`](docs/RUNBOOK.md) (Mac Studio vs npsecondbrain).

## Setup

```bash
uv sync --extra dev
cp .env.example .env   # local only; never commit secrets
```

## Test (offline)

```bash
uv run pytest
```

## Ingest fixture (Discord HTML → JSONL)

```bash
uv run alexrag ingest-discord tests/fixtures/discord/sample.html --out /tmp/discord.jsonl
```

GitBook/playbook snapshot stub:

```bash
uv run alexrag ingest-gitbook --path tests/fixtures/gitbook --out /tmp/gitbook.jsonl
```

## Run a paper day (dry run, fixtures, no network)

```bash
uv run alexrag run-paper-day --dry-run --fixtures tests/fixtures --out /tmp/proposal.json
```

Prints an audited `Proposal` JSON (`mode=paper`). `abstain` may be `true` (default hard limits are fail-closed at 0). Audit JSONL defaults to `data/audit/events.jsonl`.

Kill switch drill:

```bash
ALEXRAG_KILL_SWITCH=true uv run alexrag run-paper-day --dry-run --fixtures tests/fixtures
```

## Layout

| Path | What |
| --- | --- |
| `src/alexrag/ingest` | Discord HTML (streaming) + GitBook stub |
| `src/alexrag/vision_caption` | Vision stub (TODO: Mac Studio VLM) |
| `src/alexrag/rag` | Chunking, fake embeddings, precedence retrieve |
| `src/alexrag/agents` | Regime, Setup, Risk, Exec paper stub, Auditor |
| `src/alexrag/broker` | Alpaca paper stub (TODO: real paper API) |
| `src/alexrag/notify` | Discord stub (TODO: bot token) |
| `src/alexrag/eval` | Paper window + citation/abstain helpers |
| `src/alexrag/schemas` | `Proposal`, `FillIntent`, `AuditEvent` |
| `config/default.yaml` | `mode=paper`, kill switch, hard limits |

## TODOs (not in MVP)

- Vision model
- TradingView MCP
- Real Alpaca **paper** client
- Discord bot token / webhook
- Real embedding model (replace in-memory/fake)
