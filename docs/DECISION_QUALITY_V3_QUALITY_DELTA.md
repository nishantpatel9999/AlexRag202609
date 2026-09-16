# Decision-quality V3 emitter delta

**Owner:** Dev  
**Upstream lock:** `docs/DECISION_QUALITY_PASS_V1_LOCK.md` (Research re-score gate)  
**Still binding:** `docs/MODEL_EVAL_LOCK_V0.md`  
**Prior formal pack:** `inferhub-cbcn-v2-quality` (A–F HIT, **model CLEAR still KILL**)  
**Capital:** 0  
**Paper authority:** false (KILL)  
**CLEAR claim:** **do not claim CLEAR** from this delta or from the next live emit.

This is an engineering quality delta so Research can bother with a **new** Golden-48 re-score. It is not a v0/v1/v2 identical re-run. Desk: next sealed pass must lift **behavioral_action_match** and **no-trade precision** without relaxing `MODEL_EVAL_LOCK_V0`. No soft-relabel of the 16 AMBIGUOUS. No GT injection.

## Next live `run_id`

Use **`inferhub-cbcn-v3-quality`**.

Do not reuse `inferhub-cbcn-v0`, `inferhub-cbcn-v1`, or `inferhub-cbcn-v2-quality` (Desk: no identical re-scores). If that directory already exists, pick `inferhub-cbcn-v3-quality-<suffix>` and record it; the canonical name is still `inferhub-cbcn-v3-quality`.

## Why V3 (vs V2)

Formal `inferhub-cbcn-v2-quality` scorecard (`results/MODEL_GOLDEN48_SCORECARD_v2_quality.md`):

| Metric | V2 live | MODEL_EVAL_LOCK_V0 bar |
|---|---:|---:|
| A–F research MVP | **HIT** | n/a (not CLEAR) |
| enter PASS non-AMBIG | **9** | n/a (V1 MVP was ≥1) |
| parse_failure | **0** | keep low |
| CFP | **0** | **0** |
| no-trade recall | **1.0** | ≥ 0.80 |
| behavioral_action_match | **0.4375** | ≥ **0.70** |
| no-trade precision | **0.25** | ≥ **0.75** |
| emitter abstain | 16 | false abstains dominate P |
| model_eval_clear | **false** | still KILL |

V2 already cut the abstain swamp (42 → 16) and got enter PASSes. Remaining CLEAR kills are **match** (need ~23/32 non-AMBIG PASS) and **no-trade P** (4 true abstains / 16 predicted abstains). GC-15 / GC-29 stay honest thin-prior abstains if ticker-aware retrieval still finds no listed ticker.

## What changed (allowed levers only)

| Lever | V2 | V3 |
|---|---|---|
| Prompt | Enter when Long/Short names a listed ticker; abstain when thin | Stronger abstain discipline: **only abstain when `primary_question` is abstain or evidence is thin**. Enter/size/manage/exit + sealed Long/Short/Closed/ADD/trim language → **prefer asked action + cite**. Explicit manage/exit ticker rules (empty ticker OK on manage if unclear; exit must name Closed/Sold ticker) |
| Decode | `temperature=0.15`, `max_tokens=8192`, `json_object` | `temperature=0.1`, same max_tokens / json_object (HTTP 400 still drops format and retries) |
| Model id | `cbcn/glm-5.3-flash` | unchanged |
| Parse | fences / truncated braces / schema nudge / greedy `{...}` | same, plus **false-abstain coerce**: if primary is not abstain and sealed ticker+intent exists, map model `abstain` (or enter-on-manage/exit) to the asked action and attach a retrieved citation. **Never** coerce when primary is abstain (CFP guard). Thin priors still fail-closed before Inferhub |
| Retrieval | key_evidence then recency, `max_messages=32` | **ticker-aware**: key_evidence same-ticker first, then other same-ticker eligible (newest), then remaining key_evidence, then recency. `max_messages=48` so long key_evidence lists cannot drop older ticker hits |
| Thin priors | no auto-enter; GC-15/29 honest `thin_evidence_*` | **unchanged honesty**: no ticker in retrieved priors → abstain before Inferhub; no banned/GT injection |

Not changed: `eligible_filter`, frozen pack hash `1a3cb17781211ad0`, locked 16 AMBIGUOUS labels, GT/`target_action` injection ban, CFP=0, capital/paper, GC-15/29 cheat = run invalid.

## Research re-emit / score (operator Mac)

```bash
uv run alexrag emit-model-predictions \
  --no-dry-run \
  --ingest data/ingest \
  --frozen eval/golden_cases_v0_frozen.json \
  --lock docs/model_eval_lock_v0.json \
  --out results/model_eval_runs \
  --run-id inferhub-cbcn-v3-quality

uv run alexrag score-model \
  --predictions results/model_eval_runs/inferhub-cbcn-v3-quality/predictions.jsonl \
  --ingest data/ingest \
  --frozen eval/golden_cases_v0_frozen.json \
  --out results/model_score_runs
```

Read emit `run_metadata.json` for `quality_delta=decision_quality_v3`, `n_parse_failure`, `n_parse_retry_recovered`, `n_parse_local_repaired`, `n_abstain`, `temperature`, `max_tokens`, `max_messages`, `fixture_sha256_16`. Keep CFP=0 and GC-15/29 retrieved∩banned=∅.

Compare against V2 (`inferhub-cbcn-v2-quality`) on match + no-trade P. A–F should remain HIT. **Do not claim CLEAR** unless `gates.model_eval_clear=true` under MODEL_EVAL_LOCK_V0 (this PR does not run live Inferhub and does not land a scorecard).

Offline CI remains `--dry-run` (no Inferhub).

## Honest gaps this PR cannot close

Live Inferhub is not run in this PR. Match / no-trade P are **targets**, not measured here. GC-15/29 must remain honest fail/abstain if priors stay thin after ticker-aware retrieval. V2’s 16 abstains include the 4 GT abstain goldens; precision ≥ 0.75 needs almost no remaining false abstains (GC-29 is a known false-abstain watch). This delta aims at that ceiling; it does not graduate paper or CLEAR.
