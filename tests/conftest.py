from __future__ import annotations

from pathlib import Path

import pytest

from alexrag.config import Settings, load_settings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def paper_settings() -> Settings:
    return load_settings(overrides={"mode": "paper", "kill_switch": False})
