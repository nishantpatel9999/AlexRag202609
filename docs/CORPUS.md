# Corpus inventory (research) — operator paths + retrieval precedence

MVP **does not** ingest Mac Studio export paths. This file is the inventory
and conflict/precedence spec. Runtime still uses `tests/fixtures` only.

Full channel HTML lives on the operator Mac (DiscordChatExporter). Do not copy
those trees into this repo.

## Discord channels (DiscordChatExporter HTML)

Treat naive timestamps as **America/Los_Angeles** unless the export already
has an offset. DiscordChatExporter omits `<time datetime>` on follow-on
messages; **timestamps inherit across messages and message groups** from the
last seen datetime.

| Channel | `source_type` | Approx msgs | Role |
| --- | --- | ---: | --- |
| equity-trades | `trade_log` | 6664 | Text tape / fills / closes. **Ground truth** when sources disagree. |
| alex-journal | `journal` | 5471 | Chart-heavy same-session notes. |
| prime-report | `report` | 3062 | Evening focuslists. |
| morning gameplan | `gameplan` | (split TBD) | Morning plan stream. Label exists even if it still sits inside journal exports until split. |

Operator-local layout (example only — not read by MVP):

```text
<mac-exports>/equity-trades/*.html
<mac-exports>/alex-journal/*.html
<mac-exports>/prime-report/*.html
```

## Doctrine (not a local GitBook mirror)

There is **no** GitBook clone in-tree or on disk as a source of truth.

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
5. **GitBook doctrine-only** (`gitbook`) — qualitative rules, never overrides tape

Config: `retrieval.precedence` in `config/default.yaml`.

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

## 48 golden cases (later eval pack)

A 48-case eval pack is reserved. Stub IDs live in `docs/eval/golden_cases_stub.md` and `alexrag.eval.golden_cases.stub_golden_cases()` (`golden-01` … `golden-48`). MVP does not score them. Future work should attach real session dates and citations from the Discord exports — still without inventing indicator numbers.
