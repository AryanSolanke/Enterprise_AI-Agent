from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    artifact_dir: Path
    session_token_secret: str
    oidc_issuer_url: str | None
    oidc_client_id: str | None
    oidc_client_secret: str | None
    oidc_redirect_uri: str | None
    external_oidc_issuer_url: str | None
    external_oidc_client_id: str | None
    external_oidc_client_secret: str | None
    external_oidc_redirect_uri: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_env=os.getenv("APP_ENV", "development").lower(),
            database_url=os.getenv("DATABASE_URL", "sqlite:///./data/ueaa.db"),
            artifact_dir=Path(os.getenv("ARTIFACT_DIR", "./artifacts")),
            session_token_secret=os.getenv("SESSION_TOKEN_SECRET", "development-only-change-me"),
            oidc_issuer_url=os.getenv("OIDC_ISSUER_URL") or None,
            oidc_client_id=os.getenv("OIDC_CLIENT_ID") or None,
            oidc_client_secret=os.getenv("OIDC_CLIENT_SECRET") or None,
            oidc_redirect_uri=os.getenv("OIDC_REDIRECT_URI") or None,
            external_oidc_issuer_url=os.getenv("EXTERNAL_OIDC_ISSUER_URL") or None,
            external_oidc_client_id=os.getenv("EXTERNAL_OIDC_CLIENT_ID") or None,
            external_oidc_client_secret=os.getenv("EXTERNAL_OIDC_CLIENT_SECRET") or None,
            external_oidc_redirect_uri=os.getenv("EXTERNAL_OIDC_REDIRECT_URI") or None,
        )

    @property
    def database_path(self) -> Path:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            raise ValueError("This reference implementation requires a sqlite:/// DATABASE_URL")
        return Path(self.database_url.removeprefix(prefix))

    @property
    def development_identity_enabled(self) -> bool:
        return self.app_env in {"development", "test"}
