"""MODEL_EVAL_LOCK_V0 scorer hooks. Offline; no Mac ingest; capital 0."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from alexrag.cli import app
from alexrag.eval.frozen_pack import EligibleFilter, FrozenCase, FrozenPackIntegrityError, TargetAction, load_frozen_pack
from alexrag.eval.model_context import GroundTruthLeakError, build_model_context
from alexrag.eval.model_lock import EXPECTED_FIXTURE_SHA16, load_model_eval_lock
from alexrag.eval.model_prediction import ModelPrediction
from alexrag.eval.model_scorer import (
    KillScarError,
    make_abstain_prediction,
    run_score_model,
    score_model_run,
    score_prediction,
)
from alexrag.eval.sealed_corpus import eligible_messages, load_mvp_ingest

PT = ZoneInfo("America/Los_Angeles")
FIXTURE_INGEST = Path(__file__).parent / "fixtures" / "model_eval" / "ingest"
RUNNER = CliRunner()


def _synth_case() -> FrozenCase:
    decision = datetime(2024, 1, 15, 10, 0, tzinfo=PT)
    return FrozenCase(
        case_id="SYN-01",
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


def test_frozen_pack_pins_lock_sha() -> None:
    pack = load_frozen_pack()
    lock = load_model_eval_lock()
    assert pack.sha256_16 == EXPECTED_FIXTURE_SHA16 == lock.fixture_sha256_16
    assert pack.case_count == 48 == len(pack.cases)
    assert lock.capital == 0
    assert lock.paper_authority_default is False
    assert len(lock.ambiguous_case_ids_locked) == 16


def test_frozen_pack_hash_mismatch(tmp_path: Path) -> None:
    src = Path("eval/golden_cases_v0_frozen.json")
    dest = tmp_path / "tampered.json"
    dest.write_bytes(src.read_bytes() + b"\n")
    with pytest.raises(FrozenPackIntegrityError):
        load_frozen_pack(dest)


def test_eligible_filter_excludes_banned_ids() -> None:
    case = _synth_case()
    corpus = load_mvp_ingest(FIXTURE_INGEST)
    eligible = eligible_messages(case, corpus)
    ids = {m.message_id for m in eligible}
    assert "ban-fill" not in ids
    assert "ban-journal" not in ids
    assert "eq-equal" not in ids
    assert "eq-after" not in ids
    assert "eq-ok" in ids
    assert "j-ok" in ids
    assert "r-ok" in ids
    assert "pf-ok" in ids
    assert "gc29-banned" not in ids


def test_context_builder_rejects_gt_injection() -> None:
    case = _synth_case()
    corpus = load_mvp_ingest(FIXTURE_INGEST)
    eligible = eligible_messages(case, corpus)
    ctx = build_model_context(case, eligible)
    dumped = ctx.model_dump_sealed()
    assert "target_action" not in dumped
    assert case.target_action.message_id not in ctx.retrieved_ids
    assert ctx.paper_authority is False
    assert ctx.capital == 0
    with pytest.raises(GroundTruthLeakError):
        build_model_context(
            case,
            eligible,
            inject={"target_action": case.target_action.model_dump(mode="json")},
        )
    with pytest.raises(GroundTruthLeakError):
        build_model_context(case, eligible, retrieved_ids=["ban-fill"])
    poisoned = list(eligible) + [corpus.lookup("ban-fill")]  # type: ignore[list-item]
    # Banned/GT rows in the eligible list are filtered out (not raised).
    ctx2 = build_model_context(case, poisoned)
    assert "ban-fill" not in ctx2.retrieved_ids
    assert case.target_action.message_id not in ctx2.retrieved_ids


def _pred_for(case: FrozenCase, **overrides: object) -> ModelPrediction:
    ack = case.eligible_filter.ts_lt.isoformat()
    data: dict = {
        "case_id": case.case_id,
        "decision_ts": case.decision_ts.isoformat(),
        "action": "enter",
        "side": "long",
        "ticker": case.tickers[0] if case.tickers else "X",
        "size_pct": None,
        "stop": None,
        "management": None,
        "exit": None,
        "rejected_alternatives": [],
        "citations": [
            {
                "source": "equity-trades",
                "message_id": "eq-ok",
                "ts": "2024-01-15T09:00:00-08:00",
                "quote_span": "journal setup on AAA",
            }
        ],
        "confidence": 0.1,
        "abstain_reason": None,
        "sealed_cutoff_ack": ack,
        "retrieved_ids": ["eq-ok"],
        "model_id": "test-hooks",
        "run_id": "test-run",
    }
    data.update(overrides)
    return ModelPrediction.model_validate(data)


def test_gc15_gc29_banned_cite_kills_run() -> None:
    pack = load_frozen_pack()
    lock = load_model_eval_lock()
    gc15 = next(c for c in pack.cases if c.case_id == "GC-15-2023-09-21")
    gc29 = next(c for c in pack.cases if c.case_id == "GC-29-2025-03-05")
    others = [
        make_abstain_prediction(c, run_id="kill-test", model_id="test-hooks")
        for c in pack.cases
        if c.case_id not in {gc15.case_id, gc29.case_id}
    ]
    leak15 = _pred_for(
        gc15,
        action="enter",
        side="short",
        ticker="STRL",
        retrieved_ids=[gc15.banned_same_day_ids[0]],
        citations=[
            {
                "source": "equity-trades",
                "message_id": gc15.banned_same_day_ids[0],
                "ts": gc15.decision_ts.isoformat(),
                "quote_span": "STRL",
            }
        ],
        run_id="kill-test",
    )
    honest29 = make_abstain_prediction(gc29, run_id="kill-test", model_id="test-hooks")
    run = score_model_run(pack, others + [leak15, honest29], lock)
    assert run.summary.run_valid is False
    assert any("GC-15-2023-09-21" in hit for hit in run.summary.kill_scars)
    assert run.summary.paper_authority is False
    assert run.summary.capital == 0

    leak29 = _pred_for(
        gc29,
        action="enter",
        side="long",
        ticker="NFLX",
        retrieved_ids=["eq-ok"],
        citations=[
            {
                "source": "alex-journal",
                "message_id": gc29.banned_same_day_ids[0],
                "ts": "2025-03-05T12:00:00-08:00",
                "quote_span": "NFLX",
            }
        ],
        run_id="kill-test-29",
    )
    honest15 = make_abstain_prediction(gc15, run_id="kill-test-29", model_id="test-hooks")
    rest = [
        make_abstain_prediction(c, run_id="kill-test-29", model_id="test-hooks")
        for c in pack.cases
        if c.case_id not in {gc15.case_id, gc29.case_id}
    ]
    run29 = score_model_run(pack, rest + [honest15, leak29], lock)
    assert run29.summary.run_valid is False
    assert any("GC-29-2025-03-05" in hit for hit in run29.summary.kill_scars)


def test_ambiguous_ids_stay_ambiguous() -> None:
    pack = load_frozen_pack()
    lock = load_model_eval_lock()
    assert len(lock.ambiguous_ids) == 16
    case = next(c for c in pack.cases if c.case_id == "GC-02-2022-11-03")
    pred = _pred_for(
        case,
        action="enter",
        side="long",
        ticker="SOXS",
        citations=[
            {
                "source": "equity-trades",
                "message_id": case.key_evidence_ids[0],
                "ts": "2022-11-02T10:00:00-07:00",
                "quote_span": "prior",
            }
        ],
        retrieved_ids=[case.key_evidence_ids[0]],
    )
    score = score_prediction(case, pred, lock)
    assert score.status == "AMBIGUOUS"
    assert score.fixture_tag == "AMBIGUOUS"
    assert "fixture_tag=AMBIGUOUS_no_soft_relabel" in score.notes

    preds = [make_abstain_prediction(c, run_id="amb", model_id="test-hooks") for c in pack.cases]
    run = score_model_run(pack, preds, lock)
    amb_ids = {s.case_id for s in run.scores if s.status == "AMBIGUOUS"}
    assert amb_ids == set(lock.ambiguous_case_ids_locked)
    assert run.summary.n_ambiguous == 16


def test_cli_score_model_abstain_baseline(tmp_path: Path) -> None:
    pack = load_frozen_pack()
    pred_path = tmp_path / "preds.jsonl"
    with pred_path.open("w", encoding="utf-8") as fh:
        for case in pack.cases:
            fh.write(
                make_abstain_prediction(case, run_id="cli-smoke", model_id="abstain-everywhere").model_dump_json()
                + "\n"
            )
    out = tmp_path / "runs"
    result = RUNNER.invoke(
        app,
        [
            "score-model",
            "--predictions",
            str(pred_path),
            "--ingest",
            str(FIXTURE_INGEST),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "paper_authority=false" in result.output
    assert "capital=0" in result.output
    assert "ambiguous=16" in result.output
    dest = out / "cli-smoke"
    manifest = (dest / "manifest.json").read_text(encoding="utf-8")
    assert '"paper_authority": false' in manifest
    assert '"capital": 0' in manifest
    assert '"run_valid": true' in manifest


def test_cli_kill_scar_exits_nonzero(tmp_path: Path) -> None:
    pack = load_frozen_pack()
    gc15 = next(c for c in pack.cases if c.case_id == "GC-15-2023-09-21")
    pred_path = tmp_path / "preds.jsonl"
    with pred_path.open("w", encoding="utf-8") as fh:
        for case in pack.cases:
            if case.case_id == gc15.case_id:
                fh.write(
                    _pred_for(
                        case,
                        retrieved_ids=[case.banned_same_day_ids[0]],
                        citations=[
                            {
                                "source": "equity-trades",
                                "message_id": case.banned_same_day_ids[0],
                                "ts": case.decision_ts.isoformat(),
                                "quote_span": "leak",
                            }
                        ],
                        run_id="cli-kill",
                    ).model_dump_json()
                    + "\n"
                )
            else:
                fh.write(
                    make_abstain_prediction(case, run_id="cli-kill", model_id="test-hooks").model_dump_json()
                    + "\n"
                )
    out = tmp_path / "runs"
    result = RUNNER.invoke(
        app,
        ["score-model", "--predictions", str(pred_path), "--ingest", str(FIXTURE_INGEST), "--out", str(out)],
    )
    assert result.exit_code == 2, result.output
    assert "KILL_SCAR" in result.output
    assert (out / "cli-kill" / "manifest.json").is_file()
    with pytest.raises(KillScarError):
        run_score_model(
            predictions_path=pred_path,
            ingest_dir=FIXTURE_INGEST,
            out_root=tmp_path / "runs2",
        )


def test_existing_eval_golden_still_works() -> None:
    result = RUNNER.invoke(app, ["eval-golden"])
    assert result.exit_code == 0, result.output
    assert "loaded 48 cases" in result.output
