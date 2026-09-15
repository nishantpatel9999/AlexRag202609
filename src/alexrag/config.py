from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

from alexrag import envutil

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "config" / "default.yaml"

PRECEDENCE_DEFAULT = ("trade_log", "journal", "report", "gitbook")


class RetrievalSettings(BaseModel):
    min_confidence: float = 0.2
    stale_after_hours: float = 36.0
    top_k: int = 8
    precedence: list[str] = Field(default_factory=lambda: list(PRECEDENCE_DEFAULT))


class PaperGateSettings(BaseModel):
    min_sessions: int = 60
    min_decisions: int = 100


class HardLimits(BaseModel):
    """Coded hard limits. Present even while Exec is a stub. Operator-owned values."""

    max_notional: float = 0.0
    max_positions: int = 0
    max_daily_loss: float = 0.0
    max_portfolio_dd: float = 0.0


class PathSettings(BaseModel):
    audit_log: str = "data/audit/events.jsonl"
    gitbook_snapshot: str = "data/gitbook"


class EmbeddingSettings(BaseModel):
    provider: Literal["fake"] = "fake"
    dim: int = 32


class Settings(BaseModel):
    """Runtime settings. Live mode is rejected at parse time — no live trading path."""

    mode: Literal["paper"] = "paper"
    kill_switch: bool = False
    fail_closed: bool = True
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    paper_gates: PaperGateSettings = Field(default_factory=PaperGateSettings)
    hard_limits: HardLimits = Field(default_factory=HardLimits)
    paths: PathSettings = Field(default_factory=PathSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)

    @field_validator("mode")
    @classmethod
    def _paper_only(cls, v: str) -> str:
        if v != "paper":
            raise ValueError(
                "AlexRag202609 MVP allows mode=paper only; live paths are not implemented"
            )
        return v

    def hard_limits_snapshot(self) -> dict[str, Any]:
        return self.hard_limits.model_dump()


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config {path} must be a mapping")
    return data


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _env_overlay() -> dict[str, Any]:
    overlay: dict[str, Any] = {}
    mode = envutil.get_str("ALEXRAG_MODE")
    if mode is not None:
        overlay["mode"] = mode
    ks = envutil.get_bool("ALEXRAG_KILL_SWITCH")
    if ks is not None:
        overlay["kill_switch"] = ks
    fc = envutil.get_bool("ALEXRAG_FAIL_CLOSED")
    if fc is not None:
        overlay["fail_closed"] = fc

    retrieval: dict[str, Any] = {}
    conf = envutil.get_float("ALEXRAG_MIN_RETRIEVAL_CONFIDENCE")
    if conf is not None:
        retrieval["min_confidence"] = conf
    stale = envutil.get_float("ALEXRAG_STALE_AFTER_HOURS")
    if stale is not None:
        retrieval["stale_after_hours"] = stale
    if retrieval:
        overlay["retrieval"] = retrieval

    gates: dict[str, Any] = {}
    sessions = envutil.get_int("ALEXRAG_MIN_PAPER_SESSIONS")
    if sessions is not None:
        gates["min_sessions"] = sessions
    decisions = envutil.get_int("ALEXRAG_MIN_PAPER_DECISIONS")
    if decisions is not None:
        gates["min_decisions"] = decisions
    if gates:
        overlay["paper_gates"] = gates

    limits: dict[str, Any] = {}
    for env_name, key, caster in (
        ("ALEXRAG_MAX_NOTIONAL", "max_notional", envutil.get_float),
        ("ALEXRAG_MAX_POSITIONS", "max_positions", envutil.get_int),
        ("ALEXRAG_MAX_DAILY_LOSS", "max_daily_loss", envutil.get_float),
        ("ALEXRAG_MAX_PORTFOLIO_DD", "max_portfolio_dd", envutil.get_float),
    ):
        val = caster(env_name)
        if val is not None:
            limits[key] = val
    if limits:
        overlay["hard_limits"] = limits

    paths: dict[str, Any] = {}
    audit = envutil.get_str("ALEXRAG_AUDIT_LOG_PATH")
    if audit is not None:
        paths["audit_log"] = audit
    gitbook = envutil.get_str("ALEXRAG_GITBOOK_PATH")
    if gitbook is not None:
        paths["gitbook_snapshot"] = gitbook
    if paths:
        overlay["paths"] = paths
    return overlay


def load_settings(
    config_path: Path | None = None,
    overrides: dict[str, Any] | None = None,
    load_env_file: bool = True,
) -> Settings:
    if load_env_file:
        load_dotenv(ROOT / ".env", override=False)
    data = load_yaml(config_path or DEFAULT_CONFIG_PATH)
    data = _deep_merge(data, _env_overlay())
    if overrides:
        data = _deep_merge(data, overrides)
    return Settings.model_validate(data)
