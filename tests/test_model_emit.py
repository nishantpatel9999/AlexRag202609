"""Sealed-cutoff emit-model-predictions. Offline; capital 0; no Inferhub network."""

from __future__ import annotations

import io
import json
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from alexrag.cli import app
from alexrag.eval.frozen_pack import EligibleFilter, FrozenCase, TargetAction, load_frozen_pack
from alexrag.eval.model_context import build_model_context
from alexrag.eval.model_emit import (
    DRY_RUN_MODEL_ID,
    SUGGESTED_LIVE_RUN_ID,
    EmitParseStats,
    emit_model_predictions,
    emit_one_case,
    extract_json_object,
    greedy_first_json_object,
    prediction_from_model_obj,
    repair_truncated_json,
    select_retrieved_ids,
    thin_evidence_reason,
)
from alexrag.eval.model_lock import HARD_KILL_SCAR_IDS, load_model_eval_lock
from alexrag.eval.model_prediction import load_predictions
from alexrag.eval.sealed_corpus import eligible_messages, load_mvp_ingest
from alexrag.llm.inferhub import (
    INFERHUB_API_KEY_ENV,
    INFERHUB_MAX_TOKENS,
    INFERHUB_MODEL,
    INFERHUB_TEMPERATURE,
    InferhubClient,
    InferhubError,
)

FIXTURE_INGEST = Path(__file__).parent / "fixtures" / "model_eval" / "ingest"
RUNNER = CliRunner()
GC15 = "GC-15-2023-09-21"
GC29 = "GC-29-2025-03-05"


def _syn_enter_case() -> FrozenCase:
    pt = ZoneInfo("America/Los_Angeles")
    decision = datetime(2024, 1, 15, 10, 0, tzinfo=pt)
    return FrozenCase(
        case_id="SYN-PARSE",
        date_pt="2024-01-15",
        tickers=["AAA"],
        primary_question="enter",
        decision_ts=decision,
        fill_ts=decision,
        target_action=TargetAction(
            message_id="ban-fill",
            channel="equity-trades",
            ts=decision,
            text="Long 10% AAA @ 12.00 (SL @ 11.80)",
            action_classes=["enter"],
            primary_question="enter",
        ),
        eligible_filter=EligibleFilter(
            channels=["equity-trades", "alex-journal", "prime-report", "pf-update"],
            ts_lt=decision,
            tz="America/Los_Angeles",
        ),
        banned_same_day_ids=["ban-fill", "ban-journal"],
        key_evidence_ids=["eq-ok", "j-ok"],
    )


def test_cli_dry_run_emits_48_matching_case_ids(tmp_path: Path) -> None:
    pack = load_frozen_pack()
    out = tmp_path / "runs"
    result = RUNNER.invoke(
        app,
        [
            "emit-model-predictions",
            "--dry-run",
            "--ingest",
            str(FIXTURE_INGEST),
            "--out",
            str(out),
            "--run-id",
            "dry-ci",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "paper_authority=false" in result.output
    assert "capital=0" in result.output
    assert "model_id=dry_run_abstain" in result.output
    pred_path = out / "dry-ci" / "predictions.jsonl"
    meta_path = out / "dry-ci" / "run_metadata.json"
    assert pred_path.is_file()
    preds = load_predictions(pred_path)
    assert len(preds) == 48
    assert [p.case_id for p in preds] == [c.case_id for c in pack.cases]
    assert all(p.model_id == DRY_RUN_MODEL_ID for p in preds)
    assert all(p.run_id == "dry-ci" for p in preds)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["paper_authority"] is False
    assert meta["capital"] == 0
    assert meta["model_eval_clear"] is False
    assert meta["dry_run"] is True
    assert meta["live_llm"] is False
    assert meta["broker"] is False
    assert meta["suggested_live_run_id"] == SUGGESTED_LIVE_RUN_ID
    assert meta["temperature"] == INFERHUB_TEMPERATURE
    assert meta["max_tokens"] == INFERHUB_MAX_TOKENS
    assert "suggested_live_run_id=inferhub-cbcn-v2-quality" in result.output


def test_dry_run_context_never_contains_target_action(tmp_path: Path) -> None:
    run = emit_model_predictions(
        ingest_dir=FIXTURE_INGEST,
        out_root=tmp_path / "runs",
        dry_run=True,
        run_id="ctx-seal",
    )
    pack = load_frozen_pack()
    lock = load_model_eval_lock()
    corpus = load_mvp_ingest(FIXTURE_INGEST)
    for case, pred, prompts in zip(pack.cases, run.predictions, run.prompts, strict=True):
        eligible = eligible_messages(case, corpus)
        ctx = build_model_context(case, eligible, retrieved_ids=pred.retrieved_ids)
        dumped = ctx.model_dump_sealed()
        assert "target_action" not in dumped
        assert "action_classes" not in dumped
        blob = json.dumps(dumped) + "\n".join(m["content"] for m in prompts)
        assert "target_action" not in blob
        assert f"id={case.target_action.message_id} " not in blob
        banned = set(case.banned_same_day_ids)
        assert banned.isdisjoint(pred.retrieved_ids)
        assert banned.isdisjoint({c.message_id for c in pred.citations})
        assert case.target_action.message_id not in pred.retrieved_ids
    assert lock.paper_authority_default is False


def test_banned_ids_never_in_retrieved_ids(tmp_path: Path) -> None:
    run = emit_model_predictions(
        ingest_dir=FIXTURE_INGEST,
        out_root=tmp_path / "runs",
        dry_run=True,
        run_id="no-ban",
    )
    pack = load_frozen_pack()
    by_case = {c.case_id: c for c in pack.cases}
    for pred in run.predictions:
        banned = set(by_case[pred.case_id].banned_same_day_ids)
        assert banned.isdisjoint(pred.retrieved_ids)
        assert by_case[pred.case_id].target_action.message_id not in pred.retrieved_ids
    gc15_pred = next(p for p in run.predictions if p.case_id == GC15)
    gc29_pred = next(p for p in run.predictions if p.case_id == GC29)
    assert "gc15-banned" not in gc15_pred.retrieved_ids
    assert "gc29-banned" not in gc29_pred.retrieved_ids


def test_gc15_gc29_dry_run_abstain_honest(tmp_path: Path) -> None:
    run = emit_model_predictions(
        ingest_dir=FIXTURE_INGEST,
        out_root=tmp_path / "runs",
        dry_run=True,
        run_id="kill-scars-dry",
    )
    by_id = {p.case_id: p for p in run.predictions}
    for case_id in HARD_KILL_SCAR_IDS:
        pred = by_id[case_id]
        assert pred.action == "abstain"
        assert pred.side == "n/a"
        assert pred.ticker == ""
        assert pred.model_id == DRY_RUN_MODEL_ID
        assert pred.abstain_reason == "dry_run_skip_network"
        assert pred.action != "enter"


def test_no_dry_run_without_key_exits(tmp_path: Path) -> None:
    result = RUNNER.invoke(
        app,
        [
            "emit-model-predictions",
            "--no-dry-run",
            "--ingest",
            str(FIXTURE_INGEST),
            "--out",
            str(tmp_path / "runs"),
        ],
    )
    assert result.exit_code == 2, result.output
    assert "INFERHUB_API_KEY" in result.output


def test_parse_failure_and_thin_evidence_abstain(tmp_path: Path) -> None:
    pack = load_frozen_pack()
    lock = load_model_eval_lock()
    corpus = load_mvp_ingest(FIXTURE_INGEST)
    gc15 = next(c for c in pack.cases if c.case_id == GC15)
    gc29 = next(c for c in pack.cases if c.case_id == GC29)

    class EmptyClient:
        configured = True
        model = INFERHUB_MODEL

        def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            return {"status": "ok", "text": "not-json {", "model": self.model}

    pred15, _ = emit_one_case(
        gc15,
        corpus,
        lock,
        run_id="thin",
        model_id=INFERHUB_MODEL,
        dry_run=False,
        client=EmptyClient(),  # type: ignore[arg-type]
    )
    assert pred15.action == "abstain"
    assert pred15.abstain_reason in {
        "thin_evidence_no_eligible_messages",
        "thin_evidence_no_ticker_in_priors",
        "parse_failure",
    }
    # Fixture ingest has no STRL/VRT before GC-15 cutoff → thin, no LLM parse path.
    assert pred15.abstain_reason.startswith("thin_evidence")

    pred29, prompts = emit_one_case(
        gc29,
        corpus,
        lock,
        run_id="thin",
        model_id=INFERHUB_MODEL,
        dry_run=False,
        client=EmptyClient(),  # type: ignore[arg-type]
    )
    assert pred29.action == "abstain"
    ctx29 = build_model_context(
        gc29, eligible_messages(gc29, corpus), retrieved_ids=pred29.retrieved_ids
    )
    assert "NFLX" not in " ".join(m.text for m in ctx29.messages)
    assert pred29.abstain_reason.startswith("thin_evidence")
    assert "target_action" not in "\n".join(p["content"] for p in prompts)


def test_prediction_from_model_drops_banned_cites() -> None:
    pack = load_frozen_pack()
    corpus = load_mvp_ingest(FIXTURE_INGEST)
    case = next(c for c in pack.cases if c.case_id == "GC-02-2022-11-03")
    eligible = eligible_messages(case, corpus)
    retrieved = select_retrieved_ids(case, eligible)
    ctx = build_model_context(case, eligible, retrieved_ids=retrieved)
    banned = case.banned_same_day_ids[0]
    obj = {
        "action": "enter",
        "side": "short",
        "ticker": "SOXS",
        "citations": [
            {"source": "equity-trades", "message_id": banned, "ts": case.decision_ts.isoformat(), "quote_span": "leak"}
        ],
        "confidence": 0.9,
    }
    pred = prediction_from_model_obj(obj, case, ctx, run_id="p", model_id="t")
    assert pred.action == "abstain"
    assert pred.abstain_reason == "thin_evidence_no_eligible_citations"
    assert banned not in pred.retrieved_ids
    assert all(c.message_id != banned for c in pred.citations)


def test_extract_json_object_strips_fence() -> None:
    obj = extract_json_object("```json\n{\"action\": \"abstain\"}\n```")
    assert obj["action"] == "abstain"
    # Prose before fence + trailing junk after closing brace.
    obj2 = extract_json_object(
        'Here you go:\n```JSON\n{"action": "enter", "side": "long"}\n```\nthanks'
    )
    assert obj2["action"] == "enter"
    obj3 = extract_json_object('prefix {"action": "abstain", "x": 1} trailing prose')
    assert obj3["action"] == "abstain"


def test_extract_json_object_repairs_truncated_braces() -> None:
    truncated = (
        '{"action": "abstain", "side": "n/a", "ticker": "", '
        '"citations": [{"message_id": "eq-ok", "quote_span": "watching AAA"'
    )
    obj = extract_json_object(truncated)
    assert obj["action"] == "abstain"
    assert obj["citations"][0]["message_id"] == "eq-ok"
    repaired = repair_truncated_json(truncated)
    assert repaired is not None
    json.loads(repaired)


def test_extract_json_object_greedy_first_object() -> None:
    raw = 'noise {"action": "enter", "side": "long"} extra } {"nope": 1}'
    obj = extract_json_object(raw)
    assert obj == {"action": "enter", "side": "long"}
    greedy = greedy_first_json_object(raw)
    assert greedy == '{"action": "enter", "side": "long"}'


def test_inferhub_complete_posts_chat_completions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(INFERHUB_API_KEY_ENV, "secret-must-not-leak")
    captured: dict[str, Any] = {}

    class _Resp:
        def read(self) -> bytes:
            payload = {
                "choices": [{"message": {"content": json.dumps({"action": "abstain", "abstain_reason": "ok"})}}]
            }
            return json.dumps(payload).encode("utf-8")

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_urlopen(req: Any, timeout: float | None = None) -> _Resp:
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["method"] = req.get_method()
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["auth"] = req.get_header("Authorization")
        return _Resp()

    monkeypatch.setattr("alexrag.llm.inferhub.urllib.request.urlopen", fake_urlopen)
    client = InferhubClient()
    payload = client.complete([{"role": "user", "content": "hello"}])
    assert payload["status"] == "ok"
    assert payload["text"] is not None
    assert "abstain" in payload["text"]
    assert captured["url"] == "https://api.inferhub.dev/v1/chat/completions"
    assert captured["method"] == "POST"
    assert captured["body"]["provider"] == "cbcn"
    assert captured["body"]["model"] == INFERHUB_MODEL
    assert captured["body"]["temperature"] == INFERHUB_TEMPERATURE
    assert captured["body"]["max_tokens"] == INFERHUB_MAX_TOKENS
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["auth"] == "Bearer secret-must-not-leak"
    blob = str(payload)
    assert "secret-must-not-leak" not in blob
    assert "Authorization" not in blob
    assert "secret-must-not-leak" not in repr(client)

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Bearer secret-must-not-leak exploded")

    monkeypatch.setattr("alexrag.llm.inferhub.urllib.request.urlopen", boom)
    with pytest.raises(InferhubError) as excinfo:
        client.complete([{"role": "user", "content": "x"}])
    assert "secret-must-not-leak" not in str(excinfo.value)
    assert "[redacted]" in str(excinfo.value)


def test_parse_failure_abstains_when_priors_exist() -> None:
    case = _syn_enter_case()
    lock = load_model_eval_lock()
    corpus = load_mvp_ingest(FIXTURE_INGEST)

    class BadClient:
        configured = True

        def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            blob = "\n".join(m["content"] for m in messages)
            assert "target_action" not in blob
            assert "Long 10% AAA @ 12.00" not in blob
            return {"status": "ok", "text": "I think you should enter AAA", "model": INFERHUB_MODEL}

    pred, prompts = emit_one_case(
        case,
        corpus,
        lock,
        run_id="parse",
        model_id=INFERHUB_MODEL,
        dry_run=False,
        client=BadClient(),  # type: ignore[arg-type]
    )
    assert pred.action == "abstain"
    assert pred.abstain_reason == "parse_failure"
    assert "ban-fill" not in pred.retrieved_ids
    assert "target_action" not in "\n".join(p["content"] for p in prompts)


def test_thin_evidence_gc15_with_fixture_ingest() -> None:
    pack = load_frozen_pack()
    corpus = load_mvp_ingest(FIXTURE_INGEST)
    case = next(c for c in pack.cases if c.case_id == GC15)
    eligible = eligible_messages(case, corpus)
    ctx = build_model_context(case, eligible, retrieved_ids=select_retrieved_ids(case, eligible))
    reason = thin_evidence_reason(case, ctx)
    assert reason == "thin_evidence_no_eligible_messages"
    assert "gc15-banned" not in ctx.retrieved_ids


def test_rejected_alternatives_dict_coerce() -> None:
    """Model often returns rejected_alternatives as objects; lock schema is list[str]."""

    pack = load_frozen_pack()
    corpus = load_mvp_ingest(FIXTURE_INGEST)
    case = next(c for c in pack.cases if c.case_id == "GC-02-2022-11-03")
    eligible = eligible_messages(case, corpus)
    retrieved = select_retrieved_ids(case, eligible)
    ctx = build_model_context(case, eligible, retrieved_ids=retrieved)
    mid = retrieved[0] if retrieved else None
    cites: list[dict[str, str]] = []
    if mid:
        msg = next(m for m in ctx.messages if m.message_id == mid)
        cites = [
            {
                "source": msg.channel or "equity-trades",
                "message_id": mid,
                "ts": msg.ts.isoformat() if msg.ts else case.decision_ts.isoformat(),
                "quote_span": (msg.text or "")[:20],
            }
        ]
    obj = {
        "action": "abstain",
        "side": "n/a",
        "ticker": "",
        "citations": cites,
        "confidence": 0.1,
        "abstain_reason": "unsure",
        "rejected_alternatives": [
            {"alternative": "enter", "reason": "thin priors"},
            {"action": "size", "why": "no size cue"},
            "plain-string-alt",
            {"alt": "exit"},
        ],
    }
    pred = prediction_from_model_obj(obj, case, ctx, run_id="rej", model_id="t")
    assert pred.rejected_alternatives == [
        "enter: thin priors",
        "size: no size cue",
        "plain-string-alt",
        "exit",
    ]


def test_parse_retry_recovers_then_counts(tmp_path: Path) -> None:
    """One repair complete() recovers bad first response; metadata counts recovery."""

    case = _syn_enter_case()
    lock = load_model_eval_lock()
    corpus = load_mvp_ingest(FIXTURE_INGEST)
    good = json.dumps(
        {
            "action": "abstain",
            "side": "n/a",
            "ticker": "",
            "citations": [],
            "confidence": 0.0,
            "abstain_reason": "model_abstain",
            "rejected_alternatives": [],
        }
    )

    class RetryClient:
        configured = True
        calls = 0

        def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            self.calls += 1
            if self.calls == 1:
                return {"status": "ok", "text": "not json at all", "model": INFERHUB_MODEL}
            assert any(m.get("role") == "user" and "JSON object" in m.get("content", "") for m in messages)
            return {"status": "ok", "text": good, "model": INFERHUB_MODEL}

    stats = EmitParseStats()
    client = RetryClient()
    pred, _ = emit_one_case(
        case,
        corpus,
        lock,
        run_id="retry",
        model_id=INFERHUB_MODEL,
        dry_run=False,
        client=client,  # type: ignore[arg-type]
        parse_stats=stats,
    )
    assert client.calls == 2
    assert pred.action == "abstain"
    assert pred.abstain_reason == "model_abstain"
    assert stats.n_parse_retry_recovered == 1
    assert stats.n_parse_failure == 0

    class AlwaysBad:
        configured = True
        calls = 0

        def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            self.calls += 1
            return {"status": "ok", "text": "still not json", "model": INFERHUB_MODEL}

    stats2 = EmitParseStats()
    bad = AlwaysBad()
    pred2, _ = emit_one_case(
        case,
        corpus,
        lock,
        run_id="retry-fail",
        model_id=INFERHUB_MODEL,
        dry_run=False,
        client=bad,  # type: ignore[arg-type]
        parse_stats=stats2,
    )
    assert bad.calls == 2
    assert pred2.action == "abstain"
    assert pred2.abstain_reason == "parse_failure"
    assert stats2.n_parse_failure == 1
    assert stats2.n_parse_retry_recovered == 0


def test_truncated_json_recovers_without_llm_retry() -> None:
    case = _syn_enter_case()
    lock = load_model_eval_lock()
    corpus = load_mvp_ingest(FIXTURE_INGEST)
    truncated = (
        '{"action": "abstain", "side": "n/a", "ticker": "", "citations": [], '
        '"confidence": 0.0, "abstain_reason": "model_abstain", '
        '"rejected_alternatives": ['
    )

    class TruncClient:
        configured = True
        calls = 0

        def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            self.calls += 1
            return {"status": "ok", "text": truncated, "model": INFERHUB_MODEL}

    stats = EmitParseStats()
    client = TruncClient()
    pred, prompts = emit_one_case(
        case,
        corpus,
        lock,
        run_id="trunc",
        model_id=INFERHUB_MODEL,
        dry_run=False,
        client=client,  # type: ignore[arg-type]
        parse_stats=stats,
    )
    assert client.calls == 1
    assert pred.action == "abstain"
    assert pred.abstain_reason == "model_abstain"
    assert stats.n_parse_failure == 0
    assert stats.n_parse_local_repaired == 1
    assert "target_action" not in "\n".join(p["content"] for p in prompts)
    assert "Long 10% AAA @ 12.00" not in "\n".join(p["content"] for p in prompts)


def test_greedy_extract_after_schema_nudge() -> None:
    case = _syn_enter_case()
    lock = load_model_eval_lock()
    corpus = load_mvp_ingest(FIXTURE_INGEST)
    good = (
        'ok here {"action": "abstain", "side": "n/a", "ticker": "", '
        '"citations": [], "confidence": 0, "abstain_reason": "model_abstain", '
        '"rejected_alternatives": []} trailing } junk'
    )

    class GreedyRetry:
        configured = True
        calls = 0

        def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            self.calls += 1
            if self.calls == 1:
                return {"status": "ok", "text": "not json at all", "model": INFERHUB_MODEL}
            return {"status": "ok", "text": good, "model": INFERHUB_MODEL}

    stats = EmitParseStats()
    pred, _ = emit_one_case(
        case,
        corpus,
        lock,
        run_id="greedy",
        model_id=INFERHUB_MODEL,
        dry_run=False,
        client=GreedyRetry(),  # type: ignore[arg-type]
        parse_stats=stats,
    )
    assert pred.action == "abstain"
    assert pred.abstain_reason == "model_abstain"
    assert stats.n_parse_retry_recovered == 1
    assert stats.n_parse_failure == 0


def test_schema_coerce_enter_long_and_numeric_citation_id() -> None:
    case = _syn_enter_case()
    corpus = load_mvp_ingest(FIXTURE_INGEST)
    eligible = eligible_messages(case, corpus)
    retrieved = select_retrieved_ids(case, eligible)
    ctx = build_model_context(case, eligible, retrieved_ids=retrieved)
    mid = retrieved[0]
    msg = next(m for m in ctx.messages if m.message_id == mid)
    obj = {
        "action": "ENTER",
        "side": "Long",
        "ticker": "AAA",
        "size_pct": "1.5%",
        "citations": {
            "messageId": mid,
            "source": msg.channel,
            "ts": msg.ts.isoformat() if msg.ts else "",
            "quote_span": (msg.text or "")[:12],
        },
        "confidence": "0.8",
        "rejected_alternatives": [],
    }
    pred = prediction_from_model_obj(obj, case, ctx, run_id="coerce", model_id="t")
    assert pred.action == "enter"
    assert pred.side == "long"
    assert pred.ticker == "AAA"
    assert pred.size_pct == 1.5
    assert pred.citations[0].message_id == mid


def test_does_not_auto_enter_when_model_abstains() -> None:
    """Prompt may require enter; emitter must not rewrite an honest abstain."""

    case = _syn_enter_case()
    lock = load_model_eval_lock()
    corpus = load_mvp_ingest(FIXTURE_INGEST)
    payload = json.dumps(
        {
            "action": "abstain",
            "side": "n/a",
            "ticker": "",
            "citations": [],
            "confidence": 0.1,
            "abstain_reason": "thin_language",
        }
    )

    class AbstainClient:
        configured = True

        def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            blob = "\n".join(m["content"] for m in messages)
            assert "JSON object" in blob or "json object" in blob.casefold()
            assert "fill-intent" in blob.casefold() or "Long/Short" in blob
            assert "target_action" not in blob
            return {"status": "ok", "text": payload, "model": INFERHUB_MODEL}

    pred, prompts = emit_one_case(
        case,
        corpus,
        lock,
        run_id="no-auto",
        model_id=INFERHUB_MODEL,
        dry_run=False,
        client=AbstainClient(),  # type: ignore[arg-type]
    )
    assert pred.action == "abstain"
    assert pred.abstain_reason == "thin_language"
    system = next(p["content"] for p in prompts if p["role"] == "system")
    assert "exactly one JSON object" in system
    assert "target_action" not in system


def test_gc15_gc29_live_path_never_auto_enter() -> None:
    pack = load_frozen_pack()
    lock = load_model_eval_lock()
    corpus = load_mvp_ingest(FIXTURE_INGEST)

    class WouldEnter:
        configured = True
        called = False

        def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            self.called = True
            return {
                "status": "ok",
                "text": json.dumps({"action": "enter", "side": "short", "ticker": "STRL"}),
                "model": INFERHUB_MODEL,
            }

    client = WouldEnter()
    for case_id in (GC15, GC29):
        case = next(c for c in pack.cases if c.case_id == case_id)
        pred, _ = emit_one_case(
            case,
            corpus,
            lock,
            run_id="no-cheat",
            model_id=INFERHUB_MODEL,
            dry_run=False,
            client=client,  # type: ignore[arg-type]
        )
        assert pred.action == "abstain"
        assert pred.abstain_reason.startswith("thin_evidence")
        assert pred.ticker == ""
    assert client.called is False


def test_inferhub_response_format_http400_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(INFERHUB_API_KEY_ENV, "secret-must-not-leak")
    bodies: list[dict[str, Any]] = []

    class _Resp:
        def read(self) -> bytes:
            payload = {"choices": [{"message": {"content": '{"action":"abstain"}'}}]}
            return json.dumps(payload).encode("utf-8")

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_urlopen(req: Any, timeout: float | None = None) -> _Resp:
        body = json.loads(req.data.decode("utf-8"))
        bodies.append(body)
        if "response_format" in body:
            fp = io.BytesIO(b'{"error":"response_format"}')
            raise urllib.error.HTTPError(
                req.full_url, 400, "Bad Request", hdrs={}, fp=fp
            )
        return _Resp()

    monkeypatch.setattr("alexrag.llm.inferhub.urllib.request.urlopen", fake_urlopen)
    client = InferhubClient()
    payload = client.complete([{"role": "user", "content": "hello"}])
    assert payload["status"] == "ok"
    assert len(bodies) == 2
    assert "response_format" in bodies[0]
    assert "response_format" not in bodies[1]
    assert bodies[1]["temperature"] == INFERHUB_TEMPERATURE
    assert bodies[1]["max_tokens"] == INFERHUB_MAX_TOKENS
    assert "secret-must-not-leak" not in str(payload)
