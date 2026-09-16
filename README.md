# AlexRag202609

RAG + multi-agent system that reasons like Alex (Prime Trading). **MVP scaffold is paper-only.** There is no live trading path and no go-live date — promotion is gate-driven (`docs/RISK_GATES.md`).

Locked spec: [`docs/SDD_MVP.md`](docs/SDD_MVP.md). Corpus: [`docs/CORPUS.md`](docs/CORPUS.md). Eval: [`docs/EVAL_SPEC_V0.md`](docs/EVAL_SPEC_V0.md). Paper fills: [`docs/FILL_FIDELITY_M1.md`](docs/FILL_FIDELITY_M1.md) (default `m1_realistic_v0`) and [`docs/FILL_FIDELITY_M0.md`](docs/FILL_FIDELITY_M0.md) (legacy 0bps mid). Also [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

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

Prints an audited `Proposal` JSON (`mode=paper`). `abstain` may be `true` (`paper.nav` defaults to 0 so dollar limits cannot be derived). Audit JSONL defaults to `data/audit/events.jsonl`. To exercise Exec without live keys, pass `--config config/fixture.yaml` (same operator pcts + `paper.nav`). Default fill model is `m1_realistic_v0` (`ALEXRAG_FILL_MODEL`); this **does not unlock paper**.

Eval Spec V0 golden pack (offline, no P&L):

```bash
uv run alexrag eval-golden --pack eval/golden_cases_v0.json
```

Decision-model eval (MODEL_EVAL_LOCK_V0, **capital 0**, **does not unlock paper**). Research sequence is **emit → score-model**. Orthogonal to fill receipts. `m1_realistic_v0` kills the M0 0bps-mid scar for Quant re-score only; it does **not** flip paper_authority or model CLEAR.

Emit sealed-cutoff predictions for all 48 frozen Golden cases (`eval/golden_cases_v0_frozen.json` + `docs/model_eval_lock_v0.json`). Retrieval applies `eligible_filter` over MVP ingest JSONL and excludes `banned_same_day_ids`. Context never includes `target_action`, banned fill bodies, or GT labels.

Offline CI / no Inferhub key — `--dry-run` (default) skips the network and writes abstain rows with `model_id=dry_run_abstain`:

```bash
uv run alexrag emit-model-predictions \
  --dry-run \
  --ingest data/ingest \
  --frozen eval/golden_cases_v0_frozen.json \
  --lock docs/model_eval_lock_v0.json \
  --out results/model_eval_runs
```

Live Inferhub (operator Mac; `INFERHUB_API_KEY` in env only — never committed/logged). Locked route is `cbcn` / `cbcn/glm-5.3-flash` (case-insensitive accept of `cbcn/GLM-5.3-flash`) at `https://api.inferhub.dev/v1`. Decode: `temperature=0.1`, `max_tokens=8192`, `response_format=json_object` (HTTP 400 drops the format field and retries). Parse failure or thin sealed evidence fail-closed to `abstain`. **Do not claim CLEAR.** Next live audit `run_id` **must** be `inferhub-cbcn-v3-quality` (v0/v1/v2 identical re-scores are banned):

```bash
uv run alexrag emit-model-predictions \
  --no-dry-run \
  --ingest data/ingest \
  --out results/model_eval_runs \
  --run-id inferhub-cbcn-v3-quality
```

Then score (offline):

```bash
uv run alexrag score-model \
  --predictions results/model_eval_runs/inferhub-cbcn-v3-quality/predictions.jsonl \
  --ingest data/ingest \
  --frozen eval/golden_cases_v0_frozen.json \
  --out results/model_score_runs
```

See `docs/DECISION_QUALITY_V3_QUALITY_DELTA.md` for the emitter delta vs V2 (`inferhub-cbcn-v2-quality` A–F HIT / CLEAR KILL). Flags: `--ingest`, `--frozen`, `--lock`, `--out` (run dir root), `--dry-run/--no-dry-run`, `--run-id`, `--max-messages`. Writes `results/model_eval_runs/<run_id>/predictions.jsonl` plus `run_metadata.json` (`paper_authority=false`, `capital=0`, `model_eval_clear=false`).

Smoke baseline (abstain-everywhere, no emitter):

```bash
uv run alexrag score-model \
  --predictions eval/baselines/abstain_everywhere_v0.jsonl \
  --ingest data/ingest \
  --frozen eval/golden_cases_v0_frozen.json
```

Scoring artifacts land in `results/model_eval_runs/<run_id>/` with `paper_authority=false` and `capital=0`. Ingest JSONL is used only for sealed eligible/citation checks; missing ingest still scores GT vs predictions. **Does not unlock paper. Does not claim model CLEAR.**

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
| `src/alexrag/broker` | `paper_sim` (`m1_realistic_v0` default, M0 regression) + Alpaca paper stub (`stubbed` ≠ filled) |
| `src/alexrag/llm` | Inferhub OpenAI-compatible client (`LLM_PROVIDER=inferhub`, `LLM_MODEL=cbcn/glm-5.3-flash`, `INFERHUB_PROVIDER=cbcn`; `INFERHUB_API_KEY` env only; `--dry-run` skips HTTP) |
| `src/alexrag/notify` | Discord stub (TODO: bot token) |
| `src/alexrag/eval` | Paper window, sealed cutoff, golden harness, M0/M1 fill scorers, model-eval lock scorer + sealed emitter |
| `eval/golden_cases_v0.json` | 48-case V0 pack |
| `eval/golden_cases_v0_frozen.json` | Frozen Golden-48 (sha256[:16]=`1a3cb17781211ad0`) |
| `docs/DECISION_QUALITY_PASS_V1_LOCK.md` | Research re-score gate (MVP bars A–F) |
| `docs/DECISION_QUALITY_V2_QUALITY_DELTA.md` | V2 emitter delta (formal pack `inferhub-cbcn-v2-quality`; CLEAR KILL) |
| `docs/DECISION_QUALITY_V3_QUALITY_DELTA.md` | V3 emitter delta + next live `run_id=inferhub-cbcn-v3-quality` |
| `eval/baselines/abstain_everywhere_v0.jsonl` | Smoke predictions (abstain all 48) |
| `docs/EVAL_SPEC_V0.md` | Enter/abstain/size/manage/exit + citation scoring |
| `docs/FILL_FIDELITY_M0.md` | PaperFill / FillIntent / M0 (legacy 0bps fixture mid) |
| `docs/FILL_FIDELITY_M1.md` | `m1_realistic_v0` proxy scar (`proxy_half_spread_not_alex_slippage`); does not unlock paper |
| `config/fixture.yaml` | Locked operator pcts + `paper.nav` for offline Exec |
| `src/alexrag/schemas` | `Proposal`, `FillIntent`, `PaperFill`/`FillReceipt`, `AuditEvent` |
| `docs/CORPUS.md` | MVP channels (incl. pf-update snapshots), PT timestamps, doctrine, precedence |

## TODOs (not in MVP)

- Vision model
- TradingView MCP
- Inferhub live run still needs `INFERHUB_API_KEY` on the operator Mac (`emit-model-predictions --no-dry-run`)
- Real Alpaca **paper** client (`ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY`)
- Discord bot token / webhook
- Real embedding model (replace in-memory/fake)
