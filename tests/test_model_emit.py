"""Sealed-cutoff emit-model-predictions. Offline; capital 0; no Inferhub network."""

from __future__ import annotations

import json
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
    emit_model_predictions,
    emit_one_case,
    extract_json_object,
    prediction_from_model_obj,
    select_retrieved_ids,
    thin_evidence_reason,
)
from alexrag.eval.model_lock import HARD_KILL_SCAR_IDS, load_model_eval_lock
from alexrag.eval.model_prediction import load_predictions
from alexrag.eval.sealed_corpus import eligible_messages, load_mvp_ingest
from alexrag.llm.inferhub import (
    INFERHUB_API_KEY_ENV,
    INFERHUB_MODEL,
    InferhubClient,
    InferhubError,
)

FIXTURE_INGEST = Path(__file__).parent / "fixtures" / "model_eval" / "ingest"
RUNNER = CliRunner()
GC15 = "GC-15-2023-09-21"
GC29 = "GC-29-2025-03-05"


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
    pt = ZoneInfo("America/Los_Angeles")
    decision = datetime(2024, 1, 15, 10, 0, tzinfo=pt)
    case = FrozenCase(
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
