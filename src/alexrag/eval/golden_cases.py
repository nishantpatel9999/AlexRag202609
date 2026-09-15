"""Golden-case pack loader. Canonical data is eval/golden_cases_v0.json."""

from __future__ import annotations

from pathlib import Path

from alexrag.eval.harness import GoldenPack, load_golden_pack
from alexrag.schemas.sources import GOLDEN_CASE_COUNT


def stub_golden_cases() -> list[dict]:
    """Compatibility helper: 48 cases from the V0 pack."""

    pack = load_golden_pack()
    return [c.model_dump(mode="json") for c in pack.cases]


def golden_pack_path() -> Path:
    from alexrag.eval.harness import DEFAULT_PACK

    return DEFAULT_PACK


__all__ = ["GOLDEN_CASE_COUNT", "GoldenPack", "load_golden_pack", "stub_golden_cases", "golden_pack_path"]
