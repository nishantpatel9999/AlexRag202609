from alexrag.agents.extract import extract_regime, extract_size_ner_pct, extract_tickers


def test_extractors_copy_evidence_only() -> None:
    text = "Journal: trend day. Trade log: filled $NVDA long. Size NER 0.25%."
    assert extract_tickers(text) == ["NVDA"]
    assert extract_size_ner_pct(text) == 0.25
    assert extract_regime(text) == "trend_day"
    assert extract_tickers("no symbols here") == []
    assert extract_size_ner_pct("no size mentioned") is None
    assert extract_regime("nothing useful") == "unknown"
