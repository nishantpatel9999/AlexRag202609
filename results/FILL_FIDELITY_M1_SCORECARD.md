# Fill fidelity M1 scorecard (Quant)

Paper/shadow scoring only. **No live trading. No invented Alex slippage. P&L is not scored.**

This is a **labeled proxy**, not Alex-calibrated slippage. **Capital 0. `paper_authority=false`. NOT a paper unlock.** Orthogonal to decision-model **CLEAR KILL**.

| Field | Value |
| --- | --- |
| Date scored (UTC) | 2026-09-16 |
| Repo | AlexRag202609 |
| Branch scored | `main` (after PR #15 merge) |
| Main tip SHA | `2226ea82c1a4d1d5a1678b348f9cc054e57f17de` |
| Main tip subject | Merge pull request #15 from nishantpatel9999/cursor/realistic-paper-fill-m1-814e |
| Fill model | **`m1_realistic_v0`** (default FillIntent→PaperFill path) |
| Capital | **0** (`config/default.yaml` `paper.nav = 0.0`) |
| `paper_authority` | **false** |
| Paper-authority unlock | **No. This scorecard is not an unlock.** |
| Decision-model CLEAR | **KILL** (orthogonal; this pack does not score MODEL_EVAL_LOCK_V0) |
| Live path | None (confirmed: `mode=paper` only; no Alpaca live URLs in `src/` / `docs/` / `config/`; no keys used) |

## Method

Contract: `docs/FILL_FIDELITY_M1.md`, `PaperFill` / `FillIntent` schemas, sealed fixtures under `tests/fixtures/m1/cases/`.

Pass criteria applied by `alexrag.eval.fill_m1.score_m1_case`:

- `stubbed` ≠ filled (`filled=False`, `qty_filled=0`)
- sealed `decision_clock` (citations `<` clock; acked fill uses next bar **after** clock, never a past mid/open)
- acked M1 scar **≠ 0bps mid claim**: `scar_bps=6`, label `proxy_half_spread_not_alex_slippage` (never `fixture_mid_0bps_not_alex_slippage` on an M1 fill)
- non-fills: `filled=false`, `scar_bps=0`, must not claim the M0 0bps-mid label
- intent↔receipt field match + audit completeness
- **P&L is not a scoring axis**; scorer sets `paper_authority=false`, `capital=0`, `unlocks_paper=false`

There is **no M1 CLI**. Scoring used:

1. `uv sync --extra dev` (local install; no Alpaca env vars set)
2. `uv run pytest tests/test_fill_fidelity.py -q`
3. Offline `from alexrag.eval.fill_m1 import load_m1_cases, score_m1_pack` then `score_m1_pack(load_m1_cases(), audit_dir)` against all `tests/fixtures/m1/cases/*.json`
4. M0 regression: `load_m0_cases()` + `score_m0_pack()` (pack still **forces** `m0_fixture_mid_0bps`)

No network. No real Alpaca keys. Fixture `paper.nav=100000` in sealed cases / `config/fixture.yaml` is **offline Exec replay only**, not operator capital.

## Pytest (offline)

| Command | Result |
| --- | --- |
| `uv run pytest tests/test_fill_fidelity.py -q` | **11 passed** |
| Related: `tests/test_no_live.py`, `tests/test_schemas.py`, `tests/test_operator_lock.py`, `tests/test_orchestrator.py` (with fill-fidelity) | **38 passed** |
| Full offline `uv run pytest -q` | **101 passed** |

Schema / default-path unit checks inside `test_fill_fidelity.py` (not fixture replay, still contract):

- `stubbed` + `filled=True` → `ValidationError`
- M0 `PaperFill` with `scar_bps != 0` → `ValidationError` (“do not invent Alex slippage”)
- M1 acked with `scar_bps=0` or M0 scar label → `ValidationError`
- default `paper.nav == 0.0` → `max_notional_dollars() == 0.0`, `hard_limits_ready() is False`
- default `paper.fill_model == m1_realistic_v0` (**M0 0bps mid scar killed on the default path**)

## Case table

Replay actuals from `replay_m1_case` match expected `PaperFill.status` on every sealed case. `receipt_match` uses `math.isclose` (`abs_tol=1e-9`); acked mid fill `125 * (1 + 6/10000)` is reported as **125.075**.

| id | expected status | actual status | filled (exp / act) | pass/fail | scar_bps / scar_label notes |
| --- | --- | --- | --- | --- | --- |
| `m1_acked_long` | `acked` | `acked` | true / true | **PASS** | Next NVDA bar after `2026-09-15T18:15:00Z` is mid `125.0` at `18:16Z` (no open). Past mid `99.0` unused. Buy mark ± proxy → `fill_px=125.075`. **`scar_bps=6`**, label **`proxy_half_spread_not_alex_slippage`**. `qty_filled=2`, `latency_ms=60000`. Venue `paper_sim`. Not Alex slippage. |
| `m1_acked_next_open` | `acked` | `acked` | true / true | **PASS** | Next-bar **open 126** is the mark (mid 125 unused; past open 98 unused) then +6bps → `fill_px=126.0756`. **`scar_bps=6`**, label **`proxy_half_spread_not_alex_slippage`**. Same clock/qty as acked long. |
| `m1_abstain_skipped` | `skipped` | `skipped` | false / false | **PASS** | Abstain `unknown_regime` → skip, not fill. Next bar ignored. `fill_px=null`, `qty_filled=0`, `skip_reason=unknown_regime`. Non-fill `scar_bps=0`; label is the M1 proxy name, **not** `fixture_mid_0bps_not_alex_slippage`. Audit includes `exec_skipped_abstain`. |
| `m1_stubbed_alpaca` | `stubbed` | `stubbed` | false / false | **PASS** | Same go-intent shape as acked long. `alpaca_paper` without keys → **`stubbed` ≠ filled** even though an M1 bar exists. `fill_px=null`, `qty_filled=0`, `qty_left=2`, `scar_bps=0`, **`scar_label=stubbed_not_filled`**, `skip_reason=alpaca_paper_no_keys`. No network. |
| `m1_no_bar_skipped` | `skipped` | `skipped` | false / false | **PASS** | Complete limit go-intent (`ref_px` sealed 125). Only bar is **at or before** clock (`18:00` vs `18:15`) → `no_next_fixture_bar`. Past open/mid not used as a mark. `filled=false`, `scar_bps=0`. |

All scorer axes (`intent_match`, `receipt_match`, `intent_receipt_consistency`, `sealed_clock`, `audit_completeness`, `m1_nonzero_scar`, `no_pnl`, `paper_not_unlocked`) passed on every case.

## Aggregate

| Metric | Value |
| --- | --- |
| Cases in pack | 5 (files `01`–`05` under `tests/fixtures/m1/cases/`; ids as above) |
| Passed | 5 |
| Failed | 0 |
| Pass rate | **5/5 = 100%** |
| `pnl_scored` | `false` |
| `fill_model` | `m1_realistic_v0` |
| `scar_label_acked` | `proxy_half_spread_not_alex_slippage` |
| `paper_authority` | `false` |
| `capital` | `0` |
| `unlocks_paper` | `false` |

Statuses covered: `acked`, `skipped`, `stubbed` (no `partial` / `rejected` fixtures in this sealed pack).

## Scars (labeled proxy — not Alex slippage)

| Scar | Observed |
| --- | --- |
| `proxy_half_spread_not_alex_slippage` `scar_bps=6` on acked | Both acked receipts: `scar_bps == 6.0`, label `proxy_half_spread_not_alex_slippage`. Documented as half-spread 5bps + impact stub 1bps. **Labeled proxy, not Alex-calibrated slippage.** Buy pays mark × (1 + 6/10000). |
| `stubbed` ≠ filled | `m1_stubbed_alpaca`: `status=stubbed`, `filled=False`, `qty_filled=0`, `scar_label=stubbed_not_filled`. Schema rejects stubbed-as-filled. |
| M0 0bps mid scar **killed for default path** | Default config `paper.fill_model=m1_realistic_v0`. Unit path: mid 125 → M1 `125.075` (`scar_bps=6`), not M0 mid 125 / `scar_bps=0` / `fixture_mid_0bps_not_alex_slippage`. M1 acked receipts never carry the M0 0bps-mid label. |
| Paper only | All intents `mode=paper`. Venues `paper_sim` or `alpaca_paper` stub. Default config `mode=paper`. No live Alpaca URL in `src/` / `docs/` / `config/`. No keys present during scoring. |

## M0 regression (pack not broken)

M1 default does **not** rewrite the M0 sealed pack. M0 replay still **forces** `m0_fixture_mid_0bps`.

| Check | Result |
| --- | --- |
| `uv run pytest tests/test_fill_fidelity.py::test_m0_sealed_replay_pack` | included in **11 passed** |
| `score_m0_pack(load_m0_cases(), audit_dir)` | **5/5 passed**, `pnl_scored=false`, `fill_model=M0` |
| Spot replay `m0_acked_long` | `status=acked`, `fill_px=125.0` (fixture mid, not 125.075), `scar_bps=0`, label `fixture_mid_0bps_not_alex_slippage`, `fill_model=m0_fixture_mid_0bps` |

M0 cases still green: `m0_acked_long`, `m0_abstain_skipped`, `m0_stubbed_alpaca`, `m0_no_bar_skipped`, `m0_limit_citation`.

## Capital 0 — not a paper-authority unlock — orthogonal to model CLEAR KILL

- Default operator capital is **`paper.nav = 0`**. Dollar notional / daily-loss cannot be derived (`hard_limits_ready() is False` → Risk fail-closed `hard_limits_unconfigured` on the default path).
- Sealed M1 cases and `config/fixture.yaml` set nav **only** so Exec can be replayed offline. That is fixture scaffolding, not an authority to trade paper size.
- **`paper_authority=false`.** This scorecard does **not** unlock paper. It does not set capital, enable Alpaca submit, or change `mode`.
- Decision-model **CLEAR remains KILL** and is **orthogonal**. Quant M1 receipt scoring is not a MODEL_EVAL_LOCK_V0 CLEAR attempt and does not flip `gates.model_eval_clear`.
- M1 kills the M0 0bps-mid scar so Quant can re-score receipts. It does **not** claim measured quotes or Alex slippage.

## Blockers for Risk / Red

M1 Quant fill-fidelity on this sealed pack is **green (5/5)**. That is **not** a Risk/Red promotion and **not** a paper unlock.

Still blocking / out of scope for Risk/Red:

1. **Capital 0** on default config — Risk remains fail-closed for dollar limits until an operator sets nav via an approved paper path (not this PR).
2. **`paper_authority=false` — not a paper-authority unlock** — no Exec live-submit, no Alpaca paper client, no capital mandate.
3. **Model CLEAR KILL** — orthogonal; do not treat M1 5/5 as decision-model CLEAR.
4. Alpaca paper without keys/network is **correctly stubbed**; a real paper submit client is still TODO and must not be treated as filled.
5. Promotion review in `docs/RISK_GATES.md` still requires replay stability, citation faithfulness, hindsight coverage, abstain-reason metrics, and fail-closed drills. M1 is one fidelity input, not the whole gate.
6. **No P&L gate** and none was computed. Do not treat 100% M1 replay as a win-rate or as an Alex slippage model.
7. Sealed pack has no `partial` / `rejected` receipts; Risk should not assume those statuses are exercised.

## Scorer dump (verbatim keys from `score_m1_pack`)

```json
{
  "n_cases": 5,
  "n_passed": 5,
  "pnl_scored": false,
  "fill_model": "m1_realistic_v0",
  "scar_label_acked": "proxy_half_spread_not_alex_slippage",
  "paper_authority": false,
  "capital": 0,
  "unlocks_paper": false,
  "cases": [
    {"case_id": "m1_acked_long", "passed": true, "pnl_scored": false, "paper_authority": false},
    {"case_id": "m1_acked_next_open", "passed": true, "pnl_scored": false, "paper_authority": false},
    {"case_id": "m1_abstain_skipped", "passed": true, "pnl_scored": false, "paper_authority": false},
    {"case_id": "m1_stubbed_alpaca", "passed": true, "pnl_scored": false, "paper_authority": false},
    {"case_id": "m1_no_bar_skipped", "passed": true, "pnl_scored": false, "paper_authority": false}
  ]
}
```

Harness: **no code changes**. Tests were not broken; no fills invented. Prefer reporting FAIL over inventing — none to report on this tip.
