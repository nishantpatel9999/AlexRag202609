# Fill fidelity M1 (paper-only)

Quant-facing contract for **realistic paper fills** (`m1_realistic_v0`). There is **no live path**, **no P&L gate**, and **no paper unlock**. Capital remains **0**. Decision-model CLEAR stays **KILL** and orthogonal.

M1 kills the M0 0bps-mid scar (`fixture_mid_0bps_not_alex_slippage`) so Quant can re-score receipts. It does **not** claim Alex-calibrated slippage.

Legacy M0 remains selectable for regression: `docs/FILL_FIDELITY_M0.md`.

## Modes

| `fill_model` / `ALEXRAG_FILL_MODEL` | Behavior | Scar |
| --- | --- | --- |
| `m0_fixture_mid_0bps` (alias `M0`) | Next fixture **mid** after `decision_clock` | `scar_bps=0`, label `fixture_mid_0bps_not_alex_slippage` |
| `m1_realistic_v0` (**default**) | Next-bar **open** if present, else mid; then adverse half-spread + impact stub | `scar_bps=6` documented proxy, label `proxy_half_spread_not_alex_slippage` |

Default for the FillIntent→PaperFill path is `m1_realistic_v0` (`config/default.yaml`, `config/fixture.yaml`, env `ALEXRAG_FILL_MODEL`). M0 pack replay still **forces** `m0_fixture_mid_0bps`.

## Documented M1 proxy (not Alex slippage)

```
half_spread_bps  = 5.0     # or bar.spread_bps / 2 when the fixture provides spread_bps
impact_stub_bps  = 1.0     # size-agnostic stub
scar_bps         = 6.0     # half-spread + impact
scar_label       = proxy_half_spread_not_alex_slippage
```

Fill price (acked `paper_sim`):

1. Next fixture bar with `ts > decision_clock` (same sealed clock as M0). Past bars are not marks.
2. Mark = `open` if `open > 0`, else `mid`.
3. Buy pays `mark * (1 + scar_bps / 10000)`; sell receives `mark * (1 - scar_bps / 10000)`.

Example: mid `125`, no open → buy `125.075`. Open `126` → buy `126.0756`.

This is a **labeled proxy**. Do **not** treat it as measured quotes or as Alex slippage.

## Receipt rules (unchanged except scar)

| Field | Notes |
| --- | --- |
| `fill_ts` | Next fixture bar ts on acked; decision clock on skip/stub |
| `fill_px` | M1 mark ± scar when acked; `null` when not filled |
| `status` | `acked` \| `partial` \| `rejected` \| `skipped` \| `stubbed` |
| `filled` | **`stubbed` ≠ filled.** Also false for `skipped` / `rejected` |
| `fill_model` | Canonical `m1_realistic_v0` (or `m0_fixture_mid_0bps` on the legacy path) |
| `scar_bps` / `scar_label` | Non-zero + `proxy_half_spread_not_alex_slippage` on acked M1. Never `fixture_mid_0bps_not_alex_slippage` on an M1 fill. |
| `venue` | `paper_sim` or `alpaca_paper` (no-keys/no-network stub) |

- No next bar → `status=skipped` (not a fill). Scar is 0 because nothing filled.
- `alpaca_paper` without keys/network → `status=stubbed` (not a fill), even if an M1 bar exists. Label `stubbed_not_filled`. **No network unless stub.**

Intent mapping (ticker / side / notional / qty / sealed limit) is unchanged. Sizing still uses next-fixture **mid** (or sealed limit) as `ref_px`. Scar is applied only on the receipt.

## What M1 does **not** do

- Does **not** unlock paper (`paper_authority=false`).
- Does **not** flip decision-model CLEAR (remains KILL).
- Does **not** enable live submit / capital > 0.
- Does **not** invent Alex slippage, limit-price improvement, or a calibrated impact model.

## Fixtures / scorer

Sealed replay: `tests/fixtures/m1/cases/*.json`. Offline scorer: `alexrag.eval.fill_m1`.

The scorer checks intent↔receipt, sealed clock, audit completeness, **acked scar ≠ 0bps mid claim**, stubbed≠filled. **P&L is not scored.**

## Quant re-score

```bash
uv run pytest tests/test_fill_fidelity.py -q
```

Programmatic:

```python
from alexrag.eval.fill_m1 import load_m1_cases, score_m1_pack
summary = score_m1_pack(load_m1_cases(), audit_dir)  # paper_authority=false, capital=0
```

M0 regression pack is unchanged: `alexrag.eval.fill_m0` / `tests/fixtures/m0/cases/`.
