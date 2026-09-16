# Fill fidelity M0 scorecard (Quant)

Paper/shadow scoring only. **No live trading. No invented slippage. P&L is not scored.**

| Field | Value |
| --- | --- |
| Date scored (UTC) | 2026-09-16 |
| Repo | AlexRag202609 |
| Branch scored | `main` |
| Main tip SHA | `abe5b513911e08305d4ebda83197184dd810db49` |
| Main tip subject | Merge pull request #5 from nishantpatel9999/chore/land-golden-cases-v0-frozen |
| Fill model | M0 (mark-to-next-available fixture bar/mid) |
| Capital | **0** (`config/default.yaml` `paper.nav = 0.0`) |
| Paper-authority unlock | **No.** This scorecard is not an unlock. |
| Live path | None (confirmed: `mode=paper` only; Alpaca live URLs absent; no keys used) |

## Method

Contract: `docs/FILL_FIDELITY_M0.md`, `PaperFill` / `FillIntent` schemas, sealed fixtures under `tests/fixtures/m0/cases/`.

Pass criteria applied by `alexrag.eval.fill_m0.score_m0_case`:

- `stubbed` ≠ filled (`filled=False`, `qty_filled=0`)
- sealed `decision_ts` / `decision_clock` (citations `<` clock; acked fill uses next bar **after** clock, never a past mid)
- M0 scar **0bps**, labeled `fixture_mid_0bps_not_alex_slippage` (or `stubbed_not_filled` on the Alpaca stub)
- intent↔receipt field match + audit completeness
- **P&L is not a scoring axis**

There is **no M0 CLI**. `alexrag eval-golden` scores the V0 golden pack, not fills. Scoring used:

1. `uv sync --extra dev` (local install; no Alpaca env vars set)
2. `uv run pytest tests/test_fill_fidelity.py -q` (and related fill/m0 tests)
3. Offline `load_m0_cases()` + `score_m0_pack()` + per-case `replay_m0_case()` against all `tests/fixtures/m0/cases/*.json`

No network. No real Alpaca keys. Fixture `paper.nav=100000` in sealed cases / `config/fixture.yaml` is **offline Exec replay only**, not operator capital.

## Pytest (offline)

| Command | Result |
| --- | --- |
| `uv run pytest tests/test_fill_fidelity.py -q` | **7 passed** |
| Related: `tests/test_no_live.py`, `tests/test_schemas.py`, `tests/test_operator_lock.py` (with fill-fidelity) | **24 passed** |
| `tests/test_orchestrator.py::test_fixture_config_exercises_m0_exec` | **passed** (fixture.yaml Exec/M0 smoke; not a capital unlock) |
| Full offline `uv run pytest -q` | **74 passed** |

Schema unit checks inside `test_fill_fidelity.py` (not fixture replay, still contract):

- `stubbed` + `filled=True` → `ValidationError`
- `scar_bps != 0` → `ValidationError` (“do not invent Alex slippage”)
- default `paper.nav == 0.0` → `max_notional_dollars() == 0.0`, `hard_limits_ready() is False`

## Case table

Replay actuals from `replay_m0_case` match expected `PaperFill.status` on every sealed case.

| id | expected status | actual status | filled (exp / act) | pass/fail | notes |
| --- | --- | --- | --- | --- | --- |
| `m0_acked_long` | `acked` | `acked` | true / true | **PASS** | Next NVDA mid after `2026-09-15T18:15:00Z` is `125.0` at `18:16Z`. Past mid `99.0` unused. `scar_bps=0`, label `fixture_mid_0bps_not_alex_slippage`. `qty_filled=2`, `latency_ms=60000`. Venue `paper_sim`. |
| `m0_abstain_skipped` | `skipped` | `skipped` | false / false | **PASS** | Abstain `unknown_regime` → skip, not fill. Next bar ignored. `fill_px=null`, `qty_filled=0`, `skip_reason=unknown_regime`. Audit includes `exec_skipped_abstain`. |
| `m0_stubbed_alpaca` | `stubbed` | `stubbed` | false / false | **PASS** | Same go-intent shape as acked long. `alpaca_paper` without keys → `stubbed` ≠ filled even though an M0 bar exists. `fill_px=null`, `qty_filled=0`, `qty_left=2`, `scar_label=stubbed_not_filled`, `skip_reason=alpaca_paper_no_keys`. |
| `m0_no_bar_skipped` | `skipped` | `skipped` | false / false | **PASS** | Complete limit go-intent (`ref_px` sealed 125). Only bar is **at or before** clock (`18:00` vs `18:15`) → `no_next_fixture_bar`. Past mid not used as a mark. `filled=false`. |
| `m0_limit_citation` | `acked` | `acked` | true / true | **PASS** | Sealed citation copies `limit_px=120` / invalidation `118` into intent; M0 still marks **next fixture mid 125**, `scar_bps=0`. Did **not** invent spread, limit improvement, or Alex slippage. `qty=notional/120`. |

All scorer axes (`intent_match`, `receipt_match`, `intent_receipt_consistency`, `sealed_clock`, `audit_completeness`, `m0_zero_scar`, `no_pnl`) passed on every case.

## Aggregate

| Metric | Value |
| --- | --- |
| Cases in pack | 5 (files `01`–`05` under `tests/fixtures/m0/cases/`; ids as above) |
| Passed | 5 |
| Failed | 0 |
| Pass rate | **5/5 = 100%** |
| `pnl_scored` | `false` |
| `fill_model` | `M0` |

Statuses covered: `acked`, `skipped`, `stubbed` (no `partial` / `rejected` fixtures in this sealed pack).

## Scars (labeled; not slippage)

| Scar | Observed |
| --- | --- |
| M0 0bps | Every receipt `scar_bps == 0`. Acked cases labeled `fixture_mid_0bps_not_alex_slippage`. This is a **fixture mark**, not Alex slippage. |
| `stubbed` ≠ filled | `m0_stubbed_alpaca`: `status=stubbed`, `filled=False`, `qty_filled=0`. Schema rejects stubbed-as-filled. |
| Paper only | All intents `mode=paper`. Venues `paper_sim` or `alpaca_paper` stub. Default config `mode=paper`. No live Alpaca URL in `src/`. No keys present during scoring. |

## Capital 0 — not a paper-authority unlock

- Default operator capital is **`paper.nav = 0`**. Dollar notional / daily-loss cannot be derived (`hard_limits_ready() is False` → Risk fail-closed `hard_limits_unconfigured` on the default path).
- Sealed M0 cases and `config/fixture.yaml` set nav **only** so Exec can be replayed offline. That is fixture scaffolding, not an authority to trade paper size.
- **This scorecard does not unlock paper authority.** It does not set capital, enable Alpaca submit, or change `mode`.

## Blockers for Risk / Red

M0 Quant fill-fidelity on this sealed pack is **green (5/5)**. That is **not** a Risk/Red promotion.

Still blocking / out of scope for Risk/Red:

1. **Capital 0** on default config — Risk remains fail-closed for dollar limits until an operator sets nav via an approved paper path (not this PR).
2. **Not a paper-authority unlock** — no Exec live-submit, no Alpaca paper client, no capital mandate.
3. Alpaca paper without keys/network is **correctly stubbed**; a real paper submit client is still TODO and must not be treated as filled.
4. Promotion review in `docs/RISK_GATES.md` still requires replay stability, citation faithfulness, hindsight coverage, abstain-reason metrics, and fail-closed drills (stale feed / missing audit / daily-loss / DD). M0 is one fidelity input, not the whole gate.
5. **No P&L gate** and none was computed. Do not treat 100% M0 replay as a win-rate or slippage model.
6. Sealed pack has no `partial` / `rejected` receipts; Risk should not assume those statuses are exercised.

## Scorer dump (verbatim)

```json
{
  "n_cases": 5,
  "n_passed": 5,
  "pnl_scored": false,
  "fill_model": "M0",
  "cases": [
    {"case_id": "m0_acked_long", "passed": true, "pnl_scored": false},
    {"case_id": "m0_abstain_skipped", "passed": true, "pnl_scored": false},
    {"case_id": "m0_stubbed_alpaca", "passed": true, "pnl_scored": false},
    {"case_id": "m0_no_bar_skipped", "passed": true, "pnl_scored": false},
    {"case_id": "m0_limit_citation", "passed": true, "pnl_scored": false}
  ]
}
```

Harness: no code changes. Tests were not broken; no fills invented.
