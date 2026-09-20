from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import date

from services.shared.access import AccessController
from services.shared.db import Database
from services.shared.models import Domain, RetrievedChunk, UserContext

TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]{1,}", re.IGNORECASE)


def tokens(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


def hashed_vector(text: str, dimensions: int = 128) -> list[float]:
    vector = [0.0] * dimensions
    for token in tokens(text):
        vector[hash(token) % dimensions] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


class RetrievalService:
    def __init__(self, database: Database, access: AccessController):
        self.database = database
        self.access = access

    def retrieve(
        self, query: str, domain: Domain, user: UserContext, limit: int = 5
    ) -> list[RetrievedChunk]:
        self.access.require(user, domain)
        with self.database.connect() as db:
            rows = db.execute(
                """
                SELECT chunks.id AS chunk_id, chunks.content AS chunk_content, chunks.section,
                       documents.id AS document_id, documents.title, documents.domain,
                       documents.version, documents.effective_date, documents.jurisdiction,
                       documents.allowed_roles_json
                FROM chunks JOIN documents ON chunks.document_id = documents.id
                WHERE documents.domain = ? AND documents.is_current = 1
                """,
                (domain.value,),
            ).fetchall()
        allowed_rows = []
        for row in rows:
            allowed_roles = set(json.loads(row["allowed_roles_json"]))
            if not allowed_roles or allowed_roles.intersection(user.roles):
                allowed_rows.append(row)
        if not allowed_rows:
            return []

        query_terms = Counter(tokens(query))
        document_frequency = Counter(
            token for row in allowed_rows for token in set(tokens(row["chunk_content"]))
        )
        query_vector = hashed_vector(query)
        scored: list[tuple[float, object]] = []
        total = len(allowed_rows)
        for row in allowed_rows:
            chunk_terms = Counter(tokens(row["chunk_content"]))
            length = max(sum(chunk_terms.values()), 1)
            keyword_score = sum(
                query_count
                * (math.log((total + 1) / (document_frequency[term] + 1)) + 1)
                * (chunk_terms[term] / length)
                for term, query_count in query_terms.items()
            )
            vector_score = cosine(query_vector, hashed_vector(row["chunk_content"]))
            scored.append((0.65 * vector_score + 0.35 * min(keyword_score, 1.0), row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            RetrievedChunk(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                document_title=row["title"],
                domain=Domain(row["domain"]),
                content=row["chunk_content"],
                version=row["version"],
                effective_date=date.fromisoformat(row["effective_date"]) if row["effective_date"] else None,
                jurisdiction=row["jurisdiction"],
                score=round(score, 4),
                section=row["section"],
            )
            for score, row in scored[:limit]
            if score > 0
        ]
