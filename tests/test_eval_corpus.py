from alexrag.eval.golden_cases import stub_golden_cases
from alexrag.schemas.sources import CONFLICT_LABELS, GOLDEN_CASE_COUNT, PRECEDENCE_DEFAULT


def test_golden_case_stub_count() -> None:
    cases = stub_golden_cases()
    assert len(cases) == GOLDEN_CASE_COUNT == 48
    assert {c["conflict_label"] for c in cases} == set(CONFLICT_LABELS)
    assert cases[0]["id"] == "golden-01"
    assert cases[-1]["id"] == "golden-48"
    assert all(c["status"] == "stub" for c in cases)


def test_precedence_matches_corpus_spec() -> None:
    assert PRECEDENCE_DEFAULT == (
        "trade_log",
        "journal",
        "gameplan",
        "report",
        "gitbook",
    )
