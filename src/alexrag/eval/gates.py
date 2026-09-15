"""Promotion gate helpers. Paper→live is gate-driven; this repo has no live path."""

from __future__ import annotations

from alexrag.config import Settings
from alexrag.eval.metrics import PaperMetrics, paper_window_met


def evaluate_promotion_readiness(metrics: PaperMetrics, settings: Settings) -> dict:
    window = paper_window_met(
        metrics.sessions,
        metrics.decisions,
        min_sessions=settings.paper_gates.min_sessions,
        min_decisions=settings.paper_gates.min_decisions,
    )
    return {
        "paper_window_met": window,
        "kill_switch": settings.kill_switch,
        "live_allowed": False,
        "reason": "MVP has no live trading path; promotion is documented in docs/RISK_GATES.md",
        "golden_cases_reserved": 48,
        "metrics": {
            "sessions": metrics.sessions,
            "decisions": metrics.decisions,
            "abstain_rate": metrics.abstain_rate,
            "citation_rate": metrics.citation_rate,
            "timestamped_citation_rate": metrics.timestamped_citation_rate,
            "conflict_rate": metrics.conflict_rate,
        },
    }
