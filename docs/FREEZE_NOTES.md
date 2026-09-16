# FREEZE_NOTES — golden_cases_v0_frozen

**Freeze date (PT):** 2026-09-15
**Ingest:** Mac `/Users/n_mac/Documents/AlexRag202609/data/ingest/*.jsonl` (post DiscordChatExporter `title=` timestamp parser fix).
**Counts:** equity-trades 6664 / alex-journal 5471 / prime-report 3062 / pf-update 1428 (100% with_ts; inherited flags rare: journal 1, report 1, pf-update 2, equity 0).
**Message IDs:** taken from current JSONL `id` fields (stable snowflakes); not re-parsed from HTML.

## Resolution rules

1. **enter / size:** `decision_ts` = earliest same-day equity-trades msg matching case tickers with Long/Short (or pilot) grammar.
2. **exit:** earliest same-day Closed/Sold/Stopped matching tickers.
3. **manage:** earliest ADD/trim/SL-move/reopen (etc.) matching tickers; else exit/enter fallback.
4. **abstain:** `decision_ts` = announcing no-trade journal/report `ts + 1s` (so the plan message is eligible); else prior-evening report + 06:30 PT; else 13:00 PT end-of-entry-window default.
5. **eligible_filter:** MVP channels + `ts < decision_ts`. Full ID lists not stored.
6. **banned_same_day_ids:** all MVP msgs on `date_pt` with `ts >= decision_ts` (especially post-fill journal rationalizations).
7. **key_evidence_ids:** ≤40 ranked priors (same-day/preferred sources/ticker/no-trade language/pf-update).

## Timestamp quality

- Minute precision only (exporter title clock). Same-minute ties broken by message_id.
- No missing timestamps after title= fix. Prefer current JSONL over re-export.
- `ts_inherited` nearly always false now; a handful remain (journal/report/pf).
- No dedicated `edited` field; literal `(edited)` may appear inside `text`.

## Summary

- Cases: 48
- Fully resolved: 48
- Cases with any freeze_blockers flag: 1

## Per-case blockers / notes

- **GC-04-2022-12-09** resolved=True decision_ts=2022-12-09T06:36:01-08:00 method=abstain_plan_or_default blockers=['abstain_case_has_same_day_equity_msgs']

## pf_update_fixtures

Candidate notes from the Research pack now have up to 5 prior `pf-update` message_ids attached (`candidate_notes_resolved` in frozen JSON). Portfolio/state only — fills GT remains equity-trades.

## Outputs

- `/workspace/alexrag/golden_cases_v0_frozen.json`
- `/workspace/alexrag/INGEST_SCHEMA.md`
- `/workspace/alexrag/FREEZE_NOTES.md`

## Soft notes (still fully_resolved)

- **GC-04-2022-12-09**: Rejected-setup abstain on GFS while ARRY/KGC/etc. traded same day. `abstain_case_has_same_day_equity_msgs` is informational; `decision_ts` = journal pass `2022-12-09T06:36:01-08:00`.
- **GC-07-2023-03-09**: Inventory conflict label is sidelines→entries; tape order is FOUR/PATH entries @06:46 then journal “sidelines rest of day” @08:24. Freeze scores `enter` at first FOUR fill; post-entry sidelines language is banned.
- **GC-29 / GC-37**: Morning no-trade journals are in `key_evidence` (ts < decision_ts); same-day post-fill rationalizations are in `banned_same_day_ids`.

## Parser / timestamp issues

- Post-`title=` fix ingest: **0 missing timestamps** across all four MVP channels.
- Minute precision only; DST offsets `-07:00` / `-08:00` present and correct.
- Prefer current JSONL message IDs (stable). Do not re-mint from HTML for sealed cutoff.
