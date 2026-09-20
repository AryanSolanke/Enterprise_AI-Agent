from __future__ import annotations

from fastapi import HTTPException, status

from services.shared.models import Domain, UserContext


class AccessController:
    """Authorization is intentionally invoked by retrieval, never just the gateway."""

    def check_access(self, user: UserContext, domain: Domain) -> bool:
        return domain in user.domain_access

    def require(self, user: UserContext, domain: Domain) -> None:
        if not self.check_access(user, domain):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"The caller is not authorized for the {domain.value} domain.",
            )
