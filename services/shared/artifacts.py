from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, status

from services.shared.db import Database
from services.shared.models import UserContext


class ArtifactAccess:
    def __init__(self, database: Database, artifact_dir: Path):
        self.database = database
        self.artifact_dir = artifact_dir

    def initialize(self) -> None:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        with self.database.connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS artifact_access (
                    filename TEXT PRIMARY KEY, user_id TEXT NOT NULL, session_id TEXT NOT NULL
                )
                """
            )

    def grant(self, filename: str, user: UserContext) -> None:
        with self.database.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO artifact_access VALUES (?, ?, ?)",
                (filename, user.user_id, user.session_id),
            )

    def resolve(self, filename: str, user: UserContext) -> Path:
        if Path(filename).name != filename:
            raise HTTPException(status_code=404, detail="Artifact not found")
        with self.database.connect() as db:
            row = db.execute("SELECT user_id FROM artifact_access WHERE filename = ?", (filename,)).fetchone()
        path = self.artifact_dir / filename
        if not row or row["user_id"] != user.user_id or not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
        return path
