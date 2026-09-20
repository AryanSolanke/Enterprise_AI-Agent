"""Stable, versioned contracts shared across every KUEA boundary."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Domain(StrEnum):
    HR = "hr"
    FINANCE = "finance"
    SUPPORT = "support"
    PRIVACY = "privacy"
    LEGAL = "legal"


HIGH_RISK_DOMAINS = {Domain.PRIVACY, Domain.LEGAL}


class OutputFormat(StrEnum):
    CHAT = "chat"
    JSON = "json"
    XML = "xml"
    XLSX = "xlsx"
    EMAIL = "email"


class Citation(BaseModel):
    document_id: str
    document_title: str
    chunk_id: str
    excerpt: str
    effective_date: date | None = None
    jurisdiction: str | None = None
    section: str | None = None


class SourceMetadata(BaseModel):
    retrieved_at: datetime
    document_versions: dict[str, str] = Field(default_factory=dict)
    retrieval_scores: dict[str, float] = Field(default_factory=dict)


class AnswerPayload(BaseModel):
    """v1 contract between domain agents, guardrails, and renderers."""

    model_config = ConfigDict(extra="forbid")
    answer_text: str = Field(min_length=1)
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    domain: Domain
    needs_human_review: bool = False
    source_metadata: SourceMetadata
    guardrail_notes: list[str] = Field(default_factory=list)


class UserContext(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    roles: set[str] = Field(default_factory=set)
    domain_access: set[Domain] = Field(default_factory=set)
    session_id: str = Field(min_length=1, max_length=255)
    is_external: bool = False


class OutputRequest(BaseModel):
    target_format: OutputFormat = OutputFormat.CHAT
    schema_override: dict[str, Any] | None = None
    tone: str | None = Field(default=None, max_length=40)
    recipient_hint: str | None = Field(default=None, max_length=255)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12_000)
    session_id: str = Field(min_length=1, max_length=255)
    output: OutputRequest | None = None


class DocumentCreate(BaseModel):
    domain: Domain
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=2_000_000)
    version: str = Field(default="1", max_length=100)
    effective_date: date | None = None
    jurisdiction: str | None = Field(default=None, max_length=120)
    allowed_roles: set[str] = Field(default_factory=set)
    document_id: str | None = None

    @field_validator("content")
    @classmethod
    def reject_instruction_only_documents(cls, value: str) -> str:
        if len(value.strip()) < 10:
            raise ValueError("document content is too short to be useful knowledge")
        return value


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    domain: Domain
    content: str
    version: str
    effective_date: date | None
    jurisdiction: str | None
    score: float
    section: str | None = None


class RenderedArtifact(BaseModel):
    filename: str
    media_type: str
    download_url: str


class EscalationTicket(BaseModel):
    ticket_id: str
    reason: str
    domains: list[Domain]
    created_at: datetime


class ChatResponse(BaseModel):
    answer: str
    payloads: list[AnswerPayload]
    output_format: OutputFormat
    rendered_content: Any | None = None
    artifact: RenderedArtifact | None = None
    escalation: EscalationTicket | None = None
    session_id: str
    cache_hit: bool = False
