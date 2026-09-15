"""Deterministic Proposal → FillIntent mapping. Paper-only; no invented slippage."""

from __future__ import annotations

import uuid

from alexrag.agents.extract import extract_invalidation, extract_limit_px, extract_side
from alexrag.eval.cutoff import sealed_ok
from alexrag.schemas.fill_intent import FillIntent
from alexrag.schemas.proposal import Proposal


def sealed_citation_text(proposal: Proposal) -> str:
    parts = [
        c.excerpt
        for c in proposal.citations
        if sealed_ok(c.timestamp, proposal.decision_clock)
    ]
    return "\n".join(parts)


def notional_from_ner(
    size_ner_pct: float,
    paper_nav: float,
    max_notional: float,
) -> float:
    """Map citation NER percent to notional, clipped to operator max_notional."""

    if size_ner_pct <= 0 or paper_nav <= 0 or max_notional <= 0:
        return 0.0
    raw = paper_nav * (size_ner_pct / 100.0)
    return min(raw, max_notional)


def proposal_to_intent(
    proposal: Proposal,
    *,
    paper_nav: float,
    max_notional: float,
    fallback_ref_px: float | None,
    intent_id: str | None = None,
) -> FillIntent:
    """Build a FillIntent. Go intents are fully specified; holes become abstain/skip."""

    iid = intent_id or str(uuid.uuid4())
    clock = proposal.decision_clock
    ticker = proposal.tickers[0] if proposal.tickers else None
    sealed = sealed_citation_text(proposal)
    side = extract_side(sealed)
    limit_px = extract_limit_px(sealed)
    invalidation = extract_invalidation(sealed)
    if limit_px is not None:
        ref_px = limit_px
        ref_source = "sealed_limit"
        order_type: str | None = "limit"
    elif fallback_ref_px is not None and fallback_ref_px > 0:
        ref_px = fallback_ref_px
        ref_source = "next_fixture_mid"
        order_type = "market"
    else:
        ref_px = None
        ref_source = None
        order_type = "market" if side else None

    notional = notional_from_ner(proposal.size_ner_pct, paper_nav, max_notional)
    qty = (notional / ref_px) if (notional > 0 and ref_px and ref_px > 0) else None

    notes: list[str] = []
    if proposal.abstain:
        return FillIntent(
            intent_id=iid,
            proposal_id=proposal.proposal_id,
            mode="paper",
            ticker=ticker,
            side=None,
            order_type=None,
            limit_px=None,
            invalidation=None,
            notional=0.0,
            qty=None,
            size_ner_pct=0.0,
            decision_clock=clock,
            ref_px=None,
            ref_px_source=None,
            abstain=True,
            abstain_reason=proposal.abstain_reason or "proposal_abstain",
            notes=["exec_skipped_proposal_abstain"],
        )

    reason: str | None = None
    if not ticker:
        reason = "missing_ticker"
    elif side is None:
        reason = "missing_side"
    elif notional <= 0:
        reason = "cannot_size"
    elif ref_px is None or qty is None or qty <= 0:
        reason = "missing_ref_px"

    if reason:
        return FillIntent(
            intent_id=iid,
            proposal_id=proposal.proposal_id,
            mode="paper",
            ticker=ticker,
            side=None,
            order_type=None,
            limit_px=None,
            invalidation=None,
            notional=0.0,
            qty=None,
            size_ner_pct=proposal.size_ner_pct,
            decision_clock=clock,
            ref_px=None,
            ref_px_source=None,
            abstain=True,
            abstain_reason=reason,
            notes=[f"exec_skipped_{reason}"],
        )

    if limit_px is not None:
        notes.append("limit_px_from_sealed_citation")
    if invalidation:
        notes.append("invalidation_from_sealed_citation")
    notes.append(f"ref_px_{ref_source}")
    notes.append("notional_clipped_to_hard_limits")

    return FillIntent(
        intent_id=iid,
        proposal_id=proposal.proposal_id,
        mode="paper",
        ticker=ticker,
        side=side,
        order_type=order_type,
        limit_px=limit_px,
        invalidation=invalidation,
        notional=notional,
        qty=qty,
        size_ner_pct=proposal.size_ner_pct,
        decision_clock=clock,
        ref_px=ref_px,
        ref_px_source=ref_source,
        abstain=False,
        abstain_reason=None,
        notes=notes,
    )
