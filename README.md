# Unified Enterprise AI Agent

KUEA is a runnable, local-first reference implementation of a secure, domain-partitioned enterprise knowledge agent. It keeps the key architectural boundaries from the design: retrieval is isolated by domain and authorized before search; agents return a stable `AnswerPayload`; guardrails run before rendering; and rendering is separate from answering.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn services.gateway.app:app --reload
```

Open `http://localhost:8000/docs` for the API. The web client is available with `docker compose up --build` at `http://localhost:5173`.

For local development, use the `X-Dev-User`, `X-Dev-Roles`, and `X-Dev-Domains` headers. Development identity is rejected when `APP_ENV=production`; configure either internal or external OpenID Connect settings from `.env.example` instead.

## End-to-end flow

1. Ingest a document through `POST /documents` with a permitted identity.
2. Send a conversation turn to `POST /chat`.
3. Retrieval filters data by both requested domain and the caller's domain access before ranking it.
4. The orchestrator fans out, applies guardrails, persists an audit event, and returns plain text or JSON/XML/XLSX/email output.

## Important deployment decisions

The supplied plans leave the identity provider, production LLM/embedding provider, vector database, escalation system, source-system APIs, and cloud provider unspecified. This implementation deliberately does not invent live integrations. It provides a working local hybrid retrieval engine and secure OIDC configuration boundary; replacing the local repository with an approved vector/keyword provider belongs behind `services/retrieval/service.py` after those decisions are approved.

See [the architecture validation](docs/architecture-validation.md) and [the deployment guide](docs/deployment.md) before a production rollout.
