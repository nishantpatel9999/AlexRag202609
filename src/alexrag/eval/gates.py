"""Promotion gate helpers. Paper→live is gate-driven; this repo has no live path."""

from __future__ import annotations

from alexrag.config import Settings
from alexrag.eval.metrics import PaperMetrics, paper_run_diagnostics, paper_window_met

NISHANT_OVERRIDE = (
    "Approximately 2 weeks of clean paper may promote IF fidelity gates pass. "
    "min_sessions/min_decisions are diagnostics, not a hard floor. "
    "Calendar time alone never promotes."
)


def evaluate_promotion_readiness(metrics: PaperMetrics, settings: Settings) -> dict:
    window = paper_window_met(
        metrics.sessions,
        metrics.decisions,
        min_sessions=settings.paper_gates.min_sessions,
        min_decisions=settings.paper_gates.min_decisions,
    )
    diagnostics = paper_run_diagnostics(
        metrics.sessions,
        metrics.decisions,
        min_sessions=settings.paper_gates.min_sessions,
        min_decisions=settings.paper_gates.min_decisions,
    )
    return {
        "paper_window_met": window,
        "paper_window_hard_floor": False,
        "calendar_promotes": False,
        "nishant_override": NISHANT_OVERRIDE,
        "fidelity_gates_required": True,
        "kill_switch": settings.kill_switch,
        "live_allowed": False,
        "reason": "MVP has no live trading path; promotion is documented in docs/RISK_GATES.md",
        "golden_cases_reserved": 48,
        "diagnostics": diagnostics,
        "metrics": {
            "sessions": metrics.sessions,
            "decisions": metrics.decisions,
            "sessions_decisions_role": "diagnostic",
            "abstain_rate": metrics.abstain_rate,
            "citation_rate": metrics.citation_rate,
            "timestamped_citation_rate": metrics.timestamped_citation_rate,
            "conflict_rate": metrics.conflict_rate,
            "citation_faithful_decisions": metrics.citation_faithful_decisions,
            "hindsight_decisions": metrics.hindsight_decisions,
        },
    }
