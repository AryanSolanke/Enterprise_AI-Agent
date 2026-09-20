"""Authentication boundary with a safe development mode.

Production deployments must populate request.state.user from a validated OIDC callback.
Development headers are deliberately unavailable outside development/test.
"""

from __future__ import annotations

from fastapi import Header, HTTPException, Request, status

from services.shared.config import Settings
from services.shared.models import Domain, UserContext

EXTERNAL_DOMAINS = {Domain.SUPPORT, Domain.PRIVACY}


def _parse_csv(value: str | None) -> set[str]:
    return {part.strip() for part in (value or "").split(",") if part.strip()}


async def current_user(
    request: Request,
    x_dev_user: str | None = Header(default=None),
    x_dev_roles: str | None = Header(default="employee"),
    x_dev_domains: str | None = Header(default=None),
    x_dev_external: str | None = Header(default="false"),
) -> UserContext:
    """Get a validated production principal or an explicitly development-only principal."""
    stored_principal = request.session.get("user")
    if stored_principal is not None:
        return UserContext.model_validate(stored_principal)

    settings: Settings = request.app.state.settings
    if not settings.development_identity_enabled or not x_dev_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required. Configure OIDC or use development headers locally.",
        )
    try:
        domains = {Domain(domain) for domain in _parse_csv(x_dev_domains)}
    except ValueError as error:
        raise HTTPException(status_code=422, detail="X-Dev-Domains contains an unknown domain") from error
    is_external = x_dev_external.lower() == "true"
    if is_external:
        domains &= EXTERNAL_DOMAINS
    return UserContext(
        user_id=x_dev_user,
        roles=_parse_csv(x_dev_roles),
        domain_access=domains,
        session_id="request",
        is_external=is_external,
    )
