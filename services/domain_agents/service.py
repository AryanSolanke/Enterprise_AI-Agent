from __future__ import annotations

import re
from datetime import UTC, datetime

from services.shared.models import (
    HIGH_RISK_DOMAINS,
    AnswerPayload,
    Citation,
    Domain,
    RetrievedChunk,
    SourceMetadata,
)

PROMPT_INTENT = {
    Domain.HR: "Answer from HR policy sources. Cite the policy and effective date.",
    Domain.FINANCE: "Answer from finance guidelines. Do not provide personalized financial advice.",
    Domain.SUPPORT: "Answer from approved support knowledge. Use a helpful, practical tone.",
    Domain.PRIVACY: "Answer from privacy sources. Do not make binding compliance determinations.",
    Domain.LEGAL: "Answer from legal sources. Do not issue binding legal advice; cite section names.",
}


def _sentences(content: str, maximum: int = 2) -> str:
    pieces = re.split(r"(?<=[.!?])\s+", content.strip())
    return " ".join(piece.strip() for piece in pieces[:maximum] if piece.strip())


class DomainAgent:
    """A provider-neutral, extractive agent that never answers outside retrieved context."""

    def __init__(self, domain: Domain):
        self.domain = domain
        self.prompt = PROMPT_INTENT[domain]
        self.review_threshold = 0.72 if domain in HIGH_RISK_DOMAINS else 0.48

    def answer(self, chunks: list[RetrievedChunk]) -> AnswerPayload:
        if not chunks:
            return AnswerPayload(
                answer_text=(
                    f"I could not find an authorized, current {self.domain.value} source for this question."
                ),
                citations=[],
                confidence=0.0,
                domain=self.domain,
                needs_human_review=self.domain in HIGH_RISK_DOMAINS,
                source_metadata=SourceMetadata(retrieved_at=datetime.now(UTC)),
            )
        selected = chunks[:3]
        citations = [
            Citation(
                document_id=chunk.document_id,
                document_title=chunk.document_title,
                chunk_id=chunk.chunk_id,
                excerpt=chunk.content[:600],
                effective_date=chunk.effective_date,
                jurisdiction=chunk.jurisdiction,
                section=chunk.section,
            )
            for chunk in selected
        ]
        confidence = min(0.98, sum(chunk.score for chunk in selected) / len(selected) + 0.25)
        answer_text = "\n\n".join(_sentences(chunk.content) for chunk in selected)
        return AnswerPayload(
            answer_text=answer_text,
            citations=citations,
            confidence=round(confidence, 2),
            domain=self.domain,
            needs_human_review=confidence < self.review_threshold,
            source_metadata=SourceMetadata(
                retrieved_at=datetime.now(UTC),
                document_versions={chunk.document_id: chunk.version for chunk in selected},
                retrieval_scores={chunk.chunk_id: chunk.score for chunk in selected},
            ),
        )


def configured_agents() -> dict[Domain, DomainAgent]:
    return {domain: DomainAgent(domain) for domain in Domain}
