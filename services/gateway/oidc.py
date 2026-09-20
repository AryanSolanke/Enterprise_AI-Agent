"""Generic OIDC authorization-code flow using discovery and PKCE.

An enterprise must supply registered issuer/client/redirect settings before these routes are enabled.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import HTTPException, status
from fastapi import Request as FastAPIRequest
from fastapi.responses import RedirectResponse

from services.shared.models import Domain, UserContext
from services.shared.policy import RolePolicyStore


@dataclass(frozen=True)
class OidcConfig:
    issuer: str | None
    client_id: str | None
    client_secret: str | None
    redirect_uri: str | None
    external: bool = False

    @property
    def configured(self) -> bool:
        return all((self.issuer, self.client_id, self.client_secret, self.redirect_uri))


def _json_request(url: str, data: bytes | None = None) -> dict:
    request = Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urlopen(request, timeout=10) as response:  # noqa: S310 - URL comes from operator config.
        return json.loads(response.read())


class OidcFlow:
    def __init__(self, config: OidcConfig, policies: RolePolicyStore):
        self.config = config
        self.policies = policies

    def start(self, request: FastAPIRequest) -> RedirectResponse:
        if not self.config.configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OIDC is not configured for this audience.",
            )
        metadata = _json_request(f"{self.config.issuer.rstrip('/')}/.well-known/openid-configuration")
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        request.session["oidc"] = {
            "state": state,
            "verifier": verifier,
            "metadata": metadata,
            "external": self.config.external,
        }
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.config.client_id,
                "redirect_uri": self.config.redirect_uri,
                "scope": "openid profile email",
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return RedirectResponse(f"{metadata['authorization_endpoint']}?{query}")

    def callback(self, request: FastAPIRequest, code: str, state: str) -> UserContext:
        flow = request.session.pop("oidc", None)
        if not flow or not secrets.compare_digest(flow["state"], state):
            raise HTTPException(status_code=400, detail="Invalid or expired OIDC state.")
        payload = urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.config.redirect_uri,
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "code_verifier": flow["verifier"],
            }
        ).encode()
        tokens = _json_request(flow["metadata"]["token_endpoint"], payload)
        # Fetch userinfo with the issued bearer token, not a token embedded in a caller request.

        bearer = Request(
            flow["metadata"]["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        with urlopen(bearer, timeout=10) as response:  # noqa: S310
            userinfo = json.loads(response.read())
        roles = set(userinfo.get("roles", userinfo.get("groups", [])))
        is_external = bool(flow["external"])
        domains = {Domain.SUPPORT, Domain.PRIVACY} if is_external else self.policies.domains_for_roles(roles)
        return UserContext(
            user_id=str(userinfo.get("sub") or userinfo.get("email")),
            roles=roles,
            domain_access=domains,
            session_id="oidc",
            is_external=is_external,
        )
