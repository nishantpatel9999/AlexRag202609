from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PaperMetrics:
    """Paper-window and citation/abstain/conflict rates. See docs/CORPUS.md and RISK_GATES.md.

    ``sessions`` and ``decisions`` are **diagnostics**, not a promotion hard floor.
    """

    sessions: int
    decisions: int
    abstain_count: int
    cited_decisions: int
    timestamped_citation_decisions: int
    # First-class corpus conflicts (docs/CORPUS.md). Counted in a later eval pack.
    conflict_decisions: int = 0
    citation_faithful_decisions: int = 0
    hindsight_decisions: int = 0

    @property
    def abstain_rate(self) -> float:
        if self.decisions == 0:
            return 0.0
        return self.abstain_count / self.decisions

    @property
    def citation_rate(self) -> float:
        if self.decisions == 0:
            return 0.0
        return self.cited_decisions / self.decisions

    @property
    def timestamped_citation_rate(self) -> float:
        if self.decisions == 0:
            return 0.0
        return self.timestamped_citation_decisions / self.decisions

    @property
    def conflict_rate(self) -> float:
        if self.decisions == 0:
            return 0.0
        return self.conflict_decisions / self.decisions


def paper_window_met(
    sessions: int,
    decisions: int,
    *,
    min_sessions: int = 60,
    min_decisions: int = 100,
) -> bool:
    """Legacy ≥60 sessions OR 100 decisions check.

    Diagnostic only — not a promotion hard floor. Calendar time never promotes.
    """

    return sessions >= min_sessions or decisions >= min_decisions


def paper_run_diagnostics(
    sessions: int,
    decisions: int,
    *,
    min_sessions: int = 60,
    min_decisions: int = 100,
) -> dict:
    """Session/decision counters for audit payloads. Not a gate."""

    return {
        "sessions": sessions,
        "decisions": decisions,
        "min_sessions": min_sessions,
        "min_decisions": min_decisions,
        "meets_legacy_session_or_decision_threshold": paper_window_met(
            sessions,
            decisions,
            min_sessions=min_sessions,
            min_decisions=min_decisions,
        ),
        "paper_window_hard_floor": False,
        "calendar_promotes": False,
        "counters_are_diagnostics": True,
    }
