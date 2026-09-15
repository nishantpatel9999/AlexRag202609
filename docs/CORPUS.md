# Corpus inventory (research) — operator paths + retrieval precedence

MVP **does not** ingest Mac Studio export paths. This file is the inventory
and conflict/precedence spec. Runtime still uses `tests/fixtures` only.

Full channel HTML lives on the operator Mac (DiscordChatExporter). Do not copy
those trees into this repo.

## Discord channels (DiscordChatExporter HTML)

Timestamps are **America/Los_Angeles (PT)**. Treat naive / missing-offset
datetimes as `America/Los_Angeles` unless the export already has an offset.
DiscordChatExporter omits `<time datetime>` on follow-on messages;
**timestamps inherit across messages and message groups** from the last seen
datetime.

### In MVP

| Channel | `source_type` | Approx msgs | Role |
| --- | --- | ---: | --- |
| equity-trades | `trade_log` | 6664 | Text tape / fills / closes. **Ground truth** when sources disagree. |
| alex-journal | `journal` | 5471 | Chart-heavy same-session notes. |
| prime-report | `report` | 3062 | Evening focuslists. |
| pf-update | `pf_update` | (count TBD) | **Portfolio snapshots** (NAV / DD / positions). **Not a fill log.** Never overrides tape. |
| morning gameplan | `gameplan` | (split TBD) | Morning plan stream. Label exists even if it still sits inside journal exports until split. |

pf-update on the operator Mac (not read by MVP; inventory only):

```text
/Users/n_mac/DiscordArchives/PrimeTrading/PrimeTrading - Alex - 📒pf-update [1019259954101747753].html
/Users/n_mac/DiscordArchives/PrimeTrading/PrimeTrading - Alex - 📒pf-update [1019259954101747753]_Files
```

Other in-MVP Discord exports (example layout — not read by MVP):

```text
<mac-exports>/equity-trades/*.html
<mac-exports>/alex-journal/*.html
<mac-exports>/prime-report/*.html
```

### Out of MVP

| Channel | Notes |
| --- | --- |
| focuslist-ideas | **Out of MVP.** Do not ingest. |

## Doctrine (not a local GitBook mirror)

There is **no** GitBook clone in-tree or on disk as a source of truth.
**No full offline GitBook scrape for MVP.**

| Source | How it is used |
| --- | --- |
| Live GitBook | Doctrine, fetched later — not mirrored locally in MVP |
| `PRIMETRADING_RULEBOOK_DISTILLATION.md` | Distilled rulebook (operator file) |
| `PrimeTrading_Ebook.pdf` | Ebook doctrine (operator file; PDF parse is out of MVP) |

`ingest-gitbook` on a local directory is a **fixture stub** only (tiny playbook markdown under `tests/fixtures/gitbook`). It must not be treated as a GitBook dump of the live book.

## Precedence when sources conflict

Highest wins:

1. **equity fills/closes** (`trade_log` / equity-trades) — tape is ground truth
2. **same-time journal** (`journal` / alex-journal)
3. **morning gameplan** (`gameplan`)
4. **evening prime-report** (`report`)
5. **pf-update portfolio snapshots** (`pf_update`) — account-state context only; **not a fill log**; never outranks tape/journal/gameplan/report on fills
6. **GitBook doctrine-only** (`gitbook`) — qualitative rules, never overrides tape

Config: `retrieval.precedence` in `config/default.yaml`.

pf-update may later inform paper-book diagnostics (NAV / daily loss / portfolio DD). It is **not** enter-evidence for a fill.

## Conflicts are first-class

Conflicts are common, not anomalies. Typical patterns:

- No-trade / wait plan, then entries the same session
- Shorts vs rulebook default (often long-biased doctrine)

Machine labels on `Proposal.conflict_labels` and eval notes:

| Label | Meaning |
| --- | --- |
| `no_trade_plan_then_entry` | Gameplan/journal said stay flat; tape shows fills |
| `short_vs_rulebook_default` | Tape/journal short vs doctrine default |
| `fill_vs_same_time_journal` | Fill tape disagrees with simultaneous journal |
| `gameplan_vs_tape` | Morning plan vs later fills |
| `evening_report_vs_intraday` | Prime-report focuslist vs what traded |
| `doctrine_vs_tape` | GitBook/ebook rule vs fills |

## 48 golden cases (Eval Spec V0)

Canonical pack: [`eval/golden_cases_v0.json`](../eval/golden_cases_v0.json).
Spec: [`docs/EVAL_SPEC_V0.md`](EVAL_SPEC_V0.md).

MVP loads and validates all 48 offline and scores enter/abstain/size/manage/exit
plus citation coverage when a prediction is supplied. **No P&L.** Evidence must
have `timestamp < decision_ts`. Post-fill journal/doctrine/pf-update cannot justify enter.

Session dates and tickers are filled from Discord exports later — do not invent
indicator numbers.
