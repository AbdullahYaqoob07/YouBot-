# SaaS Enterprise Architecture V1

## 1) Architecture Goal
Build a multi-tenant AI support platform where each client:
- Brings their own LLM provider account and API key (BYOK)
- Chooses their own model (BYOM)
- Connects their own channels and knowledge sources
- Supervises conversations and takes over live at any time

This architecture keeps your current product strengths and evolves them into a reusable SaaS foundation.

## 2) Architecture Style (Decision)
Use a modular monolith first, then split into services later.

Why:
- Faster for a small team and easier for a junior engineer to understand
- Keeps one deployment unit while enforcing clean module boundaries
- Avoids premature microservice complexity

Future split path:
- Conversation Runtime Service
- Ingestion Service
- Channel Connector Service
- Billing and Metering Service

## 3) System Planes

### A. Control Plane
Owns tenant-level configuration and governance.
- Organizations
- Workspaces
- Users and roles
- LLM provider settings and encrypted API keys
- Plans, quotas, and billing settings

### B. Runtime Plane
Handles live message processing.
- LangGraph workflow execution
- LLM broker (provider-agnostic abstraction)
- Retrieval and response generation
- Human handoff and takeover logic

### C. Knowledge Plane
Handles dynamic RAG lifecycle.
- Source connectors (CSV, web scraping, files, APIs)
- Ingestion jobs and scheduling
- Chunking, embeddings, indexing
- Page-aware indexing for long-form and compliance-heavy documents
- Retrieval modes: RAG, Page Index, and Hybrid
- Knowledge curation and approvals

### D. Channel Plane
Normalizes inbound and outbound channel traffic.
- Web chat
- Social media adapters
- Messaging adapters
- Email adapters

### E. Observability Plane
Tracks reliability, usage, and governance.
- Metrics, traces, logs
- Audit events
- Token and cost telemetry
- SLO monitoring per tenant
- Client analytics dashboards (tenant-facing)
- User, team, KB, and channel performance KPIs

## 4) Core Technical Decisions

### 4.1 Multi-tenancy
- Shared database with strict tenant_id scoping on all rows
- Vector database namespace per tenant
- Cache keys prefixed with tenant_id
- Every request must resolve tenant context before business logic

### 4.2 BYOK and BYOM
- Platform does not provide shared LLM inference keys
- Tenant stores provider key encrypted at rest
- Tenant selects provider and model per workspace
- Runtime loads tenant provider config dynamically per request

### 4.3 LLM Provider Abstraction
Create one internal interface:
- chat_completion
- embeddings
- token_count
- health_check

Adapters:
- Groq adapter
- OpenAI adapter
- Gemini adapter
- Anthropic adapter

### 4.4 Dynamic RAG & Adaptive Ingestion
- Multiple source types per tenant (arbitrary formats: PDF, DOCX, CSV, HTML, raw text, APIs)
- Adaptive chunking techniques based on data format (e.g., semantic chunking, recursive character chunking, structural PDF chunking) for maximum precision and accuracy
- User-selectable retrieval modes applied at ingestion: Vector-based (chunks), Page Index, or Hybrid
- Async ingestion pipeline with job states
- Incremental sync support for changed content
- Re-index and rollback support by source version

### 4.5 Human Supervision
- Live queue by tenant and workspace
- Watch mode and takeover mode
- AI lock during human takeover
- Resume AI mode by supervisor action
- Full audit trail of interventions

### 4.6 Retrieval Modes and Recommendation Engine
Provide multiple retrieval modes and let each tenant choose per workspace.

Modes:
- RAG Mode: chunk-based retrieval for lower latency and lower token cost
- Page Index Mode: page-level retrieval and stitched page windows for full-document context tasks
- Hybrid Mode: page-level narrowing plus chunk-level retrieval for balanced quality/cost

Plan-aware capability:
- Starter: RAG Mode only
- Growth: RAG Mode + limited Page Index Mode
- Enterprise: full RAG, Page Index, and Hybrid with policy controls

Recommendation service:
- Inputs: document length, cross-page dependency score, compliance criticality, query scope, latency budget, token budget
- Output: recommended mode plus reason string and expected cost/latency impact
- UX rule: always show recommendation, but tenant admin can override

### 4.7 Tenant Analytics and Performance Intelligence
Expose tenant-facing analytics so each client can monitor performance and continuously improve.

Analytics domains:
- User performance: conversation completion rate, repeat contact rate, user sentiment trend, drop-off points
- AI performance: auto-resolution rate, handoff rate, fallback rate, confidence distribution
- Supervisor performance: first takeover response time, queue wait time, average handling time, SLA breaches
- Knowledge performance: retrieval hit rate, citation coverage, stale-content rate, unanswered-question trend
- Channel performance: response latency, resolution rate, and escalation profile by channel

Design principles:
- Every metric is tenant-scoped and workspace-aware
- Real-time tiles plus daily/weekly aggregates
- Transparent metric definitions in UI to avoid ambiguity
- Export support (CSV/API) for enterprise reporting

### 4.8 Client Integration Pathways (Channel Expansion)
To expose the chatbot to the client's end-users, the platform supports three integration pathways:
1. **Drop-in Web Widget (Easiest & Most Common):** Client embeds a lightweight JS snippet (`<script>`) on their website. It uses a Public Widget Key and makes secure CORS-enabled requests directly to our generic `/v1/chat` endpoint.
2. **Turn-Key Channel Integrations (Webhooks):** Client authorizes via OAuth (e.g., Meta for WhatsApp/Messenger, Slack). The platform registers webhooks to process inbound messages and replies directly via the channel's API.
3. **Direct API Integration:** Enterprise clients or clients with custom mobile apps (iOS/Android) use a secure Client API Key to build their own custom UIs, routing backend traffic directly to our REST API.

## 5) Data Model Additions (Minimum)
- organizations
- workspaces
- workspace_members
- llm_provider_configs
- api_key_secrets (encrypted references)
- channel_connections
- knowledge_sources
- ingestion_jobs
- documents
- document_chunks
- document_pages
- page_index_entries
- retrieval_profiles
- retrieval_recommendation_events
- model_usage_events
- conversation_metrics
- session_outcomes
- sla_events
- tenant_analytics_daily
- tenant_analytics_hourly
- audit_logs

Existing conversation and admin tables get tenant_id and workspace_id.

## 6) Request Flow (Runtime)
1. Message arrives from channel adapter
2. Resolve tenant and workspace
3. Validate channel auth and tenant quota
4. Load tenant LLM config (provider, model, key)
5. Resolve retrieval mode (workspace default, recommendation service, optional policy override)
6. Run LangGraph with tenant-aware retrieval
7. If escalation needed, route to supervision queue
8. Return response to channel
9. Emit usage and audit events asynchronously

## 7) Ingestion Flow (Dynamic Knowledge Base)
1. Tenant creates source (CSV, URL, file, raw text, API) and explicitly selects the desired retrieval mode (Vector-based, Page Index, or Hybrid).
2. Source creates ingestion job
3. Worker extracts and normalizes content robustly, handling arbitrary input data formats
4. Adaptive chunking applied based on data type (semantic, recursive, structural) and embedding generation
5. Page index extraction and page metadata generation (if Page Index or Hybrid mode is selected)
6. Write vectors and/or page index artifacts to tenant namespace based on selected mode
7. Validate retrieval quality by mode
8. Mark job complete and publish report

## 8) Security Baseline
- Encrypt all tenant API keys
- Never log raw API keys
- RBAC: owner, admin, supervisor, analyst
- Per-tenant rate limiting
- Audit log for config, key, and takeover actions
- Optional IP allowlist for enterprise tenants

## 9) Deployment Baseline
Phase 1 deployment:
- FastAPI app (modular monolith)
- Worker process for ingestion jobs
- MySQL (or Postgres), Redis, Vector DB
- Centralized logging and metrics

Phase 2 deployment:
- Kubernetes
- Horizontal workers
- Separate runtime and ingestion services
- High availability and backup strategy

## 10) Build Order (Execution Plan)

### Sprint 1: Tenant Foundation
- Add organization, workspace, membership, tenant context middleware
- Add tenant_id and workspace_id to existing core tables
- Enforce tenant scoping in all repositories

### Sprint 2: LLM Abstraction and BYOK
- Implement LLM interface and provider adapters
- Add encrypted provider key storage and model selection APIs
- Add provider connectivity tests

### Sprint 3: Dynamic RAG
- Add knowledge_sources and ingestion_jobs
- Implement CSV and web scraping connectors first
- Add re-ingestion and manual refresh
- Add Page Index Mode pipeline (document_pages and page index artifacts)
- Add first recommendation engine rules for mode selection

### Sprint 4: Channels and Supervision
- Refactor channel adapters to unified interface
- Add live supervision dashboard improvements
- Add takeover and resume controls with audit trail

### Sprint 5: Governance and Billing
- Add usage metering
- Add quota enforcement and alerts
- Integrate billing events

### Sprint 6: Tenant Analytics and Reporting
- Add analytics data mart tables and metric aggregation jobs
- Add tenant dashboards for user, AI, supervisor, KB, and channel performance
- Add CSV/API export for enterprise reporting
- Add KPI alerts for SLA risk and quality regressions

## 11) Junior-friendly Learning Path
Learn in this order:
1. Multi-tenant data isolation
2. Interface design and provider adapters
3. Async background workers and retry patterns
4. RAG ingestion and chunking strategies
5. Observability and operational excellence

This sequence lets you ship value while learning enterprise engineering patterns safely.

## 12) Definition of Done for Architecture V1
- Tenant isolation proven by tests
- Tenant can configure provider, model, and key
- Tenant can ingest and update knowledge sources
- Tenant can choose retrieval mode by plan (RAG, Page Index, Hybrid where allowed)
- System recommends retrieval mode with transparent rationale
- Tenant can connect at least two channels
- Tenant supervisors can monitor and take over conversations
- Usage and audit events are visible per tenant
- Tenant analytics dashboard is available with defined KPI glossary
- Tenant can export analytics and set alert thresholds

## 13) Retrieval Design Reference
Detailed retrieval-mode decision and rollout guidance is documented in:
- RETRIEVAL_MODES_PLAYBOOK.md

## 14) Analytics Design Reference
Detailed tenant analytics blueprint is documented in:
- TENANT_ANALYTICS_BLUEPRINT.md

## 15) Frontend Delivery Strategy
Frontend execution approach is backend-first:
1. Stabilize backend workflows and API contracts.
2. Validate end-to-end behavior with simple HTML test dashboards.
3. Build the production frontend in Next.js after contract stability.

Detailed plan is documented in:
- FRONTEND_DELIVERY_PLAN.md
