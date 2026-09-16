# Eval Spec V0 — golden pack + sealed cutoff

Offline evaluation for AlexRag202609. **No P&L** in MVP. **No live trading.**

Pack file: [`eval/golden_cases_v0.json`](../eval/golden_cases_v0.json).
Corpus lock: [`docs/CORPUS.md`](CORPUS.md).

Research lock delta applied here (binary attachments were not present in the
agent workspace; this spec follows that lock and does **not** invent Discord
message IDs):

1. Doctrine MVP = **live GitBook** + `PRIMETRADING_RULEBOOK_DISTILLATION.md` + `PrimeTrading_Ebook.pdf` only — **no full scrape**.
2. Timezone = **America/Los_Angeles**, confirmed. Ingest is labeled **PT**.
3. **pf-update is in MVP** (~1428 msgs): portfolio/state only, **not** fills ground truth. **equity-trades remains #1** in precedence. **focuslist-ideas stays OOS**.

## 1. What is scored

Each golden case may name a **primary axis**. The harness scores all of:

| Axis | Pass when |
| --- | --- |
| `enter` | Predicted enter matches `expected.enter` when that field is set. Enter citations must be sealed (below). |
| `abstain` | Predicted abstain matches `expected.abstain` when set. |
| `size` | Predicted `size_ner_pct` matches `expected.size_ner_pct` when set. **Do not invent** a size if expected is null. |
| `manage` | Predicted manage label matches `expected.manage` when set. |
| `exit` | Predicted exit label matches `expected.exit` when set. |
| `citation` | At least `expected.min_citations` (default 1) citations with timestamps, all sealed. |

P&L, win rate, and slippage are **out of V0**.

Unset `expected.*` fields are **not scored** (null ≠ fail). Research session IDs,
tickers, and numeric sizes are filled later from Discord exports — still without
inventing indicator numbers.

## 2. Sealed chronological cutoff (hard)

Only evidence with **`timestamp < decision_ts`** may be used for a decision.

- Naive timestamps are `America/Los_Angeles` (**PT**). See `docs/CORPUS.md`.
- Missing timestamps **do not** qualify as sealed (fail-closed for that citation).
- Equality is excluded: `timestamp == decision_ts` is **not** allowed.

`decision_ts` is the case clock (and the orchestrator `decision_clock` when the
harness is scoring a live paper-day proposal).

## 3. Post-fill rationalization is banned as enter-evidence

A fill/close on the tape is not a reason to have entered. Journal, gameplan,
prime-report, **pf-update**, or doctrine written **at or after** `fill_ts` (or
`decision_ts` if `fill_ts` is absent) **must not** be cited to justify `enter`.

Allowed after fill: **manage** and **exit** scoring may cite the fill itself and
later tape. Enter/abstain-before-entry may not. pf-update is portfolio/state
context only and is never fills ground truth.

## 4. Conflict labels (first-class)

Cases carry `conflict_label` from `docs/CORPUS.md`. Conflicts are scored as
labels, not merged away.

Precedence when sources disagree remains:

**equity-trades (fills/closes, #1)** → same-time journal → morning gameplan → evening prime-report → **pf-update (portfolio/state, not a fill log)** → GitBook doctrine-only.

## 5. Pack layout (48 cases + pf_update_fixtures)

`eval/golden_cases_v0.json`:

- `version`: `v0`
- `n_cases`: 48
- `score_axes`: enter, abstain, size, manage, exit, citation
- `timezone`: `America/Los_Angeles` / `timezone_label`: `PT`
- `doctrine`: live GitBook + distillation.md + ebook.pdf; `gitbook_scrape`: false
- `mvp_channels` / `oos_channels` (focuslist-ideas OOS)
- `cases[]`: `golden-01` … `golden-48`
- eight cases per conflict label; primary axes cycle the six score axes
- **`pf_update_fixtures`**: reserved slots whose **`message_id` is `TBD`**. Do not invent concrete Discord IDs.

`status` is `schema_v0` until operator fills `decision_ts` / citations from Mac
exports. The harness still **loads and validates** all 48 offline.

## 6. Harness (MVP stub)

```bash
uv run alexrag eval-golden --pack eval/golden_cases_v0.json
```

Python:

```python
from alexrag.eval.harness import load_golden_pack, score_case, score_pack
from alexrag.eval.cutoff import sealed_ok, enter_evidence_illegal
```

MVP does **not** replay Mac HTML against the 48 cases. It loads the pack, applies
cutoff helpers, and scores a `Prediction` when one is supplied.

## 7. Non-goals (V0)

- Full paper trading loop
- P&L / expectancy
- Invented prices, NER sizes, indicators, or Discord message IDs
- Ingest of operator Mac corpus trees
- Full GitBook scrape
- focuslist-ideas
