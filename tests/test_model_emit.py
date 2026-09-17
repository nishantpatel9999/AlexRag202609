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
    CONFLICT_NO_TRADE_STALE_REASON,
    DEFAULT_MAX_MESSAGES,
    DRY_RUN_MODEL_ID,
    QUALITY_DELTA,
    SUGGESTED_LIVE_RUN_ID,
    EmitParseStats,
    build_prompt_messages,
    conflict_no_trade_plan_vs_stale_setup,
    emit_model_predictions,
    emit_one_case,
    extract_json_object,
    greedy_first_json_object,
    prediction_from_model_obj,
    repair_truncated_json,
    sealed_primary_support,
    select_retrieved_ids,
    thin_evidence_reason,
)
from alexrag.eval.model_lock import HARD_KILL_SCAR_IDS, load_model_eval_lock
from alexrag.eval.model_prediction import load_predictions
from alexrag.eval.sealed_corpus import CorpusMessage, SealedCorpus, eligible_messages, load_mvp_ingest
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


def _syn_exit_case() -> FrozenCase:
    """GC-01 analog: exit primary; Sold fill is banned; sealed tape is open Long."""

    pt = ZoneInfo("America/Los_Angeles")
    decision = datetime(2022, 10, 3, 12, 42, tzinfo=pt)
    return FrozenCase(
        case_id="SYN-EXIT-GC01",
        date_pt="2022-10-03",
        tickers=["TH", "TQQQ", "XMTR"],
        primary_question="exit",
        decision_ts=decision,
        fill_ts=decision,
        target_action=TargetAction(
            message_id="ban-sold-xmtr",
            channel="equity-trades",
            ts=decision,
            text="Sold XMTR @ 58.20 - below entry EOD",
            action_classes=["exit"],
            primary_question="exit",
        ),
        eligible_filter=EligibleFilter(
            channels=["equity-trades", "alex-journal", "prime-report", "pf-update"],
            ts_lt=decision,
            tz="America/Los_Angeles",
        ),
        banned_same_day_ids=["ban-sold-xmtr", "ban-closed-th"],
        key_evidence_ids=["eq-long-xmtr"],
    )


def _syn_manage_case() -> FrozenCase:
    pt = ZoneInfo("America/Los_Angeles")
    decision = datetime(2023, 6, 22, 10, 0, tzinfo=pt)
    return FrozenCase(
        case_id="SYN-MANAGE",
        date_pt="2023-06-22",
        tickers=["STNE"],
        primary_question="manage",
        decision_ts=decision,
        fill_ts=decision,
        target_action=TargetAction(
            message_id="ban-add-stne",
            channel="equity-trades",
            ts=decision,
            text="Long 11% STNE (ADD#1) @ 13.97 (SL @ 13.63)",
            action_classes=["manage"],
            primary_question="manage",
        ),
        eligible_filter=EligibleFilter(
            channels=["equity-trades", "alex-journal", "prime-report", "pf-update"],
            ts_lt=decision,
            tz="America/Los_Angeles",
        ),
        banned_same_day_ids=["ban-add-stne"],
        key_evidence_ids=["eq-trim-stne"],
    )


def _syn_gc29_case() -> FrozenCase:
    """GC-29 analog: C1 same-morning no-trade vs stale NFLX chart alerts."""

    pt = ZoneInfo("America/Los_Angeles")
    decision = datetime(2025, 3, 5, 11, 5, tzinfo=pt)
    return FrozenCase(
        case_id="SYN-GC29",
        date_pt="2025-03-05",
        tickers=["NFLX"],
        primary_question="enter",
        decision_ts=decision,
        fill_ts=decision,
        target_action=TargetAction(
            message_id="ban-nflx-fill",
            channel="equity-trades",
            ts=decision,
            text="@everyone Long 23% NFLX @ 991.43 (SSL @ 969.48)",
            action_classes=["enter"],
            primary_question="enter",
        ),
        eligible_filter=EligibleFilter(
            channels=["equity-trades", "alex-journal", "prime-report", "pf-update"],
            ts_lt=decision,
            tz="America/Los_Angeles",
        ),
        banned_same_day_ids=["ban-nflx-fill", "ban-journal-rationalize"],
        key_evidence_ids=["j-no-trade", "rpt-no-fl", "rpt-stale-nflx"],
    )


def _gc29_like_messages() -> list[CorpusMessage]:
    pt = ZoneInfo("America/Los_Angeles")
    return [
        CorpusMessage(
            message_id="j-no-trade",
            channel="alex-journal",
            ts=datetime(2025, 3, 5, 4, 53, tzinfo=pt),
            text="03-05 Good morning everyone! No trades planned for today again.",
            source_type="journal",
        ),
        CorpusMessage(
            message_id="rpt-no-fl",
            channel="prime-report",
            ts=datetime(2025, 3, 4, 18, 46, tzinfo=pt),
            text="FOCUSLIST 03/04 No Focuslist for me tomorrow. QQQE below 10<21dma.",
            source_type="report",
        ),
        CorpusMessage(
            message_id="rpt-stale-nflx",
            channel="prime-report",
            ts=datetime(2025, 1, 15, 18, 12, tzinfo=pt),
            text="NFLX chart alert — watching NFLX into HWM; long setup if 10dma holds.",
            source_type="report",
        ),
        CorpusMessage(
            message_id="rpt-stale-nflx-feb",
            channel="prime-report",
            ts=datetime(2025, 2, 12, 17, 40, tzinfo=pt),
            text="FOCUSLIST names: NFLX still on the chart watch from January.",
            source_type="report",
        ),
        CorpusMessage(
            message_id="ban-nflx-fill",
            channel="equity-trades",
            ts=datetime(2025, 3, 5, 11, 5, tzinfo=pt),
            text="@everyone Long 23% NFLX @ 991.43 (SSL @ 969.48)",
            source_type="trade_log",
        ),
        CorpusMessage(
            message_id="ban-journal-rationalize",
            channel="alex-journal",
            ts=datetime(2025, 3, 5, 11, 6, tzinfo=pt),
            text="NFLX long position Ok guys, I didn't plan to take trade on this bounce",
            source_type="journal",
        ),
    ]


def _model_abstain_payload() -> str:
    return json.dumps(
        {
            "action": "abstain",
            "side": "n/a",
            "ticker": "",
            "citations": [],
            "confidence": 0.1,
            "abstain_reason": "unsure",
        }
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
    assert meta["quality_delta"] == QUALITY_DELTA
    assert meta["max_messages"] == DEFAULT_MAX_MESSAGES
    assert meta["temperature"] == INFERHUB_TEMPERATURE
    assert meta["max_tokens"] == INFERHUB_MAX_TOKENS
    assert f"suggested_live_run_id={SUGGESTED_LIVE_RUN_ID}" in result.output


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


def test_select_retrieved_ids_ticker_bias_beats_recency() -> None:
    """Same-ticker eligible rows beat newer chatter even when key_evidence is noise."""

    case = _syn_enter_case().model_copy(update={"key_evidence_ids": ["noise-new"]})
    pt = ZoneInfo("America/Los_Angeles")
    chatter = [
        CorpusMessage(
            message_id=f"noise-{i}",
            channel="alex-journal",
            ts=datetime(2024, 1, 15, 9, i, tzinfo=pt),
            text=f"tape chatter {i} no listed names",
            source_type="journal",
        )
        for i in range(12)
    ]
    eligible = [
        CorpusMessage(
            message_id="old-aaa",
            channel="equity-trades",
            ts=datetime(2024, 1, 2, 9, 0, tzinfo=pt),
            text="Long 4% AAA last month still watching",
            source_type="trade_log",
        ),
        CorpusMessage(
            message_id="noise-new",
            channel="alex-journal",
            ts=datetime(2024, 1, 15, 9, 59, tzinfo=pt),
            text="tape is choppy",
            source_type="journal",
        ),
        *chatter,
    ]
    got = select_retrieved_ids(case, eligible, max_messages=8)
    assert "old-aaa" in got
    assert got[0] == "old-aaa"
    assert "ban-fill" not in got
    assert case.target_action.message_id not in got
    # Recency-only would have filled with noise-* and dropped the old ticker hit.
    assert sum(1 for mid in got if mid.startswith("noise-")) <= 7


def test_select_retrieved_ids_key_evidence_ticker_first() -> None:
    case = _syn_enter_case().model_copy(update={"key_evidence_ids": ["hint-aaa", "hint-noise"]})
    pt = ZoneInfo("America/Los_Angeles")
    eligible = [
        CorpusMessage(
            message_id="hint-noise",
            channel="prime-report",
            ts=datetime(2024, 1, 14, 8, 0, tzinfo=pt),
            text="FOCUSLIST only QQQ",
            source_type="report",
        ),
        CorpusMessage(
            message_id="hint-aaa",
            channel="equity-trades",
            ts=datetime(2024, 1, 14, 9, 0, tzinfo=pt),
            text="watching AAA into resistance",
            source_type="trade_log",
        ),
        CorpusMessage(
            message_id="other-aaa",
            channel="alex-journal",
            ts=datetime(2024, 1, 14, 10, 0, tzinfo=pt),
            text="AAA still on radar",
            source_type="journal",
        ),
    ]
    got = select_retrieved_ids(case, eligible, max_messages=3)
    assert got[0] == "hint-aaa"
    assert "other-aaa" in got
    assert "hint-noise" in got


def test_v4_prompt_abstain_discipline_invariants() -> None:
    pack = load_frozen_pack()
    lock = load_model_eval_lock()
    corpus = load_mvp_ingest(FIXTURE_INGEST)
    enter_case = next(
        c for c in pack.cases if c.primary_question == "enter" and c.case_id not in HARD_KILL_SCAR_IDS
    )
    abstain_case = next(c for c in pack.cases if c.primary_question == "abstain")
    for case in (enter_case, abstain_case):
        eligible = eligible_messages(case, corpus)
        retrieved = select_retrieved_ids(case, eligible)
        ctx = build_model_context(case, eligible, retrieved_ids=retrieved)
        prompts = build_prompt_messages(ctx, lock)
        blob = "\n".join(p["content"] for p in prompts)
        assert "target_action" not in blob
        assert "action_classes" not in blob
        assert f"id={case.target_action.message_id} " not in blob
        system = next(p["content"] for p in prompts if p["role"] == "system")
        user = next(p["content"] for p in prompts if p["role"] == "user")
        lowered = (system + "\n" + user).casefold()
        assert "exactly one json object" in lowered
        assert "abstain discipline" in lowered
        assert "no-trade precision" in lowered
        assert "primary_question is abstain" in lowered
        assert "do not abstain" in lowered or "not abstain" in lowered
        assert "open long/short" in lowered
        assert "post-cutoff" in lowered
        if case.primary_question == "enter":
            assert "primary_question: enter" in user
        else:
            assert "primary_question: abstain" in user
            assert "if primary_question is abstain, abstain" in lowered
        assert "conflict_no_trade_plan_vs_stale_setup" in lowered
        assert "stale" in lowered
        assert "no-trade" in lowered or "no trades" in lowered


def test_gc29_stale_alert_vs_same_morning_no_trade_abstains() -> None:
    """GC-29-like: stale NFLX chart alert + same-morning no trades → honest abstain.

    Model enter (and banned fill) must not win. Fail-closed before Inferhub.
    """

    case = _syn_gc29_case()
    lock = load_model_eval_lock()
    corpus = SealedCorpus(_gc29_like_messages())

    class BoomClient:
        configured = True

        def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            raise AssertionError("conflict rule must fail-closed before Inferhub")

    pred, prompts = emit_one_case(
        case,
        corpus,
        lock,
        run_id="gc29-scar",
        model_id=INFERHUB_MODEL,
        dry_run=False,
        client=BoomClient(),  # type: ignore[arg-type]
    )
    blob = "\n".join(p["content"] for p in prompts)
    assert pred.action == "abstain"
    assert pred.ticker == ""
    assert pred.side == "n/a"
    assert pred.abstain_reason == CONFLICT_NO_TRADE_STALE_REASON
    assert "ban-nflx-fill" not in pred.retrieved_ids
    assert "ban-journal-rationalize" not in pred.retrieved_ids
    assert all(c.message_id != "ban-nflx-fill" for c in pred.citations)
    assert "target_action" not in blob
    assert "action_classes" not in blob
    assert f"id={case.target_action.message_id} " not in blob
    assert "Long 23% NFLX @ 991.43" not in blob
    assert "I didn't plan to take trade on this bounce" not in blob
    assert "conflict_no_trade_plan_vs_stale_setup" in blob.casefold() or (
        "no trades" in blob.casefold() and "stale" in blob.casefold()
    )

    eligible = eligible_messages(case, corpus)
    retrieved = select_retrieved_ids(case, eligible)
    ctx = build_model_context(case, eligible, retrieved_ids=retrieved)
    assert thin_evidence_reason(case, ctx) is None
    assert conflict_no_trade_plan_vs_stale_setup(case, ctx, extra_messages=eligible) == (
        CONFLICT_NO_TRADE_STALE_REASON
    )
    obj = {
        "action": "enter",
        "side": "long",
        "ticker": "NFLX",
        "citations": [{"message_id": "rpt-stale-nflx", "quote_span": "NFLX chart alert"}],
        "confidence": 0.8,
        "abstain_reason": None,
    }
    parsed = prediction_from_model_obj(obj, case, ctx, run_id="gc29-parse", model_id="t")
    assert parsed.action == "abstain"
    assert parsed.abstain_reason == CONFLICT_NO_TRADE_STALE_REASON
    assert parsed.ticker == ""
    assert all(c.message_id != "ban-nflx-fill" for c in parsed.citations)


def _syn_gc31_case() -> FrozenCase:
    """GC-31 analog: evening ACMR/MP setup list vs leftover no-trade language."""

    pt = ZoneInfo("America/Los_Angeles")
    decision = datetime(2025, 3, 10, 6, 57, tzinfo=pt)
    return FrozenCase(
        case_id="SYN-GC31",
        date_pt="2025-03-10",
        tickers=["MP", "ACMR"],
        primary_question="enter",
        decision_ts=decision,
        fill_ts=decision,
        target_action=TargetAction(
            message_id="ban-mp-fill",
            channel="equity-trades",
            ts=decision,
            text="@everyone Long 12% MP @ 25.09 (SSL @ 24.57)",
            action_classes=["enter"],
            primary_question="enter",
        ),
        eligible_filter=EligibleFilter(
            channels=["equity-trades", "alex-journal", "prime-report", "pf-update"],
            ts_lt=decision,
            tz="America/Los_Angeles",
        ),
        banned_same_day_ids=["ban-mp-fill"],
        key_evidence_ids=["rpt-setup-list", "eq-old-mp", "pf-no-trade-yday"],
    )


def _syn_gc32_case() -> FrozenCase:
    """GC-32 analog: year-old ERY tape + leftover no-trade, no report alert."""

    pt = ZoneInfo("America/Los_Angeles")
    decision = datetime(2025, 3, 13, 7, 39, tzinfo=pt)
    return FrozenCase(
        case_id="SYN-GC32",
        date_pt="2025-03-13",
        tickers=["ERY"],
        primary_question="enter",
        decision_ts=decision,
        fill_ts=decision,
        target_action=TargetAction(
            message_id="ban-ery-fill",
            channel="equity-trades",
            ts=decision,
            text="@everyone Long 11% ERY @ 23.82 (SSL @ 23.57)",
            action_classes=["enter"],
            primary_question="enter",
        ),
        eligible_filter=EligibleFilter(
            channels=["equity-trades", "alex-journal", "prime-report", "pf-update"],
            ts_lt=decision,
            tz="America/Los_Angeles",
        ),
        banned_same_day_ids=["ban-ery-fill"],
        key_evidence_ids=["eq-old-ery", "j-ppi", "pf-no-trade-yday"],
    )


def test_no_trade_plan_does_not_block_contemporaneous_enter() -> None:
    """Same-morning no-trade + same-session Long listed ticker must still enter."""

    case = _syn_enter_case()
    lock = load_model_eval_lock()
    pt = ZoneInfo("America/Los_Angeles")
    extra = [
        CorpusMessage(
            message_id="j-no-trade",
            channel="alex-journal",
            ts=datetime(2024, 1, 15, 6, 30, tzinfo=pt),
            text="No trades planned for today again.",
            source_type="journal",
        ),
        CorpusMessage(
            message_id="eq-long-aaa",
            channel="equity-trades",
            ts=datetime(2024, 1, 14, 12, 0, tzinfo=pt),
            text="Long 6% AAA @ 11.50 (SL @ 11.20)",
            source_type="trade_log",
        ),
    ]
    corpus = SealedCorpus(extra)
    eligible = eligible_messages(case, corpus)
    retrieved = select_retrieved_ids(case, eligible)
    ctx = build_model_context(case, eligible, retrieved_ids=retrieved)
    assert conflict_no_trade_plan_vs_stale_setup(case, ctx, extra_messages=eligible) is None

    class Client:
        configured = True

        def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            blob = "\n".join(m["content"] for m in messages)
            assert "target_action" not in blob
            return {"status": "ok", "text": _model_abstain_payload(), "model": INFERHUB_MODEL}

    pred, _ = emit_one_case(
        case,
        corpus,
        lock,
        run_id="gc29-neg-contemporaneous",
        model_id=INFERHUB_MODEL,
        dry_run=False,
        client=Client(),  # type: ignore[arg-type]
    )
    assert pred.action == "enter"
    assert pred.ticker == "AAA"
    assert pred.citations[0].message_id == "eq-long-aaa"
    assert "ban-fill" not in pred.retrieved_ids


def test_gc31_setup_list_does_not_conflict_abstain() -> None:
    """GC-31-like: ACMR/MP setup list + leftover no-trade + old tape must not fire."""

    case = _syn_gc31_case()
    lock = load_model_eval_lock()
    pt = ZoneInfo("America/Los_Angeles")
    extra = [
        CorpusMessage(
            message_id="rpt-setup-list",
            channel="prime-report",
            ts=datetime(2025, 3, 9, 19, 9, tzinfo=pt),
            text=(
                "Still dropping some good chart setups if you guys still want "
                "to engage. ACMR AEM ASTS GFL MP PAAS UBER WGS"
            ),
            source_type="report",
        ),
        CorpusMessage(
            message_id="pf-no-trade-yday",
            channel="pf-update",
            ts=datetime(2025, 3, 9, 18, 20, tzinfo=pt),
            text="PORTFOLIO UPDATE 03/09 No trades again today. Breadth still contracting.",
            source_type="pf_update",
        ),
        CorpusMessage(
            message_id="eq-old-mp",
            channel="equity-trades",
            ts=datetime(2024, 5, 28, 7, 49, tzinfo=pt),
            text="@everyone Long 16% MP @ 16.91 (SL @ 16.76)",
            source_type="trade_log",
        ),
        CorpusMessage(
            message_id="rpt-stale-mp-alert",
            channel="prime-report",
            ts=datetime(2024, 5, 27, 18, 10, tzinfo=pt),
            text="MP (Long) daily - Alert: 16.91, SL: 16.76 Base still constructive.",
            source_type="report",
        ),
        CorpusMessage(
            message_id="ban-mp-fill",
            channel="equity-trades",
            ts=datetime(2025, 3, 10, 6, 57, tzinfo=pt),
            text="@everyone Long 12% MP @ 25.09 (SSL @ 24.57)",
            source_type="trade_log",
        ),
    ]
    corpus = SealedCorpus(extra)
    eligible = eligible_messages(case, corpus)
    retrieved = select_retrieved_ids(case, eligible)
    ctx = build_model_context(case, eligible, retrieved_ids=retrieved)
    assert conflict_no_trade_plan_vs_stale_setup(case, ctx, extra_messages=eligible) is None

    called = {"n": 0}

    class Client:
        configured = True

        def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            called["n"] += 1
            blob = "\n".join(m["content"] for m in messages)
            assert "target_action" not in blob
            return {"status": "ok", "text": _model_abstain_payload(), "model": INFERHUB_MODEL}

    pred, _ = emit_one_case(
        case,
        corpus,
        lock,
        run_id="gc31-no-fire",
        model_id=INFERHUB_MODEL,
        dry_run=False,
        client=Client(),  # type: ignore[arg-type]
    )
    assert called["n"] == 1
    assert pred.action == "enter"
    assert pred.ticker == "MP"
    assert pred.abstain_reason is None
    assert "ban-mp-fill" not in pred.retrieved_ids


def test_gc32_ancient_tape_does_not_conflict_abstain() -> None:
    """GC-32-like: year-old ERY Long + leftover no-trade is not a stale report alert."""

    case = _syn_gc32_case()
    lock = load_model_eval_lock()
    pt = ZoneInfo("America/Los_Angeles")
    extra = [
        CorpusMessage(
            message_id="j-ppi",
            channel="alex-journal",
            ts=datetime(2025, 3, 13, 5, 51, tzinfo=pt),
            text=(
                "03/13 Good morning everyone! Mixed reaction to a soft PPI "
                "report this morning, with the market under pressure."
            ),
            source_type="journal",
        ),
        CorpusMessage(
            message_id="pf-no-trade-yday",
            channel="pf-update",
            ts=datetime(2025, 3, 12, 18, 20, tzinfo=pt),
            text="PORTFOLIO UPDATE 03/12 No trades again today. Day #10 of MCSI downtrend.",
            source_type="pf_update",
        ),
        CorpusMessage(
            message_id="eq-old-ery",
            channel="equity-trades",
            ts=datetime(2023, 3, 10, 7, 20, tzinfo=pt),
            text="Long 5% ERY @ 31.37 (SL 30.56) - BORS",
            source_type="trade_log",
        ),
        CorpusMessage(
            message_id="ban-ery-fill",
            channel="equity-trades",
            ts=datetime(2025, 3, 13, 7, 39, tzinfo=pt),
            text="@everyone Long 11% ERY @ 23.82 (SSL @ 23.57)",
            source_type="trade_log",
        ),
    ]
    corpus = SealedCorpus(extra)
    eligible = eligible_messages(case, corpus)
    retrieved = select_retrieved_ids(case, eligible)
    ctx = build_model_context(case, eligible, retrieved_ids=retrieved)
    assert conflict_no_trade_plan_vs_stale_setup(case, ctx, extra_messages=eligible) is None

    called = {"n": 0}

    class Client:
        configured = True

        def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            called["n"] += 1
            blob = "\n".join(m["content"] for m in messages)
            assert "target_action" not in blob
            return {"status": "ok", "text": _model_abstain_payload(), "model": INFERHUB_MODEL}

    pred, _ = emit_one_case(
        case,
        corpus,
        lock,
        run_id="gc32-no-fire",
        model_id=INFERHUB_MODEL,
        dry_run=False,
        client=Client(),  # type: ignore[arg-type]
    )
    assert called["n"] == 1
    assert pred.action == "enter"
    assert pred.ticker == "ERY"
    assert pred.abstain_reason is None
    assert "ban-ery-fill" not in pred.retrieved_ids


def test_false_abstain_coerced_when_sealed_long_language() -> None:
    case = _syn_enter_case()
    lock = load_model_eval_lock()
    pt = ZoneInfo("America/Los_Angeles")
    extra = CorpusMessage(
        message_id="eq-long-aaa",
        channel="equity-trades",
        ts=datetime(2024, 1, 14, 10, 0, tzinfo=pt),
        text="Long 6% AAA @ 11.50 (SL @ 11.20)",
        source_type="trade_log",
    )
    base = load_mvp_ingest(FIXTURE_INGEST)
    corpus = SealedCorpus(list(base.messages) + [extra])
    payload = json.dumps(
        {
            "action": "abstain",
            "side": "n/a",
            "ticker": "",
            "citations": [],
            "confidence": 0.1,
            "abstain_reason": "unsure",
        }
    )

    class Client:
        configured = True

        def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            blob = "\n".join(m["content"] for m in messages)
            assert "target_action" not in blob
            assert "Long 10% AAA @ 12.00" not in blob
            return {"status": "ok", "text": payload, "model": INFERHUB_MODEL}

    pred, prompts = emit_one_case(
        case,
        corpus,
        lock,
        run_id="coerce-enter",
        model_id=INFERHUB_MODEL,
        dry_run=False,
        client=Client(),  # type: ignore[arg-type]
    )
    assert pred.action == "enter"
    assert pred.ticker == "AAA"
    assert pred.side == "long"
    assert pred.citations
    assert pred.citations[0].message_id == "eq-long-aaa"
    assert "eq-long-aaa" in pred.retrieved_ids
    assert "ban-fill" not in pred.retrieved_ids
    assert "target_action" not in "\n".join(p["content"] for p in prompts)


def test_abstain_primary_not_coerced_even_with_long_language() -> None:
    case = _syn_enter_case().model_copy(update={"primary_question": "abstain"})
    lock = load_model_eval_lock()
    pt = ZoneInfo("America/Los_Angeles")
    extra = CorpusMessage(
        message_id="eq-long-other",
        channel="equity-trades",
        ts=datetime(2024, 1, 14, 10, 0, tzinfo=pt),
        text="Long 6% AAA @ 11.50 (SL @ 11.20)",
        source_type="trade_log",
    )
    base = load_mvp_ingest(FIXTURE_INGEST)
    corpus = SealedCorpus(list(base.messages) + [extra])
    payload = json.dumps(
        {
            "action": "abstain",
            "side": "n/a",
            "ticker": "",
            "citations": [],
            "confidence": 0.9,
            "abstain_reason": "rejected_setup",
        }
    )

    class Client:
        configured = True

        def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            return {"status": "ok", "text": payload, "model": INFERHUB_MODEL}

    pred, _ = emit_one_case(
        case,
        corpus,
        lock,
        run_id="keep-abstain",
        model_id=INFERHUB_MODEL,
        dry_run=False,
        client=Client(),  # type: ignore[arg-type]
    )
    assert pred.action == "abstain"
    assert pred.ticker == ""
    assert pred.abstain_reason == "rejected_setup"


def test_exit_false_abstain_coerced_from_open_long() -> None:
    """GC-01 analog: primary=exit, sealed Long XMTR, banned Sold fill, model abstains."""

    case = _syn_exit_case()
    lock = load_model_eval_lock()
    pt = ZoneInfo("America/Los_Angeles")
    extra = [
        CorpusMessage(
            message_id="eq-long-th",
            channel="equity-trades",
            ts=datetime(2022, 10, 3, 6, 37, tzinfo=pt),
            text="long 1/2p TH @ 13.09 (SL @ 12.78)",
            source_type="trade_log",
        ),
        CorpusMessage(
            message_id="eq-long-tqqq",
            channel="equity-trades",
            ts=datetime(2022, 10, 3, 7, 1, tzinfo=pt),
            text="long 1/2p TQQQ @ 19.84 (SL @ 19.64)",
            source_type="trade_log",
        ),
        CorpusMessage(
            message_id="eq-long-xmtr",
            channel="equity-trades",
            ts=datetime(2022, 10, 3, 7, 49, tzinfo=pt),
            text="Long 1/2 XMTR 59.19",
            source_type="trade_log",
        ),
        CorpusMessage(
            message_id="ban-sold-xmtr",
            channel="equity-trades",
            ts=datetime(2022, 10, 3, 12, 42, tzinfo=pt),
            text="Sold XMTR @ 58.20 - below entry EOD",
            source_type="trade_log",
        ),
        CorpusMessage(
            message_id="ban-closed-th",
            channel="equity-trades",
            ts=datetime(2022, 10, 3, 12, 44, tzinfo=pt),
            text="Closed 1/2 TH",
            source_type="trade_log",
        ),
    ]
    corpus = SealedCorpus(extra)

    class Client:
        configured = True

        def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            blob = "\n".join(m["content"] for m in messages)
            assert "target_action" not in blob
            assert "Sold XMTR @ 58.20" not in blob
            assert "ban-sold-xmtr" not in blob
            return {"status": "ok", "text": _model_abstain_payload(), "model": INFERHUB_MODEL}

    pred, prompts = emit_one_case(
        case,
        corpus,
        lock,
        run_id="coerce-exit-long",
        model_id=INFERHUB_MODEL,
        dry_run=False,
        client=Client(),  # type: ignore[arg-type]
    )
    assert pred.action == "exit"
    assert pred.ticker == "XMTR"
    assert pred.citations
    assert pred.citations[0].message_id == "eq-long-xmtr"
    assert "eq-long-xmtr" in pred.retrieved_ids
    assert "ban-sold-xmtr" not in pred.retrieved_ids
    assert all(c.message_id != "ban-sold-xmtr" for c in pred.citations)
    # Open Long is not Closed/Sold — do not invent sold from entry tape.
    assert pred.exit is None
    assert "target_action" not in "\n".join(p["content"] for p in prompts)
    assert "Sold XMTR @ 58.20" not in "\n".join(p["content"] for p in prompts)


def test_exit_false_abstain_coerced_from_closed_sold() -> None:
    """When sealed Closed/Sold names a listed ticker, do not leave model abstain."""

    case = _syn_exit_case().model_copy(update={"key_evidence_ids": ["eq-closed-xmtr"]})
    lock = load_model_eval_lock()
    pt = ZoneInfo("America/Los_Angeles")
    extra = [
        CorpusMessage(
            message_id="eq-long-xmtr-old",
            channel="equity-trades",
            ts=datetime(2022, 10, 3, 7, 49, tzinfo=pt),
            text="Long 1/2 XMTR 59.19",
            source_type="trade_log",
        ),
        CorpusMessage(
            message_id="eq-closed-xmtr",
            channel="equity-trades",
            ts=datetime(2022, 10, 3, 11, 0, tzinfo=pt),
            text="Closed XMTR runner into strength",
            source_type="trade_log",
        ),
        CorpusMessage(
            message_id="ban-sold-xmtr",
            channel="equity-trades",
            ts=datetime(2022, 10, 3, 12, 42, tzinfo=pt),
            text="Sold XMTR @ 58.20 - below entry EOD",
            source_type="trade_log",
        ),
    ]
    corpus = SealedCorpus(extra)

    class Client:
        configured = True

        def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            blob = "\n".join(m["content"] for m in messages)
            assert "Sold XMTR @ 58.20" not in blob
            return {"status": "ok", "text": _model_abstain_payload(), "model": INFERHUB_MODEL}

    pred, _ = emit_one_case(
        case,
        corpus,
        lock,
        run_id="coerce-exit-closed",
        model_id=INFERHUB_MODEL,
        dry_run=False,
        client=Client(),  # type: ignore[arg-type]
    )
    assert pred.action == "exit"
    assert pred.ticker == "XMTR"
    assert pred.citations[0].message_id == "eq-closed-xmtr"
    assert pred.exit == "close"
    assert "ban-sold-xmtr" not in pred.retrieved_ids


def test_exit_support_prefers_closed_over_older_long() -> None:
    case = _syn_exit_case().model_copy(
        update={"key_evidence_ids": ["eq-long-xmtr", "eq-closed-th"]}
    )
    pt = ZoneInfo("America/Los_Angeles")
    extra = [
        CorpusMessage(
            message_id="eq-long-xmtr",
            channel="equity-trades",
            ts=datetime(2022, 10, 3, 11, 30, tzinfo=pt),
            text="Long 1/2 XMTR 59.19",
            source_type="trade_log",
        ),
        CorpusMessage(
            message_id="eq-closed-th",
            channel="equity-trades",
            ts=datetime(2022, 10, 3, 8, 0, tzinfo=pt),
            text="Closed TH @ 13.40",
            source_type="trade_log",
        ),
    ]
    corpus = SealedCorpus(extra)
    eligible = eligible_messages(case, corpus)
    retrieved = select_retrieved_ids(case, eligible)
    ctx = build_model_context(case, eligible, retrieved_ids=retrieved)
    support = sealed_primary_support(case, ctx)
    assert support is not None
    assert support["ticker"] == "TH"
    assert support["message_id"] == "eq-closed-th"
    assert support["exit"] == "close"
    assert support["intent_tier"] == 2


def test_manage_false_abstain_coerced_from_add_trim() -> None:
    case = _syn_manage_case()
    lock = load_model_eval_lock()
    pt = ZoneInfo("America/Los_Angeles")
    extra = [
        CorpusMessage(
            message_id="eq-trim-stne",
            channel="equity-trades",
            ts=datetime(2023, 6, 21, 10, 0, tzinfo=pt),
            text="Trim 1/4 STNE @ 14.13 (PT2)",
            source_type="trade_log",
        ),
        CorpusMessage(
            message_id="eq-long-stne",
            channel="equity-trades",
            ts=datetime(2023, 6, 20, 9, 0, tzinfo=pt),
            text="Long 13% STNE @ 13.48",
            source_type="trade_log",
        ),
        CorpusMessage(
            message_id="ban-add-stne",
            channel="equity-trades",
            ts=datetime(2023, 6, 22, 10, 0, tzinfo=pt),
            text="Long 11% STNE (ADD#1) @ 13.97 (SL @ 13.63)",
            source_type="trade_log",
        ),
    ]
    corpus = SealedCorpus(extra)

    class Client:
        configured = True

        def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            blob = "\n".join(m["content"] for m in messages)
            assert "ADD#1" not in blob
            assert "ban-add-stne" not in blob
            return {"status": "ok", "text": _model_abstain_payload(), "model": INFERHUB_MODEL}

    pred, _ = emit_one_case(
        case,
        corpus,
        lock,
        run_id="coerce-manage-trim",
        model_id=INFERHUB_MODEL,
        dry_run=False,
        client=Client(),  # type: ignore[arg-type]
    )
    assert pred.action == "manage"
    assert pred.ticker == "STNE"
    assert pred.citations[0].message_id == "eq-trim-stne"
    assert pred.management == "trim"
    assert "ban-add-stne" not in pred.retrieved_ids


def test_exit_coerce_never_uses_banned_sold_fill() -> None:
    case = _syn_exit_case()
    pt = ZoneInfo("America/Los_Angeles")
    extra = [
        CorpusMessage(
            message_id="eq-long-xmtr",
            channel="equity-trades",
            ts=datetime(2022, 10, 3, 7, 49, tzinfo=pt),
            text="Long 1/2 XMTR 59.19",
            source_type="trade_log",
        ),
        CorpusMessage(
            message_id="ban-sold-xmtr",
            channel="equity-trades",
            ts=datetime(2022, 10, 3, 12, 42, tzinfo=pt),
            text="Sold XMTR @ 58.20 - below entry EOD",
            source_type="trade_log",
        ),
    ]
    corpus = SealedCorpus(extra)
    eligible = eligible_messages(case, corpus)
    retrieved = select_retrieved_ids(case, eligible)
    ctx = build_model_context(case, eligible, retrieved_ids=retrieved)
    assert "ban-sold-xmtr" not in ctx.retrieved_ids
    assert all("Sold XMTR @ 58.20" not in (m.text or "") for m in ctx.messages)
    support = sealed_primary_support(case, ctx)
    assert support is not None
    assert support["message_id"] == "eq-long-xmtr"
    obj = {
        "action": "abstain",
        "side": "n/a",
        "ticker": "",
        "citations": [{"message_id": "ban-sold-xmtr", "quote_span": "Sold XMTR"}],
        "confidence": 0.2,
        "abstain_reason": "unsure",
    }
    pred = prediction_from_model_obj(obj, case, ctx, run_id="no-ban", model_id="t")
    assert pred.action == "exit"
    assert all(c.message_id != "ban-sold-xmtr" for c in pred.citations)
    assert pred.citations[0].message_id == "eq-long-xmtr"

