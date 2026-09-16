# MODEL Golden-48 Scorecard (LIVE Inferhub)

**Audit type:** `MODEL_EVAL_LOCK_V0` decision-model score — **LIVE** (`dry_run=false`)  
**CLEAR claim:** **NO** — `gates.model_eval_clear=false`  
**Paper authority:** **NOT unlocked** (`paper_authority=false`)  
**Capital:** **0**  
**Run id:** `inferhub-cbcn-v0`  
**Model:** `cbcn/glm-5.3-flash` (Inferhub provider `cbcn`)  
**Repo tip:** `8960118` (main after PR #10/#11/#12)  
**Frozen pack sha256[:16]:** `1a3cb17781211ad0`  
**Generated:** 2026-09-15 08:59:34 PM PT

> Live Inferhub chat.completions over sealed-cutoff Golden-48. Not dry-run abstain.  
> Scorer offline; capital stays 0; broker/submit not touched.

## Headline metrics

| Metric | Value |
|---|---:|
| n scored | 48 |
| **PASS** | **4** |
| **FAIL** | **28** |
| **AMBIGUOUS** | **16** |
| behavioral_action_match | 0.125 |
| **CFP** | **0** |
| no-trade precision | 0.0909 |
| no-trade recall | 1.0000 |
| citation_coverage_non_abstain | 1.000 |
| run_valid | True |
| kill_scars | [] |
| **model_eval_clear** | **false** |
| paper_authority | false |
| capital | 0 |

## Gates (MODEL_EVAL_LOCK_V0)

| Gate | Value |
|---|---|
| behavioral_action_match_ok | False |
| no_trade_recall_ok | True |
| no_trade_precision_ok | False |
| cfp_ok | True |
| citation_coverage_ok | True |
| kill_scars_clear | True |
| **model_eval_clear** | **False** |

**Paper NOT unlocked.** Do not treat this run as CLEAR.

## By primary_question

| primary_question | PASS | FAIL | AMBIGUOUS |
|---|---:|---:|---:|
| abstain | 4 | 0 | 0 |
| enter | 0 | 15 | 11 |
| exit | 0 | 5 | 0 |
| manage | 0 | 6 | 0 |
| size | 0 | 2 | 5 |

## Prediction action mix (emitter)

| action | n |
|---|---:|
| abstain | 44 |
| manage | 4 |

- parse_failure abstains (emitter fallback): **12**  
- thin_evidence abstains: **2** (`GC-15-2023-09-21, GC-29-2025-03-05`)

## Catastrophic false positives

**CFP count = 0.** No enter/size on abstain-GT days flagged as CFP.

## Kill scars — GC-15 / GC-29

| Case | Status | Pred | GT | CFP | Notes |
|---|---|---|---|---|---|
| GC-15-2023-09-21 | FAIL | abstain | enter short STRL | False | honest thin_evidence abstain (no ticker in priors); ticker_mismatch pred='' gt='STRL'; side_mismatch pred=n/a gt=short; action_mismatch pred=abstain gt=enter |
| GC-29-2025-03-05 | FAIL | abstain | enter long NFLX | False | honest thin_evidence abstain; ticker_mismatch pred='' gt='NFLX'; side_mismatch pred=n/a gt=long; action_mismatch pred=abstain gt=enter |

Kill-scar audit: `run_valid=true`, `kill_scars=[]` (no banned/future id intersection in retrieved_ids/citations).

## PASS cases

- `GC-04-2022-12-09`
- `GC-09-2023-03-19`
- `GC-28-2025-03-04`
- `GC-30-2025-03-07`

## Operator notes

1. **Live key** loaded from `~/.alexrag/.env` (+ repo `.env`); secret not logged.  
2. API model id **`cbcn/glm-5.3-flash`** (lowercase). Code pin `cbcn/GLM-5.3-flash` returns HTTP 404 `model_not_found`.  
3. Local emitter fix: coerce `rejected_alternatives` dicts → strings (otherwise pydantic ValidationError → `parse_failure`).  
4. `max_tokens=4096` to avoid truncated JSON (`finish_reason=length`).  
5. Remaining 12 `parse_failure` rows stayed abstain — **not** invented enters.  
6. Score artifacts: `results/model_score_runs/inferhub-cbcn-v0/` (emit dir kept separate to avoid overwrite lock).

## Artifacts

| Path | Role |
|---|---|
| `results/model_eval_runs/inferhub-cbcn-v0/predictions.jsonl` | Live predictions |
| `results/model_eval_runs/inferhub-cbcn-v0/run_metadata.json` | Emit meta (`live_llm=true`, capital 0) |
| `results/model_score_runs/inferhub-cbcn-v0/summary.json` | Scorer summary + gates |
| `results/MODEL_GOLDEN48_SCORECARD.md` | This scorecard |
| `results/model_golden48_scores.json` | Machine-readable twin |

*End of LIVE model scorecard. Paper NOT unlocked. CLEAR not claimed.*
