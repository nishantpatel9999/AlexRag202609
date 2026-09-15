"""M0 paper-fill replay scoring. Offline; no P&L; no live path.

See docs/FILL_FIDELITY_M0.md.
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from alexrag.agents.audit_log import AuditLog
from alexrag.agents.auditor import AuditorAgent
from alexrag.agents.exec_agent import ExecAgent
from alexrag.config import ROOT, Settings
from alexrag.eval.cutoff import aware, sealed_ok
from alexrag.marketdata.fixture_bars import FixtureBar
from alexrag.schemas.fill_intent import FillIntent
from alexrag.schemas.paper_fill import PaperFill
from alexrag.schemas.proposal import Proposal

DEFAULT_M0_DIR = ROOT / "tests" / "fixtures" / "m0" / "cases"

INTENT_CORE = (
    "intent_id",
    "proposal_id",
    "mode",
    "ticker",
    "side",
    "order_type",
    "limit_px",
    "invalidation",
    "notional",
    "qty",
    "size_ner_pct",
    "decision_clock",
    "ref_px",
    "ref_px_source",
    "abstain",
    "abstain_reason",
)

RECEIPT_CORE = (
    "fill_ts",
    "fill_px",
    "qty_filled",
    "qty_left",
    "status",
    "venue",
    "latency_ms",
    "intent_id",
    "proposal_id",
    "filled",
    "fill_model",
    "scar_bps",
    "scar_label",
    "skip_reason",
)

AUDIT_REQUIRED = (
    "regime_classified",
    "setup_built",
    "exec_intent_mapped",
    "exec_paper_fill",
    "auditor_complete",
)


class M0ReplayCase(BaseModel):
    case_id: str
    fill_model: Literal["M0"] = "M0"
    scar_bps: float = 0.0
    paper_nav: float
    hard_limits: dict[str, Any]
    bars: list[FixtureBar] = Field(default_factory=list)
    proposal: Proposal
    intent: FillIntent
    expected_fill: PaperFill
    notes: str = ""


class AxisCheck(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class M0CaseScore(BaseModel):
    case_id: str
    passed: bool
    checks: list[AxisCheck]
    pnl_scored: bool = False


def load_m0_cases(directory: Path | None = None) -> list[M0ReplayCase]:
    root = Path(directory) if directory is not None else DEFAULT_M0_DIR
    paths = sorted(root.glob("*.json"))
    cases = [M0ReplayCase.model_validate_json(p.read_text(encoding="utf-8")) for p in paths]
    if not cases:
        raise FileNotFoundError(f"no M0 replay cases under {root}")
    return cases


def _close(a: Any, b: Any) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        if a is None or b is None:
            return a is b
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(a, datetime) and isinstance(b, datetime):
        return aware(a) == aware(b)
    return a == b


def _field_diff(left: dict[str, Any], right: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    diffs = []
    for key in keys:
        if not _close(left.get(key), right.get(key)):
            diffs.append(f"{key}: got={left.get(key)!r} expected={right.get(key)!r}")
    return diffs


def replay_m0_case(case: M0ReplayCase, audit_path: Path) -> tuple[FillIntent, PaperFill, Proposal, AuditLog]:
    settings = Settings.model_validate(
        {
            "mode": "paper",
            "hard_limits": case.hard_limits,
            "paper": {
                "nav": case.paper_nav,
                "fill_model": "M0",
                "venue": case.expected_fill.venue,
            },
        }
    )
    audit = AuditLog(audit_path)
    proposal = case.proposal.model_copy(deep=True)
    audit.emit(
        kind="regime_classified",
        actor="regime",
        proposal_id=proposal.proposal_id,
        payload={"regime": proposal.regime, "fixture": True},
    )
    audit.emit(
        kind="setup_built",
        actor="setup",
        proposal_id=proposal.proposal_id,
        payload={"tickers": proposal.tickers, "fixture": True},
    )
    intent, receipt = ExecAgent().run(
        proposal,
        audit,
        settings=settings,
        bars=case.bars,
        venue=case.expected_fill.venue,
        intent_id=case.intent.intent_id,
    )
    proposal = AuditorAgent().run(proposal, audit, intent, receipt)
    return intent, receipt, proposal, audit


def score_m0_case(case: M0ReplayCase, audit_path: Path) -> M0CaseScore:
    intent, receipt, _proposal, audit = replay_m0_case(case, audit_path)
    checks: list[AxisCheck] = []

    intent_diffs = _field_diff(intent.model_dump(), case.intent.model_dump(), INTENT_CORE)
    checks.append(
        AxisCheck(
            name="intent_match",
            passed=not intent_diffs,
            detail="; ".join(intent_diffs),
        )
    )

    receipt_diffs = _field_diff(receipt.model_dump(), case.expected_fill.model_dump(), RECEIPT_CORE)
    checks.append(
        AxisCheck(
            name="receipt_match",
            passed=not receipt_diffs,
            detail="; ".join(receipt_diffs),
        )
    )

    consistent = (
        receipt.intent_id == intent.intent_id
        and receipt.proposal_id == intent.proposal_id
        and receipt.proposal_id == case.proposal.proposal_id
    )
    if intent.abstain:
        consistent = consistent and receipt.status == "skipped" and receipt.filled is False
    if receipt.status == "stubbed":
        consistent = consistent and receipt.filled is False and receipt.qty_filled == 0
    if receipt.status == "acked":
        consistent = consistent and receipt.filled is True and receipt.qty_filled == intent.qty
    checks.append(
        AxisCheck(
            name="intent_receipt_consistency",
            passed=consistent,
            detail="stubbed≠filled; ids bind intent↔receipt",
        )
    )

    clock = case.proposal.decision_clock
    cites_sealed = all(sealed_ok(c.timestamp, clock) for c in case.proposal.citations)
    fill_not_before = aware(receipt.fill_ts) >= aware(clock)
    used_future_bar = True
    if receipt.status == "acked":
        used_future_bar = any(
            bar.ticker == intent.ticker
            and aware(bar.ts) == aware(receipt.fill_ts)
            and bar.mid == receipt.fill_px
            and aware(bar.ts) > aware(clock)
            for bar in case.bars
        )
        past_used = any(
            aware(bar.ts) <= aware(clock) and receipt.fill_px == bar.mid and bar.ticker == intent.ticker
            for bar in case.bars
        )
        used_future_bar = used_future_bar and not past_used
    checks.append(
        AxisCheck(
            name="sealed_clock",
            passed=cites_sealed and fill_not_before and used_future_bar,
            detail="citations < decision_ts; fill_ts >= decision_clock; M0 uses next bar after clock",
        )
    )

    kinds = {e.kind for e in audit.events if e.proposal_id == case.proposal.proposal_id}
    missing = [k for k in AUDIT_REQUIRED if k not in kinds]
    if case.proposal.abstain and "exec_skipped_abstain" not in kinds:
        missing.append("exec_skipped_abstain")
    checks.append(
        AxisCheck(
            name="audit_completeness",
            passed=not missing,
            detail="missing=" + ",".join(missing) if missing else "ok",
        )
    )

    checks.append(
        AxisCheck(
            name="m0_zero_scar",
            passed=receipt.scar_bps == 0 and case.scar_bps == 0,
            detail="M0 scar_bps must be 0 (fixture mid, not Alex slippage)",
        )
    )
    checks.append(
        AxisCheck(
            name="no_pnl",
            passed=True,
            detail="P&L is not a scoring axis",
        )
    )

    return M0CaseScore(
        case_id=case.case_id,
        passed=all(c.passed for c in checks),
        checks=checks,
        pnl_scored=False,
    )


def score_m0_pack(cases: list[M0ReplayCase], audit_dir: Path) -> dict[str, Any]:
    audit_dir = Path(audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    scores = [score_m0_case(case, audit_dir / f"{case.case_id}.jsonl") for case in cases]
    return {
        "n_cases": len(scores),
        "n_passed": sum(1 for s in scores if s.passed),
        "pnl_scored": False,
        "fill_model": "M0",
        "cases": [s.model_dump() for s in scores],
    }


def dump_m0_summary(summary: dict[str, Any], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
