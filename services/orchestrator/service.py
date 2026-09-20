from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta

from services.domain_agents.service import DomainAgent, configured_agents
from services.formatting_engine.service import FormattingService
from services.guardrails.service import GuardrailService
from services.retrieval.service import RetrievalService
from services.shared.audit import AuditLog
from services.shared.db import Database
from services.shared.memory import SessionMemory
from services.shared.models import (
    ChatRequest,
    ChatResponse,
    Domain,
    OutputFormat,
    OutputRequest,
    UserContext,
)

DOMAIN_TERMS = {
    Domain.HR: {"leave", "pto", "benefits", "employee", "payroll", "hiring", "manager"},
    Domain.FINANCE: {"finance", "budget", "expense", "invoice", "reimbursement", "payout"},
    Domain.SUPPORT: {"support", "product", "warranty", "order", "repair", "customer", "troubleshoot"},
    Domain.PRIVACY: {"privacy", "personal data", "gdpr", "ccpa", "delete my data", "consent"},
    Domain.LEGAL: {"legal", "contract", "compliance", "litigation", "clause", "regulation"},
}


class ResponseCache:
    def __init__(self, database: Database):
        self.database = database

    def get(self, key: str) -> ChatResponse | None:
        now = datetime.now(UTC).isoformat()
        with self.database.connect() as db:
            row = db.execute(
                "SELECT response_json FROM response_cache WHERE cache_key = ? AND expires_at > ?",
                (key, now),
            ).fetchone()
        return ChatResponse.model_validate_json(row["response_json"]) if row else None

    def put(self, key: str, response: ChatResponse, ttl_minutes: int = 10) -> None:
        expiry = (datetime.now(UTC) + timedelta(minutes=ttl_minutes)).isoformat()
        now = datetime.now(UTC).isoformat()
        with self.database.connect() as db:
            db.execute("DELETE FROM response_cache WHERE expires_at <= ?", (now,))
            db.execute(
                "INSERT OR REPLACE INTO response_cache VALUES (?, ?, ?)",
                (key, response.model_dump_json(), expiry),
            )


class Orchestrator:
    def __init__(
        self,
        database: Database,
        retrieval: RetrievalService,
        formatter: FormattingService,
        audit: AuditLog,
        memory: SessionMemory,
    ):
        self.database = database
        self.retrieval = retrieval
        self.formatter = formatter
        self.audit = audit
        self.memory = memory
        self.agents: dict[Domain, DomainAgent] = configured_agents()
        self.guardrails = GuardrailService()
        self.cache = ResponseCache(database)

    @staticmethod
    def classify_domains(message: str, permitted: set[Domain]) -> list[Domain]:
        lowered = message.lower()
        hits = [
            domain
            for domain, terms in DOMAIN_TERMS.items()
            if domain in permitted and any(term in lowered for term in terms)
        ]
        if hits:
            return hits
        return [Domain.SUPPORT] if Domain.SUPPORT in permitted else []

    @staticmethod
    def detect_output(message: str, requested: OutputRequest | None) -> OutputRequest:
        if requested is not None:
            return requested
        lowered = message.lower()
        # Inference is intentionally conservative; ordinary references to audit do not force a format.
        if " as json" in lowered or "json format" in lowered:
            return OutputRequest(target_format=OutputFormat.JSON)
        if " as xml" in lowered or "xml format" in lowered:
            return OutputRequest(target_format=OutputFormat.XML)
        if any(phrase in lowered for phrase in ("excel file", "spreadsheet", "xlsx")):
            return OutputRequest(target_format=OutputFormat.XLSX)
        if any(phrase in lowered for phrase in ("draft an email", "email draft", "send this to")):
            return OutputRequest(target_format=OutputFormat.EMAIL)
        return OutputRequest()

    def _document_fingerprint(self, domains: list[Domain], user: UserContext) -> str:
        visible: list[str] = []
        with self.database.connect() as db:
            for domain in domains:
                rows = db.execute(
                    "SELECT id, version, allowed_roles_json FROM documents WHERE domain = ? AND is_current = 1",
                    (domain.value,),
                ).fetchall()
                for row in rows:
                    roles = set(json.loads(row["allowed_roles_json"]))
                    if not roles or roles.intersection(user.roles):
                        visible.append(f"{row['id']}:{row['version']}")
        return hashlib.sha256("|".join(sorted(visible)).encode()).hexdigest()

    async def respond(self, request: ChatRequest, user: UserContext) -> ChatResponse:
        scoped_session = self.memory.scoped_session_id(user.user_id, request.session_id)
        user = user.model_copy(update={"session_id": scoped_session})
        output = self.detect_output(request.message, request.output)
        domains = self.classify_domains(request.message, user.domain_access)
        if not domains:
            answer = "Please specify an authorized topic, such as customer support or privacy."
            self.memory.append(scoped_session, "user", request.message)
            self.memory.append(scoped_session, "assistant", answer)
            return ChatResponse(
                answer=answer,
                payloads=[],
                output_format=OutputFormat.CHAT,
                session_id=request.session_id,
            )
        fingerprint = self._document_fingerprint(domains, user)
        key_material = {
            "user": user.user_id,
            "roles": sorted(user.roles),
            "domains": [domain.value for domain in domains],
            "session": request.session_id,
            "message": request.message,
            "output": output.model_dump(mode="json"),
            "document_versions": fingerprint,
        }
        cache_key = hashlib.sha256(json.dumps(key_material, sort_keys=True).encode()).hexdigest()
        cached = self.cache.get(cache_key)
        if cached:
            cached = cached.model_copy(update={"cache_hit": True, "session_id": request.session_id})
            self.audit.record(user, "chat_cache_hit", {"domains": [domain.value for domain in domains]})
            return cached

        self.memory.append(scoped_session, "user", request.message)
        retrievals = await asyncio.gather(
            *[
                asyncio.to_thread(self.retrieval.retrieve, request.message, domain, user)
                for domain in domains
            ]
        )
        payloads = [
            self.guardrails.apply(self.agents[domain].answer(chunks), user, request.message)
            for domain, chunks in zip(domains, retrievals, strict=True)
        ]
        sections = [f"{payload.domain.value.title()}: {payload.answer_text}" for payload in payloads]
        answer = "\n\n".join(sections)
        review_payloads = [payload for payload in payloads if payload.needs_human_review]
        escalation = None
        if review_payloads:
            escalation = self.audit.create_escalation(
                user,
                [payload.domain for payload in review_payloads],
                "; ".join(note for payload in review_payloads for note in payload.guardrail_notes)
                or "Confidence threshold requires review.",
            )
        rendered_content, artifact = self.formatter.render(payloads, output)
        response = ChatResponse(
            answer=answer,
            payloads=payloads,
            output_format=output.target_format,
            rendered_content=rendered_content,
            artifact=artifact,
            escalation=escalation,
            session_id=request.session_id,
        )
        self.memory.append(scoped_session, "assistant", answer)
        self.audit.record(
            user,
            "chat_completed",
            {
                "domains": [domain.value for domain in domains],
                "sources": [citation.document_id for payload in payloads for citation in payload.citations],
                "output_format": output.target_format.value,
                "escalated": escalation is not None,
            },
        )
        # Escalated answers are deliberately not shared from cache: each event must reach its queue.
        if escalation is None:
            self.cache.put(cache_key, response)
        return response
