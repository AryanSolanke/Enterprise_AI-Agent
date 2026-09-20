from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from services.gateway.app import create_app
from services.shared.config import Settings


def make_client(tmp_path: Path) -> TestClient:
    app = create_app(
        Settings(
            app_env="test",
            database_url=f"sqlite:///{tmp_path / 'kuea.db'}",
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
    )
    return TestClient(app)


ADMIN_HEADERS = {
    "X-Dev-User": "knowledge-admin",
    "X-Dev-Roles": "knowledge_admin,employee",
    "X-Dev-Domains": "hr,finance,support,privacy,legal",
}


def ingest(client: TestClient, domain: str, title: str, content: str, roles: list[str] | None = None) -> str:
    response = client.post(
        "/documents",
        headers=ADMIN_HEADERS,
        json={"domain": domain, "title": title, "content": content, "allowed_roles": roles or []},
    )
    assert response.status_code == 201, response.text
    return response.json()["document_id"]


def test_authorized_retrieval_and_json_output(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    ingest(
        client,
        "hr",
        "Parental Leave Policy",
        "# Eligibility\nEligible employees receive twelve weeks of paid parental leave.",
        ["employee"],
    )
    response = client.post(
        "/chat",
        headers={"X-Dev-User": "alex", "X-Dev-Roles": "employee", "X-Dev-Domains": "hr"},
        json={"session_id": "leave-question", "message": "Explain parental leave as JSON"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["output_format"] == "json"
    assert "twelve weeks" in body["answer"].lower()
    assert body["rendered_content"]["answers"][0]["citations"][0]["document_title"] == "Parental Leave Policy"


def test_document_role_and_domain_are_enforced_before_retrieval(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    ingest(
        client,
        "finance",
        "Restricted Finance Policy",
        "# Forecast\nThe confidential finance forecast is 20 percent growth.",
        ["finance_analyst"],
    )
    unauthorized = client.post(
        "/chat",
        headers={"X-Dev-User": "alex", "X-Dev-Roles": "employee", "X-Dev-Domains": "finance"},
        json={"session_id": "finance", "message": "What does the finance forecast say?"},
    )
    assert unauthorized.status_code == 200
    assert "20 percent" not in unauthorized.json()["answer"]
    authorized = client.post(
        "/chat",
        headers={"X-Dev-User": "pat", "X-Dev-Roles": "finance_analyst", "X-Dev-Domains": "finance"},
        json={"session_id": "finance", "message": "What does the finance forecast say?"},
    )
    assert authorized.status_code == 200
    assert "20 percent" in authorized.json()["answer"]


def test_xlsx_artifacts_are_owned_and_privacy_is_escalated(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    ingest(client, "support", "Warranty", "# Warranty\nThe warranty period is five years.")
    headers = {"X-Dev-User": "sam", "X-Dev-Roles": "employee", "X-Dev-Domains": "support"}
    response = client.post(
        "/chat",
        headers=headers,
        json={"session_id": "warranty", "message": "Create an Excel file with the warranty details"},
    )
    assert response.status_code == 200
    artifact = response.json()["artifact"]
    assert artifact["filename"].endswith(".xlsx")
    assert client.get(artifact["download_url"], headers=headers).status_code == 200
    assert client.get(
        artifact["download_url"],
        headers={"X-Dev-User": "other", "X-Dev-Roles": "employee", "X-Dev-Domains": "support"},
    ).status_code == 404

    ingest(client, "privacy", "Privacy Policy", "# Requests\nPrivacy requests are reviewed within 30 days.")
    privacy = client.post(
        "/chat",
        headers={"X-Dev-User": "customer", "X-Dev-External": "true", "X-Dev-Domains": "privacy"},
        json={"session_id": "privacy", "message": "How are privacy requests handled?"},
    )
    assert privacy.status_code == 200
    assert privacy.json()["escalation"] is not None
