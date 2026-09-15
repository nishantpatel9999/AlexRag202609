# Risk gates — paper promotion (not a live date)

Paper→live is **gate-driven**, not calendar-driven. This repository **does not** contain a live trading path. Meeting a gate does not flip `mode` to live; that would be a separate, explicit spec and code change.

There is **no target go-live date** in this project.

## Always-on controls (MVP and later)

| Control | Behavior |
| --- | --- |
| Kill switch | `ALEXRAG_KILL_SWITCH=true` → immediate abstain, Exec skipped |
| Coded hard limits | `max_notional`, `max_positions`, `max_daily_loss`, `max_portfolio_dd` must be present and operator-set; `≤0` notional/positions blocks go-decisions |
| Fail-closed stale feed | Newest citation timestamp missing or older than `stale_after_hours` vs `decision_clock` → `abstain` |
| Fail-closed missing audit | Audit path missing or unwritable → `abstain` (no Exec) |
| Fail-closed retrieval | Confidence `< min_confidence` → `abstain` |
| Citations | Go-decisions require citations **with timestamps** |

## Minimum paper window (default)

Promotion **discussion** is allowed only after:

- **≥ 60 paper sessions**, **or**
- **≥ 100 paper decisions**

Implemented in `alexrag.eval.metrics.paper_window_met`. This is a **necessary** condition, not a sufficient one, and **not a date**.

## Metrics that must be reported before any promotion review

| Metric | Intent |
| --- | --- |
| Replay | Same fixtures / session tapes produce stable abstain vs go (no silent drift) |
| Citation | Share of decisions with at least one citation; share with **timestamped** citations |
| Abstain | Abstain rate overall and by reason (`kill_switch`, `stale_feed`, `missing_audit`, `low_retrieval_confidence`, …) |
| Conflict | Share of decisions with first-class `conflict_labels`. 48 golden cases: `eval/golden_cases_v0.json` / `docs/EVAL_SPEC_V0.md` (enter/abstain/size/manage/exit + citation; no P&L). Sealed cutoff: evidence `timestamp < decision_ts`; post-fill rationalization banned as enter-evidence. |

Helpers live in `alexrag.eval`. Thresholds for “good enough” replay/citation/abstain are **not** invented here; a future eval spec must set them from observed paper data.

## Paper fill fidelity (M0, not a promotion metric)

Offline paper fills use model **M0**: mark-to-next-available fixture bar/mid, **0bps** scar labeled (`docs/FILL_FIDELITY_M0.md`). `stubbed` (Alpaca paper without keys) is **not** `filled`. Default `hard_limits` stay `0` (fail-closed); `config/fixture.yaml` is the non-zero operator file for Exec replay. **No P&L gate.** **No live path.**

## What does *not* satisfy a gate

- A calendar reminder or “we have been in paper for N weeks”
- A non-zero win rate without citation/audit coverage
- Operator override of fail-closed (`fail_closed=false` is ignored in MVP)
- Filling in vision, Alpaca, Discord, or TradingView TODOs without the paper window and metrics

## After the window

Even if `paper_window_met` is true:

1. Kill switch and hard limits remain in force.
2. Live mode remains unimplemented.
3. A promotion review must still show replay + citation + abstain metrics and fail-closed behavior under stale feed / missing audit drills.
