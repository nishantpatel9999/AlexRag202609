from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PaperMetrics:
    sessions: int
    decisions: int
    abstain_count: int
    cited_decisions: int
    timestamped_citation_decisions: int

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


def paper_window_met(
    sessions: int,
    decisions: int,
    *,
    min_sessions: int = 60,
    min_decisions: int = 100,
) -> bool:
    """Default paper window: ≥60 sessions OR 100 decisions. Not a calendar date."""

    return sessions >= min_sessions or decisions >= min_decisions
