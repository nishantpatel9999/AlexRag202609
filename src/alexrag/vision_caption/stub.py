"""Vision caption stub. Real model lives on Mac Studio later."""

from __future__ import annotations

from pathlib import Path


def caption_image(path: Path | str) -> str:
    """Return a placeholder caption.

    TODO: vision model (local VLM on Mac Studio). Do not call network APIs from MVP.
    """

    name = Path(path).name
    return f"[VISION_STUB] TODO vision model caption for {name}"


def caption_paths(paths: list[str]) -> list[str]:
    return [caption_image(p) for p in paths]
