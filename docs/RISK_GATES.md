# Risk gates — paper promotion (not a live date)

Paper→live is **gate-driven**, not calendar-driven. This repository **does not** contain a live trading path. Meeting a gate does not flip `mode` to live; that would be a separate, explicit spec and code change.

There is **no target go-live date** in this project.

## Always-on controls (MVP and later)

| Control | Behavior |
| --- | --- |
| Kill switch | `ALEXRAG_KILL_SWITCH=true` → `abstain_reason=kill_switch_fail`, Exec skipped |
| Coded hard limits | Nishant-locked: `max_positions=15`, `max_daily_loss_pct=0.10`, `max_portfolio_dd=0.25`, `max_notional_pct=1.0`. Dollar notional/daily-loss = `paper.nav * pct` at runtime. `paper.nav` ≤ 0 or pcts/positions ≤ 0 → `hard_limits_unconfigured`. Risk **enforces** daily loss (dollars vs 10% equity) and portfolio DD (fraction vs 25%) against `paper_book` (`daily_loss_breach` / `portfolio_dd_breach`) — not snapshot-only. |
| Fail-closed stale feed | Newest citation vs `decision_clock` older than `stale_after_hours` → `stale_feed` (orchestrator **and** RiskAgent) |
| Fail-closed missing audit | Audit path missing or unwritable → `missing_audit` (no Exec) |
| Fail-closed retrieval | Confidence `< min_confidence` → `low_retrieval_confidence` |
| Citations | Go-decisions require timestamped citations. Sealed citations must evidence side or Risk emits `unexplained_order`. |

Closed `abstain_reason` set: `alexrag.schemas.reasons.AbstainReason` (includes `stale_feed`, `missing_audit`, `daily_loss_breach`, `portfolio_dd_breach`, `kill_switch_fail`, `unexplained_order`, plus existing reasons).

## Paper-run counters (diagnostics, not a hard floor)

`sessions` and `decisions` (`paper_gates.min_sessions` / `min_decisions`, default 60 / 100) are **diagnostics** reported on `PaperMetrics` and audit `paper_day_complete` payloads. They are **not** a promotion hard floor.

Implemented in `alexrag.eval.metrics.paper_window_met` / `paper_run_diagnostics`. `paper_window_met` remaining true is **not sufficient** and **not required**.

## Nishant override

Approximately **2 weeks of clean paper** may be enough to **discuss** promotion **if fidelity gates pass** (replay, citation faithfulness, abstain-reason coverage, fail-closed drills, M0 fill fidelity). `min_sessions` / `min_decisions` do **not** block that review. **Calendar time alone never promotes.**

## Metrics that must be reported before any promotion review

| Metric | Intent |
| --- | --- |
| Replay | Same fixtures / session tapes produce stable abstain vs go (no silent drift). Audit carries `replay_case_id`. |
| Citation | Share of decisions with timestamped citations; per-decision `citation_faithfulness` |
| Hindsight | Per-decision `hindsight` flag (unsealed or post-fill enter-evidence) |
| Abstain | Abstain rate overall and by closed `abstain_reason` |
| Conflict | Share of decisions with first-class `conflict_labels`. 48 golden cases: `eval/golden_cases_v0.json` / `docs/EVAL_SPEC_V0.md` (enter/abstain/size/manage/exit + citation; no P&L). Sealed cutoff: evidence `timestamp < decision_ts`; post-fill rationalization banned as enter-evidence. |

Helpers live in `alexrag.eval`. Thresholds for “good enough” replay/citation/abstain are **not** invented here; a future eval spec must set them from observed paper data.

## Paper fill fidelity (M0, not a P&L gate)

Offline paper fills use model **M0**: mark-to-next-available fixture bar/mid, **0bps** scar labeled (`docs/FILL_FIDELITY_M0.md`). `stubbed` (Alpaca paper without keys/network) is **not** `filled`. Operator pcts are locked in `config/default.yaml`; `paper.nav` defaults to `0` (fail-closed dollar derivation). `config/fixture.yaml` sets `paper.nav` for Exec replay. **No P&L gate.** **No live path.**

## What does *not* satisfy a gate

- A calendar reminder or “we have been in paper for N weeks” (including the ~2 week override **without** fidelity)
- Hitting 60 sessions or 100 decisions as if that were a hard floor
- A non-zero win rate without citation/audit coverage
- Operator override of fail-closed (`fail_closed=false` is ignored in MVP)
- Filling in vision, Alpaca, Discord, or TradingView TODOs without fidelity metrics

## After a clean paper window (diagnostic or ~2 weeks)

Even then:

1. Kill switch and hard limits remain in force.
2. Live mode remains unimplemented.
3. A promotion review must still show replay + citation faithfulness + abstain metrics, `hindsight` coverage, and fail-closed behavior under stale feed / missing audit / daily-loss / DD drills.
