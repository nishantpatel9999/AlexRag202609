"""Load MODEL_EVAL_LOCK_V0. Offline contract only — capital 0, paper KILL."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from alexrag.config import ROOT

DEFAULT_LOCK_PATH = ROOT / "docs" / "model_eval_lock_v0.json"
DEFAULT_FROZEN_PACK = ROOT / "eval" / "golden_cases_v0_frozen.json"
EXPECTED_FIXTURE_SHA16 = "1a3cb17781211ad0"

MVP_CHANNELS = ("equity-trades", "alex-journal", "prime-report", "pf-update")
MVP_JSONL_NAMES = {channel: f"{channel}.jsonl" for channel in MVP_CHANNELS}

NEVER_INJECT_INTO_CONTEXT = frozenset(
    {"target_action", "banned_same_day_ids_text", "fill_message_body"}
)

HARD_KILL_SCAR_IDS = ("GC-15-2023-09-21", "GC-29-2025-03-05")


class ModelEvalLockMetrics(BaseModel):
    model_config = ConfigDict(extra="allow")

    axes: list[str] = Field(default_factory=list)
    status_enum: list[str] = Field(default_factory=list)
    behavioral_action_match_min: float = 0.7
    no_trade_recall_min: float = 0.8
    no_trade_precision_min: float = 0.75
    catastrophic_fp_max: int = 0
    citation_coverage_min_non_abstain: float = 0.9
    size_tolerance_pp_soft: float = 2.0
    gt_abstain_case_ids: list[str] = Field(default_factory=list)
    cfp_definition: str = ""
    ambiguous_no_soft_relabel: bool = True


class ModelEvalLock(BaseModel):
    """Research lock twin for the decision-model scorer. Does not unlock paper."""

    model_config = ConfigDict(extra="allow")

    version: str
    lock_date_pt: str | None = None
    owner: str | None = None
    capital: int = 0
    paper_authority_default: bool = False
    market_fighter: bool = False
    fixture_path: str | None = None
    fixture_sha256_16: str = EXPECTED_FIXTURE_SHA16
    ingest_channels: list[str] = Field(default_factory=lambda: list(MVP_CHANNELS))
    timezone: str = "America/Los_Angeles"
    sealed_cutoff_rule: str = "only artifacts with timestamp < decision_ts"
    metrics: ModelEvalLockMetrics = Field(default_factory=ModelEvalLockMetrics)
    ambiguous_case_ids_locked: list[str] = Field(default_factory=list)
    kill_scars: dict[str, Any] = Field(default_factory=dict)
    graduation: dict[str, Any] = Field(default_factory=dict)
    scorer_hooks: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)

    @property
    def hard_kill_scar_ids(self) -> tuple[str, ...]:
        rows = self.kill_scars.get("hard_model_kill_if_cheat_thin_sealed_priors") or []
        ids = tuple(str(row["case_id"]) for row in rows if isinstance(row, dict) and row.get("case_id"))
        return ids or HARD_KILL_SCAR_IDS

    @property
    def gt_abstain_ids(self) -> frozenset[str]:
        return frozenset(self.metrics.gt_abstain_case_ids)

    @property
    def ambiguous_ids(self) -> frozenset[str]:
        return frozenset(self.ambiguous_case_ids_locked)


def load_model_eval_lock(path: Path | None = None) -> ModelEvalLock:
    lock_path = Path(path) if path is not None else DEFAULT_LOCK_PATH
    return ModelEvalLock.model_validate_json(lock_path.read_text(encoding="utf-8"))
