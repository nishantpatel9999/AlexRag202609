"""Sealed-cutoff decision-model emitter. Capital 0; does not unlock paper.

Builds retrieval context via ``eligible_filter`` (excluding ``banned_same_day_ids``),
never injects GT / target_action / banned fill bodies, and writes one
MODEL_EVAL_LOCK_V0 prediction per frozen case.

``--dry-run`` skips Inferhub and emits honest abstains (``model_id=dry_run_abstain``).
Live Inferhub needs ``INFERHUB_API_KEY`` on the operator Mac; pytest stays offline.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from alexrag.eval.frozen_pack import FrozenCase, FrozenPack, load_frozen_pack
from alexrag.eval.model_context import ModelContext, assert_no_gt_keys, build_model_context
from alexrag.eval.model_lock import (
    DEFAULT_FROZEN_PACK,
    DEFAULT_LOCK_PATH,
    HARD_KILL_SCAR_IDS,
    NEVER_INJECT_INTO_CONTEXT,
    ModelEvalLock,
    load_model_eval_lock,
)
from alexrag.eval.model_prediction import ACTIONS, SIDES, ModelCitation, ModelPrediction
from alexrag.eval.sealed_corpus import CorpusMessage, SealedCorpus, eligible_messages, load_mvp_ingest
from alexrag.llm.inferhub import INFERHUB_MODEL, InferhubClient, InferhubError

DRY_RUN_MODEL_ID = "dry_run_abstain"
DEFAULT_MAX_MESSAGES = 32
DEFAULT_MAX_TEXT_CHARS = 480
DEFAULT_OUT_ROOT = Path("results/model_eval_runs")

class EmitRunMeta(BaseModel):
    """Sidecar for an emit run. Paper stays KILL; capital stays 0."""

    model_config = ConfigDict(extra="allow")

    run_id: str
    model_id: str
    dry_run: bool
    n_cases: int
    n_abstain: int
    paper_authority: bool = False
    capital: int = 0
    fixture_sha256_16: str
    lock_version: str
    ingest: str | None = None
    predictions_path: str
    sealed_cutoff_rule: str = "only artifacts with timestamp < decision_ts"
    live_llm: bool = False
    broker: bool = False
    model_eval_clear: bool = False
    orthogonal_to: str = "Quant_M0_fill_receipts"
    created_at: str
    max_messages: int = DEFAULT_MAX_MESSAGES

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

    @field_validator("model_eval_clear")
    @classmethod
    def _not_clear(cls, value: bool) -> bool:
        del value
        return False


class EmitRun(BaseModel):
    predictions: list[ModelPrediction]
    meta: EmitRunMeta
    out_dir: str
    prompts: list[list[dict[str, str]]] = Field(default_factory=list)


def new_run_id() -> str:
    return f"emit-{uuid.uuid4().hex[:12]}"


def select_retrieved_ids(
    case: FrozenCase,
    eligible: Sequence[CorpusMessage],
    *,
    max_messages: int = DEFAULT_MAX_MESSAGES,
) -> list[str]:
    """Eligible key_evidence hints first, then most recent eligible. Never banned/GT."""

    banned = set(case.banned_same_day_ids)
    target_id = case.target_action.message_id
    eligible_by_id = {m.message_id: m for m in eligible}
    chosen: list[str] = []
    seen: set[str] = set()

    def _accept(mid: str) -> bool:
        if not mid or mid in seen or mid in banned or mid == target_id:
            return False
        if mid not in eligible_by_id:
            return False
        return True

    for mid in case.key_evidence_ids:
        if not _accept(mid):
            continue
        chosen.append(mid)
        seen.add(mid)
        if len(chosen) >= max_messages:
            return chosen

    # eligible_for sorts ascending by ts; walk newest first.
    for msg in reversed(list(eligible)):
        mid = msg.message_id
        if not _accept(mid):
            continue
        chosen.append(mid)
        seen.add(mid)
        if len(chosen) >= max_messages:
            break
    return chosen


def truncate_text(text: str, max_chars: int = DEFAULT_MAX_TEXT_CHARS) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def ticker_mentioned(text: str, ticker: str) -> bool:
    token = (ticker or "").strip().upper()
    if not token:
        return False
    return re.search(rf"\b{re.escape(token)}\b", (text or "").upper()) is not None


def thin_evidence_reason(case: FrozenCase, ctx: ModelContext) -> str | None:
    """Fail-closed: no sealed rows, or enter/size with no ticker in priors."""

    if not ctx.messages:
        return "thin_evidence_no_eligible_messages"
    if case.primary_question in {"enter", "size"} and case.tickers:
        blob = " ".join(m.text for m in ctx.messages)
        if not any(ticker_mentioned(blob, t) for t in case.tickers):
            return "thin_evidence_no_ticker_in_priors"
    return None


def _schema_instruction(lock: ModelEvalLock) -> str:
    fields = lock.output_schema.get("per_case_required_fields") or [
        "case_id",
        "decision_ts",
        "action",
        "side",
        "ticker",
        "size_pct",
        "stop",
        "management",
        "exit",
        "rejected_alternatives",
        "citations",
        "confidence",
        "abstain_reason",
        "sealed_cutoff_ack",
        "retrieved_ids",
        "model_id",
        "run_id",
    ]
    actions = lock.output_schema.get("action_enum") or list(ACTIONS)
    sides = lock.output_schema.get("side_enum") or list(SIDES)
    return (
        "You are a sealed-cutoff trading decision model. Reply with one JSON object "
        "and nothing else (no markdown, no prose). Required keys: "
        + ", ".join(fields)
        + f". action is one of {actions}. side is one of {sides}. "
        "citations is an array of {source, message_id, ts, quote_span}; each "
        "message_id must be from the sealed context. quote_span must be a verbatim "
        "substring of that message. If evidence is thin or you are unsure, set "
        "action=abstain with abstain_reason. Do not invent fills. Do not use "
        "information after the sealed cutoff. Do not echo ground-truth labels."
    )


def build_prompt_messages(ctx: ModelContext, lock: ModelEvalLock) -> list[dict[str, str]]:
    """Short system+user prompt. Sealed messages only; no GT keys."""

    lines = [
        f"case_id: {ctx.case_id}",
        f"decision_ts: {ctx.decision_ts}",
        f"tickers: {', '.join(ctx.tickers) if ctx.tickers else '(none)'}",
        f"primary_question: {ctx.primary_question}",
        f"sealed_cutoff_ack: {ctx.sealed_cutoff_ack}",
        f"retrieved_ids: {', '.join(ctx.retrieved_ids) if ctx.retrieved_ids else '(none)'}",
        "sealed_context:",
    ]
    if not ctx.messages:
        lines.append("(empty — no eligible messages before cutoff)")
    for msg in ctx.messages:
        ts = msg.ts.isoformat() if msg.ts is not None else ""
        lines.append(
            f"- id={msg.message_id} ts={ts} channel={msg.channel} "
            f"text={truncate_text(msg.text)}"
        )
    user = "\n".join(lines)
    payload = {"system": _schema_instruction(lock), "user": user}
    assert_no_gt_keys({"case_id": ctx.case_id, "primary_question": ctx.primary_question})
    for forbidden in NEVER_INJECT_INTO_CONTEXT | {"target_action", "action_classes"}:
        if forbidden in user or forbidden in payload["system"]:
            raise ValueError(f"prompt leaked forbidden token {forbidden}")
    return [
        {"role": "system", "content": payload["system"]},
        {"role": "user", "content": payload["user"]},
    ]


def extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty model text")
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("no JSON object in model text")
    obj = json.loads(raw[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError("model JSON must be an object")
    return obj


def sealed_abstain(
    case: FrozenCase,
    ctx: ModelContext,
    *,
    run_id: str,
    model_id: str,
    reason: str,
) -> ModelPrediction:
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
        abstain_reason=reason,
        sealed_cutoff_ack=ctx.sealed_cutoff_ack,
        retrieved_ids=list(ctx.retrieved_ids),
        model_id=model_id,
        run_id=run_id,
    )


def _eligible_citation(
    raw: Any,
    eligible_ids: set[str],
    by_id: dict[str, Any],
) -> ModelCitation | None:
    if not isinstance(raw, dict):
        return None
    mid = str(raw.get("message_id") or "").strip()
    if not mid or mid not in eligible_ids:
        return None
    msg = by_id.get(mid)
    source = str(raw.get("source") or (msg.channel if msg is not None else "") or "")
    ts = str(raw.get("ts") or "")
    if not ts and msg is not None and msg.ts is not None:
        ts = msg.ts.isoformat()
    quote = str(raw.get("quote_span") or "")
    if quote and msg is not None and quote.casefold() not in (msg.text or "").casefold():
        quote = ""
    return ModelCitation(source=source, message_id=mid, ts=ts, quote_span=quote)


def prediction_from_model_obj(
    obj: dict[str, Any],
    case: FrozenCase,
    ctx: ModelContext,
    *,
    run_id: str,
    model_id: str,
) -> ModelPrediction:
    """Map model JSON onto the lock schema. Overwrite audit fields; drop leaks."""

    cleaned = dict(obj)
    for key in NEVER_INJECT_INTO_CONTEXT | {"target_action", "action_classes", "fill_message_body"}:
        cleaned.pop(key, None)
    eligible_ids = set(ctx.retrieved_ids)
    by_id = {m.message_id: m for m in ctx.messages}
    citations: list[ModelCitation] = []
    for raw in cleaned.get("citations") or []:
        cite = _eligible_citation(raw, eligible_ids, by_id)
        if cite is not None:
            citations.append(cite)

    action = cleaned.get("action")
    if action not in ACTIONS:
        raise ValueError(f"invalid action {action!r}")
    side = cleaned.get("side") if cleaned.get("side") in SIDES else ("n/a" if action == "abstain" else None)
    if side is None:
        raise ValueError(f"invalid side {cleaned.get('side')!r}")

    abstain_reason = cleaned.get("abstain_reason")
    if action != "abstain" and not citations:
        action = "abstain"
        side = "n/a"
        abstain_reason = "thin_evidence_no_eligible_citations"
    if action == "abstain" and not (abstain_reason or "").strip():
        abstain_reason = "model_abstain"

    size_pct = cleaned.get("size_pct")
    if size_pct == "":
        size_pct = None

    pred = ModelPrediction(
        case_id=case.case_id,
        decision_ts=case.decision_ts.isoformat(),
        action=action,
        side=side,
        ticker="" if action == "abstain" else str(cleaned.get("ticker") or ""),
        size_pct=size_pct,
        stop=cleaned.get("stop"),
        management=cleaned.get("management"),
        exit=cleaned.get("exit"),
        rejected_alternatives=list(cleaned.get("rejected_alternatives") or []),
        citations=citations,
        confidence=cleaned.get("confidence", 0.0),
        abstain_reason=abstain_reason,
        sealed_cutoff_ack=ctx.sealed_cutoff_ack,
        retrieved_ids=list(ctx.retrieved_ids),
        model_id=model_id,
        run_id=run_id,
    )
    banned = set(case.banned_same_day_ids)
    if any(mid in banned for mid in pred.retrieved_ids):
        raise ValueError("retrieved_ids intersect banned_same_day_ids")
    if any(c.message_id in banned for c in pred.citations):
        raise ValueError("citations intersect banned_same_day_ids")
    return pred


def emit_one_case(
    case: FrozenCase,
    corpus: SealedCorpus,
    lock: ModelEvalLock,
    *,
    run_id: str,
    model_id: str,
    dry_run: bool,
    client: InferhubClient | None = None,
    max_messages: int = DEFAULT_MAX_MESSAGES,
) -> tuple[ModelPrediction, list[dict[str, str]]]:
    eligible = eligible_messages(case, corpus)
    retrieved_ids = select_retrieved_ids(case, eligible, max_messages=max_messages)
    ctx = build_model_context(case, eligible, retrieved_ids=retrieved_ids)
    dumped = ctx.model_dump_sealed()
    assert_no_gt_keys(dumped)
    prompts = build_prompt_messages(ctx, lock)
    joined = "\n".join(m["content"] for m in prompts)
    if "target_action" in joined:
        raise ValueError("prompt contains target_action")
    if f"id={case.target_action.message_id} " in joined:
        raise ValueError("prompt contains GT fill id")

    if dry_run:
        pred = sealed_abstain(
            case,
            ctx,
            run_id=run_id,
            model_id=DRY_RUN_MODEL_ID,
            reason="dry_run_skip_network",
        )
        return pred, prompts

    thin = thin_evidence_reason(case, ctx)
    if thin:
        return sealed_abstain(case, ctx, run_id=run_id, model_id=model_id, reason=thin), prompts

    if client is None:
        return (
            sealed_abstain(
                case, ctx, run_id=run_id, model_id=model_id, reason="inferhub_unconfigured"
            ),
            prompts,
        )

    try:
        result = client.complete(prompts)
    except InferhubError:
        return (
            sealed_abstain(case, ctx, run_id=run_id, model_id=model_id, reason="inferhub_error"),
            prompts,
        )

    text = result.get("text") if isinstance(result, dict) else None
    if not text:
        return (
            sealed_abstain(
                case, ctx, run_id=run_id, model_id=model_id, reason="inferhub_empty_completion"
            ),
            prompts,
        )
    try:
        obj = extract_json_object(str(text))
        pred = prediction_from_model_obj(obj, case, ctx, run_id=run_id, model_id=model_id)
    except Exception:
        return (
            sealed_abstain(case, ctx, run_id=run_id, model_id=model_id, reason="parse_failure"),
            prompts,
        )

    # Second-look thin evidence: do not keep an invented enter on empty priors.
    post_thin = thin_evidence_reason(case, ctx)
    if post_thin and pred.action in {"enter", "size"}:
        return sealed_abstain(case, ctx, run_id=run_id, model_id=model_id, reason=post_thin), prompts
    return pred, prompts


def write_emit_artifacts(
    predictions: Sequence[ModelPrediction],
    meta: EmitRunMeta,
    out_root: Path,
) -> Path:
    dest = Path(out_root) / meta.run_id
    if dest.exists():
        raise FileExistsError(f"refusing to overwrite emit run dir {dest}")
    dest.mkdir(parents=True, exist_ok=False)
    pred_path = dest / "predictions.jsonl"
    with pred_path.open("w", encoding="utf-8") as fh:
        for pred in predictions:
            fh.write(pred.model_dump_json() + "\n")
    meta.predictions_path = str(pred_path)
    (dest / "run_metadata.json").write_text(
        json.dumps(meta.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )
    return dest


def emit_model_predictions(
    *,
    ingest_dir: Path | None,
    frozen_path: Path | None = None,
    lock_path: Path | None = None,
    out_root: Path = DEFAULT_OUT_ROOT,
    dry_run: bool = True,
    run_id: str | None = None,
    max_messages: int = DEFAULT_MAX_MESSAGES,
    client: InferhubClient | None = None,
) -> EmitRun:
    lock = load_model_eval_lock(lock_path or DEFAULT_LOCK_PATH)
    pack = load_frozen_pack(frozen_path or DEFAULT_FROZEN_PACK, lock_path=lock_path or DEFAULT_LOCK_PATH)
    corpus = load_mvp_ingest(ingest_dir)
    rid = run_id or new_run_id()
    model_id = DRY_RUN_MODEL_ID if dry_run else INFERHUB_MODEL
    if not dry_run and client is None:
        client = InferhubClient()

    predictions: list[ModelPrediction] = []
    prompts_all: list[list[dict[str, str]]] = []
    for case in pack.cases:
        pred, prompts = emit_one_case(
            case,
            corpus,
            lock,
            run_id=rid,
            model_id=model_id,
            dry_run=dry_run,
            client=client,
            max_messages=max_messages,
        )
        predictions.append(pred)
        prompts_all.append(prompts)

    n_abstain = sum(1 for p in predictions if p.action == "abstain")
    created = datetime.now(timezone.utc).isoformat()
    meta = EmitRunMeta(
        run_id=rid,
        model_id=model_id,
        dry_run=dry_run,
        n_cases=len(predictions),
        n_abstain=n_abstain,
        paper_authority=False,
        capital=0,
        fixture_sha256_16=pack.sha256_16,
        lock_version=lock.version,
        ingest=str(ingest_dir) if ingest_dir is not None else None,
        predictions_path="",
        live_llm=not dry_run,
        broker=False,
        model_eval_clear=False,
        created_at=created,
        max_messages=max_messages,
    )
    assert_emit_sealed(pack, predictions)
    dest = write_emit_artifacts(predictions, meta, out_root)
    return EmitRun(predictions=predictions, meta=meta, out_dir=str(dest), prompts=prompts_all)


def assert_emit_sealed(pack: FrozenPack, predictions: Sequence[ModelPrediction]) -> None:
    """Invariant checks for tests and the CLI: 48 ids, no banned retrieval, no enter on kill scars in dry-run."""

    by_id = {p.case_id: p for p in predictions}
    expected = {c.case_id for c in pack.cases}
    if set(by_id) != expected:
        raise ValueError(f"prediction case_ids mismatch: extra={set(by_id)-expected} missing={expected-set(by_id)}")
    for case in pack.cases:
        pred = by_id[case.case_id]
        banned = set(case.banned_same_day_ids)
        leaked = [i for i in pred.retrieved_ids if i in banned]
        if leaked:
            raise ValueError(f"{case.case_id} retrieved banned ids {leaked}")
        cited = [c.message_id for c in pred.citations if c.message_id in banned]
        if cited:
            raise ValueError(f"{case.case_id} cited banned ids {cited}")
        if case.case_id in HARD_KILL_SCAR_IDS and pred.model_id == DRY_RUN_MODEL_ID:
            if pred.action != "abstain":
                raise ValueError(f"{case.case_id} dry-run must abstain, got {pred.action}")
