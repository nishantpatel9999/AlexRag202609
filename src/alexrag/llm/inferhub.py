"""Inferhub glm-5.3-flash client. OpenAI-compatible chat completions.

Nishant / Hermes lock: ``https://api.inferhub.dev/v1`` with
``INFERHUB_PROVIDER=cbcn`` and canonical model id ``cbcn/glm-5.3-flash``
(HTTP ``model`` field). Accepts ``cbcn/GLM-5.3-flash`` case-insensitively
and normalizes to the lowercase API id. Do not route to any non-cbcn
Inferhub upstream.

``INFERHUB_API_KEY`` is read from the environment only and is never stored on
the client, returned in payloads, or written to logs.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from alexrag import envutil

LLM_PROVIDER = "inferhub"
LLM_PROVIDER_ENV = "LLM_PROVIDER"
LLM_MODEL_ENV = "LLM_MODEL"

INFERHUB_BASE_URL = "https://api.inferhub.dev/v1"
INFERHUB_BASE_URL_ENV = "INFERHUB_BASE_URL"
INFERHUB_PROVIDER = "cbcn"
INFERHUB_PROVIDER_ENV = "INFERHUB_PROVIDER"
INFERHUB_MODEL = "cbcn/glm-5.3-flash"
INFERHUB_API_KEY_ENV = "INFERHUB_API_KEY"

CHAT_COMPLETIONS_PATH = "/chat/completions"
_BEARER_RE = re.compile(r"Bearer\s+\S+", re.IGNORECASE)


class InferhubError(RuntimeError):
    """Network or protocol failure talking to Inferhub. Message is redacted."""


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
    """Accept locked model case-insensitively; return canonical API id.

    Canonical HTTP ``model`` is ``cbcn/glm-5.3-flash``. Env/validators may
    pass ``cbcn/GLM-5.3-flash`` or ``cbcn/glm-5.3-flash``.
    """

    prefix = f"{INFERHUB_PROVIDER}/"
    if not model.casefold().startswith(prefix.casefold()):
        raise ValueError(
            f"Inferhub model id must be prefixed with {prefix!r} "
            f"(got {model!r}); do not route to non-cbcn upstreams"
        )
    if model.casefold() != INFERHUB_MODEL.casefold():
        raise ValueError(
            f"locked Inferhub model is {INFERHUB_MODEL!r} "
            f"(case-insensitive); got {model!r}"
        )
    return INFERHUB_MODEL


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


def _read_api_key() -> str | None:
    """Return the env key or None. Caller must not log or persist it."""

    return envutil.get_str(INFERHUB_API_KEY_ENV)


def redact_secrets(text: str, secret: str | None = None) -> str:
    """Strip Bearer tokens and an optional known secret from an error string."""

    redacted = _BEARER_RE.sub("Bearer [redacted]", text)
    if secret:
        redacted = redacted.replace(secret, "[redacted]")
    return redacted


def _choice_text(payload: dict[str, Any]) -> str | None:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        text = payload.get("text")
        return text if isinstance(text, str) else None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts.append(part["text"])
                elif isinstance(part, str):
                    parts.append(part)
            if parts:
                return "".join(parts)
    text = first.get("text")
    return text if isinstance(text, str) else None


class InferhubClient:
    """OpenAI-compatible chat client pinned to cbcn / glm-5.3-flash.

    Request shape always includes ``provider=cbcn`` and canonical
    ``model=cbcn/glm-5.3-flash``. Secrets stay in ``INFERHUB_API_KEY``.
    Without a key, ``complete`` returns a local stub (no HTTP) so unit tests
    stay offline. With a key, POST ``{base_url}/chat/completions``.
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
        timeout: float = 60.0,
    ) -> None:
        self.provider = require_cbcn_provider(provider or locked_inferhub_provider())
        self.model = require_cbcn_model(model or locked_inferhub_model())
        self.base_url = require_inferhub_base_url(base_url or locked_inferhub_base_url())
        self.timeout = timeout
        self.configured = inferhub_key_present()

    def __repr__(self) -> str:
        return (
            f"InferhubClient(provider={self.provider!r}, model={self.model!r}, "
            f"base_url={self.base_url!r}, configured={self.configured})"
        )

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
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Chat completion. Never logs the API key.

        No key → local stub, no HTTP. Key present → POST chat/completions.
        """

        if provider is not None:
            require_cbcn_provider(provider)
        if model is not None:
            require_cbcn_model(model)
        body = self.request_body(messages)
        key = _read_api_key()
        self.configured = key is not None
        stub = {
            "status": "stubbed",
            "llm_provider": LLM_PROVIDER,
            "base_url": self.base_url,
            "provider": body["provider"],
            "model": body["model"],
            "configured": self.configured,
            "text": None,
            "request": body,
            "notes": [
                "no INFERHUB_API_KEY; returning stub (no HTTP)",
                f"{LLM_PROVIDER_ENV}={LLM_PROVIDER}",
                f"{INFERHUB_BASE_URL_ENV}={INFERHUB_BASE_URL}",
                f"{INFERHUB_PROVIDER_ENV}={INFERHUB_PROVIDER} only",
                f"{LLM_MODEL_ENV}={INFERHUB_MODEL}",
                "secrets via INFERHUB_API_KEY env only",
            ],
        }
        if not key:
            return stub

        url = f"{self.base_url}{CHAT_COMPLETIONS_PATH}"
        raw_body = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=raw_body, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json")
        request.add_header("Authorization", f"Bearer {key}")
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                err_body = ""
            msg = redact_secrets(f"Inferhub HTTP {exc.code}: {err_body}", key)
            raise InferhubError(msg) from None
        except Exception as exc:
            raise InferhubError(redact_secrets(str(exc), key)) from None

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InferhubError(f"Inferhub response was not JSON: {exc}") from None
        if not isinstance(payload, dict):
            raise InferhubError("Inferhub response JSON must be an object")
        text = _choice_text(payload)
        return {
            "status": "ok",
            "llm_provider": LLM_PROVIDER,
            "base_url": self.base_url,
            "provider": body["provider"],
            "model": body["model"],
            "configured": True,
            "text": text,
            "request": body,
            "notes": [
                "inferhub chat.completions",
                f"{LLM_PROVIDER_ENV}={LLM_PROVIDER}",
                f"{INFERHUB_BASE_URL_ENV}={INFERHUB_BASE_URL}",
                f"{INFERHUB_PROVIDER_ENV}={INFERHUB_PROVIDER} only",
                f"{LLM_MODEL_ENV}={INFERHUB_MODEL}",
                "secrets via INFERHUB_API_KEY env only",
            ],
        }
