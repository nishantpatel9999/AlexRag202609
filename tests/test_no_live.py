from __future__ import annotations

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
    broker = AlpacaPaperBroker()
    with pytest.raises(Exception):
        FillIntent(intent_id="i", proposal_id="p", mode="live")  # type: ignore[arg-type]
    intent = FillIntent(intent_id="i", proposal_id="p", mode="paper")
    result = broker.submit_paper(intent)
    assert result["submitted"] is False
    assert result["status"] == "stubbed"


def test_tradingview_mcp_is_stub() -> None:
    with pytest.raises(NotImplementedError):
        TradingViewMCP().snapshot("NVDA")
