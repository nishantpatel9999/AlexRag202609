"""Score MODEL_EVAL_LOCK_V0 predictions vs frozen GT. Offline; capital 0.

Orthogonal to M0 fill receipts. Does not unlock paper and does not call a model.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from alexrag.eval.cutoff import aware, parse_ts, sealed_ok
from alexrag.eval.frozen_pack import FrozenCase, FrozenPack, load_frozen_pack
from alexrag.eval.model_lock import (
    DEFAULT_LOCK_PATH,
    EXPECTED_FIXTURE_SHA16,
    ModelEvalLock,
    load_model_eval_lock,
)
from alexrag.eval.model_prediction import ModelPrediction, load_predictions
from alexrag.eval.sealed_corpus import SealedCorpus, load_mvp_ingest

Status = Literal["PASS", "FAIL", "AMBIGUOUS"]

_PCT = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")

GC04_ID = "GC-04-2022-12-09"


class KillScarError(RuntimeError):
    """GC-15 / GC-29 retrieved or cited a banned or unsealed id — run invalid."""

    def __init__(self, hits: list[str], run: ModelEvalRun | None = None):
        self.hits = hits
        self.run = run
        super().__init__("kill scar leakage: " + "; ".join(hits))


class GroundTruthView(BaseModel):
    action: str
    side: str
    ticker: str
    size_pct: float | None = None
    management: str | None = None
    exit: str | None = None
    abstain_ticker: str | None = None


class CaseModelScore(BaseModel):
    model_config = ConfigDict(extra="allow")

    case_id: str
    status: Status
    raw_status: Status
    fixture_tag: str | None = None
    primary_question: str
    cfp: bool = False
    citation_ok: bool = True
    notes: list[str] = Field(default_factory=list)
    gt: dict[str, Any] = Field(default_factory=dict)
    predicted: dict[str, Any] = Field(default_factory=dict)


class ModelEvalSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    n_cases: int
    n_scored: int
    n_pass: int
    n_fail: int
    n_ambiguous: int
    n_missing: int
    behavioral_action_match: float | None = None
    no_trade_precision: float | None = None
    no_trade_recall: float | None = None
    cfp_count: int = 0
    citation_coverage_non_abstain: float | None = None
    run_valid: bool = True
    kill_scars: list[str] = Field(default_factory=list)
    paper_authority: bool = False
    capital: int = 0
    pnl_scored: bool = False
    gates: dict[str, Any] = Field(default_factory=dict)


class ModelEvalRun(BaseModel):
    summary: ModelEvalSummary
    scores: list[CaseModelScore]
    predictions: list[ModelPrediction]
    fixture_sha256_16: str
    lock_version: str
    run_id: str
    out_dir: str | None = None


def iso_decision_ts(case: FrozenCase) -> str:
    return case.decision_ts.isoformat()


def parse_gt_side(text: str, primary_question: str) -> str:
    if primary_question == "abstain":
        return "n/a"
    lowered = text.lower()
    if re.search(r"\bshort\b", lowered) or re.search(r"\bhedged\b", lowered):
        return "short"
    if re.search(r"\blong\b", lowered) or re.search(r"\bfilled\b", lowered):
        return "long"
    return "n/a"


def parse_gt_size_pct(text: str) -> float | None:
    for match in _PCT.finditer(text):
        window = text[max(0, match.start() - 24) : match.start()].lower()
        if "risk" in window or "ec " in window or "ec:" in window:
            continue
        value = float(match.group(1))
        if value < 0:
            continue
        return value
    return None


def parse_gt_ticker(case: FrozenCase) -> str:
    text = case.target_action.text or ""
    upper = text.upper()
    for ticker in case.tickers:
        token = ticker.upper()
        if re.search(rf"\b{re.escape(token)}\b", upper):
            return ticker
    return case.tickers[0] if case.tickers else ""


def parse_management(text: str) -> str | None:
    lowered = text.lower()
    if "reopen" in lowered:
        return "reopen"
    if re.search(r"\btrim", lowered):
        return "trim"
    if re.search(r"\badd", lowered):
        return "add"
    if "closed" in lowered or re.search(r"\bsold\b", lowered):
        return "close_all"
    if re.search(r"\bsl\b", lowered) or "stop" in lowered:
        return "move_sl"
    return None


def parse_exit(text: str) -> str | None:
    lowered = text.lower()
    if "closed" in lowered:
        return "close"
    if re.search(r"\bsold\b", lowered):
        return "sold"
    if "stopped" in lowered:
        return "stopped"
    return None


def ground_truth(case: FrozenCase) -> GroundTruthView:
    text = case.target_action.text or ""
    ticker = parse_gt_ticker(case)
    abstain_ticker = None
    if case.primary_question == "abstain" and case.tickers:
        abstain_ticker = case.tickers[0]
    return GroundTruthView(
        action=case.primary_question,
        side=parse_gt_side(text, case.primary_question),
        ticker=ticker,
        size_pct=parse_gt_size_pct(text) if case.primary_question in {"size", "enter"} else None,
        management=parse_management(text) if case.primary_question == "manage" else None,
        exit=parse_exit(text) if case.primary_question == "exit" else None,
        abstain_ticker=abstain_ticker,
    )


def _norm_ticker(value: str | None) -> str:
    return (value or "").strip().upper()


def _ticker_matches(pred_ticker: str, gt: GroundTruthView, case: FrozenCase) -> bool:
    got = _norm_ticker(pred_ticker)
    if not got:
        return False
    if got == _norm_ticker(gt.ticker):
        return True
    return got in {_norm_ticker(t) for t in case.tickers}


def _side_matches(pred_side: str, gt_side: str) -> bool:
    if gt_side == "n/a":
        return True
    return pred_side == gt_side


def citation_violations(
    case: FrozenCase,
    pred: ModelPrediction,
    corpus: SealedCorpus | None = None,
) -> list[str]:
    notes: list[str] = []
    banned = set(case.banned_same_day_ids)
    cutoff = case.decision_ts
    tz_name = case.eligible_filter.tz
    for cite in pred.citations:
        if cite.message_id in banned:
            notes.append(f"banned_cite:{cite.message_id}")
        ts = parse_ts(cite.ts, tz_name)
        if ts is None:
            notes.append(f"cite_unparseable_ts:{cite.message_id}")
        elif not sealed_ok(ts, cutoff):
            notes.append(f"unsealed_cite:{cite.message_id}")
        if corpus is not None:
            row = corpus.lookup(cite.message_id)
            if row is None:
                notes.append(f"cite_not_in_ingest:{cite.message_id}")
            else:
                if row.ts is not None and not sealed_ok(aware(row.ts, tz_name), cutoff):
                    notes.append(f"unsealed_cite_ingest:{cite.message_id}")
                if row.message_id in banned:
                    notes.append(f"banned_cite_ingest:{cite.message_id}")
                quote = (cite.quote_span or "").strip()
                if quote and quote.casefold() not in (row.text or "").casefold():
                    notes.append(f"hallucinated_quote:{cite.message_id}")
    for mid in pred.retrieved_ids:
        if mid in banned:
            notes.append(f"banned_retrieved:{mid}")
        if corpus is not None:
            row = corpus.lookup(mid)
            if row is not None and row.ts is not None and not sealed_ok(aware(row.ts, tz_name), cutoff):
                notes.append(f"unsealed_retrieved:{mid}")
    return notes


def is_catastrophic_fp(case: FrozenCase, pred: ModelPrediction, gt: GroundTruthView, lock: ModelEvalLock) -> bool:
    """Enter or large size when GT is abstain/no-fill for the scored ticker/day."""

    if case.case_id not in lock.gt_abstain_ids and gt.action != "abstain":
        return False
    if pred.action not in {"enter", "size"}:
        return False
    scored = _norm_ticker(gt.abstain_ticker or (case.tickers[0] if case.tickers else ""))
    pred_ticker = _norm_ticker(pred.ticker)
    if not scored:
        return True
    if case.case_id == GC04_ID:
        return (not pred_ticker) or pred_ticker == scored
    if pred_ticker and pred_ticker != scored and pred_ticker not in {_norm_ticker(t) for t in case.tickers}:
        return True
    return (not pred_ticker) or pred_ticker == scored or pred_ticker in {_norm_ticker(t) for t in case.tickers}


def kill_scar_hits(
    case: FrozenCase,
    pred: ModelPrediction,
    lock: ModelEvalLock,
    corpus: SealedCorpus | None = None,
) -> list[str]:
    if case.case_id not in lock.hard_kill_scar_ids:
        return []
    banned = set(case.banned_same_day_ids)
    cutoff = case.decision_ts
    tz_name = case.eligible_filter.tz
    hits: list[str] = []

    def consider(kind: str, message_id: str, ts: datetime | None) -> None:
        if message_id in banned:
            hits.append(f"{case.case_id}:{kind}:{message_id}:banned")
        if ts is not None and aware(ts, tz_name) >= aware(cutoff, tz_name):
            hits.append(f"{case.case_id}:{kind}:{message_id}:ts_gte_decision")

    for mid in pred.retrieved_ids:
        row_ts = None
        if corpus is not None:
            row = corpus.lookup(mid)
            if row is not None:
                row_ts = row.ts
        consider("retrieved", mid, row_ts)
    for cite in pred.citations:
        ts = parse_ts(cite.ts, tz_name)
        if corpus is not None:
            row = corpus.lookup(cite.message_id)
            if row is not None and row.ts is not None:
                ts = row.ts
        consider("cite", cite.message_id, ts)
    return hits


def _size_ok(pred_pct: float | None, gt_pct: float | None, tol: float) -> tuple[bool, str]:
    if gt_pct is None:
        return True, "size_gt_not_on_tape"
    if pred_pct is None:
        return False, "missing_size_pct"
    delta = abs(float(pred_pct) - float(gt_pct))
    if delta <= 0:
        return True, "size_exact"
    if delta <= tol:
        return True, f"size_soft_band delta={delta}"
    return False, f"size_fail delta={delta} gt={gt_pct} pred={pred_pct}"


def score_prediction(
    case: FrozenCase,
    pred: ModelPrediction | None,
    lock: ModelEvalLock,
    corpus: SealedCorpus | None = None,
) -> CaseModelScore:
    gt = ground_truth(case)
    fixture_tag = "AMBIGUOUS" if case.case_id in lock.ambiguous_ids else None
    predicted = {}
    if pred is not None:
        predicted = {
            "action": pred.action,
            "side": pred.side,
            "ticker": pred.ticker,
            "size_pct": pred.size_pct,
            "management": pred.management,
            "exit": pred.exit,
        }

    if pred is None:
        raw: Status = "FAIL"
        notes = ["missing_prediction"]
        cfp = False
        citation_ok = False
        status: Status = "AMBIGUOUS" if fixture_tag else raw
        return CaseModelScore(
            case_id=case.case_id,
            status=status,
            raw_status=raw,
            fixture_tag=fixture_tag,
            primary_question=case.primary_question,
            cfp=cfp,
            citation_ok=citation_ok,
            notes=notes,
            gt=gt.model_dump(),
            predicted=predicted,
        )

    notes: list[str] = []
    cite_notes = citation_violations(case, pred, corpus)
    notes.extend(cite_notes)
    leakage = any(
        n.startswith(("banned_", "unsealed_", "hallucinated_quote")) for n in cite_notes
    )
    citation_ok = not leakage
    if pred.action != "abstain" and not pred.citations:
        citation_ok = False
        notes.append("empty_citations_non_abstain")

    cfp = is_catastrophic_fp(case, pred, gt, lock)
    if cfp:
        notes.append("catastrophic_fp")

    pq = case.primary_question
    action_ok = pred.action == pq
    if pq == "size" and pred.action in {"size", "enter"}:
        action_ok = True
    if pq == "manage" and pred.action == "manage":
        action_ok = True

    ticker_ok = True
    side_ok = True
    size_ok = True
    extra_ok = True

    if pq == "enter":
        ticker_ok = _ticker_matches(pred.ticker, gt, case)
        side_ok = _side_matches(pred.side, gt.side)
        if not ticker_ok:
            notes.append(f"ticker_mismatch pred={pred.ticker!r} gt={gt.ticker!r}")
        if not side_ok:
            notes.append(f"side_mismatch pred={pred.side} gt={gt.side}")
        if not action_ok:
            notes.append(f"action_mismatch pred={pred.action} gt={pq}")
    elif pq == "abstain":
        if not action_ok:
            notes.append(f"action_mismatch pred={pred.action} gt=abstain")
    elif pq == "size":
        ticker_ok = _ticker_matches(pred.ticker, gt, case)
        side_ok = _side_matches(pred.side, gt.side) if pred.action in {"enter", "size"} else True
        size_ok, size_note = _size_ok(pred.size_pct, gt.size_pct, lock.metrics.size_tolerance_pp_soft)
        notes.append(size_note)
        if not ticker_ok:
            notes.append(f"ticker_mismatch pred={pred.ticker!r} gt={gt.ticker!r}")
        if not side_ok:
            notes.append(f"side_mismatch pred={pred.side} gt={gt.side}")
        if pred.action not in {"size", "enter"}:
            action_ok = False
            notes.append(f"action_mismatch pred={pred.action} gt=size")
    elif pq == "manage":
        if not action_ok:
            notes.append(f"action_mismatch pred={pred.action} gt=manage")
        if gt.management and pred.management and pred.management != gt.management:
            extra_ok = False
            notes.append(f"management_mismatch pred={pred.management} gt={gt.management}")
        ticker_ok = (not pred.ticker) or _ticker_matches(pred.ticker, gt, case) or _norm_ticker(pred.ticker) in {
            _norm_ticker(t) for t in case.tickers
        }
        if pred.ticker and not ticker_ok:
            notes.append(f"ticker_mismatch pred={pred.ticker!r}")
    elif pq == "exit":
        if not action_ok:
            notes.append(f"action_mismatch pred={pred.action} gt=exit")
        ticker_ok = _ticker_matches(pred.ticker, gt, case)
        if not ticker_ok:
            notes.append(f"ticker_mismatch pred={pred.ticker!r} gt={gt.ticker!r}")
        if gt.exit and pred.exit and pred.exit != gt.exit:
            extra_ok = False
            notes.append(f"exit_mismatch pred={pred.exit} gt={gt.exit}")

    raw_pass = (
        action_ok
        and ticker_ok
        and side_ok
        and size_ok
        and extra_ok
        and citation_ok
        and not cfp
        and not leakage
    )
    raw: Status = "PASS" if raw_pass else "FAIL"
    # Locked 16 stay AMBIGUOUS even if the model would otherwise PASS (no soft-relabel).
    status = "AMBIGUOUS" if fixture_tag else raw
    if fixture_tag:
        notes.append("fixture_tag=AMBIGUOUS_no_soft_relabel")

    return CaseModelScore(
        case_id=case.case_id,
        status=status,
        raw_status=raw,
        fixture_tag=fixture_tag,
        primary_question=pq,
        cfp=cfp,
        citation_ok=citation_ok,
        notes=notes,
        gt=gt.model_dump(),
        predicted=predicted,
    )


def _no_trade_pr(
    pack: FrozenPack,
    preds: dict[str, ModelPrediction],
    lock: ModelEvalLock,
) -> tuple[float | None, float | None]:
    gt_abstain = lock.gt_abstain_ids
    pred_abstain_ids = [cid for cid, pred in preds.items() if pred.action == "abstain"]
    if pred_abstain_ids:
        tp = sum(1 for cid in pred_abstain_ids if cid in gt_abstain)
        precision = tp / len(pred_abstain_ids)
    else:
        precision = None
    if gt_abstain:
        recall = sum(1 for cid in gt_abstain if preds.get(cid) and preds[cid].action == "abstain") / len(
            gt_abstain
        )
    else:
        recall = None
    return precision, recall


def score_model_run(
    pack: FrozenPack,
    predictions: Sequence[ModelPrediction],
    lock: ModelEvalLock,
    corpus: SealedCorpus | None = None,
) -> ModelEvalRun:
    by_id = {p.case_id: p for p in predictions}
    scores: list[CaseModelScore] = []
    kill_hits: list[str] = []
    for case in pack.cases:
        pred = by_id.get(case.case_id)
        if pred is not None:
            kill_hits.extend(kill_scar_hits(case, pred, lock, corpus))
        scores.append(score_prediction(case, pred, lock, corpus))

    run_valid = not kill_hits
    n_missing = sum(1 for s in scores if "missing_prediction" in s.notes)
    n_pass = sum(1 for s in scores if s.status == "PASS")
    n_fail = sum(1 for s in scores if s.status == "FAIL")
    n_amb = sum(1 for s in scores if s.status == "AMBIGUOUS")
    cfp_count = sum(1 for s in scores if s.cfp)

    non_amb = [s for s in scores if s.fixture_tag != "AMBIGUOUS" and "missing_prediction" not in s.notes]
    if non_amb:
        match = sum(1 for s in non_amb if s.raw_status == "PASS") / len(non_amb)
    else:
        match = None

    non_abstain_preds = [
        s
        for s in scores
        if by_id.get(s.case_id) is not None and by_id[s.case_id].action != "abstain"
    ]
    if non_abstain_preds:
        coverage = sum(1 for s in non_abstain_preds if s.citation_ok) / len(non_abstain_preds)
    else:
        coverage = None

    precision, recall = _no_trade_pr(pack, by_id, lock)
    metrics = lock.metrics
    gates = {
        "behavioral_action_match_ok": match is not None and match >= metrics.behavioral_action_match_min,
        "no_trade_recall_ok": recall is not None and recall >= metrics.no_trade_recall_min,
        "no_trade_precision_ok": precision is not None and precision >= metrics.no_trade_precision_min,
        "cfp_ok": cfp_count <= metrics.catastrophic_fp_max,
        "citation_coverage_ok": coverage is not None and coverage >= metrics.citation_coverage_min_non_abstain,
        "kill_scars_clear": run_valid,
        "model_eval_clear": False,
        "paper_authority": False,
        "capital": 0,
    }
    model_eval_clear = (
        run_valid
        and gates["behavioral_action_match_ok"]
        and gates["no_trade_recall_ok"]
        and gates["no_trade_precision_ok"]
        and gates["cfp_ok"]
        and gates["citation_coverage_ok"]
    )
    gates["model_eval_clear"] = model_eval_clear
    # Model CLEAR ≠ paper authority. Stay false / capital 0.
    gates["paper_authority"] = False

    run_id = next((p.run_id for p in predictions if p.run_id), f"melv0-{uuid.uuid4().hex[:12]}")
    summary = ModelEvalSummary(
        n_cases=len(scores),
        n_scored=len(scores) - n_missing,
        n_pass=n_pass,
        n_fail=n_fail,
        n_ambiguous=n_amb,
        n_missing=n_missing,
        behavioral_action_match=match,
        no_trade_precision=precision,
        no_trade_recall=recall,
        cfp_count=cfp_count,
        citation_coverage_non_abstain=coverage,
        run_valid=run_valid,
        kill_scars=kill_hits,
        paper_authority=False,
        capital=0,
        pnl_scored=False,
        gates=gates,
    )
    return ModelEvalRun(
        summary=summary,
        scores=scores,
        predictions=list(predictions),
        fixture_sha256_16=pack.sha256_16 or EXPECTED_FIXTURE_SHA16,
        lock_version=lock.version,
        run_id=run_id,
    )


def write_run_artifact(run: ModelEvalRun, out_root: Path, *, pack_path: Path | None = None) -> Path:
    """Write immutable JSON/JSONL under results/model_eval_runs/<run_id>/."""

    dest = Path(out_root) / run.run_id
    if dest.exists():
        raise FileExistsError(f"refusing to overwrite model-eval run dir {dest}")
    dest.mkdir(parents=True, exist_ok=False)
    created = datetime.now(timezone.utc).isoformat()
    manifest = {
        "run_id": run.run_id,
        "lock_version": run.lock_version,
        "fixture_sha256_16": run.fixture_sha256_16,
        "fixture_path": str(pack_path) if pack_path else None,
        "created_at": created,
        "paper_authority": False,
        "capital": 0,
        "run_valid": run.summary.run_valid,
        "kill_scars": run.summary.kill_scars,
        "cfp_count": run.summary.cfp_count,
        "pnl_scored": False,
        "orthogonal_to": "Quant_M0_fill_receipts",
        "live_llm": False,
        "broker": False,
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (dest / "summary.json").write_text(
        json.dumps(run.summary.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )
    (dest / "scores.json").write_text(
        json.dumps([s.model_dump(mode="json") for s in run.scores], indent=2) + "\n", encoding="utf-8"
    )
    pred_path = dest / "predictions.jsonl"
    with pred_path.open("w", encoding="utf-8") as fh:
        for pred in run.predictions:
            fh.write(pred.model_dump_json() + "\n")
    scores_jsonl = dest / "scores.jsonl"
    with scores_jsonl.open("w", encoding="utf-8") as fh:
        for score in run.scores:
            fh.write(score.model_dump_json() + "\n")
    run.out_dir = str(dest)
    return dest


def make_abstain_prediction(case: FrozenCase, *, run_id: str, model_id: str) -> ModelPrediction:
    ack = case.eligible_filter.ts_lt.isoformat()
    return ModelPrediction(
        case_id=case.case_id,
        decision_ts=case.decision_ts.isoformat(),
        action="abstain",
        side="n/a",
        ticker="",
        size_pct=None,
        stop=None,
        management=None,
        exit=None,
        rejected_alternatives=[],
        citations=[],
        confidence=0.0,
        abstain_reason="baseline_abstain_everywhere",
        sealed_cutoff_ack=ack,
        retrieved_ids=[],
        model_id=model_id,
        run_id=run_id,
    )


def abstain_everywhere_predictions(pack: FrozenPack, *, run_id: str, model_id: str) -> list[ModelPrediction]:
    return [make_abstain_prediction(case, run_id=run_id, model_id=model_id) for case in pack.cases]


def write_abstain_everywhere(path: Path, pack: FrozenPack, *, run_id: str, model_id: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = abstain_everywhere_predictions(pack, run_id=run_id, model_id=model_id)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(row.model_dump_json() + "\n")
    return path


def run_score_model(
    *,
    predictions_path: Path,
    ingest_dir: Path | None,
    frozen_path: Path | None = None,
    lock_path: Path | None = None,
    out_root: Path,
) -> ModelEvalRun:
    lock = load_model_eval_lock(lock_path or DEFAULT_LOCK_PATH)
    pack = load_frozen_pack(frozen_path, lock_path=lock_path or DEFAULT_LOCK_PATH)
    predictions = load_predictions(predictions_path)
    corpus = load_mvp_ingest(ingest_dir) if ingest_dir is not None else SealedCorpus([])
    run = score_model_run(pack, predictions, lock, corpus)
    write_run_artifact(run, out_root, pack_path=Path(frozen_path) if frozen_path else None)
    if not run.summary.run_valid:
        raise KillScarError(run.summary.kill_scars, run=run)
    return run
