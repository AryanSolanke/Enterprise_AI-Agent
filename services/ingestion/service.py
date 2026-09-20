from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime

from services.shared.db import Database
from services.shared.models import DocumentCreate

_INJECTION = re.compile(
    r"(?im)^\s*(ignore|disregard|override|system\s+message|developer\s+message|assistant)\b.*$"
)
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


def sanitize_untrusted_content(content: str) -> str:
    """Index source material as data, stripping directive-like lines and direct identifiers."""
    content = _INJECTION.sub("[untrusted instruction removed]", content)
    content = _SSN.sub("[redacted-ssn]", content)
    return _EMAIL.sub("[redacted-email]", content)


def semantic_chunks(content: str, maximum_characters: int = 1_200) -> list[tuple[str | None, str]]:
    """Preserve Markdown-like headings while keeping retrieval units bounded."""
    sections = re.split(r"(?m)^(#{1,6}\s+.+)$", content)
    result: list[tuple[str | None, str]] = []
    active_heading: str | None = None
    for part in sections:
        part = part.strip()
        if not part:
            continue
        if part.startswith("#"):
            active_heading = part.lstrip("#").strip()
            continue
        paragraphs = re.split(r"\n\s*\n", part)
        buffer = ""
        for paragraph in paragraphs:
            candidate = (buffer + "\n\n" + paragraph).strip()
            if buffer and len(candidate) > maximum_characters:
                result.append((active_heading, buffer))
                buffer = paragraph
            else:
                buffer = candidate
        if buffer:
            result.append((active_heading, buffer))
    return result or [(None, content[:maximum_characters])]


class IngestionService:
    def __init__(self, database: Database):
        self.database = database

    def ingest(self, document: DocumentCreate) -> tuple[str, int]:
        source_key = document.document_id or str(uuid.uuid4())
        storage_id = f"{source_key}::{document.version}::{uuid.uuid4().hex[:8]}"
        clean_content = sanitize_untrusted_content(document.content)
        chunks = semantic_chunks(clean_content)
        now = datetime.now(UTC).isoformat()
        with self.database.connect() as db:
            # Historical revisions remain retained, but only the newest supplied revision is retrieved.
            db.execute("UPDATE documents SET is_current = 0 WHERE id LIKE ?", (f"{source_key}::%",))
            db.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
                (
                    storage_id,
                    document.domain.value,
                    document.title,
                    clean_content,
                    document.version,
                    document.effective_date.isoformat() if document.effective_date else None,
                    document.jurisdiction,
                    json.dumps(sorted(document.allowed_roles)),
                    now,
                ),
            )
            db.executemany(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?)",
                [
                    (str(uuid.uuid4()), storage_id, ordinal, section, content)
                    for ordinal, (section, content) in enumerate(chunks)
                ],
            )
        return storage_id, len(chunks)
