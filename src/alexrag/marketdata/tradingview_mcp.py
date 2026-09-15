"""TradingView MCP stub. Not wired in MVP; no network calls."""

from __future__ import annotations


class TradingViewMCP:
    """TODO: TradingView MCP client for chart context. Must not invent indicator values."""

    def snapshot(self, ticker: str) -> dict:
        raise NotImplementedError(
            "TODO: TradingView MCP — not implemented in MVP; fail-closed (do not fabricate numbers)"
        )
