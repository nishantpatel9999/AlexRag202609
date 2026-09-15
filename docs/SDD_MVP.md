# AlexRag202609 — MVP Software Design Document

Locked product/architecture spec for the **paper-only** scaffold. This document is the source of truth for MVP scope. Later phases may add models and brokers; they must not silently add a live trading path.

## 1. Purpose

AlexRag202609 is a RAG + multi-agent system that **reasons like Alex (Prime Trading)**: it retrieves cited evidence from trade logs, journals/reports, and the GitBook/playbook, then runs a gated decision pipeline.

MVP goal: an **offline-runnable scaffold** that can ingest Discord HTML, index fixtures, run `run-paper-day`, and emit an audited `Proposal` JSON (often `abstain=true`). It is not a live system.

## 2. Non-goals (MVP)

- No **live** trading paths, live Alpaca endpoints, or live mode in config.
- Do **not** invent trading indicator numbers (no synthesized RSI/VWAP/levels). Agents may only copy values that already appear in retrieved citations.
- No Discord bot, no real Alpaca submit, no vision model, no TradingView MCP client.
- No calendar “go-live” date. Paper→live is **gate-driven** (see `docs/RISK_GATES.md`).

## 3. Operating modes

| Mode | MVP |
| --- | --- |
| `paper` | Default and only allowed value |
| `live` | Rejected at config parse time |

Kill switch: when engaged, the orchestrator abstains immediately and must not call Exec.

## 4. Package map

| Package | Role |
| --- | --- |
| `alexrag.ingest` | DiscordChatExporter HTML → JSONL; GitBook snapshot stub |
| `alexrag.vision_caption` | Image caption stub (TODO: Mac Studio VLM) |
| `alexrag.rag` | Chunking, metadata tags, embedding provider interface, in-memory index |
| `alexrag.agents` | Regime → Setup → Risk → Exec (paper stub) → Auditor |
| `alexrag.broker.alpaca_paper` | Paper broker stub (TODO: real Alpaca paper API) |
| `alexrag.notify.discord` | Notify stub (TODO: bot token / webhook) |
| `alexrag.eval` | Replay/citation/abstain metrics; paper-window helper |
| `alexrag.marketdata.tradingview_mcp` | Explicit NotImplemented stub |
| `alexrag.schemas` | `Proposal`, `FillIntent`, `AuditEvent`, `IngestedMessage` |

## 5. Data flow

1. **Ingest** Discord HTML (streaming) and optional GitBook snapshot directory → JSONL records `{id, ts, author, text, attachment_paths}`.
2. **Caption stub** records a placeholder for each attachment path (no model, no network).
3. **Chunk** text with source tags: `trade_log | journal | report | gitbook`.
4. **Embed** with the `EmbeddingProvider` interface. MVP: deterministic **fake** in-memory vectors for tests.
5. **Retrieve** with precedence **trade_log > journal/report > gitbook**.
6. **Agents:** Regime → Setup → Risk → (if not abstain) Exec paper stub → Auditor.
7. **Audit log** JSONL. If the audit sink is missing or unwritable → **fail-closed abstain**.
8. Emit `Proposal` JSON. Exec never runs in live mode (there is no live mode).

## 6. Retrieval rules

- Cascading fill: take hits from `trade_log` first, then `journal`, then `report`, then `gitbook`.
- `retrieval_confidence` below `min_confidence` (default `0.2` for the fake embedding provider) → abstain (`low_retrieval_confidence`).
- Newest citation timestamp older than `stale_after_hours` relative to `decision_clock`, or **no timestamps** → abstain (`stale_feed`).
- Empty index / no hits → abstain.

## 7. Agent contracts

### Regime

Qualitative label copied from citation text if present (`trend_day`, `trend`, `range`, `chop`, `squeeze`, `inside_day`). Otherwise `unknown` (Risk abstains). Must not invent a regime from “feel” or from market data APIs.

### Setup

Builds a `Proposal` from retrieved chunks:

- `tickers` — only `$TICKER` tokens found in citations
- `size_ner_pct` — only if a NER percent already appears in citations; else `0`
- `citations[]` — excerpt, `source_type`, `source_id`, **timestamp**, path
- `confidence` / `retrieval_confidence`
- `decision_clock`

### Risk

Maps the proposal onto coded hard limits and fail-closed gates. Abstains on:

- kill switch
- missing citations
- citations without timestamps
- low retrieval confidence
- no tickers in citations
- unknown regime
- unconfigured hard limits (`max_notional` or `max_positions` ≤ 0)
- missing audit (orchestrator-level)

Hard-limit fields (present even while Exec is a stub):

- `max_notional`
- `max_positions`
- `max_daily_loss`
- `max_portfolio_dd`

Values are **operator-owned**. Defaults of `0` block any go-decision. They are not research outputs.

### Exec

Paper stub only. Records a `FillIntent` with `mode="paper"` and **does not send** an order. TODO: Alpaca paper API.

### Auditor

Verifies required audit events exist, citations are present, and fill intent (if any) is paper. On failure, forces `abstain=true` and clears size.

## 8. Schemas (Risk-mappable `Proposal`)

`Proposal` must include:

- `citations` (each with `timestamp` when available)
- `abstain` / `abstain_reason`
- `confidence`
- `size_ner_pct`
- `regime`
- `tickers`
- `decision_clock`

`FillIntent` allows `mode="paper"` only. `AuditEvent` is append-only JSONL.

## 9. Ingest

### Discord HTML

CLI consumes **DiscordChatExporter-style** HTML:

- `div.chatlog__message-container[data-message-id]`
- `span.chatlog__author`
- `time[datetime]`
- `.chatlog__content` / `.chatlog__markdown-preserve`
- `.chatlog__attachment` `href` / `img src`

The parser is **large-file friendly**: it feeds the HTML parser in chunks and writes JSONL incrementally. It must not download remote attachments.

### GitBook / playbook

Configurable local snapshot path (`paths.gitbook_snapshot` / `ALEXRAG_GITBOOK_PATH`). Walks `.md`/`.html`/`.txt`. Stub for a future export sync. No GitBook API in MVP.

## 10. Fail-closed policy

If any of the following are true, the system **abstains** (does not Exec):

- kill switch on
- stale feed
- missing or unwritable audit log
- retrieval confidence below threshold
- citations lack timestamps
- hard limits unconfigured
- non-paper mode requested (config error)

Fail-open is not supported in MVP even if `fail_closed=false` is set.

## 11. Promotion

Paper→live is **not** dated. See `docs/RISK_GATES.md`. Default paper window: **≥ 60 sessions or 100 decisions**, plus replay / citation / abstain metrics. This repository still has **no live path** after the window is met.

## 12. Topology

- **Mac Studio**: local models (future vision + embeddings), Cursor “API for Cursor” bridge.
- **npsecondbrain (VPS)**: orchestrator, Discord HTML ingest, paper loop; tunneled LLM access.

Details: `docs/RUNBOOK.md`. Secrets never go in git (`.env.example` only).

## 13. TODOs (explicit, out of MVP)

- Vision model on Mac Studio (`alexrag.vision_caption`)
- TradingView MCP (`alexrag.marketdata.tradingview_mcp`)
- Real Alpaca **paper** client (`alexrag.broker.alpaca_paper`)
- Discord bot token / webhook (`alexrag.notify.discord`)
- Real embedding model (replace `FakeEmbeddingProvider`)

## 14. Testing bar

Offline unit tests must pass with **no network calls**. `run-paper-day --dry-run` on fixtures must print a valid `Proposal` JSON (may `abstain=true`) and write audit JSONL.
