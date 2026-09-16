from datetime import datetime, timezone
from pathlib import Path

import pytest

from alexrag.broker.alpaca_paper import AlpacaPaperBroker
from alexrag.marketdata.tradingview_mcp import TradingViewMCP
from alexrag.schemas.fill_intent import FillIntent


def test_no_live_alpaca_url_in_src() -> None:
    root = Path(__file__).resolve().parents[1] / "src"
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "live-api.alpaca" in text or "api.alpaca.markets" in text:
            offenders.append(str(path))
    assert offenders == []


def test_broker_rejects_non_paper(monkeypatch) -> None:
    from alexrag.broker.alpaca_paper import ALPACA_KEY_ID_ENV, ALPACA_SECRET_KEY_ENV

    monkeypatch.delenv(ALPACA_KEY_ID_ENV, raising=False)
    monkeypatch.delenv(ALPACA_SECRET_KEY_ENV, raising=False)
    broker = AlpacaPaperBroker()
    with pytest.raises(Exception):
        FillIntent(intent_id="i", proposal_id="p", mode="live")  # type: ignore[arg-type]
    clock = datetime(2026, 9, 15, 18, 15, tzinfo=timezone.utc)
    intent = FillIntent(
        intent_id="i",
        proposal_id="p",
        mode="paper",
        ticker="NVDA",
        side="buy",
        order_type="market",
        notional=250.0,
        qty=2.0,
        size_ner_pct=0.25,
        decision_clock=clock,
        abstain=False,
    )
    result = broker.submit_paper(intent)
    assert result.status == "stubbed"
    assert result.filled is False
    assert result.qty_filled == 0
    assert result.venue == "alpaca_paper"
    assert result.skip_reason == "alpaca_paper_no_keys"


def test_alpaca_src_uses_paper_key_pair_env_names() -> None:
    text = Path(__file__).resolve().parents[1].joinpath(
        "src", "alexrag", "broker", "alpaca_paper.py"
    ).read_text(encoding="utf-8")
    assert "ALPACA_API_KEY_ID" in text
    assert "ALPACA_API_SECRET_KEY" in text
    assert "ALPACA_API_KEY=" not in text
    assert "ALPACA_API_SECRET=" not in text


def test_tradingview_mcp_is_stub() -> None:
    with pytest.raises(NotImplementedError):
        TradingViewMCP().snapshot("NVDA")
