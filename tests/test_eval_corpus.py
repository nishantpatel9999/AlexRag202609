from datetime import datetime
from zoneinfo import ZoneInfo

from alexrag.eval.cutoff import enter_evidence_illegal, sealed_ok
from alexrag.eval.harness import Expected, GoldenCase, Prediction, load_golden_pack, score_case
from alexrag.schemas.sources import CONFLICT_LABELS, GOLDEN_CASE_COUNT, PRECEDENCE_DEFAULT

PT = ZoneInfo("America/Los_Angeles")


def test_golden_pack_loads_48() -> None:
    pack = load_golden_pack()
    assert pack.n_cases == GOLDEN_CASE_COUNT == 48
    assert len(pack.cases) == 48
    assert pack.cases[0].id == "golden-01"
    assert pack.cases[-1].id == "golden-48"
    assert {c.conflict_label for c in pack.cases} == set(CONFLICT_LABELS)
    assert pack.sealed_cutoff == "timestamp < decision_ts"
    assert pack.post_fill_enter_evidence == "banned"
    assert pack.pnl_required is False


def test_precedence_matches_corpus_spec() -> None:
    assert PRECEDENCE_DEFAULT == (
        "trade_log",
        "journal",
        "gameplan",
        "report",
        "gitbook",
    )


def test_sealed_cutoff_strictly_before() -> None:
    decision = datetime(2026, 9, 15, 10, 0, tzinfo=PT)
    before = datetime(2026, 9, 15, 9, 59, tzinfo=PT)
    equal = decision
    after = datetime(2026, 9, 15, 10, 1, tzinfo=PT)
    assert sealed_ok(before, decision) is True
    assert sealed_ok(equal, decision) is False
    assert sealed_ok(after, decision) is False
    assert sealed_ok(None, decision) is False


def test_post_fill_journal_banned_as_enter_evidence() -> None:
    fill = datetime(2026, 9, 15, 10, 0, tzinfo=PT)
    post = datetime(2026, 9, 15, 10, 5, tzinfo=PT)
    pre = datetime(2026, 9, 15, 9, 50, tzinfo=PT)
    assert (
        enter_evidence_illegal(
            timestamp=post,
            source_type="journal",
            decision_ts=fill,
            fill_ts=fill,
        )
        is True
    )
    assert (
        enter_evidence_illegal(
            timestamp=pre,
            source_type="journal",
            decision_ts=fill,
            fill_ts=fill,
        )
        is False
    )


def test_score_enter_fails_on_post_fill_citation() -> None:
    decision = datetime(2026, 9, 15, 10, 0, tzinfo=PT)
    case = GoldenCase(
        id="synthetic-enter",
        conflict_label="no_trade_plan_then_entry",
        primary_axis="enter",
        expected=Expected(enter=True, abstain=False, min_citations=1),
        decision_ts=decision,
        fill_ts=decision,
        status="test",
    )
    pred = Prediction(
        enter=True,
        abstain=False,
        citations=[
            {
                "source_type": "journal",
                "timestamp": datetime(2026, 9, 15, 10, 20, tzinfo=PT),
            }
        ],
    )
    score = score_case(case, pred)
    enter_axis = next(a for a in score.axes if a.axis == "enter")
    assert score.illegal_enter_evidence is True
    assert enter_axis.passed is False


def test_score_citation_counts_only_sealed() -> None:
    decision = datetime(2026, 9, 15, 10, 0, tzinfo=PT)
    case = GoldenCase(
        id="synthetic-cite",
        conflict_label="fill_vs_same_time_journal",
        primary_axis="citation",
        expected=Expected(min_citations=1, timestamped_citations=True),
        decision_ts=decision,
        status="test",
    )
    pred = Prediction(
        abstain=True,
        citations=[
            {
                "source_type": "trade_log",
                "timestamp": datetime(2026, 9, 15, 9, 0, tzinfo=PT),
            },
            {
                "source_type": "journal",
                "timestamp": datetime(2026, 9, 15, 11, 0, tzinfo=PT),
            },
        ],
    )
    score = score_case(case, pred)
    cite = next(a for a in score.axes if a.axis == "citation")
    assert cite.passed is True
