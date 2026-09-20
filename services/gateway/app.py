from __future__ import annotations

import json

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from services.formatting_engine.service import FormattingError, FormattingService
from services.gateway.oidc import OidcConfig, OidcFlow
from services.ingestion.service import IngestionService
from services.orchestrator.service import Orchestrator
from services.retrieval.service import RetrievalService
from services.shared.access import AccessController
from services.shared.artifacts import ArtifactAccess
from services.shared.audit import AuditLog
from services.shared.auth import current_user
from services.shared.config import Settings
from services.shared.db import Database
from services.shared.memory import SessionMemory
from services.shared.models import ChatRequest, ChatResponse, DocumentCreate, Domain, UserContext
from services.shared.policy import RolePolicyStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    database = Database(settings.database_path)
    database.initialize()
    policies = RolePolicyStore(database)
    policies.initialize()
    artifacts = ArtifactAccess(database, settings.artifact_dir)
    artifacts.initialize()
    retrieval = RetrievalService(database, AccessController())
    orchestrator = Orchestrator(
        database=database,
        retrieval=retrieval,
        formatter=FormattingService(settings.artifact_dir),
        audit=AuditLog(database),
        memory=SessionMemory(database),
    )
    ingestion = IngestionService(database)
    internal_oidc = OidcFlow(
        OidcConfig(
            settings.oidc_issuer_url,
            settings.oidc_client_id,
            settings.oidc_client_secret,
            settings.oidc_redirect_uri,
        ),
        policies,
    )
    external_oidc = OidcFlow(
        OidcConfig(
            settings.external_oidc_issuer_url,
            settings.external_oidc_client_id,
            settings.external_oidc_client_secret,
            settings.external_oidc_redirect_uri,
            external=True,
        ),
        policies,
    )

    app = FastAPI(title="Kohler Unified Enterprise AI Agent", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "X-Dev-User", "X-Dev-Roles", "X-Dev-Domains", "X-Dev-External"],
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_token_secret,
        https_only=settings.app_env == "production",
        same_site="lax",
    )
    app.state.settings = settings
    app.state.database = database
    app.state.policies = policies
    app.state.artifacts = artifacts


    @app.get("/health")
    async def health() -> dict[str, str]:
        try:
            with database.connect() as db:
                db.execute("SELECT 1")
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connectivity check failed.",
            ) from err
        return {"status": "ok", "service": "kuea-gateway"}

    @app.get("/auth/login")
    async def login(request: Request) -> Response:
        return internal_oidc.start(request)

    @app.get("/auth/external/login")
    async def external_login(request: Request) -> Response:
        return external_oidc.start(request)

    @app.get("/auth/callback")
    async def auth_callback(request: Request, code: str, state: str) -> Response:
        active = external_oidc if request.session.get("oidc", {}).get("external") else internal_oidc
        principal = active.callback(request, code, state)
        request.session["user"] = principal.model_dump(mode="json")
        return RedirectResponse("/")

    @app.post("/auth/logout")
    async def logout(request: Request) -> dict[str, str]:
        request.session.clear()
        return {"status": "logged_out"}

    @app.get("/session/validate", response_model=UserContext)
    async def validate_session(user: UserContext = Depends(current_user)) -> UserContext:
        return user

    @app.post("/documents", status_code=status.HTTP_201_CREATED)
    async def ingest_document(
        document: DocumentCreate, user: UserContext = Depends(current_user)
    ) -> dict[str, object]:
        policies.require_administrator(user)
        AccessController().require(user, document.domain)
        document_id, chunks = ingestion.ingest(document)
        AuditLog(database).record(
            user, "document_ingested", {"document_id": document_id, "domain": document.domain.value}
        )
        return {"document_id": document_id, "chunk_count": chunks}

    @app.post("/documents/upload", status_code=status.HTTP_201_CREATED)
    async def upload_document(
        file: UploadFile = File(...),
        domain: Domain = Form(...),
        title: str = Form(None),
        allowed_roles: str = Form(""),
        user: UserContext = Depends(current_user)
    ) -> dict[str, object]:
        policies.require_administrator(user)
        AccessController().require(user, domain)
        
        from services.ingestion.parsers import extract_text_from_upload
        try:
            extracted_text = await extract_text_from_upload(file)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")
            
        doc_title = title or file.filename or "Uploaded Document"
        roles_set = {r.strip() for r in allowed_roles.split(",") if r.strip()}
        
        document = DocumentCreate(
            domain=domain,
            title=doc_title,
            content=extracted_text,
            allowed_roles=roles_set
        )
        
        document_id, chunks = ingestion.ingest(document)
        AuditLog(database).record(
            user, "document_uploaded", {"document_id": document_id, "domain": domain.value, "filename": file.filename}
        )
        return {"document_id": document_id, "chunk_count": chunks}

    @app.get("/documents")
    async def list_documents(
        domain: str | None = None,
        user: UserContext = Depends(current_user),
    ) -> list[dict[str, object]]:
        policies.require_administrator(user)
        with database.connect() as db:
            if domain:
                rows = db.execute(
                    "SELECT id, domain, title, version, effective_date, jurisdiction, is_current, created_at "
                    "FROM documents WHERE domain = ? ORDER BY created_at DESC",
                    (domain,),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT id, domain, title, version, effective_date, jurisdiction, is_current, created_at "
                    "FROM documents ORDER BY created_at DESC"
                ).fetchall()
        return [
            {
                "id": row["id"],
                "domain": row["domain"],
                "title": row["title"],
                "version": row["version"],
                "effective_date": row["effective_date"],
                "jurisdiction": row["jurisdiction"],
                "is_current": bool(row["is_current"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @app.delete("/documents/{document_id}", status_code=status.HTTP_200_OK)
    async def archive_document(
        document_id: str, user: UserContext = Depends(current_user)
    ) -> dict[str, object]:
        policies.require_administrator(user)
        with database.connect() as db:
            row = db.execute("SELECT id FROM documents WHERE id = ?", (document_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Document not found.")
            db.execute("UPDATE documents SET is_current = 0 WHERE id = ?", (document_id,))
        AuditLog(database).record(
            user, "document_archived", {"document_id": document_id}
        )
        return {"document_id": document_id, "archived": True}

    @app.post("/chat", response_model=ChatResponse)
    async def chat(chat_request: ChatRequest, user: UserContext = Depends(current_user)) -> ChatResponse:
        try:
            response = await orchestrator.respond(chat_request, user)
        except FormattingError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if response.artifact:
            artifacts.grant(response.artifact.filename, user)
        return response

    @app.get("/artifacts/{filename}")
    async def download_artifact(filename: str, user: UserContext = Depends(current_user)) -> FileResponse:
        path = artifacts.resolve(filename, user)
        return FileResponse(path, filename=path.name)

    @app.put("/admin/roles/{role}")
    async def set_role_domains(
        role: str, domains: set[Domain], user: UserContext = Depends(current_user)
    ) -> dict[str, object]:
        if "access_admin" not in user.roles and "admin" not in user.roles:
            raise HTTPException(status_code=403, detail="Access administrator role required.")
        policies.set_domains(role, domains)
        AuditLog(database).record(
            user, "role_policy_updated", {"role": role, "domains": sorted(domain.value for domain in domains)}
        )
        return {"role": role, "domains": sorted(domain.value for domain in domains)}

    @app.get("/escalations")
    async def list_escalations(
        status_filter: str | None = None,
        user: UserContext = Depends(current_user),
    ) -> list[dict[str, object]]:
        if "admin" not in user.roles and "audit_admin" not in user.roles:
            raise HTTPException(status_code=403, detail="Administrator role required.")
        with database.connect() as db:
            if status_filter:
                rows = db.execute(
                    "SELECT id, user_id, session_id, domains_json, reason, status, created_at "
                    "FROM escalations WHERE status = ? ORDER BY created_at DESC",
                    (status_filter,),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT id, user_id, session_id, domains_json, reason, status, created_at "
                    "FROM escalations ORDER BY created_at DESC"
                ).fetchall()
        return [
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "session_id": row["session_id"],
                "domains": json.loads(row["domains_json"]),
                "reason": row["reason"],
                "status": row["status"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @app.put("/escalations/{ticket_id}")
    async def resolve_escalation(
        ticket_id: str,
        resolution: dict[str, str],
        user: UserContext = Depends(current_user),
    ) -> dict[str, object]:
        if "admin" not in user.roles and "audit_admin" not in user.roles:
            raise HTTPException(status_code=403, detail="Administrator role required.")
        new_status = resolution.get("status", "resolved")
        if new_status not in {"resolved", "dismissed", "in_progress"}:
            raise HTTPException(status_code=422, detail="Status must be 'resolved', 'dismissed', or 'in_progress'.")
        with database.connect() as db:
            row = db.execute("SELECT id FROM escalations WHERE id = ?", (ticket_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Escalation ticket not found.")
            db.execute("UPDATE escalations SET status = ? WHERE id = ?", (new_status, ticket_id))
        AuditLog(database).record(
            user, "escalation_updated", {"ticket_id": ticket_id, "new_status": new_status}
        )
        return {"ticket_id": ticket_id, "status": new_status}

    @app.get("/audit/session/{session_id}")
    async def audit_for_session(
        session_id: str, user: UserContext = Depends(current_user)
    ) -> list[dict[str, object]]:
        if "audit_admin" not in user.roles and "admin" not in user.roles:
            raise HTTPException(status_code=403, detail="Audit administrator role required.")
        scoped = SessionMemory.scoped_session_id(user.user_id, session_id)
        with database.connect() as db:
            rows = db.execute(
                "SELECT event_type, details_json, created_at FROM audit_events WHERE session_id = ? ORDER BY created_at",
                (scoped,),
            ).fetchall()
        return [
            {"event_type": row["event_type"], "details": json.loads(row["details_json"]), "created_at": row["created_at"]}
            for row in rows
        ]

    return app


app = create_app()
