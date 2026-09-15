"""Small env helpers so config does not depend on pydantic-settings nested env."""

from __future__ import annotations

import os


def get_str(name: str) -> str | None:
    val = os.environ.get(name)
    if val is None or val == "":
        return None
    return val


def get_bool(name: str) -> bool | None:
    val = get_str(name)
    if val is None:
        return None
    return val.strip().lower() in {"1", "true", "yes", "on"}


def get_float(name: str) -> float | None:
    val = get_str(name)
    if val is None:
        return None
    return float(val)


def get_int(name: str) -> int | None:
    val = get_str(name)
    if val is None:
        return None
    return int(val)
