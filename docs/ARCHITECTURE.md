# Architecture

AlexRag202609 MVP is a **local, paper-only** pipeline. There is no service mesh, no live broker adapter, and no calendar-driven promotion.

```text
 DiscordChatExporter HTML          GitBook/playbook snapshot
            │                                  │
            ▼                                  ▼
   ingest.discord_html                 ingest.gitbook (stub)
            │                                  │
            └──────────── JSONL ───────────────┘
                           │
                           ▼
              vision_caption.stub (TODO VLM)
                           │
                           ▼
              chunk + source tags + FakeEmbeddingProvider
                           │
                           ▼
              retrieve (trade_log > journal/report > gitbook)
                           │
                           ▼
         ┌─────────┐   ┌─────────┐   ┌─────────┐
         │ Regime  │ → │  Setup  │ → │  Risk   │
         └─────────┘   └─────────┘   └────┬────┘
                                          │
                          abstain? ──yes──┤── Proposal JSON + AuditEvent
                                          │ no
                                          ▼
                                 Exec paper stub
                                 (Alpaca TODO)
                                          │
                                          ▼
                                      Auditor
```

## Runtime pieces

| Piece | Implementation now | Later |
| --- | --- | --- |
| Config | `config/default.yaml` + `ALEXRAG_*` env | same, still paper-only until a future spec |
| Embeddings | `FakeEmbeddingProvider` (hash vectors) | local model on Mac Studio |
| Index | in-memory | durable vector store |
| Broker | `AlpacaPaperBroker.submit_paper` stub | Alpaca **paper** API only |
| Notify | log stub | Discord webhook/bot |
| Charts | `TradingViewMCP` raises `NotImplementedError` | MCP client; still no invented numbers |
| Audit | JSONL file sink | same contract, maybe append-only store |

## Control flow (`run-paper-day`)

1. Parse settings (`mode` must be `paper`).
2. Open audit sink — if this fails, abstain (`missing_audit`).
3. If `kill_switch`, abstain.
4. Retrieve with source precedence.
5. Stale / low-confidence / empty → abstain.
6. Regime → Setup → Risk.
7. Exec paper stub only when `abstain=false`.
8. Auditor may force abstain if the trail is incomplete.
9. Write `Proposal` JSON.

## Schema center of gravity

Risk does not call the broker. It only maps a `Proposal`:

- citations + timestamps
- abstain / reason
- confidence
- size_ner_pct
- regime
- tickers
- decision_clock
- hard_limits_snapshot

Exec consumes a cleared proposal and produces a `FillIntent(mode="paper")`.

## Fail-closed surfaces

| Signal | Result |
| --- | --- |
| Stale feed | `abstain_reason=stale_feed` |
| Missing audit | `abstain_reason=missing_audit` |
| Low retrieval confidence | `abstain_reason=low_retrieval_confidence` |
| Kill switch | `abstain_reason=kill_switch` |
| Unconfigured hard limits | `abstain_reason=hard_limits_unconfigured` |

## What is intentionally missing

No HTTP clients in the paper dry-run path. No `live` enum values except as rejected input. No indicator engine.
