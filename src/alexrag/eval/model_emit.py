"""Sealed-cutoff decision-model emitter. Capital 0; does not unlock paper.

Builds retrieval context via ``eligible_filter`` (excluding ``banned_same_day_ids``),
never injects GT / target_action / banned fill bodies, and writes one
MODEL_EVAL_LOCK_V0 prediction per frozen case.

``--dry-run`` skips Inferhub and emits honest abstains (``model_id=dry_run_abstain``).
Live Inferhub needs ``INFERHUB_API_KEY`` on the operator Mac; pytest stays offline.
Next live ``run_id`` is ``inferhub-cbcn-v3-quality`` (decision-quality V3 delta).
Does not claim model CLEAR; capital 0; paper stays KILL.
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
from alexrag.llm.inferhub import (
    INFERHUB_MAX_TOKENS,
    INFERHUB_MODEL,
    INFERHUB_TEMPERATURE,
    InferhubClient,
    InferhubError,
)

DRY_RUN_MODEL_ID = "dry_run_abstain"
DEFAULT_MAX_MESSAGES = 48
DEFAULT_MAX_TEXT_CHARS = 480
DEFAULT_OUT_ROOT = Path("results/model_eval_runs")
SUGGESTED_LIVE_RUN_ID = "inferhub-cbcn-v3-quality"
QUALITY_DELTA = "decision_quality_v3"
PARSE_REPAIR_USER = (
    "Your previous reply was not valid JSON. Reply with a single JSON object "
    "matching the required schema and nothing else. No markdown fences, no "
    "prose, no trailing commentary — JSON object only. Required keys include "
    "action, side, ticker, citations, abstain_reason, confidence, "
    "rejected_alternatives. citations[].message_id must be copied from "
    "retrieved_ids in the user message."
)
ACTION_ALIASES = {
    "enter": "enter",
    "entry": "enter",
    "abstain": "abstain",
    "size": "size",
    "manage": "manage",
    "management": "manage",
    "exit": "exit",
    "close": "exit",
}
SIDE_ALIASES = {
    "long": "long",
    "buy": "long",
    "short": "short",
    "sell": "short",
    "n/a": "n/a",
    "na": "n/a",
    "none": "n/a",
}


class EmitParseStats:
    """Mutable counters for parse_failure / repair recovery across a run."""

    __slots__ = ("n_parse_failure", "n_parse_retry_recovered", "n_parse_local_repaired")

    def __init__(self) -> None:
        self.n_parse_failure = 0
        self.n_parse_retry_recovered = 0
        self.n_parse_local_repaired = 0


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
    n_parse_failure: int = 0
    n_parse_retry_recovered: int = 0
    n_parse_local_repaired: int = 0
    temperature: float = INFERHUB_TEMPERATURE
    max_tokens: int = INFERHUB_MAX_TOKENS
    response_format: str = "json_object"
    quality_delta: str = QUALITY_DELTA
    suggested_live_run_id: str = SUGGESTED_LIVE_RUN_ID

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


def _message_has_listed_ticker(text: str, tickers: Sequence[str]) -> bool:
    return any(ticker_mentioned(text, t) for t in tickers)


def select_retrieved_ids(
    case: FrozenCase,
    eligible: Sequence[CorpusMessage],
    *,
    max_messages: int = DEFAULT_MAX_MESSAGES,
) -> list[str]:
    """Key_evidence first among same-ticker hits, then other ticker-aware eligible.

    Recency fills remaining slots. Never banned/GT. Same-ticker rows from the
    broader eligible set are reserved so long key_evidence lists cannot drop them.
    """

    banned = set(case.banned_same_day_ids)
    target_id = case.target_action.message_id
    eligible_by_id = {m.message_id: m for m in eligible}
    chosen: list[str] = []
    seen: set[str] = set()
    tickers = list(case.tickers)

    def _accept(mid: str) -> bool:
        if not mid or mid in seen or mid in banned or mid == target_id:
            return False
        if mid not in eligible_by_id:
            return False
        return True

    def _take(mid: str) -> bool:
        if not _accept(mid):
            return False
        chosen.append(mid)
        seen.add(mid)
        return len(chosen) >= max_messages

    ticker_ids = {
        m.message_id
        for m in eligible
        if tickers and _message_has_listed_ticker(m.text, tickers)
    }

    # 1) key_evidence that mentions a listed ticker
    if tickers:
        for mid in case.key_evidence_ids:
            if mid not in ticker_ids:
                continue
            if _take(mid):
                return chosen

        # 2) other same-ticker eligible, newest first (eligible_for is ascending)
        for msg in reversed(list(eligible)):
            if msg.message_id not in ticker_ids:
                continue
            if _take(msg.message_id):
                return chosen

    # 3) remaining key_evidence (non-ticker hints)
    for mid in case.key_evidence_ids:
        if _take(mid):
            return chosen

    # 4) remaining eligible, newest first
    for msg in reversed(list(eligible)):
        if _take(msg.message_id):
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
        "You are a sealed-cutoff trading decision model. "
        "Reply with exactly one JSON object and nothing else — no markdown fences, "
        "no prose, no trailing commentary. Required keys: "
        + ", ".join(fields)
        + f". action is one of {actions}. side is one of {sides}. "
        "citations is an array of {source, message_id, ts, quote_span}. "
        "Each citations[].message_id MUST be copied from retrieved_ids in the user "
        "message. quote_span MUST be a verbatim substring of that sealed message. "
        "ABSTAIN DISCIPLINE (protect no-trade precision): action=abstain is legal "
        "ONLY when primary_question is abstain, OR evidence is thin (empty "
        "sealed_context, no listed ticker mentioned, and no Long/Short/Closed/ADD/"
        "trim/Sold language naming a listed ticker). If primary_question is enter, "
        "size, manage, or exit and that sealed language exists, you MUST emit the "
        "asked action with a citation — do not abstain. False abstains on those "
        "questions destroy no-trade precision. "
        "When primary_question is abstain you MUST abstain; do not invent a fill "
        "for the listed ticker. Same-day Long/Short tape in other names is not a "
        "reason to enter the rejected ticker. "
        "ACTION MAP: enter → action=enter, ticker+side from sealed 'Long TICKER' / "
        "'Short TICKER' / bought / filled / entered; cite that retrieved_id. "
        "size → action=size (or enter); copy size_pct from the percentage beside "
        "that ticker; ticker+side as enter. "
        "manage → action=manage (not abstain); management add|trim|move_sl|reopen|"
        "close_all when ADD/trim/SL/reopen/closed language is present; ticker from "
        "that language or empty string if unclear — never guess a wrong ticker. "
        "exit → action=exit (not abstain); ticker MUST be the Closed/Sold/stopped "
        "name; exit close|sold|stopped matching that language. "
        "Do not invent fills, prices, or message ids. Do not use information "
        "after the sealed cutoff. Do not echo labels that are not in sealed_context."
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
    lines.append(
        "Respond with one JSON object only. If primary_question is abstain, "
        "abstain. If primary_question is enter, size, manage, or exit and "
        "sealed_context has a listed ticker with Long/Short/Closed/ADD/trim/"
        "Sold language, emit that asked action (not abstain), cite retrieved_ids, "
        "and name the ticker (or leave ticker empty on manage if unclear). "
        "Abstain only if primary_question is abstain or that evidence is thin."
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


def strip_code_fences(text: str) -> str:
    """Drop markdown fences so JSON extract can see the object."""

    raw = (text or "").strip()
    if not raw:
        return ""
    fence = re.search(r"```(?:json|JSON)?\s*\n?(.*?)```", raw, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return raw


def greedy_first_json_object(text: str) -> str | None:
    """Return the first balanced `{...}` span, ignoring braces inside strings."""

    start = (text or "").find("{")
    if start < 0:
        return None
    in_string = False
    escape = False
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
            if depth < 0:
                return None
    return None


def repair_truncated_json(fragment: str) -> str | None:
    """Close dangling strings / braces / brackets; drop a trailing comma.

    Used when the model hits max_tokens mid-object. Does not invent keys.
    """

    start = (fragment or "").find("{")
    if start < 0:
        return None
    s = fragment[start:]
    in_string = False
    escape = False
    stack: list[str] = []
    for ch in s:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()
    out = s.rstrip()
    if in_string:
        if out.endswith("\\") and not out.endswith("\\\\"):
            out = out[:-1]
        out += '"'
    stripped = out.rstrip()
    if stripped.endswith(","):
        out = stripped[:-1]
    if not stack and greedy_first_json_object(out):
        return greedy_first_json_object(out)
    while stack:
        out += stack.pop()
    return out


def try_parse_json_object(candidate: str) -> dict[str, Any] | None:
    try:
        obj = json.loads(candidate)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse first JSON object; tolerate fences, trailing prose, truncated braces."""

    raw = strip_code_fences(text)
    if not raw:
        raise ValueError("empty model text")
    candidates: list[str] = []
    greedy = greedy_first_json_object(raw)
    if greedy:
        candidates.append(greedy)
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        span = raw[start : end + 1]
        if span not in candidates:
            candidates.append(span)
    if start >= 0:
        repaired = repair_truncated_json(raw[start:])
        if repaired and repaired not in candidates:
            candidates.append(repaired)
    for cand in candidates:
        obj = try_parse_json_object(cand)
        if obj is not None:
            return obj
    raise ValueError("no JSON object in model text")


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


def _coerce_action(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    token = value.strip().casefold().replace("-", " ").replace("_", " ")
    if not token:
        return None
    first = token.split()[0]
    return ACTION_ALIASES.get(first)


def _coerce_side(value: Any, action: str) -> str | None:
    if value is None or value == "":
        return "n/a" if action == "abstain" else None
    if not isinstance(value, str):
        return None
    token = value.strip().casefold().replace("-", " ").replace("_", " ")
    if not token:
        return "n/a" if action == "abstain" else None
    first = token.split()[0]
    return SIDE_ALIASES.get(first)


def _coerce_size_pct(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip().replace("%", "")
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def _coerce_confidence(value: Any) -> float | str:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        try:
            return float(stripped)
        except ValueError:
            return stripped or 0.0
    return 0.0


def _coerce_optional_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, str):
        return value
    return str(value)


def _normalize_citation_raw(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, str):
        return {"message_id": raw}
    if not isinstance(raw, dict):
        return None
    cleaned = dict(raw)
    if not cleaned.get("message_id"):
        alt = cleaned.get("id") or cleaned.get("messageId") or cleaned.get("msg_id")
        if alt is not None:
            cleaned["message_id"] = alt
    mid = cleaned.get("message_id")
    if isinstance(mid, bool):
        return None
    if isinstance(mid, (int, float)):
        cleaned["message_id"] = str(int(mid))
    elif mid is not None:
        cleaned["message_id"] = str(mid).strip()
    return cleaned


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


_ENTER_SIZE_INTENT = re.compile(
    r"\b(long|short|bought|buy|filled|entered|enter)\b",
    re.IGNORECASE,
)
_MANAGE_INTENT = re.compile(
    r"\b(add(?:ed)?(?:#\d+)?|trim(?:med)?|reopen(?:ed)?|ssl|(?:move[_\s-]?)?sl|stop(?:ped)?)\b",
    re.IGNORECASE,
)
_EXIT_INTENT = re.compile(
    r"\b(closed|sold|stopped|taking my sl)\b",
    re.IGNORECASE,
)
_LONG_SIDE = re.compile(r"\b(long|bought|buy|filled)\b", re.IGNORECASE)
_SHORT_SIDE = re.compile(r"\bshort\b", re.IGNORECASE)


def _quote_around_ticker(text: str, ticker: str, max_len: int = 80) -> str:
    compact = " ".join((text or "").split())
    token = (ticker or "").upper()
    if not compact:
        return ""
    if not token:
        return compact[:max_len]
    idx = compact.upper().find(token)
    if idx < 0:
        return compact[:max_len]
    start = max(0, idx - 16)
    end = min(len(compact), idx + len(token) + 48)
    return compact[start:end].strip()[:max_len]


def _side_from_sealed_text(text: str) -> str | None:
    has_long = _LONG_SIDE.search(text or "") is not None
    has_short = _SHORT_SIDE.search(text or "") is not None
    if has_short and not has_long:
        return "short"
    if has_long:
        return "long"
    return None


def _size_near_ticker(text: str, ticker: str) -> float | None:
    token = re.escape((ticker or "").strip())
    if not token:
        return None
    patterns = [
        rf"(\d+(?:\.\d+)?)\s*%\s*{token}\b",
        rf"\b(?:long|short)\s+(\d+(?:\.\d+)?)\s*%\s*{token}\b",
        rf"\b{token}\b[^%]{{0,24}}(\d+(?:\.\d+)?)\s*%",
    ]
    for pattern in patterns:
        match = re.search(pattern, text or "", re.IGNORECASE)
        if not match:
            continue
        try:
            return float(match.group(1))
        except (TypeError, ValueError):
            continue
    return None


def _intent_ok_for_primary(primary: str, text: str) -> bool:
    if primary in {"enter", "size"}:
        return _ENTER_SIZE_INTENT.search(text) is not None
    if primary == "manage":
        return _MANAGE_INTENT.search(text) is not None or _ENTER_SIZE_INTENT.search(text) is not None
    if primary == "exit":
        return _EXIT_INTENT.search(text) is not None
    return False


def _citation_from_ctx_message(msg: Any) -> ModelCitation:
    ts = msg.ts.isoformat() if getattr(msg, "ts", None) is not None else ""
    return ModelCitation(
        source=str(getattr(msg, "channel", "") or ""),
        message_id=str(msg.message_id),
        ts=ts,
        quote_span="",
    )


def sealed_primary_support(case: FrozenCase, ctx: ModelContext) -> dict[str, Any] | None:
    """Best sealed ticker+intent row for a non-abstain primary. No GT / fill body."""

    primary = case.primary_question
    if primary == "abstain":
        return None
    tickers = list(case.tickers)
    if not tickers or not ctx.messages:
        return None
    retrieved = set(ctx.retrieved_ids)
    ranked: list[tuple[int, Any, str]] = []
    for msg in ctx.messages:
        if msg.message_id not in retrieved:
            continue
        text = msg.text or ""
        if not _intent_ok_for_primary(primary, text):
            continue
        hit = next((t for t in tickers if ticker_mentioned(text, t)), None)
        if not hit:
            continue
        recency = 1 if msg.ts is not None else 0
        ranked.append((recency, msg, hit))
    if not ranked:
        return None
    # Prefer later sealed messages (walk already newest-last; take last hit).
    _, msg, ticker = ranked[-1]
    quote = _quote_around_ticker(msg.text or "", ticker)
    cite = _citation_from_ctx_message(msg)
    cite.quote_span = quote
    side = _side_from_sealed_text(msg.text or "")
    if primary == "exit":
        side = side or "n/a"
    elif primary == "manage":
        side = side or "n/a"
    elif not side:
        side = "long"
    return {
        "ticker": ticker,
        "side": side,
        "size_pct": _size_near_ticker(msg.text or "", ticker),
        "citation": cite,
        "message_id": msg.message_id,
    }


def _ticker_in_case(ticker: str, case: FrozenCase) -> bool:
    got = (ticker or "").strip().upper()
    if not got:
        return False
    return got in {t.strip().upper() for t in case.tickers}


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
    raw_cites = cleaned.get("citations") or []
    if isinstance(raw_cites, dict):
        raw_cites = [raw_cites]
    for raw in raw_cites:
        normalized = _normalize_citation_raw(raw)
        if normalized is None:
            continue
        cite = _eligible_citation(normalized, eligible_ids, by_id)
        if cite is not None:
            citations.append(cite)

    action = _coerce_action(cleaned.get("action"))
    if action not in ACTIONS:
        raise ValueError(f"invalid action {cleaned.get('action')!r}")
    side = _coerce_side(cleaned.get("side"), action)
    if side is None:
        raise ValueError(f"invalid side {cleaned.get('side')!r}")

    support = sealed_primary_support(case, ctx)
    asked = case.primary_question
    if (
        support is not None
        and asked != "abstain"
        and asked in ACTIONS
        and (action == "abstain" or (asked in {"enter", "manage", "exit"} and action != asked))
    ):
        # Prefer asked action + sealed cite; never invent enter on abstain goldens.
        if not (asked == "size" and action in {"size", "enter"}):
            action = "size" if asked == "size" else asked
        cite = support["citation"]
        if isinstance(cite, ModelCitation) and cite.message_id in eligible_ids:
            if all(c.message_id != cite.message_id for c in citations):
                citations.insert(0, cite)
        support_side = _coerce_side(support.get("side"), action)
        if action in {"enter", "size"} and (side in {None, "n/a"} or side == "n/a"):
            if support_side in {"long", "short"}:
                side = support_side
        elif action in {"manage", "exit"} and side is None:
            side = support_side or "n/a"

    if action != "abstain" and not citations and support is not None:
        cite = support["citation"]
        if isinstance(cite, ModelCitation) and cite.message_id in eligible_ids:
            citations.append(cite)

    abstain_reason = _coerce_optional_str(cleaned.get("abstain_reason"))
    if action != "abstain" and not citations:
        action = "abstain"
        side = "n/a"
        abstain_reason = "thin_evidence_no_eligible_citations"
    if action != "abstain":
        abstain_reason = None
    elif not (abstain_reason or "").strip():
        abstain_reason = "model_abstain"

    size_pct = _coerce_size_pct(cleaned.get("size_pct"))
    ticker_raw = cleaned.get("ticker")
    ticker = "" if action == "abstain" else str(ticker_raw or "").strip()
    if action != "abstain" and support is not None:
        support_ticker = str(support.get("ticker") or "").strip()
        if not _ticker_in_case(ticker, case):
            if action == "manage":
                ticker = support_ticker if _ticker_in_case(support_ticker, case) else ""
            elif _ticker_in_case(support_ticker, case):
                ticker = support_ticker
        if action in {"enter", "size"} and side in {None, "n/a"}:
            support_side = _coerce_side(support.get("side"), action)
            if support_side in {"long", "short"}:
                side = support_side
        if action == "size" and size_pct is None:
            size_pct = support.get("size_pct")
    if action in {"manage", "exit"} and (side is None or side == ""):
        side = "n/a"

    # Model often returns rejected_alternatives as objects; lock schema is list[str].
    raw_rejected = cleaned.get("rejected_alternatives") or []
    rejected: list[str] = []
    for item in raw_rejected:
        if isinstance(item, str):
            rejected.append(item)
        elif isinstance(item, dict):
            alt = item.get("alternative") or item.get("action") or item.get("alt")
            reason = item.get("reason") or item.get("why")
            if alt and reason:
                rejected.append(f"{alt}: {reason}")
            elif alt:
                rejected.append(str(alt))
            elif reason:
                rejected.append(str(reason))
            else:
                rejected.append(str(item))
        else:
            rejected.append(str(item))

    pred = ModelPrediction(
        case_id=case.case_id,
        decision_ts=case.decision_ts.isoformat(),
        action=action,
        side=side,
        ticker=ticker,
        size_pct=size_pct,
        stop=_coerce_optional_str(cleaned.get("stop")),
        management=_coerce_optional_str(cleaned.get("management")),
        exit=_coerce_optional_str(cleaned.get("exit")),
        rejected_alternatives=rejected,
        citations=citations,
        confidence=_coerce_confidence(cleaned.get("confidence", 0.0)),
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


def _parse_model_prediction(
    text: str,
    case: FrozenCase,
    ctx: ModelContext,
    *,
    run_id: str,
    model_id: str,
) -> tuple[ModelPrediction | None, str]:
    """Parse model text into a prediction. method is ok / repaired / failed.

    Does not invent enter on thin priors — that is handled by the caller.
    """

    raw = strip_code_fences(text)
    greedy = greedy_first_json_object(raw)
    greedy_ok = bool(greedy and try_parse_json_object(greedy) is not None)
    try:
        obj = extract_json_object(text)
        pred = prediction_from_model_obj(obj, case, ctx, run_id=run_id, model_id=model_id)
    except Exception:
        return None, "failed"
    return pred, ("ok" if greedy_ok else "repaired")


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
    parse_stats: EmitParseStats | None = None,
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

    pred, method = _parse_model_prediction(
        str(text), case, ctx, run_id=run_id, model_id=model_id
    )
    if pred is not None:
        if method == "repaired" and parse_stats is not None:
            parse_stats.n_parse_local_repaired += 1
        post_thin = thin_evidence_reason(case, ctx)
        if post_thin and pred.action in {"enter", "size"}:
            return sealed_abstain(case, ctx, run_id=run_id, model_id=model_id, reason=post_thin), prompts
        return pred, prompts

    # Schema-only LLM retry (second attempt).
    repair_msgs = list(prompts) + [
        {"role": "assistant", "content": str(text)},
        {"role": "user", "content": PARSE_REPAIR_USER},
    ]
    text2: str | None = None
    try:
        result2 = client.complete(repair_msgs)
        raw2 = result2.get("text") if isinstance(result2, dict) else None
        text2 = str(raw2) if raw2 else None
    except InferhubError:
        text2 = None

    recovered: ModelPrediction | None = None
    recovered_method = "failed"
    if text2:
        recovered, recovered_method = _parse_model_prediction(
            text2, case, ctx, run_id=run_id, model_id=model_id
        )

    # Last-ditch: greedy first `{...}` on original then retry text.
    if recovered is None:
        for blob in (str(text), text2 or ""):
            greedy = greedy_first_json_object(strip_code_fences(blob))
            if not greedy:
                continue
            try:
                obj = json.loads(greedy)
                if isinstance(obj, dict):
                    recovered = prediction_from_model_obj(
                        obj, case, ctx, run_id=run_id, model_id=model_id
                    )
                    recovered_method = "ok"
                    break
            except Exception:
                continue

    if recovered is None:
        if parse_stats is not None:
            parse_stats.n_parse_failure += 1
        return (
            sealed_abstain(case, ctx, run_id=run_id, model_id=model_id, reason="parse_failure"),
            prompts,
        )

    if parse_stats is not None:
        parse_stats.n_parse_retry_recovered += 1
        if recovered_method == "repaired":
            parse_stats.n_parse_local_repaired += 1

    post_thin = thin_evidence_reason(case, ctx)
    if post_thin and recovered.action in {"enter", "size"}:
        return sealed_abstain(case, ctx, run_id=run_id, model_id=model_id, reason=post_thin), prompts
    return recovered, prompts


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
    parse_stats = EmitParseStats()
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
            parse_stats=parse_stats,
        )
        predictions.append(pred)
        prompts_all.append(prompts)

    n_abstain = sum(1 for p in predictions if p.action == "abstain")
    created = datetime.now(timezone.utc).isoformat()
    temperature = INFERHUB_TEMPERATURE
    max_tokens = INFERHUB_MAX_TOKENS
    if client is not None:
        temperature = float(getattr(client, "temperature", INFERHUB_TEMPERATURE))
        max_tokens = int(getattr(client, "max_tokens", INFERHUB_MAX_TOKENS))
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
        n_parse_failure=parse_stats.n_parse_failure,
        n_parse_retry_recovered=parse_stats.n_parse_retry_recovered,
        n_parse_local_repaired=parse_stats.n_parse_local_repaired,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format="json_object",
        quality_delta=QUALITY_DELTA,
        suggested_live_run_id=SUGGESTED_LIVE_RUN_ID,
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
