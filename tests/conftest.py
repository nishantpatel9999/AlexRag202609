from __future__ import annotations

from pathlib import Path

import pytest

from alexrag.config import Settings, load_settings

FIXTURES = Path(__file__).parent / "fixtures"

# Credential env names that must not leak into unit tests from a linked .env
# or a sourced shell. Production code still reads them at runtime.
_CREDENTIAL_ENV = (
    "ALPACA_API_KEY_ID",
    "ALPACA_API_SECRET_KEY",
    "INFERHUB_API_KEY",
    "DISCORD_BOT_TOKEN",
)


@pytest.fixture(autouse=True)
def _clear_operator_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _CREDENTIAL_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def paper_settings() -> Settings:
    # Never load repo `.env` in unit tests (operator machines symlink real secrets).
    return load_settings(
        overrides={"mode": "paper", "kill_switch": False},
        load_env_file=False,
    )
