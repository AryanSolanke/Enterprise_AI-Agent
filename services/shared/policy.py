from __future__ import annotations

import json

from fastapi import HTTPException, status

from services.shared.db import Database
from services.shared.models import Domain, UserContext


class RolePolicyStore:
    """Durable role-to-domain policy table used to resolve production OIDC roles."""

    def __init__(self, database: Database):
        self.database = database

    def initialize(self) -> None:
        with self.database.connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS role_domain_policies (
                    role TEXT PRIMARY KEY, domains_json TEXT NOT NULL
                )
                """
            )

    def set_domains(self, role: str, domains: set[Domain]) -> None:
        with self.database.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO role_domain_policies VALUES (?, ?)",
                (role, json.dumps(sorted(domain.value for domain in domains))),
            )

    def domains_for_roles(self, roles: set[str]) -> set[Domain]:
        if not roles:
            return set()
        placeholders = ",".join("?" for _ in roles)
        with self.database.connect() as db:
            rows = db.execute(
                f"SELECT domains_json FROM role_domain_policies WHERE role IN ({placeholders})",
                tuple(roles),
            ).fetchall()
        return {Domain(domain) for row in rows for domain in json.loads(row["domains_json"])}

    def require_administrator(self, user: UserContext) -> None:
        if not {"admin", "access_admin", "knowledge_admin"}.intersection(user.roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required.")
