# AlexRag202609

RAG + multi-agent system that reasons like Alex (Prime Trading). **MVP scaffold is paper-only.** There is no live trading path and no go-live date — promotion is gate-driven (`docs/RISK_GATES.md`).

Locked spec: [`docs/SDD_MVP.md`](docs/SDD_MVP.md). Corpus: [`docs/CORPUS.md`](docs/CORPUS.md). Eval: [`docs/EVAL_SPEC_V0.md`](docs/EVAL_SPEC_V0.md). Paper fills: [`docs/FILL_FIDELITY_M0.md`](docs/FILL_FIDELITY_M0.md). Also [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

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

GitBook/doctrine stub (fixtures only — **not** a GitBook mirror):

```bash
uv run alexrag ingest-gitbook --path tests/fixtures/gitbook --out /tmp/gitbook.jsonl
```

## Run a paper day (dry run, fixtures, no network)

```bash
uv run alexrag run-paper-day --dry-run --fixtures tests/fixtures --out /tmp/proposal.json
```

Prints an audited `Proposal` JSON (`mode=paper`). `abstain` may be `true` (default hard limits are fail-closed at 0). Audit JSONL defaults to `data/audit/events.jsonl`. To exercise Exec/M0 without live keys, pass `--config config/fixture.yaml` (non-zero operator limits; `config/default.yaml` stays at 0).

Eval Spec V0 golden pack (offline, no P&L):

```bash
uv run alexrag eval-golden --pack eval/golden_cases_v0.json
```

Kill switch drill:

```bash
ALEXRAG_KILL_SWITCH=true uv run alexrag run-paper-day --dry-run --fixtures tests/fixtures
```

## Layout

| Path | What |
| --- | --- |
| `src/alexrag/ingest` | Discord HTML (streaming, PT, inherited timestamps) + doctrine stub |
| `src/alexrag/vision_caption` | Vision stub (TODO: Mac Studio VLM) |
| `src/alexrag/rag` | Chunking, fake embeddings, precedence retrieve |
| `src/alexrag/agents` | Regime, Setup, Risk, Exec paper stub, Auditor |
| `src/alexrag/broker` | `paper_sim` M0 + Alpaca paper stub (`stubbed` ≠ filled) |
| `src/alexrag/notify` | Discord stub (TODO: bot token) |
| `src/alexrag/eval` | Paper window, sealed cutoff, golden harness, M0 fill scorer |
| `eval/golden_cases_v0.json` | 48-case V0 pack |
| `docs/EVAL_SPEC_V0.md` | Enter/abstain/size/manage/exit + citation scoring |
| `docs/FILL_FIDELITY_M0.md` | PaperFill / FillIntent / M0 (0bps fixture mid) |
| `config/fixture.yaml` | Non-zero hard_limits + `paper.nav` for offline Exec |
| `src/alexrag/schemas` | `Proposal`, `FillIntent`, `PaperFill`/`FillReceipt`, `AuditEvent` |
| `docs/CORPUS.md` | Channel counts, precedence, doctrine, golden-case pointer |

## TODOs (not in MVP)

- Vision model
- TradingView MCP
- Real Alpaca **paper** client
- Discord bot token / webhook
- Real embedding model (replace in-memory/fake)
