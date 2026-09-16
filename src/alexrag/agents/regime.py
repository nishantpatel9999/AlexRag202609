from __future__ import annotations

from alexrag.agents.extract import combined_text, extract_regime
from alexrag.agents.audit_log import AuditLog
from alexrag.rag.retrieve import RetrievalResult


class RegimeAgent:
    """Stub regime classifier: copies labels that already appear in retrieved text."""

    name = "regime"

    def run(self, retrieved: RetrievalResult, audit: AuditLog, proposal_id: str) -> str:
        text = combined_text(retrieved)
        regime = extract_regime(text)
        audit.emit(
            kind="regime_classified",
            actor="regime",
            proposal_id=proposal_id,
            payload={"regime": regime, "from_citations_only": True},
        )
        return regime
