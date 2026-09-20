# Kohler Unified Enterprise AI Agent — Coding Implementation Plan

This plan translates the system design document into an actionable, dependency-ordered engineering roadmap. It does not contain code — it specifies what to build, in what order, with what tools, and how to verify each piece.

---

## 1. Analysis Summary — Key Components Identified

From the design document, the system decomposes into these buildable units:

1. **Interface Layer** — web chat, internal bot (Teams/Slack), external customer portal/mobile.
2. **API Gateway & Auth** — SSO (internal, SAML/OIDC) and OAuth (external), session/rate limiting.
3. **Orchestrator Agent** — intent/domain classifier, multi-turn context manager, domain router, output-intent detector.
4. **Domain Specialist Agents** — 5 RAG agents (HR, Finance, Customer Support, Privacy, Legal/Compliance), each producing a structured `AnswerPayload`.
5. **Retrieval Layer** — per-domain hybrid (vector + keyword) indexes with access-control metadata.
6. **Knowledge Ingestion Pipeline** — per-source connectors, chunking, embedding, indexing, versioning.
7. **Guardrail / Compliance Filter** — hallucination check, PII redaction, escalation logic.
8. **Output Formatting Engine** — JSON, XML, XLSX, email draft renderers with schema validation.
9. **Response Assembler & Delivery** — bundles response + files, logs to audit trail.
10. **Security & Governance** — RBAC enforcement, encryption, prompt-injection defense, audit logging, human escalation queue.
11. **Scalability infrastructure** — caching, async job processing, multi-region considerations, monitoring.

**Notable dependencies / complex areas flagged for special attention:**
- RBAC must be enforced at the **retrieval/index level**, not just in prompts — this has architectural implications for how indexes are structured from day one.
- The `AnswerPayload` schema is the contract between Domain Agents, the Guardrail Filter, and the Output Formatting Engine — it should be finalized **before** those three modules are built in parallel.
- The Output-Intent Detector (inferring "email me this" vs. explicit "give me JSON") requires early UX/prompt-engineering iteration and should not be treated as a trivial classifier.
- Confidence-based human escalation requires a queue/ticketing integration decision early, since Domain Agents, Guardrail Filter, and Interface Layer all touch it.

**Open questions to clarify with stakeholders before/while building:**
- Which vector DB is approved for enterprise use (Pinecone, Weaviate, pgvector, Azure AI Search)?
- Which LLM provider/model(s) are approved, and are there separate models for classification vs. reasoning vs. legal-sensitive answers?
- What is the system of record for human escalation (ServiceNow, Zendesk, internal ticketing)?
- What identity provider does Kohler use for SSO (Azure AD, Okta, etc.)?
- Are there existing source systems/APIs for HRIS, finance policy repo, legal DMS, support CRM, privacy CMS, or will ingestion start from flat file exports?

---

## 2. Recommended Technology Stack (proposed, pending confirmation)

| Layer | Technology |
|---|---|
| Backend services | Python 3.11+, FastAPI |
| Orchestration/agent framework | LangGraph or a custom lightweight agent loop over the Anthropic Messages API (tool use / function calling) |
| LLM | Claude (small/fast model for classification & routing; larger model for reasoning and legal/compliance-sensitive answers) |
| Vector DB | Pinecone or Weaviate (per-domain namespaces/collections) |
| Keyword/hybrid search | OpenSearch/Elasticsearch (BM25) alongside vector DB |
| Session/context store | Redis |
| Relational store (metadata, audit logs, user/role mapping) | PostgreSQL |
| Async job queue | Celery or RQ with Redis/RabbitMQ broker |
| XLSX generation | pandas + openpyxl |
| XML generation/validation | lxml + xmlschema |
| Auth | SAML/OIDC (internal SSO), OAuth2 (external customers) |
| Internal bot channels | Slack Bolt SDK, Microsoft Bot Framework (Teams) |
| Frontend (web chat/portal) | React + TypeScript |
| CI/CD | GitHub Actions |
| Infra as Code | Terraform |
| Containerization/orchestration | Docker, Kubernetes |
| Monitoring/observability | Prometheus + Grafana, OpenTelemetry tracing, structured logging (e.g., ELK stack) |
| Testing | pytest, pytest-asyncio, Postman/Newman or httpx for API tests, Locust for load testing |

---

## 3. Prioritized Implementation Steps

### Phase 0 — Foundations

**Step 1: Environment & Repository Setup**
- **Module/Component:** Project scaffolding & DevOps foundation
- **Tasks:**
  - Set up monorepo (or multi-repo) structure: `/services/orchestrator`, `/services/domain-agents`, `/services/ingestion`, `/services/formatting-engine`, `/services/gateway`, `/frontend`.
  - Configure Docker Compose for local dev (Postgres, Redis, vector DB emulator/local instance).
  - Set up CI pipeline: lint, type-check, unit test, build, on every PR.
  - Provision cloud environments (dev/staging/prod) via Terraform.
  - Configure secrets management (e.g., AWS Secrets Manager/Vault) for API keys, DB credentials.
- **Technologies:** Docker, Docker Compose, GitHub Actions, Terraform, Vault/Secrets Manager
- **Dependencies:** None (first step)
- **Deliverables:** Working local dev environment (`docker-compose up` runs all stub services), CI pipeline green on an empty commit, provisioned dev cloud environment.
- **Tests:** CI smoke test (services start and respond to health checks).

**Step 2: Core Data Schemas & Contracts**
- **Module/Component:** Shared schema definitions
- **Tasks:**
  - Define the `AnswerPayload` schema (answer_text, citations[], confidence, domain, needs_human_review, source_metadata).
  - Define the user/session/role schema (user_id, roles[], domain_access[], session_id).
  - Define the `OutputRequest` schema (target_format, schema_override, tone, recipient_hint).
  - Publish these as a shared library/package (e.g., Pydantic models) consumed by all services.
- **Technologies:** Python, Pydantic, JSON Schema
- **Dependencies:** Step 1
- **Deliverables:** A shared `schemas` package versioned and importable by all services.
- **Tests:** Schema validation unit tests (valid/invalid payload fixtures).

---

### Phase 1 — Identity, Access & Gateway

**Step 3: API Gateway & Authentication**
- **Module/Component:** API Gateway & Auth
- **Tasks:**
  - Implement internal SSO integration (SAML/OIDC) issuing internal session tokens with role/domain claims.
  - Implement external OAuth2 flow for customer accounts, mapped only to Customer Support + public Privacy domain.
  - Implement rate limiting and per-session quotas.
  - Implement request routing to the Orchestrator service.
- **Technologies:** FastAPI, OIDC/SAML libraries (e.g., `authlib`), Redis (rate limiting)
- **Dependencies:** Step 1, Step 2
- **Deliverables:** `/auth/login`, `/auth/callback`, `/session/validate` endpoints; middleware that attaches role/domain claims to every downstream request.
- **Tests:** Auth flow integration tests (mock IdP), unauthorized-access rejection tests, rate-limit enforcement tests.

**Step 4: RBAC Enforcement Layer**
- **Module/Component:** Access Control
- **Tasks:**
  - Design role → domain-access mapping table in PostgreSQL.
  - Build a policy-check function/service used by the Retrieval Layer (not just the gateway) to filter index queries by allowed domains.
  - Build admin tooling (CLI or simple internal UI) to manage role-to-domain mappings.
- **Technologies:** PostgreSQL, Python
- **Dependencies:** Step 3
- **Deliverables:** `check_access(user, domain) -> bool` service/library used by all Domain Specialist Agents.
- **Tests:** Access-denied and access-granted unit tests across all role/domain combinations.

---

### Phase 2 — Knowledge Ingestion & Retrieval

**Step 5: Knowledge Ingestion Pipeline (per domain)**
- **Module/Component:** Ingestion Pipeline
- **Tasks:**
  - Build source connectors for each domain (HRIS export, finance policy repo, legal DMS, support KB/CRM, privacy CMS) — start with flat-file/manual upload connector if live APIs aren't yet available.
  - Implement semantic chunking (respecting section/clause boundaries, especially for Legal).
  - Implement embedding generation and upsert into per-domain vector DB namespace.
  - Attach metadata: document version, effective date, jurisdiction, access-control tags.
  - Implement a scheduled + event-triggered re-ingestion mechanism.
- **Technologies:** Python, embedding model API, Pinecone/Weaviate SDK, Celery (scheduled jobs)
- **Dependencies:** Step 2
- **Deliverables:** `ingest(document, domain)` pipeline callable per domain; five populated (at least with sample data) vector indexes.
- **Tests:** Chunking correctness tests, end-to-end ingestion test (raw doc → queryable chunk), stale-version exclusion test.

**Step 6: Retrieval Layer (hybrid search)**
- **Module/Component:** Retrieval Service
- **Tasks:**
  - Implement per-domain hybrid retrieval: vector similarity + BM25 keyword search, merged/re-ranked.
  - Implement metadata filtering (exclude superseded document versions).
  - Integrate RBAC check from Step 4 before returning any results.
- **Technologies:** Pinecone/Weaviate, OpenSearch/Elasticsearch, Python
- **Dependencies:** Step 4, Step 5
- **Deliverables:** `retrieve(query, domain, user) -> List[Chunk]` service with a REST/internal API.
- **Tests:** Retrieval relevance tests (known-query/known-answer fixtures per domain), RBAC-filtering tests, superseded-document exclusion tests.

---

### Phase 3 — Reasoning Agents

**Step 7: Domain Specialist Agents (HR, Finance, Support, Privacy, Legal/Compliance)**
- **Module/Component:** Domain Agents (5 instances of a shared agent framework)
- **Tasks:**
  - Build a shared `DomainAgent` base class: takes a query + retrieved chunks, produces an `AnswerPayload`.
  - Write domain-specific prompt templates (citation style per domain, e.g., legal clause citation vs. HR policy name/date).
  - Implement confidence scoring logic.
  - Implement `needs_human_review` flagging based on confidence threshold (stricter thresholds for Legal/Privacy).
- **Technologies:** Python, Anthropic Messages API (tool/function calling), Pydantic
- **Dependencies:** Step 6, Step 2
- **Deliverables:** Five configured `DomainAgent` instances, each independently callable and testable; per-domain prompt template files.
- **Tests:** Golden-set Q&A tests per domain (known question → expected grounded answer + citation), low-confidence escalation trigger tests, hallucination spot-check tests (answer must map to retrieved citations).

**Step 8: Orchestrator Agent**
- **Module/Component:** Orchestrator
- **Tasks:**
  - Build Intent & Domain Classifier (fast/small model) — supports multi-domain tagging.
  - Build Context Manager: session-based turn history in Redis + rolling summarization once token budget is exceeded.
  - Build Domain Router: dispatches to one or more Domain Agents in parallel, merges results.
  - Build Output-Intent Detector: explicit keyword detection + inferred intent from conversational cues, with clarifying-question fallback for ambiguous cases.
- **Technologies:** Python, Anthropic API, Redis, LangGraph (optional) or custom async orchestration
- **Dependencies:** Step 7
- **Deliverables:** `/chat` endpoint accepting a user turn and returning a merged, routed response; conversation state persisted across turns.
- **Tests:** Multi-turn coherence tests, multi-domain fan-out tests, context-summarization correctness tests, clarifying-question trigger tests for ambiguous input.

**Step 9: Guardrail / Compliance Filter**
- **Module/Component:** Guardrail Filter
- **Tasks:**
  - Implement hallucination check: verify claims in `answer_text` are supported by `citations`.
  - Implement PII detection/redaction for both retrieved content and generated answers (stricter for external-facing responses).
  - Implement disallowed-content checks (e.g., binding legal opinions) with a rewrite-or-block response.
  - Wire escalation: low-confidence or high-risk payloads routed to a human queue (system TBD — Step "open questions").
- **Technologies:** Python, PII detection library (e.g., Presidio), Anthropic API for secondary verification pass
- **Dependencies:** Step 7
- **Deliverables:** `apply_guardrails(payload, user_context) -> payload | escalation_ticket` function used by the Orchestrator before formatting.
- **Tests:** Hallucination-detection tests (payload with fabricated claim should be caught), PII-redaction tests, escalation-trigger tests.

---

### Phase 4 — Output & Delivery

**Step 10: Output Formatting Engine**
- **Module/Component:** Formatting Engine
- **Tasks:**
  - Build JSON renderer + schema validator (supports user-supplied schema override).
  - Build XML renderer + XSD validation.
  - Build XLSX renderer: `AnswerPayload`(s) → pandas DataFrame → styled workbook, supporting multi-sheet output.
  - Build Email Draft Composer: tone-aware templates (formal for Legal/HR, friendly for Support), subject line generation, "AI-drafted, please review" marker.
  - Implement a validation/retry loop: malformed output triggers automatic regeneration before being returned.
- **Technologies:** Python, pandas, openpyxl, lxml, xmlschema, Jinja2 (email templates)
- **Dependencies:** Step 2 (schemas), Step 8 (Output-Intent Detector output)
- **Deliverables:** `format_output(payload, output_request) -> RenderedResponse` with support for all four target formats.
- **Tests:** Schema-validity tests per format, malformed-input retry tests, snapshot tests for XLSX/email templates.

**Step 11: Response Assembler & Delivery**
- **Module/Component:** Response Assembler
- **Tasks:**
  - Bundle conversational text + citations + generated file(s) into a single response object.
  - Implement async file generation path for large exports (job queue + "your file is ready" notification).
  - Log full exchange (query, retrieved sources, guardrail decisions, final response) to the audit trail (Postgres/ELK).
- **Technologies:** Python, Celery, PostgreSQL/ELK
- **Dependencies:** Step 9, Step 10
- **Deliverables:** Final `/chat` response contract delivered to the Interface Layer; audit log entries per exchange.
- **Tests:** End-to-end response-bundling tests, async-job completion tests, audit-log completeness tests.

---

### Phase 5 — Interfaces

**Step 12: Interface Layer**
- **Module/Component:** Web chat, internal bot, customer portal
- **Tasks:**
  - Build React web chat UI: message thread, file/attachment rendering, format-selection affordance.
  - Integrate Slack Bolt app / Teams bot for internal users.
  - Build/extend customer-facing portal chat widget for external users (scoped to allowed domains).
  - Implement "open in Outlook/Gmail" action for email drafts; "download" action for XLSX/JSON/XML.
- **Technologies:** React, TypeScript, Slack Bolt SDK, Microsoft Bot Framework
- **Dependencies:** Step 11
- **Deliverables:** Deployed web chat and at least one internal bot channel; customer portal integration.
- **Tests:** UI component tests, end-to-end Cypress/Playwright tests covering a full chat-to-file-download flow.

---

### Phase 6 — Hardening, Scale & Launch Readiness

**Step 13: Security Hardening**
- **Tasks:** Prompt-injection defense (treat retrieved content as untrusted, strip embedded instructions), encryption in transit/at rest, penetration test pass, review of external-facing redaction rules.
- **Technologies:** Standard security tooling, manual + automated pen-test
- **Dependencies:** All prior steps
- **Deliverables:** Security review sign-off document, injection-resistance test suite.

**Step 14: Performance, Caching & Scaling**
- **Tasks:** Implement answer-level caching (keyed to query + document version) with TTL; load-test the Orchestrator and Retrieval Layer; configure horizontal autoscaling per service; validate model-routing cost/performance split (small model for classification, large for reasoning/legal).
- **Technologies:** Redis (cache), Kubernetes HPA, Locust (load testing)
- **Dependencies:** Steps 8–11
- **Deliverables:** Load test report, autoscaling configuration, cache-hit-rate dashboard.

**Step 15: Observability & Monitoring**
- **Tasks:** Instrument tracing across orchestrator → domain agent → retrieval → formatter; build dashboards for latency, error rate, escalation volume, cost per query; set up alerting.
- **Technologies:** OpenTelemetry, Prometheus, Grafana
- **Dependencies:** All services deployed
- **Deliverables:** Live monitoring dashboards, alert rules.

**Step 16: UAT & Staged Rollout**
- **Tasks:** Internal pilot with a small HR/Finance user group; collect accuracy/UX feedback; expand to Legal/Privacy (higher-risk domains) only after escalation and guardrail behavior is validated; external Customer Support rollout last.
- **Deliverables:** UAT feedback report, go/no-go checklist per domain, phased rollout schedule.

---

## 4. High-Level Timeline (indicative, adjust to team size)

| Phase | Focus | Approx. Duration |
|---|---|---|
| Phase 0 | Foundations & schemas | 1–2 weeks |
| Phase 1 | Auth & RBAC | 1–2 weeks |
| Phase 2 | Ingestion & Retrieval | 2–3 weeks |
| Phase 3 | Domain Agents, Orchestrator, Guardrails | 3–4 weeks |
| Phase 4 | Output Formatting & Delivery | 2 weeks |
| Phase 5 | Interfaces | 2–3 weeks |
| Phase 6 | Hardening, scale, UAT, rollout | 2–3 weeks |

Phases 2–4 have internal parallelization opportunities (e.g., Domain Agents for different domains can be built by different engineers concurrently once Step 6 is stable).

---

## 5. Potential Challenges and Considerations

- **RBAC-at-retrieval is non-negotiable but easy to under-build.** If access control is only checked at the gateway/prompt level, a cleverly worded query can still leak cross-domain data through retrieval. Build and test index-level filtering before any Domain Agent goes live.
- **`AnswerPayload` schema churn.** Because three major modules (Domain Agents, Guardrail Filter, Formatting Engine) all depend on this contract, changing it mid-build has a high blast radius. Freeze v1 early and version it explicitly if it must change.
- **Confidence scoring is subjective.** Calibrating what counts as "low confidence enough to escalate" will need iteration against real user queries and stakeholder risk tolerance, especially for Legal/Privacy.
- **Multi-domain query merging** (e.g., a question spanning HR and Finance) risks producing a disjointed answer if the Orchestrator naively concatenates two Domain Agent outputs — plan for a dedicated merge/synthesis prompt, not simple concatenation.
- **Output-Intent inference** is a UX risk: inferring the wrong format (or failing to infer one at all) is more damaging to trust than simply always asking. Start conservative (default to plain chat + offer format options) and tune inference over time based on usage data.
- **Human escalation system integration** is an external dependency (ServiceNow/Zendesk/etc.) that should be identified early — it affects the Guardrail Filter and Interface Layer designs.
- **Ingestion source availability.** If HRIS/legal DMS/CRM systems don't have ready APIs, the ingestion pipeline may need to start with manual document uploads, which affects freshness guarantees and should be flagged to stakeholders.
- **Cost management.** Multi-agent fan-out (potentially 5 domain agents + orchestrator + guardrail + formatter per turn) can multiply LLM calls; the model-routing strategy (small model for classification/routing, large model reserved for final reasoning) is important to implement early, not as a later optimization.
- **Testing high-risk domains is harder than testing generic RAG.** Legal/Privacy/Finance answers need domain-expert-reviewed golden test sets, not just automated relevance scoring — budget time with actual HR/Legal/Finance stakeholders to build and periodically refresh these test sets.
