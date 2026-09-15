# Fill fidelity M0 (paper-only)

Quant-facing contract for paper fills. There is **no live path** and **no P&L gate**.

## Receipt (`PaperFill` / `FillReceipt`)

| Field | Notes |
| --- | --- |
| `fill_ts` | Mark time (next fixture bar ts on acked M0; decision clock on skip/stub) |
| `fill_px` | Next fixture **mid** when acked; `null` when not filled |
| `qty_filled` / `qty_left` | `acked` fills the full intent qty; skip/stub leave qty_filled=0 |
| `status` | `acked` \| `partial` \| `rejected` \| `skipped` \| `stubbed` |
| `venue` | `paper_sim` (M0) or `alpaca_paper` (no-keys stub) |
| `latency_ms` | `fill_ts - proposal.decision_clock` in milliseconds |
| `intent_id` / `proposal_id` | Bind receipt to intent and proposal |
| `filled` | **`stubbed` ≠ filled.** Also false for `skipped` / `rejected` |
| `scar_bps` | **Always 0** under M0. Label: `fixture_mid_0bps_not_alex_slippage` |

## Fill model M0

M0 = mark-to-**next-available fixture bar/mid** after `decision_clock`, with **0bps** scar **labeled as a fixture mark**. Do **not** invent Alex slippage, spread, or limit-price improvement.

- A bar with `ts <= decision_clock` is not a mark.
- No next bar → `status=skipped` (not a fill).
- `alpaca_paper` without keys/network → `status=stubbed` (not a fill), even if an M0 bar exists.

## FillIntent (Exec mapping)

When `proposal.abstain=false`, Exec must not leave `side=None` / `notional=0` / `qty=None`. Mapping is deterministic from the sealed proposal:

- `ticker` required (first proposal ticker)
- `side` / optional `limit_px` / optional `invalidation` copied **only** from citations with `timestamp < decision_clock`
- `order_type=limit` iff a sealed limit px is present; otherwise `market`
- `size_ner_pct → notional = min(paper_nav * ner/100, max_notional)`; `qty = notional / ref_px`
- `ref_px` = sealed limit if present, else next fixture mid
- copy `decision_clock`
- if any required field is missing, Exec **skips** (`intent.abstain=true`) rather than emitting a holey go intent

## Fixture config

`config/default.yaml` keeps `hard_limits.* = 0` and `paper.nav = 0` (fail-closed).

`config/fixture.yaml` sets operator-owned non-zero limits + `paper.nav` and points `paper.bars_path` at `tests/fixtures/m0/bars.json` so cleared proposals can exercise Exec **without live keys**.

Sealed replay cases: `tests/fixtures/m0/cases/*.json` (decision_ts, proposal snapshot, FillIntent, expected PaperFill). Offline scorer: `alexrag.eval.fill_m0` (intent↔receipt, sealed clock, audit completeness). **P&L is not scored.**
