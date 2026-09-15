"""Inferhub.dev GLM 5.3-flash stub. No network. Key via env only; never logged."""

from __future__ import annotations

from typing import Any

from alexrag import envutil

INFERHUB_PROVIDER = "inferhub.dev"
INFERHUB_MODEL = "GLM 5.3-flash"
INFERHUB_API_KEY_ENV = "INFERHUB_API_KEY"


def inferhub_key_present() -> bool:
    """True when INFERHUB_API_KEY is set. Does not return or store the secret."""

    return envutil.get_str(INFERHUB_API_KEY_ENV) is not None


class InferhubClient:
    """Stub chat client for the always-on LLM. MVP does not call the network.

    Secrets stay in ``INFERHUB_API_KEY``. This class records presence only.
    """

    provider = INFERHUB_PROVIDER
    model = INFERHUB_MODEL

    def __init__(self) -> None:
        self.configured = inferhub_key_present()

    def complete(self, messages: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """Return a stubbed completion. Never logs the API key. No HTTP."""

        _ = messages
        return {
            "status": "stubbed",
            "provider": self.provider,
            "model": self.model,
            "configured": self.configured,
            "text": None,
            "notes": [
                "TODO: Inferhub.dev GLM 5.3-flash client; no network in MVP",
                "secrets via INFERHUB_API_KEY env only",
            ],
        }
