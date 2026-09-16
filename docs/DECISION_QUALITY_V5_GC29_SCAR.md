# Decision-quality V5 — GC-29 C1 paper-block scar

**Owner:** Dev  
**Upstream lock:** `docs/DECISION_QUALITY_PASS_V1_LOCK.md`  
**Still binding:** `docs/MODEL_EVAL_LOCK_V0.md`  
**Prior live pack:** `inferhub-cbcn-v4-quality` (quality baseline **stands**; this PR does not re-score v4)  
**Capital:** 0  
**Paper authority:** false (KILL until Risk drills)  
**CLEAR claim:** **do not claim CLEAR** from this delta or from the next live emit.

This is a Red/Risk paper-block scar close, not a v4 identical re-run. Fixture labels are unchanged (no soft-relabel of GC-29 or the 16 AMBIGUOUS). No `target_action` / banned-id injection. GC-15 stays honest `thin_evidence_*` when priors have no listed ticker.

## Next live `run_id`

Use **`inferhub-cbcn-v5-gc29`**.

Do not reuse `inferhub-cbcn-v0`, `v1`, `v2-quality`, `v3-quality`, or `v4-quality` (Desk: no identical re-scores). If that directory already exists, pick `inferhub-cbcn-v5-gc29-<suffix>` and record it; the canonical name is still `inferhub-cbcn-v5-gc29`.

## The scar (citation dump `inferhub-cbcn-v4-quality`)

Case `GC-29-2025-03-05` (C1): same-morning sealed journal `1346827981015744636` (“No trades planned for today again.”) plus evening “No Focuslist” reports. Pred entered long NFLX citing **stale** prime-report NFLX chart alerts (Jan/Feb). Banned fill was not retrieved (good). Flip abstain→enter was GT-matching / weak conflict handling.

Emitter must **abstain** (or enter only with contemporaneous enter evidence). No GT peek.

## Rule

In `model_emit.py` (prompt + decode):

If eligible/retrieved context for the **decision day** or **sealed same-morning** (previous calendar-day 16:00 PT → `decision_ts`) contains explicit **no-trade / no-focuslist** language, **and** the only enter support is **older-than-1-day** (or older-than-same-session) ticker alerts **without** a contemporaneous Long/Short/bought/filled setup on a listed ticker, force `action=abstain` with `abstain_reason=conflict_no_trade_plan_vs_stale_setup`.

Fail-closed **before** Inferhub (same family as `thin_evidence_*`). Decode also refuses to coerce stale alerts into enter.

Does **not** fire when a listed ticker has enter intent younger than 1 day (protects C4/C10-style goldens that have recent tape plus plan language). Does **not** fire on GC-15 thin priors (no ticker at all).

## Metrics (honest scar close)

GC-29 GT remains **enter**. Honest abstain is a **FAIL vs GT** (false abstain on enter GT). If v4 entered NFLX, v5 match may drop slightly; no-trade precision may dip (one extra predicted abstain that is not a GT abstain). **Red prefers honest scar close** over GT-matching on stale alerts. Do not collapse other goldens’ no-trade P/match by treating every no-trade sentence as a hard label — contemporaneous enter setups still win.

This PR does not land a live scorecard and does not claim CLEAR.

## Research re-emit / score (operator Mac)

```bash
uv run alexrag emit-model-predictions \
  --no-dry-run \
  --ingest data/ingest \
  --frozen eval/golden_cases_v0_frozen.json \
  --lock docs/model_eval_lock_v0.json \
  --out results/model_eval_runs \
  --run-id inferhub-cbcn-v5-gc29

uv run alexrag score-model \
  --predictions results/model_eval_runs/inferhub-cbcn-v5-gc29/predictions.jsonl \
  --ingest data/ingest \
  --frozen eval/golden_cases_v0_frozen.json \
  --out results/model_score_runs
```

Keep CFP=0, GC-15/29 `retrieved ∩ banned = ∅`, capital 0, `paper_authority=false`. Paper still KILL until Risk drills.

Offline CI remains `--dry-run` (no Inferhub).
