"""Shared test fixtures for UEAA integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.gateway.app import create_app
from services.shared.config import Settings


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'ueaa.db'}",
        artifact_dir=tmp_path / "artifacts",
        session_token_secret="test-secret",
        oidc_issuer_url=None,
        oidc_client_id=None,
        oidc_client_secret=None,
        oidc_redirect_uri=None,
        external_oidc_issuer_url=None,
        external_oidc_client_id=None,
        external_oidc_client_secret=None,
        external_oidc_redirect_uri=None,
    )


@pytest.fixture()
def client(settings: Settings) -> TestClient:
    app = create_app(settings)
    return TestClient(app)


ADMIN_HEADERS = {
    "X-Dev-User": "knowledge-admin",
    "X-Dev-Roles": "knowledge_admin,employee",
    "X-Dev-Domains": "hr,finance,support,privacy,legal",
}

EMPLOYEE_HEADERS = {
    "X-Dev-User": "alex",
    "X-Dev-Roles": "employee",
    "X-Dev-Domains": "hr,finance,support,privacy,legal",
}

EXTERNAL_HEADERS = {
    "X-Dev-User": "external-customer",
    "X-Dev-External": "true",
    "X-Dev-Domains": "support,privacy",
}


def ingest(
    client: TestClient,
    domain: str,
    title: str,
    content: str,
    roles: list[str] | None = None,
    version: str = "1",
    document_id: str | None = None,
) -> str:
    """Ingest a document and return its storage id."""
    payload: dict = {
        "domain": domain,
        "title": title,
        "content": content,
        "allowed_roles": roles or [],
        "version": version,
    }
    if document_id is not None:
        payload["document_id"] = document_id
    response = client.post("/documents", headers=ADMIN_HEADERS, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["document_id"]
