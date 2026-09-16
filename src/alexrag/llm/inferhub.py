"""Inferhub GLM-5.3-flash stub. No network. Key via env only; never logged.

Nishant / Hermes lock: ``https://api.inferhub.dev/v1`` with
``INFERHUB_PROVIDER=cbcn`` and model id ``cbcn/GLM-5.3-flash``.
Do not route to any non-cbcn Inferhub upstream.
"""

from __future__ import annotations

from typing import Any

from alexrag import envutil

LLM_PROVIDER = "inferhub"
LLM_PROVIDER_ENV = "LLM_PROVIDER"
LLM_MODEL_ENV = "LLM_MODEL"

INFERHUB_BASE_URL = "https://api.inferhub.dev/v1"
INFERHUB_BASE_URL_ENV = "INFERHUB_BASE_URL"
INFERHUB_PROVIDER = "cbcn"
INFERHUB_PROVIDER_ENV = "INFERHUB_PROVIDER"
INFERHUB_MODEL = "cbcn/GLM-5.3-flash"
INFERHUB_API_KEY_ENV = "INFERHUB_API_KEY"


def inferhub_key_present() -> bool:
    """True when INFERHUB_API_KEY is set. Does not return or store the secret."""

    return envutil.get_str(INFERHUB_API_KEY_ENV) is not None


def require_cbcn_provider(provider: str) -> str:
    """Reject any Inferhub upstream other than ``cbcn``."""

    if provider != INFERHUB_PROVIDER:
        raise ValueError(
            f"Inferhub calls must use {INFERHUB_PROVIDER_ENV}={INFERHUB_PROVIDER!r} "
            f"at {INFERHUB_BASE_URL}; got {provider!r} (no other Inferhub upstreams)"
        )
    return provider


def require_cbcn_model(model: str) -> str:
    """Reject models that are not the locked ``cbcn/GLM-5.3-flash`` id."""

    prefix = f"{INFERHUB_PROVIDER}/"
    if not model.startswith(prefix):
        raise ValueError(
            f"Inferhub model id must be prefixed with {prefix!r} "
            f"(got {model!r}); do not route to non-cbcn upstreams"
        )
    if model != INFERHUB_MODEL:
        raise ValueError(
            f"locked Inferhub model is {INFERHUB_MODEL!r}; got {model!r}"
        )
    return model


def require_inferhub_base_url(url: str) -> str:
    normalized = url.rstrip("/")
    if normalized != INFERHUB_BASE_URL:
        raise ValueError(
            f"Inferhub base_url must be {INFERHUB_BASE_URL!r}; got {url!r}"
        )
    return INFERHUB_BASE_URL


def require_llm_provider(provider: str) -> str:
    if provider != LLM_PROVIDER:
        raise ValueError(
            f"{LLM_PROVIDER_ENV} must be {LLM_PROVIDER!r}; got {provider!r}"
        )
    return provider


def locked_inferhub_provider() -> str:
    val = envutil.get_str(INFERHUB_PROVIDER_ENV)
    if val is None:
        return INFERHUB_PROVIDER
    return require_cbcn_provider(val)


def locked_inferhub_model() -> str:
    val = envutil.get_str(LLM_MODEL_ENV)
    if val is None:
        return INFERHUB_MODEL
    return require_cbcn_model(val)


def locked_inferhub_base_url() -> str:
    val = envutil.get_str(INFERHUB_BASE_URL_ENV)
    if val is None:
        return INFERHUB_BASE_URL
    return require_inferhub_base_url(val)


class InferhubClient:
    """Stub chat client. MVP does not call the network.

    Request shape always includes ``provider=cbcn`` and
    ``model=cbcn/GLM-5.3-flash``. Secrets stay in ``INFERHUB_API_KEY``.
    """

    llm_provider = LLM_PROVIDER
    base_url = INFERHUB_BASE_URL
    provider = INFERHUB_PROVIDER
    model = INFERHUB_MODEL

    def __init__(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.provider = require_cbcn_provider(provider or locked_inferhub_provider())
        self.model = require_cbcn_model(model or locked_inferhub_model())
        self.base_url = require_inferhub_base_url(base_url or locked_inferhub_base_url())
        self.configured = inferhub_key_present()

    def request_body(self, messages: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """Body that a real client would POST. Pins cbcn provider + prefixed model."""

        return {
            "provider": require_cbcn_provider(self.provider),
            "model": require_cbcn_model(self.model),
            "messages": list(messages or []),
        }

    def complete(
        self,
        messages: list[dict[str, str]] | None = None,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Return a stubbed completion. Never logs the API key. No HTTP."""

        if provider is not None:
            require_cbcn_provider(provider)
        if model is not None:
            require_cbcn_model(model)
        body = self.request_body(messages)
        return {
            "status": "stubbed",
            "llm_provider": LLM_PROVIDER,
            "base_url": self.base_url,
            "provider": body["provider"],
            "model": body["model"],
            "configured": self.configured,
            "text": None,
            "request": body,
            "notes": [
                "TODO: Inferhub GLM-5.3-flash client; no network in MVP",
                f"{LLM_PROVIDER_ENV}={LLM_PROVIDER}",
                f"{INFERHUB_BASE_URL_ENV}={INFERHUB_BASE_URL}",
                f"{INFERHUB_PROVIDER_ENV}={INFERHUB_PROVIDER} only",
                f"{LLM_MODEL_ENV}={INFERHUB_MODEL}",
                "secrets via INFERHUB_API_KEY env only",
            ],
        }
