from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, domain TEXT NOT NULL, title TEXT NOT NULL,
                    content TEXT NOT NULL, version TEXT NOT NULL, effective_date TEXT,
                    jurisdiction TEXT, allowed_roles_json TEXT NOT NULL,
                    is_current INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_documents_domain_current
                    ON documents(domain, is_current);
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
                    ordinal INTEGER NOT NULL, section TEXT, content TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, summary TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS turns (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                    actor TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, created_at);
                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL, details_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_events(session_id, created_at);
                CREATE TABLE IF NOT EXISTS escalations (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, session_id TEXT NOT NULL,
                    domains_json TEXT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS response_cache (
                    cache_key TEXT PRIMARY KEY, response_json TEXT NOT NULL, expires_at TEXT NOT NULL
                );
                """
            )
