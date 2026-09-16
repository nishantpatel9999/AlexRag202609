# MODEL_EVAL_LOCK_V0

**Owner:** Research  
**Lock date (PT):** 2026-09-15  
**Audience:** Dev (scorer hooks) · Risk/Red (gates) · Quant (fill realism, parallel track)  
**Capital:** **0**  
**Paper authority:** **KILL** until graduation gates clear (this lock does **not** unlock paper)  
**Market Fighter:** out of scope  

**Upstream locks:**
- Fixture integrity **CLEAR** on Golden-48 (`BASELINE_ORACLE` / `FIXTURE_AUDIT`) — **oracle audit is NOT model OOS**
- Frozen pack: `/workspace/alexrag/golden_cases_v0_frozen.json` (sha256[:16]=`1a3cb17781211ad0`)
- Eval Spec: `EVAL_SPEC_V0_2026-09-15.md` · Freeze: `FREEZE_NOTES.md` · Ingest: `INGEST_SCHEMA.md`
- Scorecard: `results/BEHAVIORAL_GOLDEN48_SCORECARD.md`

**Separate tracks (do not conflate):**
- **This lock** = decision-model behavioral scoring under sealed cutoff.
- **Quant M0** = fill receipts / realistic fills (kill 0bps mid). Dev may build realistic fill in parallel; **model CLEAR ≠ paper unlock**.

Machine-readable twin: `docs/model_eval_lock_v0.json`.

---

## Purpose / non-goals

### Purpose

Lock the **contract** for scoring an AlexRag **decision model** (retrieval + predict) against Golden-48 under sealed chronology:

1. Emit one structured prediction per frozen case.
2. Score against equity-trades ground truth (precedence per Eval Spec).
3. Report PASS / FAIL / AMBIGUOUS + no-trade P/R + catastrophic FP.
4. Keep **paper_authority = false** and **capital = 0** until gates + fill scar + Risk/Red clear.

MVP modes remain: sealed chronological replay → shadow → advise. **No submit.**

### Non-goals

- No implementation code in this drop (optional stub interface sketch only, below).
- No soft-relabel of the **16 AMBIGUOUS** conflict/size cases; labels stay as scored in the fixture audit.
- No treating the careful-reader **oracle** as a model OOS result or as a paper unlock signal.
- No Quant fill-realism graduation inside this lock (0bps mid remains Quant/Dev kill scar elsewhere).
- No order submit / broker API / live trading / Market Fighter.
- No P&L as primary gate; doctrine (GitBook) never overrides fills GT.
- No inventing eligible message-id lists at score time — apply `eligible_filter` over JSONL.

---

## Input contract (fixtures + JSONL + sealed cutoff)

### Frozen fixture pack (required)

| Field | Value |
|---|---|
| Path (box) | `/workspace/alexrag/golden_cases_v0_frozen.json` |
| Path (Mac, if mirrored) | `/Users/n_mac/Documents/AlexRag202609/docs/` sibling data under `data/ingest` |
| Cases | **48** (`fully_resolved` = 48/48) |
| Timezone | `America/Los_Angeles` (PT) |
| Global seal | only artifacts with timestamp **`< decision_ts`** |
| Integrity | CLEAR (ids resolve; key_evidence sealed; banned ordering OK) |

Per case, Dev **must** consume at minimum:

- `case_id`, `date_pt`, `decision_ts`, `primary_question`, `tickers`
- `target_action` (GT for action / side / size language on tape)
- `eligible_filter` — `{ channels, ts_lt, tz }`
- `banned_same_day_ids` — same-calendar-day messages with `ts >= decision_ts` (post-fill / post-decision leakage)
- `key_evidence_ids` — citation **hints** only (≤40); not a substitute for the filter
- `conflict_class`, `scoring_notes`, `pre_trade_labeled`

**Do not** materialize full eligible ID lists (can be thousands). Scorers **MUST** apply:

```text
eligible := JSONL rows where channel ∈ eligible_filter.channels
            AND ts < eligible_filter.ts_lt   # same as decision_ts
banned  := message_id ∈ banned_same_day_ids  # hard exclude from retrieval+cite
```

### Ingest JSONL (MVP channels)

| Glob (box) | Channel |
|---|---|
| `/workspace/alexrag/ingest/equity-trades.jsonl` | equity-trades (fills GT) |
| `/workspace/alexrag/ingest/alex-journal.jsonl` | alex-journal |
| `/workspace/alexrag/ingest/prime-report.jsonl` | prime-report |
| `/workspace/alexrag/ingest/pf-update.jsonl` | pf-update (state only) |

Mac source of truth for ingest: `/Users/n_mac/Documents/AlexRag202609/data/ingest/*.jsonl`  
Message key = JSONL `id` (Discord snowflake). Prefer current JSONL IDs; do not re-mint from HTML.

### Sealed cutoff (hard)

1. Visible corpus: `ts < decision_ts` on MVP channels only.
2. **Ban** every id in `banned_same_day_ids` (includes the GT fill itself for enter/size/manage/exit).
3. Same-minute ties: message_id order within channel; if still ambiguous, **exclude** same-ts post-fill journal rationalization when fill id is earlier.
4. Citations must reference eligible ids only; future / banned cites = hard fail for that case.
5. Charts inherit their message timestamp; no later chart attached to earlier decision.

### Precedence reminder (scoring GT)

equity-trades fills ≫ same-ts journal announcement ≫ pf-update state ≫ morning plan / no-trade journal ≫ prime-report FOCUSLIST ≫ doctrine.  
**Conflict cases: score against equity-trades.** Plans are context, not abstain labels to memorize.

---

## Model output schema (JSON fields Dev must emit per case)

One JSON object per `case_id` (JSONL of predictions or array). Required fields:

| Field | Type | Notes |
|---|---|---|
| `case_id` | string | Must match frozen pack |
| `decision_ts` | string | Echo fixture `decision_ts` (audit) |
| `action` | enum | `enter` \| `abstain` \| `size` \| `manage` \| `exit` |
| `side` | enum | `long` \| `short` \| `n/a` — required for enter/size; `n/a` OK for abstain |
| `ticker` | string | Primary symbol; empty string if abstain |
| `size_pct` | number \| null | Portfolio % when predicting size/enter with size; null if N/A |
| `stop` | string \| null | Optional; scored soft unless `scoring_notes` say otherwise |
| `management` | string \| null | trim / add / move_sl / reopen / close_all / … |
| `exit` | string \| null | close / trim fraction / reason class if claimed |
| `rejected_alternatives` | string[] | Tickers deliberately passed (with cites) |
| `citations` | object[] | `{ source, message_id, ts, quote_span }` — each `message_id` must pass eligible_filter and not be banned |
| `confidence` | number \| string | Model-reported; does not override PASS/FAIL rules |
| `abstain_reason` | string \| null | Required when `action=abstain` or evidence thin |
| `sealed_cutoff_ack` | string | Echo `eligible_filter.ts_lt` |
| `retrieved_ids` | string[] | Ids actually fed to the model (audit); must ⊆ eligible \ banned |
| `model_id` | string | Version / checkpoint / prompt hash |
| `run_id` | string | Immutable audit run id |

**Primary score target** = fixture `primary_question`. Secondary fields (stop text, narrative) do not alone PASS a case unless `scoring_notes` require them.

### Optional stub interface (markdown only — not runnable)

```text
score_case(case, prediction) -> { status: PASS|FAIL|AMBIGUOUS, cfp: bool, notes: [...] }
  assert prediction.retrieved_ids ∩ case.banned_same_day_ids == ∅
  assert all citations.ts < case.decision_ts
  gt := case.target_action + primary_question
  ...
```

---

## Scoring rules (PASS / FAIL / AMBIGUOUS; no-trade; CFP; size tolerance)

### Axes (must report all)

1. **enter** — action + side + ticker vs GT fill  
2. **abstain** — no invented fill for the scored ticker/setup  
3. **size** — action=size (or enter+size) with `size_pct` vs tape  
4. **manage** — management class vs chronology  
5. **exit** — exit/close vs tape  
6. **no-trade precision / recall** — on GT abstain goldens  
7. **catastrophic FP (CFP)** — must be **0** for any paper *discussion*

### Status definitions

| Status | When |
|---|---|
| **PASS** | Primary-question action matches GT; for `enter`, side+ticker match; citations valid (non-abstain); no banned/future cite; not a CFP |
| **FAIL** | Wrong primary action; wrong ticker/side on enter; invalid/banned/future citation used as support; CFP; hallucinated quote |
| **AMBIGUOUS** | Reserved for the **locked 16** conflict/size thin-prior cases (and any new cases Research explicitly tags). Scorer may still emit a prediction; **do not soft-relabel** fixture audit labels to PASS to inflate rates |

**Rule:** Aggregate model metrics may count AMBIGUOUS separately (neither automatic PASS nor automatic credit). Research owns any future re-tag; Dev does not re-label.

### Locked AMBIGUOUS set (16) — no soft-relabel

From fixture audit (`score_label=ambiguous`):

1. GC-02-2022-11-03 (enter; side mismatch in thin priors)  
2. GC-05-2023-01-05 (enter; side mismatch)  
3. GC-10-2023-04-21 (enter; C4 conflict)  
4. GC-17-2024-01-29 (size; pilot vs large; size on banned fill)  
5. GC-18-2024-03-06 (size; exact % on banned fill)  
6. GC-19-2024-03-15 (enter; C3 conflict)  
7. GC-20-2024-07-30 (size; exact % on banned fill)  
8. GC-23-2024-09-25 (enter; side mismatch)  
9. GC-26-2025-01-06 (enter; C7 conflict)  
10. GC-31-2025-03-10 (enter; journal vs equity)  
11. GC-33-2025-03-17 (size; conflict + size on banned fill)  
12. GC-34-2025-04-11 (enter; C10 shorts doctrine)  
13. GC-35-2025-04-17 (enter; C10)  
14. GC-36-2025-04-22 (enter; gameplan vs entry)  
15. GC-40-2026-03-26 (enter; C10)  
16. GC-42-2026-08-25 (size; exact % on banned fill)

On these rows: model may PASS/FAIL on its own prediction vs GT, but **reporting must keep the AMBIGUOUS fixture tag** for conflict/size difficulty — do not rewrite the golden label set.

### No-trade P/R

GT abstain goldens (fixture audit):

- GC-04-2022-12-09 (GFS rejected-setup abstain; other names may trade same day — soft flag only)  
- GC-09-2023-03-19  
- GC-28-2025-03-04  
- GC-30-2025-03-07  

Definitions:

- **Precision** = among model `abstain` predictions on scored cases, fraction whose GT is abstain (watch GC-29 false abstain).  
- **Recall** = among GT abstain cases, fraction model abstained.  

V0 bars (Eval Spec, still Nishant-tunable): recall ≥ **0.80**, precision ≥ **0.75**.

### Catastrophic false positive (CFP)

CFP if model predicts **`enter` or large `size`** when GT is **abstain / no fill** for that ticker/day, **or** enters **opposite side** on an abstain-honored day.

- **CFP = 0 required** for any paper discussion.  
- Non-zero CFP ⇒ automatic paper_authority KILL (Risk/Red veto).

### Size tolerance

When `primary_question=size` (or enter with scored size):

| Match | Rule |
|---|---|
| Exact | `abs(pred_size_pct - gt_size_pct) ≤ 0` → full credit |
| Soft band | `≤ 2.0` percentage points → soft PASS on size axis only if action+ticker+side already match |
| Fail | `> 2.0` pp, or missing `size_pct` when size is primary |
| Thin prior | Exact % often lives **only** on banned fill text — expecting exact % from sealed priors alone is unfair; score action+ticker first; size MAE is secondary. **Do not** cheat by reading banned fill. |

Pilot language vs large size (e.g. GC-17): conflict stays AMBIGUOUS-tagged; model must not invent the fill % from future tape.

### Citation / leakage fails (any axis)

- Cite `banned_same_day_ids` or `ts >= decision_ts` → **FAIL**  
- Empty citations on non-abstain when evidence existed → FAIL citation coverage for that case  
- Fabricated quote_span → FAIL  

---

## Kill scars (GC-15, GC-29, conflict AMBIGUOUS handling)

### Hard model kill scars (thin sealed priors)

These two are **oracle FAIL** under sealed key_evidence — they stay **hard kill scars** if a model “solves” them by cheating thin/sealed priors (banned fills, post-fill journal, future reports):

| Case | Conflict | Why kill scar |
|---|---|---|
| **GC-15-2023-09-21** | C5_report_no_FL_vs_new_shorts | Enter STRL/VRT shorts; **no ticker mention in key_evidence**. Solving enter+ticker without eligible setup evidence ⇒ leakage / memorization suspect. |
| **GC-29-2025-03-05** | C1_journal_no_trade_plan_vs_equity_entry | AM “No trades planned” then NFLX long; sealed priors look like abstain. Oracle would abstain. Model that **enters NFLX correctly only by peeking banned post-fill rationalization or the fill itself** ⇒ **KILL**. Honest abstain here is preferable to CFP-inverse cheating; false abstain is a known scar, not a license to unseal. |

**Audit rule for Dev/Red:** On GC-15 / GC-29, dump `retrieved_ids` ∩ (`banned_same_day_ids` ∪ ids with `ts ≥ decision_ts`). Any hit ⇒ run invalid / kill.

### Conflict AMBIGUOUS handling

- Conflict teaching set (C1–C10 etc.): **GT = equity-trades**.  
- Morning no-trade / “no FL” language may remain **eligible** (ts < decision_ts) — context, **not** hard abstain label.  
- Model must not average plan→false abstain when a fill exists **if** eligible setup evidence supports enter; when evidence is thin (GC-15/29), abstain-or-AMBIGUOUS is honest.  
- **No soft-relabel** of the 16 AMBIGUOUS rows to PASS in fixtures to clear gates.

### Soft flag (not a hard kill)

- **GC-04-2022-12-09**: `abstain_case_has_same_day_equity_msgs` — score abstain for **GFS**, not day-flat.

---

## Graduation (what CLEAR means vs paper unlock — paper still needs fill scar + Risk/Red)

### Fixture integrity CLEAR (already done)

- Golden-48 freeze resolved; eligible/banned integrity OK; CFP_oracle = 0.  
- **Does not** grant model OOS credit.  
- **Does not** unlock paper. Capital remains **0**.

### Model-eval CLEAR (this lock’s gate)

Research proposes model CLEAR when **all** hold on a sealed run over Golden-48 (non-training holdout discipline per Eval Spec):

| Gate | Bar |
|---|---|
| Behavioral action match | ≥ **0.70** on non-AMBIGUOUS primary actions (Nishant may tighten) |
| No-trade recall / precision | ≥ **0.80** / ≥ **0.75** |
| **CFP** | **= 0** |
| Citation coverage | ≥ **0.90** on non-abstain; **0** future/banned cites |
| GC-15 / GC-29 | No banned/future id in `retrieved_ids` or citations (honest fail/abstain OK) |
| Leakage sample | No systematic future docs / post-trade rationalization as enter-evidence |
| Audit trail | Append-only: fixture hash, cutoff, retrieved ids, output, scores |

**Model CLEAR ≠ paper authority.**

### Paper unlock (still KILL by default)

Paper discussion / paper trading requires **additionally**:

1. Model-eval CLEAR (above)  
2. **Quant fill scar cleared** — realistic fills; **kill 0bps mid** (Dev building; separate from this lock / separate from Quant M0 fill receipts conflation)  
3. Shadow gate green (Risk + Red)  
4. **Human approval** + **Risk limits** configured  
5. Red unilateral veto right on leakage, CFP, injection, hallucinated reasons, unrealistic fills  

Until then: `paper_authority_default: false`, capital **0**, no submit.

---

## Dev hook checklist

- [ ] Load `golden_cases_v0_frozen.json`; pin sha256[:16] `1a3cb17781211ad0` (or re-hash and record).  
- [ ] For each case, build retrieval with **`eligible_filter`** over MVP JSONL; **exclude `banned_same_day_ids`**.  
- [ ] Never inject `target_action` text / fill id into model context.  
- [ ] Emit per-case output schema (§ above) + `run_id` / `model_id`.  
- [ ] Scorer computes PASS/FAIL/AMBIGUOUS, no-trade P/R, CFP; keep 16 AMBIGUOUS tags.  
- [ ] Hard-fail run if GC-15 or GC-29 citations/retrieval intersect banned or `ts ≥ decision_ts`.  
- [ ] Immutable audit artifact per run (inputs hash, sealed cutoff, retrieved ids, scores).  
- [ ] Do **not** flip `paper_authority` in code paths; default **false**.  
- [ ] Do **not** wire submit/broker; capital **0**.  
- [ ] Keep Quant realistic-fill work on a **separate** branch/metric surface (0bps mid kill).  
- [ ] Hold out 2026-09-* goldens from prompt/retrieval tuning until V0 baseline locked.  
- [ ] pf-update = state only; focuslist-ideas stays OOS.  

---

*End MODEL_EVAL_LOCK_V0. Spec/lock only — Capital 0; paper KILL.*
