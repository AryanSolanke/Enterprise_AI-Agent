from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from services.shared.db import Database
from services.shared.models import Domain, EscalationTicket, UserContext


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class AuditLog:
    def __init__(self, database: Database):
        self.database = database

    def record(self, user: UserContext, event_type: str, details: dict[str, Any]) -> None:
        with self.database.connect() as db:
            db.execute(
                "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), user.user_id, user.session_id, event_type, json.dumps(details), utc_now()),
            )

    def create_escalation(
        self, user: UserContext, domains: list[Domain], reason: str
    ) -> EscalationTicket:
        ticket_id = str(uuid.uuid4())
        created_at = datetime.now(UTC)
        with self.database.connect() as db:
            db.execute(
                "INSERT INTO escalations VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    ticket_id,
                    user.user_id,
                    user.session_id,
                    json.dumps([domain.value for domain in domains]),
                    reason,
                    "open",
                    created_at.isoformat(),
                ),
            )
        return EscalationTicket(
            ticket_id=ticket_id, reason=reason, domains=domains, created_at=created_at
        )
