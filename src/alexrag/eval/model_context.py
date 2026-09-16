"""Build sealed retrieval context. Never inject GT / banned fill bodies."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from alexrag.eval.frozen_pack import FrozenCase
from alexrag.eval.model_lock import NEVER_INJECT_INTO_CONTEXT
from alexrag.eval.sealed_corpus import CorpusMessage


class GroundTruthLeakError(ValueError):
    """Model context would include target_action, banned ids, or GT fill text."""


class ContextMessage(BaseModel):
    """Retrieval-safe message. No GT labels."""

    model_config = ConfigDict(extra="forbid")

    message_id: str
    channel: str
    ts: datetime | None = None
    text: str = ""
    source_type: str
    author: str = ""

    @field_serializer("ts")
    def _ser_ts(self, value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None


class ModelContext(BaseModel):
    """Offline retrieval context for one frozen case. Capital 0 / paper KILL."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    decision_ts: str
    tickers: list[str] = Field(default_factory=list)
    primary_question: str
    scoring_notes: str = ""
    conflict_class: str | None = None
    messages: list[ContextMessage] = Field(default_factory=list)
    retrieved_ids: list[str] = Field(default_factory=list)
    key_evidence_hint_ids: list[str] = Field(default_factory=list)
    sealed_cutoff_ack: str
    paper_authority: bool = False
    capital: int = 0

    @field_validator("paper_authority")
    @classmethod
    def _paper_kill(cls, value: bool) -> bool:
        del value
        return False

    @field_validator("capital")
    @classmethod
    def _capital_zero(cls, value: int) -> int:
        del value
        return 0

    def model_dump_sealed(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        assert_no_gt_keys(payload)
        return payload


def assert_no_gt_keys(payload: dict[str, Any]) -> None:
    leaked = NEVER_INJECT_INTO_CONTEXT.intersection(payload)
    if leaked:
        raise GroundTruthLeakError(f"model context contains forbidden keys: {sorted(leaked)}")
    if "target_action" in payload or "action_classes" in payload:
        raise GroundTruthLeakError("model context must not include GT action labels")


def build_model_context(
    case: FrozenCase,
    eligible: Sequence[CorpusMessage],
    *,
    retrieved_ids: Sequence[str] | None = None,
    inject: dict[str, Any] | None = None,
) -> ModelContext:
    """Build retrieval context from eligible messages only.

    ``inject`` exists so tests can prove GT keys are rejected. Production callers
    must omit it. Banned ids, the GT fill id, and fill-body copies are refused.
    """

    if inject:
        forbidden = NEVER_INJECT_INTO_CONTEXT.intersection(inject)
        if forbidden:
            raise GroundTruthLeakError(f"refusing GT injection keys: {sorted(forbidden)}")
        if "target_action" in inject:
            raise GroundTruthLeakError("refusing target_action in model context")

    banned = set(case.banned_same_day_ids)
    target_id = case.target_action.message_id
    target_text = (case.target_action.text or "").strip()
    # Drop GT target + banned rows if present. For abstain goldens, decision_ts is
    # often plan_ts+1s so the plan id is time-eligible but must not enter model context.
    filtered = [
        m
        for m in eligible
        if m.message_id not in banned
        and m.message_id != target_id
        and not (target_text and m.text.strip() == target_text and m.message_id == target_id)
    ]
    eligible_by_id = {m.message_id: m for m in filtered}
    eligible = filtered

    hint_ids = [i for i in case.key_evidence_ids if i in eligible_by_id and i not in banned]
    if retrieved_ids is None:
        chosen = hint_ids or [m.message_id for m in eligible]
    else:
        chosen = list(retrieved_ids)

    selected: list[ContextMessage] = []
    for mid in chosen:
        if mid in banned or mid == target_id:
            raise GroundTruthLeakError(
                f"retrieved_id {mid} is banned or is the GT fill for {case.case_id}"
            )
        msg = eligible_by_id.get(mid)
        if msg is None:
            raise GroundTruthLeakError(
                f"retrieved_id {mid} is not eligible under sealed cutoff for {case.case_id}"
            )
        if target_text and msg.text.strip() == target_text and mid == target_id:
            raise GroundTruthLeakError("refusing GT fill message body in context")
        selected.append(
            ContextMessage(
                message_id=msg.message_id,
                channel=msg.channel,
                ts=msg.ts,
                text=msg.text,
                source_type=msg.source_type,
                author=msg.author,
            )
        )

    cutoff_ack = case.eligible_filter.ts_lt.isoformat()
    ctx = ModelContext(
        case_id=case.case_id,
        decision_ts=case.decision_ts.isoformat(),
        tickers=list(case.tickers),
        primary_question=case.primary_question,
        scoring_notes=case.scoring_notes,
        conflict_class=case.conflict_class,
        messages=selected,
        retrieved_ids=[m.message_id for m in selected],
        key_evidence_hint_ids=hint_ids,
        sealed_cutoff_ack=cutoff_ack,
        paper_authority=False,
        capital=0,
    )
    assert_no_gt_keys(ctx.model_dump(mode="json"))
    return ctx
