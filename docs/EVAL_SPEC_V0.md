# Eval Spec V0 — golden pack + sealed cutoff

Offline evaluation for AlexRag202609. **No P&L** in MVP. **No live trading.**
This document is the V0 eval contract. The research attachment was not present
in the agent workspace; axes, cutoff, and the 48-case pack shape are locked
from that brief plus `docs/CORPUS.md`.

Pack file: [`eval/golden_cases_v0.json`](../eval/golden_cases_v0.json).

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

- Naive timestamps are `America/Los_Angeles` (see `docs/CORPUS.md`).
- Missing timestamps **do not** qualify as sealed (fail-closed for that citation).
- Equality is excluded: `timestamp == decision_ts` is **not** allowed.

`decision_ts` is the case clock (and the orchestrator `decision_clock` when the
harness is scoring a live paper-day proposal).

## 3. Post-fill rationalization is banned as enter-evidence

A fill/close on the tape is not a reason to have entered. Journal, gameplan,
prime-report, or doctrine written **at or after** `fill_ts` (or `decision_ts` if
`fill_ts` is absent) **must not** be cited to justify `enter`.

Allowed after fill: **manage** and **exit** scoring may cite the fill itself and
later tape. Enter/abstain-before-entry may not.

## 4. Conflict labels (first-class)

Cases carry `conflict_label` from `docs/CORPUS.md`. Conflicts are scored as
labels, not merged away.

Precedence when sources disagree remains:

fills/closes → same-time journal → morning gameplan → evening prime-report → pf-update (portfolio snapshots, **not** a fill log) → GitBook doctrine-only.

## 5. Pack layout (48 cases)

`eval/golden_cases_v0.json`:

- `version`: `v0`
- `n_cases`: 48
- `score_axes`: enter, abstain, size, manage, exit, citation
- `cases[]`: `golden-01` … `golden-48`
- eight cases per conflict label; primary axes cycle the six score axes

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
- Invented prices, NER sizes, or indicators
- Ingest of operator Mac corpus trees
