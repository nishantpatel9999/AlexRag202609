"""Stub index of the 48 golden cases reserved for a later eval pack.

These IDs are placeholders. They do not encode tickers, prices, or indicator
values. Wire real cases in a future eval pack; see docs/CORPUS.md and
docs/eval/golden_cases_stub.md.
"""

from __future__ import annotations

from alexrag.schemas.sources import CONFLICT_LABELS, GOLDEN_CASE_COUNT

# Equal split across the six first-class conflict labels (8 each = 48).
_CASES_PER_LABEL = GOLDEN_CASE_COUNT // len(CONFLICT_LABELS)


def stub_golden_cases() -> list[dict]:
    cases: list[dict] = []
    n = 1
    for label in CONFLICT_LABELS:
        for _ in range(_CASES_PER_LABEL):
            cases.append(
                {
                    "id": f"golden-{n:02d}",
                    "conflict_label": label,
                    "status": "stub",
                    "notes": "Reserved for later eval pack; not implemented in MVP.",
                }
            )
            n += 1
    return cases
