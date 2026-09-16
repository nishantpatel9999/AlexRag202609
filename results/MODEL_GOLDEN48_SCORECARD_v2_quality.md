# MODEL Golden-48 Scorecard v2-quality (LIVE Inferhub)

**Audit type:** `MODEL_EVAL_LOCK_V0` decision-model score — **LIVE** (`dry_run=false`)  
**CLEAR claim:** **NO** — `gates.model_eval_clear=false`  
**Paper authority:** **NOT unlocked** (`paper_authority=false`)  
**Capital:** **0**  
**Soft-relabel:** **none**  
**Run id:** `inferhub-cbcn-v2-quality`  
**Model:** `cbcn/glm-5.3-flash` (Inferhub provider `cbcn`)  
**Quality delta:** `decision_quality_v2`  
**Repo tip:** `e71c82a`  
**Frozen pack sha256[:16]:** `1a3cb17781211ad0`  
**Generated:** 2026-09-15 09:58:20 PM PT

> Formal offline score of live Inferhub predictions (`results/model_eval_runs/inferhub-cbcn-v2-quality/predictions.jsonl`, 48 lines).  
> Scorer offline; capital stays 0; broker/submit not touched; no soft-relabel.  
> A–F checked against `docs/decision_quality_pass_v1_lock.json` (`DECISION_QUALITY_PASS_V1_LOCK`).

## Headline metrics

| Metric | Value |
|---|---:|
| n scored | 48 |
| **PASS** | **14** |
| **FAIL** | **18** |
| **AMBIGUOUS** | **16** |
| behavioral_action_match | 0.4375 |
| **CFP** | **0** |
| no-trade precision | 0.2500 |
| no-trade recall | 1.0000 |
| citation_coverage_non_abstain | 1.000 |
| run_valid | True |
| kill_scars | [] |
| emitter abstain | 16 |
| parse_failure | 0 |
| enter PASS non-AMBIG | 9 |
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

**Paper NOT unlocked.** Do not treat this run as CLEAR. Capital 0. No soft-relabel.

## A–F (DECISION_QUALITY_PASS_V1_LOCK research_rescore_mvp_bar)

| Criterion | Result | Evidence |
|---|---|---|
| **A** parse_health | **PASS** | parse_failure=0 (zero-failure path OK; retry_recovered=0) |
| **B** abstain_swamp | **PASS** | emitter abstain=16 ≤ 30 (v1 baseline 42) |
| **C** enter_quality | **PASS** | enter PASS on non-AMBIG enter goldens = **9** (≥1) |
| **D** cfp | **PASS** | CFP=0 |
| **E** kill_scars | **PASS** | GC-15/GC-29 honest abstain; retrieved∩banned=∅; citations=[]; kill_scars=[] |
| **F** lock_surface | **PASS** | fixture `1a3cb17781211ad0`; no soft-relabel; eligible filter unchanged |

**A–F all HIT.** This is the research rescore MVP bar only — **not** `model_eval_clear` and **not** paper unlock.

### Enter PASS non-AMBIG case ids (9)
GC-03-2022-11-15, GC-06-2023-02-02, GC-07-2023-03-09, GC-14-2023-09-07, GC-21-2024-08-01, GC-25-2024-12-10, GC-27-2025-01-07, GC-47-2026-09-14, GC-48-2026-09-15

### GC-15 / GC-29 honesty
- **GC-15-2023-09-21:** action=abstain (`thin_evidence_no_ticker_in_priors`); status=FAIL vs gt enter; citations=[]; ret∩banned=∅
- **GC-29-2025-03-05:** action=abstain (`thin_evidence_no_ticker_in_priors`); status=FAIL vs gt enter; citations=[]; ret∩banned=∅

## vs inferhub-cbcn-v1

| | v1 | v2-quality |
|---|---:|---:|
| PASS / FAIL / AMBIGUOUS | 4 / 28 / 16 | **14 / 18 / 16** |
| behavioral_action_match | 0.125 | **0.4375** |
| CFP | 0 | **0** |
| no-trade precision | 0.0952 | 0.2500 |
| no-trade recall | 1.0000 | 1.0000 |
| abstain (emitter) | 42 | **16** |
| parse_failure | 12 | **0** |
| enter PASS non-AMBIG | 0 | **9** |
| A–F research bar | miss (enter dead / parse swamp) | **HIT** |
| model_eval_clear | false | **false** |

Large quality lift vs v1 on match / enter / abstain / parse. Still below MODEL_EVAL_LOCK_V0 clear thresholds (`behavioral_action_match_ok=false`, `no_trade_precision_ok=false`).

## By primary_question

| primary_question | PASS | FAIL | AMBIGUOUS |
|---|---:|---:|---:|
| abstain | 4 | 0 | 0 |
| enter | 9 | 6 | 11 |
| exit | 0 | 5 | 0 |
| manage | 0 | 6 | 0 |
| size | 1 | 1 | 5 |

## Prediction action mix

| action | n |
|---|---:|
| abstain | 16 |
| enter | 16 |
| exit | 5 |
| manage | 6 |
| size | 5 |

## PASS case ids (14)
GC-03-2022-11-15, GC-04-2022-12-09, GC-06-2023-02-02, GC-07-2023-03-09, GC-09-2023-03-19, GC-14-2023-09-07, GC-21-2024-08-01, GC-22-2024-08-30, GC-25-2024-12-10, GC-27-2025-01-07, GC-28-2025-03-04, GC-30-2025-03-07, GC-47-2026-09-14, GC-48-2026-09-15

## Explicit non-claims
- **NOT** `model_eval_clear`
- **NOT** paper unlocked / paper_authority
- **Capital 0**
- A–F HIT ≠ CLEAR; CLEAR still requires MODEL_EVAL_LOCK_V0 graduation bars (match / no-trade P&R / etc.)

## Artifacts
- Predictions: `results/model_eval_runs/inferhub-cbcn-v2-quality/predictions.jsonl`
- Score audit: `results/model_score_runs/inferhub-cbcn-v2-quality/`
- This scorecard JSON: `results/model_golden48_scores_v2_quality.json`
