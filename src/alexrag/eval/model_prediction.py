"""MODEL_EVAL_LOCK_V0 per-case prediction schema. No live LLM, no broker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Action = Literal["enter", "abstain", "size", "manage", "exit"]
Side = Literal["long", "short", "n/a"]
ACTIONS = ("enter", "abstain", "size", "manage", "exit")
SIDES = ("long", "short", "n/a")


class ModelCitation(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str
    message_id: str
    ts: str
    quote_span: str = ""


class ModelPrediction(BaseModel):
    """One structured prediction per frozen case_id (lock output_schema)."""

    model_config = ConfigDict(extra="allow")

    case_id: str
    decision_ts: str
    action: Action
    side: Side
    ticker: str = ""
    size_pct: float | None = None
    stop: str | None = None
    management: str | None = None
    exit: str | None = None
    rejected_alternatives: list[str] = Field(default_factory=list)
    citations: list[ModelCitation] = Field(default_factory=list)
    confidence: float | str = 0.0
    abstain_reason: str | None = None
    sealed_cutoff_ack: str
    retrieved_ids: list[str] = Field(default_factory=list)
    model_id: str
    run_id: str

    @field_validator("action")
    @classmethod
    def _action(cls, value: str) -> str:
        if value not in ACTIONS:
            raise ValueError(f"action must be one of {ACTIONS}")
        return value

    @field_validator("side")
    @classmethod
    def _side(cls, value: str) -> str:
        if value not in SIDES:
            raise ValueError(f"side must be one of {SIDES}")
        return value

    @model_validator(mode="after")
    def _abstain_reason_required(self) -> ModelPrediction:
        if self.action == "abstain" and not (self.abstain_reason or "").strip():
            raise ValueError("abstain_reason is required when action=abstain")
        return self


def load_predictions(path: Path) -> list[ModelPrediction]:
    """Load JSONL (one object per line) or a JSON array of prediction objects."""

    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        return []
    rows: list[Any]
    if text.startswith("["):
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise ValueError(f"{path} must be a JSON array or JSONL")
        rows = payload
    else:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    return [ModelPrediction.model_validate(row) for row in rows]
