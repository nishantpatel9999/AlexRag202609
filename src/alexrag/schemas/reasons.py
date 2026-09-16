"""Closed set of paper-only abstain reasons. Live mode is not in this enum."""

from __future__ import annotations

from enum import StrEnum


class AbstainReason(StrEnum):
    """Fail-closed reasons Risk, Exec, Auditor, and the orchestrator may emit."""

    UNINITIALIZED = "uninitialized"
    PIPELINE_START = "pipeline_start"
    NON_PAPER_MODE = "non_paper_mode"
    KILL_SWITCH = "kill_switch"  # legacy alias; prefer KILL_SWITCH_FAIL
    KILL_SWITCH_FAIL = "kill_switch_fail"
    MISSING_AUDIT = "missing_audit"
    STALE_FEED = "stale_feed"
    EMPTY_RETRIEVAL = "empty_retrieval"
    LOW_RETRIEVAL_CONFIDENCE = "low_retrieval_confidence"
    NO_CITATIONS = "no_citations"
    CITATIONS_MISSING_TIMESTAMPS = "citations_missing_timestamps"
    NO_TICKERS_IN_CITATIONS = "no_tickers_in_citations"
    UNKNOWN_REGIME = "unknown_regime"
    HARD_LIMITS_UNCONFIGURED = "hard_limits_unconfigured"
    INVALID_SIZE = "invalid_size"
    DAILY_LOSS_BREACH = "daily_loss_breach"
    PORTFOLIO_DD_BREACH = "portfolio_dd_breach"
    UNEXPLAINED_ORDER = "unexplained_order"
    MISSING_TICKER = "missing_ticker"
    MISSING_SIDE = "missing_side"
    CANNOT_SIZE = "cannot_size"
    MISSING_REF_PX = "missing_ref_px"
    PROPOSAL_ABSTAIN = "proposal_abstain"
    AUDIT_INCOMPLETE = "audit_incomplete"
    GO_INTENT_INCOMPLETE = "go_intent_incomplete"
    NON_PAPER_FILL = "non_paper_fill"
    RECEIPT_INCONSISTENT = "receipt_inconsistent"


# Quant-required names plus the rest of the closed set.
REQUIRED_ABSTAIN_REASONS = (
    AbstainReason.STALE_FEED,
    AbstainReason.MISSING_AUDIT,
    AbstainReason.DAILY_LOSS_BREACH,
    AbstainReason.PORTFOLIO_DD_BREACH,
    AbstainReason.KILL_SWITCH_FAIL,
    AbstainReason.UNEXPLAINED_ORDER,
)

ABSTAIN_REASONS = tuple(AbstainReason)


def as_abstain_reason(value: str | AbstainReason | None) -> AbstainReason | None:
    if value is None:
        return None
    return AbstainReason(value)
