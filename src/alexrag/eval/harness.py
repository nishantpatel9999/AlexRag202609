"""Load and score Eval Spec V0 golden cases. Offline; no P&L."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from alexrag.config import ROOT
from alexrag.eval.cutoff import enter_evidence_illegal, sealed_ok
from alexrag.schemas.proposal import Proposal
from alexrag.schemas.sources import GOLDEN_CASE_COUNT

DEFAULT_PACK = ROOT / "eval" / "golden_cases_v0.json"
SCORE_AXES = ("enter", "abstain", "size", "manage", "exit", "citation")


class Expected(BaseModel):
    enter: bool | None = None
    abstain: bool | None = None
    size_ner_pct: float | None = None
    manage: str | None = None
    exit: str | None = None
    min_citations: int = 1
    timestamped_citations: bool = True


class GoldenCase(BaseModel):
    id: str
    conflict_label: str
    primary_axis: str
    expected: Expected = Field(default_factory=Expected)
    decision_ts: datetime | None = None
    fill_ts: datetime | None = None
    ticker: str | None = None
    status: str = "schema_v0"
    notes: str = ""


class GoldenPack(BaseModel):
    version: str
    n_cases: int
    score_axes: list[str]
    sealed_cutoff: str
    post_fill_enter_evidence: str
    pnl_required: bool = False
    cases: list[GoldenCase]


class Prediction(BaseModel):
    """Model output the harness can score. Built from Proposal or tests."""

    enter: bool = False
    abstain: bool = True
    size_ner_pct: float | None = None
    manage: str | None = None
    exit: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    conflict_labels: list[str] = Field(default_factory=list)

    @classmethod
    def from_proposal(cls, proposal: Proposal) -> Prediction:
        cites = []
        for c in proposal.citations:
            cites.append(
                {
                    "source_type": c.source_type,
                    "timestamp": c.timestamp,
                    "chunk_id": c.chunk_id,
                }
            )
        return cls(
            enter=not proposal.abstain,
            abstain=proposal.abstain,
            size_ner_pct=proposal.size_ner_pct,
            citations=cites,
            conflict_labels=list(proposal.conflict_labels),
        )


class AxisResult(BaseModel):
    axis: str
    scored: bool
    passed: bool | None = None
    notes: list[str] = Field(default_factory=list)


class CaseScore(BaseModel):
    case_id: str
    axes: list[AxisResult]
    illegal_enter_evidence: bool = False

    @property
    def passed(self) -> bool:
        scored = [a for a in self.axes if a.scored]
        if not scored:
            return True
        return all(a.passed for a in scored)


def load_golden_pack(path: Path | None = None) -> GoldenPack:
    pack_path = Path(path) if path else DEFAULT_PACK
    data = json.loads(pack_path.read_text(encoding="utf-8"))
    pack = GoldenPack.model_validate(data)
    if pack.n_cases != GOLDEN_CASE_COUNT or len(pack.cases) != GOLDEN_CASE_COUNT:
        raise ValueError(f"golden pack must contain {GOLDEN_CASE_COUNT} cases")
    return pack


def _cite_ts(cite: dict[str, Any]) -> datetime | None:
    raw = cite.get("timestamp")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    text = str(raw).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def score_case(case: GoldenCase, prediction: Prediction | None = None) -> CaseScore:
    """Score one case. Without a prediction, only pack/cutoff rules are checked."""

    exp = case.expected
    axes: list[AxisResult] = []
    illegal = False
    pred = prediction or Prediction()
    cutoff = case.fill_ts or case.decision_ts

    sealed_cites = []
    for cite in pred.citations:
        ts = _cite_ts(cite)
        src = str(cite.get("source_type") or "")
        if cutoff is not None and enter_evidence_illegal(
            timestamp=ts,
            source_type=src,
            decision_ts=case.decision_ts,
            fill_ts=case.fill_ts,
        ):
            illegal = True
        if sealed_ok(ts, case.decision_ts or cutoff):
            sealed_cites.append(cite)

    def add(axis: str, scored: bool, passed: bool | None, *notes: str) -> None:
        axes.append(AxisResult(axis=axis, scored=scored, passed=passed, notes=list(notes)))

    if exp.enter is None:
        add("enter", False, None, "expected.enter unset")
    else:
        ok = pred.enter is exp.enter
        if pred.enter and illegal:
            ok = False
            notes = ("post-fill or unsealed citation used as enter-evidence",)
        else:
            notes = ()
        add("enter", True, ok, *notes)

    if exp.abstain is None:
        add("abstain", False, None, "expected.abstain unset")
    else:
        add("abstain", True, pred.abstain is exp.abstain)

    if exp.size_ner_pct is None:
        add("size", False, None, "expected.size_ner_pct unset; do not invent size")
    else:
        add("size", True, pred.size_ner_pct == exp.size_ner_pct)

    if exp.manage is None:
        add("manage", False, None, "expected.manage unset")
    else:
        add("manage", True, pred.manage == exp.manage)

    if exp.exit is None:
        add("exit", False, None, "expected.exit unset")
    else:
        add("exit", True, pred.exit == exp.exit)

    need = exp.min_citations
    n = len(sealed_cites)
    timestamped = all(_cite_ts(c) is not None for c in sealed_cites) if sealed_cites else False
    cite_ok = n >= need and (timestamped if exp.timestamped_citations else True)
    if prediction is None:
        add("citation", False, None, "no prediction")
    else:
        add(
            "citation",
            True,
            cite_ok,
            f"sealed_citations={n} need={need}",
        )

    return CaseScore(case_id=case.id, axes=axes, illegal_enter_evidence=illegal)


def score_pack(
    pack: GoldenPack,
    predictions: dict[str, Prediction] | None = None,
) -> dict[str, Any]:
    preds = predictions or {}
    scores = [score_case(case, preds.get(case.id)) for case in pack.cases]
    scored = [s for s in scores if any(a.scored for a in s.axes)]
    passed = sum(1 for s in scored if s.passed)
    return {
        "version": pack.version,
        "n_cases": len(scores),
        "n_scored": len(scored),
        "n_passed": passed,
        "pnl_scored": False,
        "cases": [s.model_dump() for s in scores],
    }
