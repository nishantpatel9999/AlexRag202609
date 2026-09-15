from __future__ import annotations

from alexrag.agents.extract import combined_text, extract_size_ner_pct, extract_tickers
from alexrag.agents.audit_log import AuditLog
from alexrag.rag.retrieve import RetrievalResult
from alexrag.schemas.proposal import Citation, Proposal


class SetupAgent:
    """Stub setup agent: maps retrieved citations into Proposal fields. No invented numbers."""

    name = "setup"

    def run(
        self,
        retrieved: RetrievalResult,
        *,
        proposal: Proposal,
        audit: AuditLog,
    ) -> Proposal:
        text = combined_text(retrieved)
        tickers = extract_tickers(text)
        ner = extract_size_ner_pct(text)
        citations = [
            Citation(
                source_id=h.chunk.source_id,
                source_type=h.chunk.source_type,
                chunk_id=h.chunk.chunk_id,
                excerpt=h.chunk.text[:400],
                timestamp=h.chunk.timestamp,
                path=h.chunk.path,
                author=h.chunk.author,
            )
            for h in retrieved.hits
        ]
        proposal.tickers = tickers
        proposal.citations = citations
        proposal.retrieval_confidence = retrieved.confidence
        proposal.confidence = retrieved.confidence
        if ner is not None:
            proposal.size_ner_pct = ner
        excerpts = " | ".join(c.excerpt[:80] for c in citations[:3])
        proposal.setup_summary = excerpts
        proposal.thesis = (
            f"Setup derived only from retrieved citations ({len(citations)}). "
            "No indicator values were synthesized."
        )
        audit.emit(
            kind="setup_built",
            actor="setup",
            proposal_id=proposal.proposal_id,
            payload={
                "tickers": tickers,
                "size_ner_pct": proposal.size_ner_pct,
                "citation_count": len(citations),
            },
        )
        return proposal
