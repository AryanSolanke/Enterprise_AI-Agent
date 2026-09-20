from __future__ import annotations

import uuid
from datetime import UTC, datetime

from services.shared.db import Database


class SessionMemory:
    """SQLite-backed rolling memory; session keys are isolated per authenticated user."""

    def __init__(self, database: Database, max_recent_turns: int = 12):
        self.database = database
        self.max_recent_turns = max_recent_turns

    @staticmethod
    def scoped_session_id(user_id: str, supplied_session_id: str) -> str:
        return f"{user_id}:{supplied_session_id}"

    def context(self, session_id: str) -> str:
        with self.database.connect() as db:
            session = db.execute("SELECT summary FROM sessions WHERE id = ?", (session_id,)).fetchone()
            turns = db.execute(
                "SELECT actor, content FROM turns WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, self.max_recent_turns),
            ).fetchall()
        recent = "\n".join(f"{row['actor']}: {row['content']}" for row in reversed(turns))
        return "\n".join(part for part in [session["summary"] if session else "", recent] if part)

    def append(self, session_id: str, actor: str, content: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self.database.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO sessions(id, summary, updated_at) VALUES (?, '', ?)",
                (session_id, now),
            )
            db.execute(
                "INSERT INTO turns VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), session_id, actor, content, now),
            )
            count = db.execute("SELECT COUNT(*) FROM turns WHERE session_id = ?", (session_id,)).fetchone()[0]
            if count > self.max_recent_turns:
                oldest = db.execute(
                    "SELECT id, actor, content FROM turns WHERE session_id = ? ORDER BY created_at LIMIT ?",
                    (session_id, count - self.max_recent_turns),
                ).fetchall()
                existing = db.execute("SELECT summary FROM sessions WHERE id = ?", (session_id,)).fetchone()[0]
                additions = " ".join(f"{row['actor']}: {row['content'][:240]}" for row in oldest)
                db.execute(
                    "UPDATE sessions SET summary = ?, updated_at = ? WHERE id = ?",
                    ((existing + " " + additions).strip()[-4000:], now, session_id),
                )
                db.executemany("DELETE FROM turns WHERE id = ?", [(row["id"],) for row in oldest])
