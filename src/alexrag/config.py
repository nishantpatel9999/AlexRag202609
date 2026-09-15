from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

from alexrag import envutil
from alexrag.schemas.sources import PRECEDENCE_DEFAULT

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "config" / "default.yaml"

# Nishant-locked operator paper limits. Dollar notional / daily-loss are derived
# from paper.nav at runtime — never stored as secrets or as live sizes.
OPERATOR_MAX_POSITIONS = 15
OPERATOR_MAX_DAILY_LOSS_PCT = 0.10
OPERATOR_MAX_PORTFOLIO_DD = 0.25
OPERATOR_MAX_NOTIONAL_PCT = 1.0


class RetrievalSettings(BaseModel):
    min_confidence: float = 0.2
    stale_after_hours: float = 36.0
    top_k: int = 8
    precedence: list[str] = Field(default_factory=lambda: list(PRECEDENCE_DEFAULT))


class PaperGateSettings(BaseModel):
    min_sessions: int = 60
    min_decisions: int = 100


class HardLimits(BaseModel):
    """Coded hard limits. Operator-owned percents + position cap.

    Dollar notional and dollar daily-loss are **not** stored here; Settings
    derives them from ``paper.nav`` at runtime.
    """

    max_notional_pct: float = OPERATOR_MAX_NOTIONAL_PCT
    max_positions: int = OPERATOR_MAX_POSITIONS
    max_daily_loss_pct: float = OPERATOR_MAX_DAILY_LOSS_PCT
    max_portfolio_dd: float = OPERATOR_MAX_PORTFOLIO_DD


class PathSettings(BaseModel):
    audit_log: str = "data/audit/events.jsonl"
    # Fixture/doctrine files only — not a local GitBook mirror (see docs/CORPUS.md).
    gitbook_snapshot: str = "data/gitbook"


class EmbeddingSettings(BaseModel):
    provider: Literal["fake"] = "fake"
    dim: int = 32


class LlmSettings(BaseModel):
    """Always-on LLM. API key is env-only (INFERHUB_API_KEY); never a field here."""

    provider: Literal["inferhub.dev"] = "inferhub.dev"
    model: Literal["GLM 5.3-flash"] = "GLM 5.3-flash"


class PaperSimSettings(BaseModel):
    """Offline paper sizing + M0 venue. ``nav`` 0 fail-closes Exec sizing."""

    nav: float = 0.0
    fill_model: Literal["M0"] = "M0"
    venue: Literal["paper_sim", "alpaca_paper"] = "paper_sim"
    bars_path: str | None = None


class PaperBook(BaseModel):
    """Operator/fixture snapshot of the paper book. Risk enforces loss/DD against this.

    ``daily_loss`` is dollars of paper loss. ``portfolio_dd`` is a fraction of equity
    (0.25 = 25%). ``sessions`` / ``decisions`` are diagnostics, not a promotion hard floor.
    """

    daily_loss: float = 0.0
    portfolio_dd: float = 0.0
    sessions: int = 0
    decisions: int = 0


class Settings(BaseModel):
    """Runtime settings. Live mode is rejected at parse time — no live trading path."""

    mode: Literal["paper"] = "paper"
    kill_switch: bool = False
    fail_closed: bool = True
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    paper_gates: PaperGateSettings = Field(default_factory=PaperGateSettings)
    hard_limits: HardLimits = Field(default_factory=HardLimits)
    paper: PaperSimSettings = Field(default_factory=PaperSimSettings)
    paper_book: PaperBook = Field(default_factory=PaperBook)
    paths: PathSettings = Field(default_factory=PathSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    llm: LlmSettings = Field(default_factory=LlmSettings)

    @field_validator("mode")
    @classmethod
    def _paper_only(cls, v: str) -> str:
        if v != "paper":
            raise ValueError(
                "AlexRag202609 MVP allows mode=paper only; live paths are not implemented"
            )
        return v

    def paper_equity(self) -> float:
        return self.paper.nav

    def max_notional_dollars(self) -> float:
        """100% of paper equity when ``max_notional_pct`` is 1.0. 0 if nav/pct unconfigured."""

        nav = self.paper.nav
        pct = self.hard_limits.max_notional_pct
        if nav <= 0 or pct <= 0:
            return 0.0
        return nav * pct

    def max_daily_loss_dollars(self) -> float:
        """10% of paper equity when ``max_daily_loss_pct`` is 0.10. 0 if nav/pct unconfigured."""

        nav = self.paper.nav
        pct = self.hard_limits.max_daily_loss_pct
        if nav <= 0 or pct <= 0:
            return 0.0
        return nav * pct

    def hard_limits_ready(self) -> bool:
        """Operator pcts/positions plus paper equity must all be positive to size a go."""

        limits = self.hard_limits
        return (
            limits.max_positions > 0
            and limits.max_notional_pct > 0
            and limits.max_daily_loss_pct > 0
            and limits.max_portfolio_dd > 0
            and self.paper.nav > 0
        )

    def hard_limits_snapshot(self) -> dict[str, Any]:
        """Pcts as configured plus dollar notional/daily-loss derived from paper equity."""

        return {
            **self.hard_limits.model_dump(),
            "paper_equity": self.paper_equity(),
            "max_notional": self.max_notional_dollars(),
            "max_daily_loss": self.max_daily_loss_dollars(),
        }


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
        ("ALEXRAG_MAX_NOTIONAL_PCT", "max_notional_pct", envutil.get_float),
        ("ALEXRAG_MAX_POSITIONS", "max_positions", envutil.get_int),
        ("ALEXRAG_MAX_DAILY_LOSS_PCT", "max_daily_loss_pct", envutil.get_float),
        ("ALEXRAG_MAX_PORTFOLIO_DD", "max_portfolio_dd", envutil.get_float),
    ):
        val = caster(env_name)
        if val is not None:
            limits[key] = val
    if limits:
        overlay["hard_limits"] = limits

    paper: dict[str, Any] = {}
    nav = envutil.get_float("ALEXRAG_PAPER_NAV")
    if nav is not None:
        paper["nav"] = nav
    if paper:
        overlay["paper"] = paper

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
