"""Inferhub GLM-5.3-flash stub. No network. Key via env only; never logged.

Nishant lock: calls to ``https://api.inferhub.dev/v1`` must pass
``provider=cbcn`` only — no other Inferhub upstreams.
"""

from __future__ import annotations

from typing import Any

from alexrag import envutil

INFERHUB_BASE_URL = "https://api.inferhub.dev/v1"
INFERHUB_PROVIDER = "cbcn"
INFERHUB_MODEL = "GLM-5.3-flash"
INFERHUB_API_KEY_ENV = "INFERHUB_API_KEY"
INFERHUB_PROVIDER_ENV = "INFERHUB_PROVIDER"


def inferhub_key_present() -> bool:
    """True when INFERHUB_API_KEY is set. Does not return or store the secret."""

    return envutil.get_str(INFERHUB_API_KEY_ENV) is not None


def require_cbcn_provider(provider: str) -> str:
    """Reject any Inferhub upstream other than ``cbcn``."""

    if provider != INFERHUB_PROVIDER:
        raise ValueError(
            f"Inferhub calls must use provider={INFERHUB_PROVIDER!r} "
            f"at {INFERHUB_BASE_URL}; got {provider!r} (no other Inferhub upstreams)"
        )
    return provider


def locked_inferhub_provider() -> str:
    """Provider from env or the cbcn lock. Non-cbcn env values fail closed."""

    val = envutil.get_str(INFERHUB_PROVIDER_ENV)
    if val is None:
        return INFERHUB_PROVIDER
    return require_cbcn_provider(val)


class InferhubClient:
    """Stub chat client. MVP does not call the network.

    Request shape always includes ``provider=cbcn``. Secrets stay in
    ``INFERHUB_API_KEY``; this class records presence only.
    """

    base_url = INFERHUB_BASE_URL
    provider = INFERHUB_PROVIDER
    model = INFERHUB_MODEL

    def __init__(self, provider: str | None = None) -> None:
        self.provider = require_cbcn_provider(provider or locked_inferhub_provider())
        self.configured = inferhub_key_present()

    def request_body(self, messages: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """Body that a real client would POST. Always pins provider=cbcn."""

        return {
            "provider": require_cbcn_provider(self.provider),
            "model": self.model,
            "messages": list(messages or []),
        }

    def complete(
        self,
        messages: list[dict[str, str]] | None = None,
        *,
        provider: str | None = None,
    ) -> dict[str, Any]:
        """Return a stubbed completion. Never logs the API key. No HTTP."""

        if provider is not None:
            require_cbcn_provider(provider)
        body = self.request_body(messages)
        return {
            "status": "stubbed",
            "base_url": self.base_url,
            "provider": body["provider"],
            "model": body["model"],
            "configured": self.configured,
            "text": None,
            "request": body,
            "notes": [
                "TODO: Inferhub GLM-5.3-flash client; no network in MVP",
                f"base_url={INFERHUB_BASE_URL}",
                f"{INFERHUB_PROVIDER_ENV}={INFERHUB_PROVIDER} only",
                "secrets via INFERHUB_API_KEY env only",
            ],
        }
