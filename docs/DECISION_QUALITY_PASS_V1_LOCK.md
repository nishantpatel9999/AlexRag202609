# DECISION_QUALITY_PASS_V1_LOCK

**Owner:** Research  
**Lock date (PT):** 2026-09-15  
**Audience:** Dev (emitter / prompt / parse) · Risk/Red (gates) · Desk (no identical re-score)  
**Capital:** **0**  
**Paper authority:** **false** (still KILL until Risk/Red + fill scar)  
**Market Fighter:** out of scope  

**Upstream (still binding):**
- `docs/MODEL_EVAL_LOCK_V0.md` + `docs/model_eval_lock_v0.json` — **MODEL_EVAL_LOCK_V0 still binds**
- Frozen pack: `/workspace/alexrag/golden_cases_v0_frozen.json` (sha256[:16]=`1a3cb17781211ad0`)
- Fixture integrity CLEAR; oracle audit ≠ model OOS
- Kill scars: **GC-15 / GC-29** stay hard thin-prior kills (honest fail/abstain OK)
- Locked **16 AMBIGUOUS** — **no soft-relabel**
- Quant fill scar / 0bps-mid kill remains **orthogonal**

**Machine-readable twin:** `docs/decision_quality_pass_v1_lock.json`

---

## Why this lock exists

Live Inferhub runs **`inferhub-cbcn-v0`** and **`inferhub-cbcn-v1`** are **identical CLEAR kills**:

| Metric | v0 / v1 |
|---|---:|
| PASS / FAIL / AMBIGUOUS | **4 / 28 / 16** |
| behavioral_action_match | **0.125** |
| CFP | **0** |
| model_eval_clear | **false** |
| enter PASS | **0** |
| emitter abstains | ~**42** (v1) / 44 (v0) |
| parse_failure abstains | **12** |
| parse_retry_recovered | **0** |

All 4 PASSes are GT-abstain goldens only. Enter axis: **0 PASS / 15 FAIL / 11 AMBIGUOUS**.  
Desk rule: **no more identical re-scores**; do not soft-relabel the 16 AMBIGUOUS; do not touch capital or paper.

**Research does not implement.** Dev ships emitter / prompt / parse / model knobs. Research re-scores **only** when a real quality change lands that meets the MVP bar below.

---

## 1) Goal

Raise **sealed** decision quality under `MODEL_EVAL_LOCK_V0` **without relaxing the lock**:

1. Produce real **enter PASSes** on **non-AMBIGUOUS** enter goldens (primary pain: enter = 0 PASS today).
2. Cut **parse_failure → abstain** fallbacks (12 today; retry recovered = 0).
3. Cut the default-abstain swamp (~42 abstains) so no-trade precision can recover without inventing CFP.
4. Keep **CFP = 0**, sealed cutoff, eligible_filter, banned_same_day_ids, and GC-15/29 honesty intact.
5. Do **not** claim model CLEAR or paper unlock from this pass alone.

This pass is an **engineering quality delta** gate for Research to bother with a formal re-score — not a graduation of paper_authority.

---

## 2) Allowed vs forbidden changes

### Allowed (Dev may ship)

| Lever | Notes |
|---|---|
| **Prompt** | Decision instruction, schema reminders, abstain discipline, citation rules — sealed corpus only |
| **Output schema / emitter** | Field coercion, required enums, rejected_alternatives typing, truncation handling |
| **Parse retry** | Recover malformed JSON; target `parse_retry_recovered > 0` and fewer parse_failure abstains |
| **Model id** | Swap Inferhub / provider model string if still sealed-eval compatible (record in `model_id`) |
| **Temperature / decoding** | Lower temp / constrained decode for structured JSON stability |
| **Tools** | Retrieval tooling under existing eligible_filter + banned excludes (no new leakage surface) |
| **max_tokens / finish_reason** | Avoid length-truncated JSON (already noted on v0) |

### Forbidden (automatic Research refuse / Desk kill)

| Forbidden | Why |
|---|---|
| Soft-relabel of the **16 AMBIGUOUS** fixture tags | Inflates rates without quality |
| Injecting **GT / `target_action` / fill body / banned ids** into model context | Leakage / cheat |
| Loosening **`eligible_filter`** or unsealing `ts ≥ decision_ts` | Chronology break |
| Treating GC-15 / GC-29 “solve via peek” as PASS | Hard thin-prior kill scars |
| Identical re-score of same emitter/prompt/model with no material delta | Desk: waste |
| Flipping `paper_authority` or capital | Separate Risk/Red + fill scar track |
| Scoring P&L as primary gate / submitting orders | Out of scope |

---

## 3) Minimum bar before Research re-scores (honest MVP)

Research will **not** open a formal Golden-48 re-score unless Dev’s candidate run shows **all** of the following vs `inferhub-cbcn-v1` baseline:

| Gate | MVP bar | Rationale |
|---|---|---|
| **A. Parse health** | `parse_failure ≤ 2` **and** `parse_retry_recovered ≥ 1` (or parse_failure = 0 with no retry needed) | Today 12 failures / 0 recovered — dominant abstain source |
| **B. Abstain swamp** | Emitter abstain count **≤ 30** (materially down from ~42) | Must leave room for real enter/size/manage/exit predicts |
| **C. Enter quality** | **≥ 1 enter PASS** on a **non-AMBIGUOUS** enter golden (fixture not in the locked 16) | Primary quality signal; abstain-only PASSes already saturated |
| **D. CFP** | **CFP = 0** (hard) | Non-negotiable for any discussion |
| **E. Kill scars** | GC-15 / GC-29: no banned/future id in `retrieved_ids` or citations; honest FAIL/abstain OK | MODEL_EVAL_LOCK_V0 still binds |
| **F. Lock surface** | Same frozen pack hash `1a3cb17781211ad0`; no soft-relabel; eligible_filter unchanged | Integrity |

**Explicit kill if still 0 enter PASS:** If A+B+D+E+F hold but enter PASS on non-AMBIGUOUS remains **0**, Dev may still request a **Desk-acknowledged kill scorecard** (not a CLEAR attempt) so Research can document “parse/abstain improved, enter still dead.” That is optional and **not** a model_eval_clear path.

**Not required for this MVP re-score trigger** (still tracked):
- Full MODEL_EVAL_LOCK_V0 CLEAR (match ≥ 0.70, no-trade P/R bars, etc.)
- Manage/exit PASSes
- paper_authority

---

## 4) Hard keeps (unchanged from MODEL_EVAL_LOCK_V0)

- **CFP = 0** always.
- **GC-15 / GC-29** honest fails/abstains OK; cheat = run invalid / kill.
- Locked **16 AMBIGUOUS** stay tagged; scorer may score prediction vs GT but **must not** rewrite fixture labels.
- Sealed cutoff: only `ts < decision_ts`; ban `banned_same_day_ids`.
- Never inject `target_action` / fill text into context.
- Capital **0**; no broker / submit.
- Fill scar / realistic fills remain **orthogonal** Quant/Dev track.

---

## 5) Paper authority

`paper_authority` remains **false** until:

1. Model-eval CLEAR under MODEL_EVAL_LOCK_V0, **and**
2. Quant **fill scar** cleared (kill 0bps mid), **and**
3. Risk + Red shadow gate green + human approval.

This V1 decision-quality pass **cannot** unlock paper even if MVP bars clear.

---

## Dev hook checklist (Research re-score trigger)

- [ ] Ship a **real** delta: prompt and/or schema/parse-retry and/or model id/temp/tools (not a noop re-run).
- [ ] Emit under new `run_id` (suggest `inferhub-cbcn-v2` or descriptive); pin `model_id`, fixture hash, lock version.
- [ ] Report emit meta: `n_parse_failure`, `n_parse_retry_recovered`, `n_abstain`, action mix.
- [ ] Self-check MVP gates A–F offline before pinging Research.
- [ ] Do **not** soft-relabel AMBIGUOUS; do **not** loosen eligible_filter; do **not** inject GT.
- [ ] Keep GC-15/29 audit dump ready (retrieved ∩ banned / future).
- [ ] Keep `paper_authority=false`, capital 0 in all code paths.
- [ ] When A–F met (or Desk-ack kill for enter-still-0), Research re-scores and writes scorecard — **not before**.

---

## 5-bullet summary for Dev

1. **Goal:** Raise sealed enter quality + kill parse_failure abstains; do not relax MODEL_EVAL_LOCK_V0 (CFP=0, GC-15/29 hard, no soft-relabel).
2. **Ship levers:** prompt / schema / parse retry / model id / temperature / tools only — never GT injection, never eligible_filter loosen, never AMBIGUOUS soft-relabel.
3. **Ping Research only when:** `parse_failure ≤ 2` (+ retry recovered or zero failures), abstains **≤ 30**, **≥ 1 non-AMBIGUOUS enter PASS**, CFP=0, GC-15/29 honest, same fixture hash — else no formal re-score.
4. **v0≡v1 kill stands:** 4/28/16, match 0.125, enter PASS=0, ~42 abstains, 12 parse_failure / 0 recovered — identical re-scores banned.
5. **Paper still false;** capital 0; fill scar orthogonal — this pass is quality delta only, not CLEAR/paper unlock.

---

*End DECISION_QUALITY_PASS_V1_LOCK. Spec/lock only — Capital 0; paper KILL; Research does not implement.*
