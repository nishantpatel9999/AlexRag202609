# Behavioral Golden-48 Scorecard

**Audit type:** `BASELINE_ORACLE` / `FIXTURE_AUDIT` — **NOT model OOS**
**Paper authority:** NOT unlocked
**Capital:** 0
**Market Fighter:** not in scope
**Frozen pack:** `/workspace/alexrag/golden_cases_v0_frozen.json` (sha256[:16]=1a3cb17781211ad0)
**Freeze PT date:** 2026-09-15
**Generated:** 2026-09-15 7:31:49 PM PT (2026-09-16T02:31:49Z)

> No trained/retriever decision model was scored. This is a human+rules audit of
> fixture integrity under sealed cutoff, plus a careful-reader oracle that may
> use only `key_evidence` (ids resolving in ingest with `ts < decision_ts`).
> Banned same-day ids and `target_action` text are **not** used as enter-evidence.

## Headline metrics

| Metric | Value |
|---|---:|
| n scored | 48 |
| fully_resolved | 48/48 |
| integrity OK (ids+sealed) | 48/48 |
| integrity FAIL | 0 |
| oracle PASS | 30 |
| oracle FAIL | 2 |
| oracle AMBIGUOUS | 16 |
| **Catastrophic FP (oracle enter on abstain GT)** | **0** |
| no-trade precision (oracle) | 0.80 |
| no-trade recall (oracle) | 1.00 |
| GC-04 soft flag | YES (`abstain_case_has_same_day_equity_msgs`) |

## By primary_question

| primary_question | pass | fail | ambiguous |
|---|---:|---:|---:|
| enter | 13 | 2 | 11 |
| abstain | 4 | 0 | 0 |
| size | 2 | 0 | 5 |
| manage | 6 | 0 | 0 |
| exit | 5 | 0 | 0 |

## Catastrophic false positives

**CFP count = 0.** Oracle did not predict enter/size on any abstain-labeled golden.

## GC-04 soft flag

- **GC-04-2022-12-09**: Rejected-setup abstain on GFS while ARRY/KGC/etc. traded same day.
  `abstain_case_has_same_day_equity_msgs` is informational; score abstain for GFS, not day-flat.

## Fixture integrity

- All 48 cases `fully_resolved=true` per freeze.
- Sealed rule: key_evidence must have `ts < decision_ts`; banned_same_day_ids are `ts >= decision_ts`.
- Target fill for enter/size/manage/exit is banned as enter-evidence (expected).
- Abstain targets are plan messages with `decision_ts = plan_ts + 1s` so plan is eligible.
- **No hard integrity failures** on id resolution / sealed key_evidence / banned ordering.

### Soft notes (1 cases)
- `GC-04-2022-12-09`: ["freeze_blockers=['abstain_case_has_same_day_equity_msgs']"]

## Leakage risks

| Risk | Finding |
|---|---|
| Future docs in key_evidence | NONE hard |
| Banned ids before decision_ts | NONE |
| Post-trade rationalization as enter-evidence | Target fills correctly banned; morning no-trade journals remain eligible on conflict enters (C1/C2) — model must not treat them as hard abstain labels |
| Conflict plan→fill | Score against equity-trades GT; plans are context only |

### Conflict / surprise-enter scars (oracle often FAIL or AMBIGUOUS)

- `GC-10-2023-04-21` pq=enter conflict=`C4_report_no_focuslist_vs_equity_trades` → oracle **ambiguous**: conflict_no_trade_language_present_but_ticker_setup_also
- `GC-15-2023-09-21` pq=enter conflict=`C5_report_no_FL_vs_new_shorts` → oracle **fail**: no_ticker_mention_in_key_evidence
- `GC-17-2024-01-29` pq=size conflict=`pilot_language_vs_large_size` → oracle **ambiguous**: ticker_setup_or_journal_mention; side_mismatch pred=short gt=long; exact_size_pct_not_in_priors gt=16.0 (expected: size on banned fill)
- `GC-19-2024-03-15` pq=enter conflict=`C3_no_new_longs_narrative_vs_new_short` → oracle **ambiguous**: conflict_no_trade_language_present_but_ticker_setup_also
- `GC-26-2025-01-06` pq=enter conflict=`C7_report_nothing_excites_vs_CIEN` → oracle **ambiguous**: ticker_setup_or_journal_mention
- `GC-29-2025-03-05` pq=enter conflict=`C1_journal_no_trade_plan_vs_equity_entry` → oracle **fail**: only_no_trade_priors_no_ticker_setup_ORACLE_WOULD_ABSTAIN; false_abstain_on_enter_gt
- `GC-31-2025-03-10` pq=enter conflict=`journal_narrative_vs_equity_entries` → oracle **ambiguous**: conflict_no_trade_language_present_but_ticker_setup_also
- `GC-33-2025-03-17` pq=size conflict=`journal_not_in_hurry_vs_multi_pilots` → oracle **ambiguous**: conflict_no_trade_language_present_but_ticker_setup_also; exact_size_pct_not_in_priors gt=3.0 (expected: size on banned fill)
- `GC-34-2025-04-11` pq=enter conflict=`C10_rulebook_shorts_disabled_vs_practice` → oracle **ambiguous**: conflict_no_trade_language_present_but_ticker_setup_also
- `GC-35-2025-04-17` pq=enter conflict=`C10_rulebook_shorts_disabled_vs_practice` → oracle **ambiguous**: conflict_no_trade_language_present_but_ticker_setup_also
- `GC-36-2025-04-22` pq=enter conflict=`journal_gameplan_vs_equity_entry` → oracle **ambiguous**: conflict_no_trade_language_present_but_ticker_setup_also
- `GC-40-2026-03-26` pq=enter conflict=`C10_rulebook_shorts_disabled_vs_practice` → oracle **ambiguous**: conflict_no_trade_language_present_but_ticker_setup_also

## Oracle FAIL cases

- `GC-15-2023-09-21` pq=enter tickers=['STRL', 'VRT'] pred=ambiguous gt=enter — no_ticker_mention_in_key_evidence
- `GC-29-2025-03-05` pq=enter tickers=['NFLX'] pred=abstain gt=enter — only_no_trade_priors_no_ticker_setup_ORACLE_WOULD_ABSTAIN; false_abstain_on_enter_gt

## Oracle AMBIGUOUS cases

- `GC-02-2022-11-03` pq=enter — ticker_setup_or_journal_mention; side_mismatch pred=short gt=long
- `GC-05-2023-01-05` pq=enter — ticker_setup_or_journal_mention; side_mismatch pred=short gt=long
- `GC-10-2023-04-21` pq=enter — conflict_no_trade_language_present_but_ticker_setup_also
- `GC-17-2024-01-29` pq=size — ticker_setup_or_journal_mention; side_mismatch pred=short gt=long; exact_size_pct_not_in_priors gt=16.0 (expected: size on banned fill)
- `GC-18-2024-03-06` pq=size — ticker_setup_or_journal_mention; exact_size_pct_not_in_priors gt=24.0 (expected: size on banned fill)
- `GC-19-2024-03-15` pq=enter — conflict_no_trade_language_present_but_ticker_setup_also
- `GC-20-2024-07-30` pq=size — ticker_setup_or_journal_mention; exact_size_pct_not_in_priors gt=15.0 (expected: size on banned fill)
- `GC-23-2024-09-25` pq=enter — ticker_setup_or_journal_mention; side_mismatch pred=long gt=short
- `GC-26-2025-01-06` pq=enter — ticker_setup_or_journal_mention
- `GC-31-2025-03-10` pq=enter — conflict_no_trade_language_present_but_ticker_setup_also
- `GC-33-2025-03-17` pq=size — conflict_no_trade_language_present_but_ticker_setup_also; exact_size_pct_not_in_priors gt=3.0 (expected: size on banned fill)
- `GC-34-2025-04-11` pq=enter — conflict_no_trade_language_present_but_ticker_setup_also
- `GC-35-2025-04-17` pq=enter — conflict_no_trade_language_present_but_ticker_setup_also
- `GC-36-2025-04-22` pq=enter — conflict_no_trade_language_present_but_ticker_setup_also
- `GC-40-2026-03-26` pq=enter — conflict_no_trade_language_present_but_ticker_setup_also
- `GC-42-2026-08-25` pq=size — ticker_setup_or_journal_mention; exact_size_pct_not_in_priors gt=18.0 (expected: size on banned fill)

## Per-case table

| case_id | pq | conflict | integrity | oracle | CFP |
|---|---|---|---|---|---|
| GC-01-2022-10-03 | exit | — | OK | pass | — |
| GC-02-2022-11-03 | enter | — | OK | ambiguous | — |
| GC-03-2022-11-15 | enter | — | OK | pass | — |
| GC-04-2022-12-09 | abstain | — | OK | pass | — |
| GC-05-2023-01-05 | enter | — | OK | ambiguous | — |
| GC-06-2023-02-02 | enter | — | OK | pass | — |
| GC-07-2023-03-09 | enter | C9_sidelines_then_entries | OK | pass | — |
| GC-08-2023-03-14 | enter | — | OK | pass | — |
| GC-09-2023-03-19 | abstain | — | OK | pass | — |
| GC-10-2023-04-21 | enter | C4_report_no_focuslist_vs_equity_trades | OK | ambiguous | — |
| GC-11-2023-05-23 | enter | C4_report_no_focuslist_vs_equity_trades | OK | pass | — |
| GC-12-2023-06-22 | manage | C8_journal_admits_mistake_vs_trade_log | OK | pass | — |
| GC-13-2023-07-28 | manage | near_conflict_invalidation_vs_same_day_adds | OK | pass | — |
| GC-14-2023-09-07 | enter | C10_rulebook_shorts_disabled_vs_practice | OK | pass | — |
| GC-15-2023-09-21 | enter | C5_report_no_FL_vs_new_shorts | OK | fail | — |
| GC-16-2023-11-09 | size | — | OK | pass | — |
| GC-17-2024-01-29 | size | pilot_language_vs_large_size | OK | ambiguous | — |
| GC-18-2024-03-06 | size | — | OK | ambiguous | — |
| GC-19-2024-03-15 | enter | C3_no_new_longs_narrative_vs_new_short | OK | ambiguous | — |
| GC-20-2024-07-30 | size | — | OK | ambiguous | — |
| GC-21-2024-08-01 | enter | worst_breadth_vs_large_longs | OK | pass | — |
| GC-22-2024-08-30 | size | — | OK | pass | — |
| GC-23-2024-09-25 | enter | — | OK | ambiguous | — |
| GC-24-2024-10-17 | enter | — | OK | pass | — |
| GC-25-2024-12-10 | enter | C6_report_no_FL_vs_longs | OK | pass | — |
| GC-26-2025-01-06 | enter | C7_report_nothing_excites_vs_CIEN | OK | ambiguous | — |
| GC-27-2025-01-07 | enter | C7_report_nothing_excites_vs_entry | OK | pass | — |
| GC-28-2025-03-04 | abstain | — | OK | pass | — |
| GC-29-2025-03-05 | enter | C1_journal_no_trade_plan_vs_equity_entry | OK | fail | — |
| GC-30-2025-03-07 | abstain | — | OK | pass | — |
| GC-31-2025-03-10 | enter | journal_narrative_vs_equity_entries | OK | ambiguous | — |
| GC-32-2025-03-13 | enter | — | OK | pass | — |
| GC-33-2025-03-17 | size | journal_not_in_hurry_vs_multi_pilots | OK | ambiguous | — |
| GC-34-2025-04-11 | enter | C10_rulebook_shorts_disabled_vs_practice | OK | ambiguous | — |
| GC-35-2025-04-17 | enter | C10_rulebook_shorts_disabled_vs_practice | OK | ambiguous | — |
| GC-36-2025-04-22 | enter | journal_gameplan_vs_equity_entry | OK | ambiguous | — |
| GC-37-2025-05-20 | manage | C2_journal_no_trades_vs_multiple_equity_actions | OK | pass | — |
| GC-38-2025-08-05 | exit | — | OK | pass | — |
| GC-39-2025-11-06 | exit | — | OK | pass | — |
| GC-40-2026-03-26 | enter | C10_rulebook_shorts_disabled_vs_practice | OK | ambiguous | — |
| GC-41-2026-04-29 | manage | — | OK | pass | — |
| GC-42-2026-08-25 | size | — | OK | ambiguous | — |
| GC-43-2026-08-28 | exit | — | OK | pass | — |
| GC-44-2026-09-02 | manage | — | OK | pass | — |
| GC-45-2026-09-03 | manage | — | OK | pass | — |
| GC-46-2026-09-10 | exit | — | OK | pass | — |
| GC-47-2026-09-14 | enter | — | OK | pass | — |
| GC-48-2026-09-15 | enter | — | OK | pass | — |

## Blockers / handoff

1. **No behavioral decision model in repo yet** — do not treat this as OOS model performance.
2. **Paper authority NOT unlocked**; capital 0; no live/paper orders from this audit.
3. Exact `size%` usually lives on the banned fill message — size axis will stay ambiguous until a model+prior size intent exists.
4. Conflict goldens (esp. GC-29 C1, GC-37 C2) are intentional scars: sealed priors say no-trade; GT is enter/manage.
5. GC-04 soft flag only — not a freeze blocker.
6. Quant fill-fidelity M0 (5/5) is orthogonal; this scorecard is behavioral/fixture only.

## Paths

- Scorecard: `/workspace/alexrag/results/BEHAVIORAL_GOLDEN48_SCORECARD.md`
- JSON: `/workspace/alexrag/results/behavioral_golden48_scores.json`

*End of BASELINE_ORACLE / FIXTURE_AUDIT scorecard.*
