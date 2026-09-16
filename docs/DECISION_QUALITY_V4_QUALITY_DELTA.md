# Decision-quality V4 emitter delta

**Owner:** Dev  
**Upstream lock:** `docs/DECISION_QUALITY_PASS_V1_LOCK.md` (Research re-score gate)  
**Still binding:** `docs/MODEL_EVAL_LOCK_V0.md`  
**Prior live smoke:** `inferhub-cbcn-v3-quality` (match **0.75 HIT**, no-trade P **0.667 FAIL**, CFP=0, PASS 24/8/16)  
**Capital:** 0  
**Paper authority:** false (KILL)  
**CLEAR claim:** **do not claim CLEAR** from this delta or from the next live emit.

This is an engineering quality delta so Research can bother with a **new** Golden-48 re-score. It is not a v0/v1/v2/v3 identical re-run. Desk: next sealed pass must lift **no-trade precision** to ≥0.75 without relaxing `MODEL_EVAL_LOCK_V0`, without CFP, and without cheating GC-15/29. No soft-relabel of the 16 AMBIGUOUS. No GT injection.

Research formal CLEAR-capable pack is **deferred** until no-trade P clears.

## Next live `run_id`

Use **`inferhub-cbcn-v4-quality`**.

Do not reuse `inferhub-cbcn-v0`, `inferhub-cbcn-v1`, `inferhub-cbcn-v2-quality`, or `inferhub-cbcn-v3-quality` (Desk: no identical re-scores). If that directory already exists, pick `inferhub-cbcn-v4-quality-<suffix>` and record it; the canonical name is still `inferhub-cbcn-v4-quality`.

## Why V4 (vs V3 live smoke)

Live `inferhub-cbcn-v3-quality` smoke:

| Metric | V3 live | MODEL_EVAL_LOCK_V0 bar |
|---|---:|---:|
| behavioral_action_match | **0.75** | ≥ **0.70** (**HIT**) |
| no-trade precision | **0.667** | ≥ **0.75** (**FAIL**) |
| no-trade recall | **1.0** | ≥ 0.80 |
| CFP | **0** | **0** |
| PASS / FAIL / AMBIGUOUS | 24 / 8 / 16 | n/a |
| predicted abstains | **6** | 4 GT abstains + 2 false |
| model_eval_clear | **false** | still KILL |

No-trade P = TP_abstain / predicted_abstain. With 4 GT abstains and recall 1.0, predicted abstains must be ≤ floor(4/0.75)=**5**. V3 predicted **6** → 4/6=0.667. The two false abstains:

| Case | V3 pred | Why |
|---|---|---|
| **GC-01-2022-10-03** | exit→abstain | Sealed priors are open **Long XMTR/TH/TQQQ**. `Sold XMTR` is the **banned** fill. V3 coerce required same-message Closed/Sold, so it left the model abstain. |
| **GC-15-2023-09-21** | enter→abstain | Honest `thin_evidence_*` before Inferhub. Hard thin-prior kill scar — **do not cheat**. |

Cutting **one** false abstain (GC-01) → 4/5=**0.80 HIT** on no-trade P. Cutting GC-15 would be a banned-id / GT cheat; leave it honest. This delta does **not** claim that live V4 will CLEAR — match is already at the bar; the job is no-trade P without CFP.

## What changed (allowed levers only)

| Lever | V3 | V4 |
|---|---|---|
| Prompt | Enter/size/manage/exit + Long/Short/Closed/ADD/trim → asked action | Same, plus **exit/manage: open Long/Short on a listed ticker is enough** — do not abstain waiting for a post-cutoff Sold/Closed/ADD fill |
| Decode | `temperature=0.1`, `max_tokens=8192`, `json_object` | unchanged |
| Model id | `cbcn/glm-5.3-flash` | unchanged |
| Parse / coerce | False-abstain coerce if same-message ticker+intent (exit required Closed/Sold) | **Exit/manage coerce strengthened:** Closed/Sold/ADD/trim+ticker still wins; **open Long/Short+ticker is now support for exit/manage**. Rank Closed/Sold/ADD/trim above Long/Short; newest timestamp breaks ties. Fill `exit`/`management` from sealed Closed/Sold/ADD/trim only (do not invent `sold` from Long tape). **Never** coerce when primary is abstain (CFP guard) |
| Retrieval | ticker-aware, `max_messages=48` | unchanged |
| Thin priors | GC-15/29 honest `thin_evidence_*` **before Inferhub** | **unchanged honesty**: no ticker in retrieved priors → abstain before Inferhub; no banned/GT injection |

Not changed: `eligible_filter`, frozen pack hash `1a3cb17781211ad0`, locked 16 AMBIGUOUS labels, GT/`target_action` injection ban, CFP=0, capital/paper, GC-15/29 cheat = run invalid.

## Why GC-01 alone can clear no-trade P

Recall is already 1.0 on the four GT abstains (GC-04, GC-09, GC-28, GC-30). Precision is 4 / (4 + false_abstains). V3 has two false abstains. GC-15 must stay a predicted abstain if priors stay thin. Removing GC-01 from predicted_abstain leaves **one** false abstain (GC-15) → 4/5=0.80 ≥ 0.75. Match (0.75) already clears its bar; this PR does not run live Inferhub and does not land a scorecard.

## Research re-emit / score (operator Mac)

```bash
uv run alexrag emit-model-predictions \
  --no-dry-run \
  --ingest data/ingest \
  --frozen eval/golden_cases_v0_frozen.json \
  --lock docs/model_eval_lock_v0.json \
  --out results/model_eval_runs \
  --run-id inferhub-cbcn-v4-quality

uv run alexrag score-model \
  --predictions results/model_eval_runs/inferhub-cbcn-v4-quality/predictions.jsonl \
  --ingest data/ingest \
  --frozen eval/golden_cases_v0_frozen.json \
  --out results/model_score_runs
```

Read emit `run_metadata.json` for `quality_delta=decision_quality_v4`, `n_parse_failure`, `n_parse_retry_recovered`, `n_parse_local_repaired`, `n_abstain`, `temperature`, `max_tokens`, `max_messages`, `fixture_sha256_16`. Keep CFP=0 and GC-15/29 retrieved∩banned=∅.

Compare against V3 (`inferhub-cbcn-v3-quality`) on no-trade P (target ≥0.75) with match still ≥0.70. **Do not claim CLEAR** unless `gates.model_eval_clear=true` under MODEL_EVAL_LOCK_V0 (this PR does not run live Inferhub and does not land a scorecard).

Offline CI remains `--dry-run` (no Inferhub).

## Honest gaps this PR cannot close

Live Inferhub is not run in this PR. No-trade P / match are **targets**, not measured here. GC-15/29 must remain honest fail/abstain if priors stay thin. If live V4 still false-abstains GC-01, predicted abstains stay at 6 and P stays 0.667. This delta aims at the GC-01 ceiling; it does not graduate paper or CLEAR.
