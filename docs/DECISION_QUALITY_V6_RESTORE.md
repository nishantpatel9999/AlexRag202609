# Decision-quality V6 — restore CLEAR bars, keep GC-29 scar

**Owner:** Dev  
**Upstream lock:** `docs/DECISION_QUALITY_PASS_V1_LOCK.md`  
**Still binding:** `docs/MODEL_EVAL_LOCK_V0.md`  
**Prior live packs:** `inferhub-cbcn-v4-quality` (CLEAR bars **HIT**); `inferhub-cbcn-v5-gc29` (GC-29 scar HIT, CLEAR bars **MISS**)  
**Capital:** 0  
**Paper authority:** false (KILL until Risk drills)  
**CLEAR claim:** **do not claim CLEAR** from this delta or from the next live emit.

This is a narrow emitter restore, not a v4/v5 identical re-score. Fixture labels are unchanged (no soft-relabel of GC-29 or the 16 AMBIGUOUS). No `target_action` / banned-id injection. GC-15 stays honest `thin_evidence_*` when priors have no listed ticker. GC-29 C1 conflict rule **stays**: same-morning no-trade vs stale NFLX report alerts still fail-closed abstain.

## Next live `run_id`

Use **`inferhub-cbcn-v6-restore`**.

Do not reuse `inferhub-cbcn-v0`, `v1`, `v2-quality`, `v3-quality`, `v4-quality`, or `v5-gc29` (Desk: no identical re-scores). If that directory already exists, pick `inferhub-cbcn-v6-restore-<suffix>` and record it; the canonical name is still `inferhub-cbcn-v6-restore`.

## Live v4 → v5 regression (do not re-emit)

| Metric | v4 CLEAR | v5 live | MODEL_EVAL_LOCK_V0 bar |
|---|---:|---:|---:|
| behavioral_action_match | **0.71875** | **0.59375** | ≥ 0.70 |
| no-trade precision | **0.80** | **0.50** | ≥ 0.75 |
| PASS / predicted abstains | 23 / 5 | 19 / 8 | n/a |
| CFP | 0 | 0 | 0 |
| GC-29 scar | enter (GT-match on stale alerts) | **HIT** `conflict_no_trade_plan_vs_stale_setup` | honest abstain OK |

**Only new conflict abstains:** GC-29 (intended), **GC-31**, **GC-32** (collateral). GC-43 / GC-46 FAIL is unrelated exit-label noise — not this rule.

## Root cause

`conflict_no_trade_plan_vs_stale_setup` (V5) was over-broad:

1. Plan “no trades…” is not ticker-scoped and can fire from **eligible** (not just retrieved). Leftover same-window pf-update / journal “No trades again today” from the prior session trips the flag on enter-GT days.
2. Stale gate treated **any ≥1d ticker mention** — including **year-old equity-trades Longs** — as a stale setup. Enter/alert intent and report/alert channel were not required.
3. Contemporaneous enter veto almost never saves enter-GT days: the same-session Long is usually the **banned fill**.

GC-31 evening report named **ACMR … MP …** on a setup list (contemporaneous plan for those tickers) while V5 abstained on ancient MP tape + leftover no-trade language. GC-32 mixed-PPI morning + 2023 ERY tape, no same-session ERY report alert.

## What changed (narrowest patch)

| Lever | V5 | V6 |
|---|---|---|
| Same-morning window | previous calendar-day **16:00 PT → `decision_ts`** | **unchanged** |
| `has_stale_ticker_alert` | any stale ticker mention | only if stale msg has enter/alert intent (`_ENTER_SIZE_INTENT` or `Alert:` / `LONG setup` / `chart alert`) **and** report/alert channel (`prime-report` / `report`) — **not** bare/year-old equity-trades tape |
| Plan veto | any plan-window no-trade/no-focuslist | same, **plus ticker-scoped veto**: if plan-window text names a listed ticker in a focuslist/setup list (GC-31 `ACMR … MP …`), **do not fire** |
| Contemporaneous enter | Long/Short/bought/filled age < 1 day still wins | **unchanged** |
| GC-29 | fail-closed abstain | **unchanged**: Jan/Feb NFLX prime-report alert + AM “No trades planned”, no same-session NFLX setup → `conflict_no_trade_plan_vs_stale_setup` |
| Decode / coerce | conflict disables stale-alert coerce | same, but conflict is rarer — coerce on GC-31/32-like tape is restored |
| Thin priors | GC-15 honest `thin_evidence_*` | **unchanged** |

Not changed: `eligible_filter`, frozen pack hash `1a3cb17781211ad0`, locked 16 AMBIGUOUS labels, GT/`target_action` injection ban, CFP=0, capital/paper, GC-15/29 cheat = run invalid. GC-29 GT remains **enter**; honest abstain is still a FAIL vs GT.

## Offline tests

- `test_gc29_stale_alert_vs_same_morning_no_trade_abstains` — still fail-closed before Inferhub.
- `test_gc31_setup_list_does_not_conflict_abstain` — ACMR/MP setup list + leftover no-trade + old tape / stale MP `Alert:` → **no fire**; Inferhub path + coerce still enter.
- `test_gc32_ancient_tape_does_not_conflict_abstain` — year-old ERY Long + leftover no-trade, no report alert → **no fire**.
- `test_no_trade_plan_does_not_block_contemporaneous_enter` — same-session Long still wins.

## Research re-emit / score (operator Mac)

```bash
uv run alexrag emit-model-predictions \
  --no-dry-run \
  --ingest data/ingest \
  --frozen eval/golden_cases_v0_frozen.json \
  --lock docs/model_eval_lock_v0.json \
  --out results/model_eval_runs \
  --run-id inferhub-cbcn-v6-restore

uv run alexrag score-model \
  --predictions results/model_eval_runs/inferhub-cbcn-v6-restore/predictions.jsonl \
  --ingest data/ingest \
  --frozen eval/golden_cases_v0_frozen.json \
  --out results/model_score_runs
```

Targets (not measured in this PR): restore v4 CLEAR bars (match ≥ 0.70, no-trade P ≥ 0.75, CFP=0) **and** keep GC-29 honest abstain + GC-15 honest thin. Do not claim CLEAR unless `gates.model_eval_clear=true`. Paper still KILL until Risk drills.

Offline CI remains `--dry-run` (no Inferhub).
