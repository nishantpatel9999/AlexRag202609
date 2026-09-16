# Decision-quality V2 emitter delta

**Owner:** Dev  
**Upstream lock:** `docs/DECISION_QUALITY_PASS_V1_LOCK.md` (Research re-score gate)  
**Still binding:** `docs/MODEL_EVAL_LOCK_V0.md`  
**Capital:** 0  
**Paper authority:** false (KILL)  
**CLEAR claim:** **do not claim CLEAR** from this delta or from the next live emit.

This is an engineering quality delta so Research can bother with a **new** Golden-48 re-score. It is not a v0/v1 identical re-run.

## Next live `run_id`

Use **`inferhub-cbcn-v2-quality`**.

Do not reuse `inferhub-cbcn-v0` or `inferhub-cbcn-v1` (Desk: no identical re-scores). If that directory already exists, pick `inferhub-cbcn-v2-quality-<suffix>` and record it; the canonical name is still `inferhub-cbcn-v2-quality`.

## What changed (allowed levers only)

| Lever | V2 setting |
|---|---|
| Prompt | Single JSON object; enter when sealed Long/Short fill-intent language names a listed ticker; citations from `retrieved_ids`; abstain only when thin |
| Decode | `temperature=0.15`, `max_tokens=8192`, `response_format=json_object` (HTTP 400 drops format and retries) |
| Model id | still `cbcn/glm-5.3-flash` |
| Parse | strip fences; repair truncated braces; schema-only LLM nudge; greedy first `{...}` |
| Schema coerce | action/side case + buy/sell aliases; citations dict/`messageId`; `rejected_alternatives` objects; size `%` strings |
| Thin priors | **no auto-enter**; GC-15 / GC-29 stay honest `thin_evidence_*` abstain before Inferhub |

Not changed: `eligible_filter`, frozen pack hash `1a3cb17781211ad0`, locked 16 AMBIGUOUS labels, GT/`target_action` injection ban, CFP=0, capital/paper.

## Research re-emit / score (operator Mac)

```bash
uv run alexrag emit-model-predictions \
  --no-dry-run \
  --ingest data/ingest \
  --frozen eval/golden_cases_v0_frozen.json \
  --lock docs/model_eval_lock_v0.json \
  --out results/model_eval_runs \
  --run-id inferhub-cbcn-v2-quality

uv run alexrag score-model \
  --predictions results/model_eval_runs/inferhub-cbcn-v2-quality/predictions.jsonl \
  --ingest data/ingest \
  --frozen eval/golden_cases_v0_frozen.json
```

Read emit `run_metadata.json` for `n_parse_failure`, `n_parse_retry_recovered`, `n_parse_local_repaired`, `n_abstain`, `temperature`, `max_tokens`, `fixture_sha256_16`. Compare against V1 lock MVP bars A–F before treating the scorecard as a formal re-score.

Offline CI remains `--dry-run` (no Inferhub).

## Honest gaps this PR cannot close

Live Inferhub is not run in this PR. Parse/abstain/enter PASS bars are **targets**, not measured here. GC-15/29 must remain honest fail/abstain if priors stay thin.
