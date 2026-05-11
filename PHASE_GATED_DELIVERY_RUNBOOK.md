# Phase-Gated Delivery Runbook

## Workflow Rule
Complete one phase at a time:
1. Implement phase scope.
2. Run validation and tests.
3. Mark phase as pass/fail.
4. Move to next phase only after pass.

## Phase 0: Baseline Snapshot
Goal: verify current system baseline before changes.

Validation commands:
- pytest tests -q
- python -m compileall .
- Manual API smoke: /health, /webhook/ai-agent, /admin/queue

Exit criteria:
- Existing tests pass.
- No syntax errors.
- Core endpoints respond.

## Phase 1: Tenant Foundation
Goal: introduce tenant/workspace context and scoped reads/writes.

Scope:
- Tenant context resolver and request plumbing
- tenant_id and workspace_id in workflow state
- tenant/workspace scoping in core database operations
- Initial tenant/workspace schema entities

Validation commands:
- Apply migration: mysql -u <user> -p <db_name> < phase1_tenant_foundation.sql
- pytest tests/test_tenant_context.py -q
- pytest tests/test_nodes.py -q
- python -m compileall .

Manual verification:
- POST /webhook/ai-agent with X-Tenant-Id and X-Workspace-Id
- GET /chat/{session_id}/history with same headers
- GET /admin/queue with same headers

Exit criteria:
- Migration applies successfully.
- Tenant context tests pass.
- Existing node tests still pass.
- Endpoints work with tenant headers and defaults.

## Phase 2: BYOK and BYOM
Goal: tenant-configurable provider/model/key.

Scope:
- Provider abstraction layer
- Workspace provider/model config
- Encrypted API key references

Validation commands:
- Apply migration: mysql -u <user> -p <db_name> < phase2_llm_provider_config.sql
- pytest tests/test_secret_crypto.py tests/test_llm_factory.py -q
- python -m compileall app.py database llm utils nodes
- Manual API checks:
	- POST /admin/workspaces/{workspace_id}/llm-config
	- GET /admin/workspaces/{workspace_id}/llm-config
	- POST /webhook/ai-agent (ensure model_used reflects selected provider:model)

Exit criteria:
- Tenant can set provider/model/key.
- Runtime uses tenant-selected provider.
- API keys are encrypted before DB persistence.

## Phase 3: Dynamic KB and Retrieval Modes
Goal: ingestion workflows and retrieval mode routing.

Scope:
- Source connectors (CSV and scraping first)
- ingestion_jobs pipeline
- RAG/Page Index/Hybrid routing
- Recommendation service V1

Validation commands:
- Ingestion integration tests
- Retrieval mode routing tests
- Cost and latency comparison checks

Exit criteria:
- Tenant can update KB and see ingestion status.
- Retrieval mode selection and recommendation work.

## Phase 4: Supervision and Channels
Goal: production-quality handoff and multi-channel support.

Scope:
- Unified channel adapter abstraction
- Live supervision improvements
- Tenant-scoped takeover and release flows

Validation commands:
- pytest tests/test_phase4_supervision_channels.py -q
- pytest tests/test_nodes.py -q
- python -m compileall app.py database nodes
- Manual frontend checks:
	- Open /phase4/supervision-validation
	- Validate channel acceptance and invalid channel rejection via /webhook/ai-agent
	- Validate supervision flow: list -> detail -> takeover -> message -> release

Exit criteria:
- Supervisors can monitor and take over safely.
- Channel messages are normalized and reliable.

## Phase 5: Analytics and Governance
Goal: tenant-facing analytics and operational controls.

Scope:
- KPI endpoints and aggregations
- Alerts and exports
- Usage and quota governance

Validation commands:
- pytest tests/test_phase5_analytics_endpoints.py tests/test_phase5_analytics_jobs.py -q
- python -m compileall app.py database
- Manual frontend checks:
	- Open /phase5/analytics-validation
	- Validate overview, user, AI, team, KB, and channel cards
	- Validate CSV export and alerts (create rule, list events)
	- Validate usage and quota governance cards (usage snapshot and quota forecast)
- Manual API checks:
	- GET /tenant-analytics/user-performance
	- GET /tenant-analytics/kb-performance
	- GET /tenant-analytics/export.csv
	- POST /tenant-analytics/alerts/rules
	- GET /tenant-analytics/alerts/events
	- GET /tenant-analytics/governance/usage
	- GET /tenant-analytics/governance/quota

Exit criteria:
- Tenants can monitor user, AI, team, KB, and channel performance.
- Exports, alerts, and governance visibility work as expected.
