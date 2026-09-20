# Architecture and implementation-plan validation

## What was validated

The repository was empty apart from its Git metadata. There was no existing application architecture, framework, configuration, database schema, API, or coding convention to conflict with the plans. The system design's essential decisions are retained: per-domain knowledge isolation, retrieval-time authorization, a contract between answering and rendering, shared guardrails, auditability, and human escalation.

## Corrections applied before implementation

| Plan assumption | Validated implementation decision | Reason |
| --- | --- | --- |
| Separate deployable services on day one | One deployable FastAPI application with explicit service modules | No cloud, provider, or operational ownership was supplied. This keeps boundaries testable without a distributed-system tax. |
| Pinecone/Weaviate plus OpenSearch | Local SQLite repository with token BM25-like scoring and deterministic vector similarity | Neither database was approved or configured. The interface is isolated so an approved provider can replace it without changing authorization or agents. |
| OIDC/SAML and external OAuth | Generic OIDC configuration boundary plus development-only signed identity headers | IdP metadata, client registrations, redirect URIs, and issuer policies are required for a real login flow. SAML is unnecessary if OIDC is approved. |
| Anthropic-based reasoning | Grounded extractive answer generation | A model credential/provider was not supplied. Extractive generation ensures runnable behavior and avoids ungrounded claims until an approved LLM adapter is configured. |
| ServiceNow/Zendesk escalation | Durable local escalation records | The system of record is explicitly undecided. Tickets are persisted and exposed through the API for a later adapter. |
| Cloud provisioning and HPA | Container, CI, and Terraform-ready configuration documented as a deployment handoff | A cloud account/provider and network policy are required before infrastructure can be provisioned safely. |

## Plan issues that remain stakeholder decisions

- Select and approve the identity, LLM/embedding, vector/keyword, escalation, source-system, and cloud providers.
- Define domain-specific retention, data residency, encryption-key, and legal review policies.
- Obtain curated, owner-approved knowledge and domain-expert golden datasets before production answers are trusted.
- Confirm whether output-format inference may be enabled by default; the implementation is intentionally conservative and defaults to chat.

These are external implementation prerequisites, not TODOs hidden in application behavior. The delivered application is usable locally with manual document ingestion and is structured for these integrations.
