"""Load and pin the Golden-48 frozen pack (MODEL_EVAL_LOCK_V0)."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from alexrag.config import ROOT
from alexrag.eval.cutoff import parse_ts
from alexrag.eval.model_lock import DEFAULT_FROZEN_PACK, EXPECTED_FIXTURE_SHA16, load_model_eval_lock
from alexrag.schemas.sources import GOLDEN_CASE_COUNT


class FrozenPackIntegrityError(ValueError):
    """Frozen JSON does not match the lock pin."""


class EligibleFilter(BaseModel):
    model_config = ConfigDict(extra="allow")

    channels: list[str]
    ts_lt: datetime
    tz: str = "America/Los_Angeles"

    @field_validator("ts_lt", mode="before")
    @classmethod
    def _ts(cls, value: Any) -> Any:
        parsed = parse_ts(value) if not isinstance(value, datetime) else value
        return parsed if parsed is not None else value


class TargetAction(BaseModel):
    """Equity-trades (or plan) ground-truth row. Never inject into model context."""

    model_config = ConfigDict(extra="allow")

    message_id: str
    channel: str
    ts: datetime
    text: str = ""
    action_classes: list[str] = Field(default_factory=list)
    primary_question: str

    @field_validator("ts", mode="before")
    @classmethod
    def _ts(cls, value: Any) -> Any:
        parsed = parse_ts(value) if not isinstance(value, datetime) else value
        return parsed if parsed is not None else value


class FrozenCase(BaseModel):
    model_config = ConfigDict(extra="allow")

    case_id: str
    date_pt: str
    tickers: list[str] = Field(default_factory=list)
    primary_question: str
    decision_ts: datetime
    fill_ts: datetime | None = None
    target_action: TargetAction
    eligible_filter: EligibleFilter
    banned_same_day_ids: list[str] = Field(default_factory=list)
    key_evidence_ids: list[str] = Field(default_factory=list)
    conflict_class: str | None = None
    scoring_notes: str = ""
    pre_trade_labeled: bool = False
    fully_resolved: bool = False
    freeze_blockers: list[str] = Field(default_factory=list)

    @field_validator("decision_ts", "fill_ts", mode="before")
    @classmethod
    def _ts(cls, value: Any) -> Any:
        if value is None:
            return None
        parsed = parse_ts(value) if not isinstance(value, datetime) else value
        return parsed if parsed is not None else value


class FrozenPack(BaseModel):
    model_config = ConfigDict(extra="allow")

    spec_version: str = "v0"
    freeze_pt: str | None = None
    timezone: str = "America/Los_Angeles"
    case_count: int
    fully_resolved_count: int | None = None
    sealed_cutoff_rule_global: str = "only artifacts with timestamp < decision_ts"
    ingest_sha256_prefix: dict[str, str] = Field(default_factory=dict)
    cases: list[FrozenCase]
    sha256_16: str = ""
    path: str = ""


def sha256_16(path: Path) -> str:
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return digest[:16]


def load_frozen_pack(
    path: Path | None = None,
    *,
    expected_sha16: str | None = None,
    lock_path: Path | None = None,
) -> FrozenPack:
    """Load eval/golden_cases_v0_frozen.json and pin sha256[:16] against the lock."""

    pack_path = Path(path) if path is not None else DEFAULT_FROZEN_PACK
    if not pack_path.is_file():
        raise FileNotFoundError(f"frozen pack not found: {pack_path}")

    digest = sha256_16(pack_path)
    pin = expected_sha16
    if pin is None:
        lock_file = Path(lock_path) if lock_path is not None else ROOT / "docs" / "model_eval_lock_v0.json"
        if lock_file.is_file():
            pin = load_model_eval_lock(lock_file).fixture_sha256_16
        else:
            pin = EXPECTED_FIXTURE_SHA16
    if pin and digest != pin:
        raise FrozenPackIntegrityError(
            f"frozen pack sha256[:16]={digest} does not match lock pin {pin} ({pack_path})"
        )

    pack = FrozenPack.model_validate_json(pack_path.read_text(encoding="utf-8"))
    if pack.case_count != GOLDEN_CASE_COUNT or len(pack.cases) != GOLDEN_CASE_COUNT:
        raise ValueError(f"frozen pack must contain {GOLDEN_CASE_COUNT} cases, got {len(pack.cases)}")
    pack.sha256_16 = digest
    pack.path = str(pack_path)
    return pack
