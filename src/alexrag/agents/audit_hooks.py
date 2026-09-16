"""Per-decision promotion-review flags on the audit trail. Paper-only."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from alexrag.eval.cutoff import enter_evidence_illegal, sealed_ok
from alexrag.schemas.proposal import Proposal


def promotion_review_hooks(
    proposal: Proposal,
    *,
    fill_ts: datetime | None = None,
    replay_case_id: str | None = None,
) -> dict[str, Any]:
    """citation_faithfulness, hindsight, replay_case_id for promotion review."""

    case_id = replay_case_id or proposal.replay_case_id
    if not proposal.citations:
        return {
            "citation_faithfulness": False,
            "hindsight": False,
            "replay_case_id": case_id,
        }

    hindsight = False
    faithful = True
    for cite in proposal.citations:
        sealed = sealed_ok(cite.timestamp, proposal.decision_clock)
        if cite.timestamp is None or not sealed:
            faithful = False
        illegal = enter_evidence_illegal(
            timestamp=cite.timestamp,
            source_type=cite.source_type,
            decision_ts=proposal.decision_clock,
            fill_ts=fill_ts,
        )
        if illegal:
            hindsight = True
            faithful = False
    return {
        "citation_faithfulness": faithful,
        "hindsight": hindsight,
        "replay_case_id": case_id,
    }


def apply_promotion_hooks(
    proposal: Proposal,
    *,
    fill_ts: datetime | None = None,
    replay_case_id: str | None = None,
) -> dict[str, Any]:
    hooks = promotion_review_hooks(
        proposal, fill_ts=fill_ts, replay_case_id=replay_case_id
    )
    proposal.citation_faithfulness = hooks["citation_faithfulness"]
    proposal.hindsight = hooks["hindsight"]
    if hooks["replay_case_id"] is not None:
        proposal.replay_case_id = hooks["replay_case_id"]
    return hooks
