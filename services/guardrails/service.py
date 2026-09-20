from __future__ import annotations

import re

from services.shared.models import HIGH_RISK_DOMAINS, AnswerPayload, UserContext

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d .()-]{7,}\d)(?!\d)")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_HIGH_STAKES = re.compile(r"\b(termination|litigation|lawsuit|data breach|breach notification)\b", re.I)


def _redact_pii(text: str) -> str:
    text = _EMAIL.sub("[redacted-email]", text)
    text = _PHONE.sub("[redacted-phone]", text)
    return _SSN.sub("[redacted-ssn]", text)


class GuardrailService:
    def apply(self, payload: AnswerPayload, user: UserContext, query: str) -> AnswerPayload:
        notes = list(payload.guardrail_notes)
        answer = payload.answer_text
        if not payload.citations:
            notes.append("No supporting citation was retrieved; response requires human review.")
        if user.is_external:
            redacted = _redact_pii(answer)
            if redacted != answer:
                notes.append("PII was redacted for an external response.")
                answer = redacted
        if payload.domain in HIGH_RISK_DOMAINS:
            notes.append("High-risk domain response is informational and requires specialist review.")
        if _HIGH_STAKES.search(query):
            notes.append("High-stakes query requires human escalation.")
        requires_review = (
            payload.needs_human_review
            or not payload.citations
            or payload.domain in HIGH_RISK_DOMAINS
            or bool(_HIGH_STAKES.search(query))
        )
        return payload.model_copy(
            update={"answer_text": answer, "needs_human_review": requires_review, "guardrail_notes": notes}
        )
