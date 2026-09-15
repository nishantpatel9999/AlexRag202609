"""Discord notify stub."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class DiscordNotifier:
    """TODO: Discord bot token / webhook. Never commit secrets. No network in MVP."""

    def send(self, text: str) -> dict:
        preview = text if len(text) < 200 else text[:200] + "…"
        log.info("discord notify stub: %s", preview)
        return {"status": "stubbed", "sent": False, "note": "TODO: Discord bot token"}
