
# YouBot Business Integration Runbook

## 1. Goal
This runbook helps you verify the actual backend implementation and integrate YouBot safely into business operations before committing to a frontend stack.

## 2. Integration Modes
YouBot currently supports three practical integration pathways:

1. Drop-in web widget or custom client UI
- Endpoint: POST /v1/chat
- Auth: X-API-Key using a client key created from admin APIs

2. Existing backend or workflow integration
- Endpoint: POST /webhook/ai-agent
- Auth: X-API-Key (platform API key)
- Tenant context: X-Tenant-Id and X-Workspace-Id headers

3. Operations and governance controls
- Endpoints: /admin/* and /tenant-analytics/*
- Auth: X-Admin-Key

## 3. Minimum Go-Live Prerequisites
1. Health endpoint stable
- GET /health returns healthy or known degraded reason with remediation plan

2. Tenant and workspace scoping enforced
- All test calls include X-Tenant-Id and X-Workspace-Id
- Data read/write is isolated to intended tenant/workspace

3. Auth keys validated
- Admin key works for admin and analytics endpoints
- Client key works for /v1/chat
- Platform API key works for /webhook/ai-agent if used

4. Supervision path works
- Admin can list and inspect supervised conversations
- Takeover and release path is operational

5. Analytics and governance path works
- Overview, user, AI, KB, channel, and team analytics return data shape
- Governance usage and quota endpoints return utilization and forecast

## 4. Verify Actual Implementation (No Next.js Needed)
Use either of these:

1. HTML verifier page
- Open: /static/saas_readiness_verifier.html
- File: langgraph_agent/static/saas_readiness_verifier.html
- Run Core Smoke first, then Full SaaS Smoke

2. Scripted readiness audit
- File: langgraph_agent/tools/business_readiness_audit.py
- Produces JSON report for internal sign-off and CI checks

## 5. Core Endpoint Checklist

### Platform
- GET /health
- GET /metrics (optional monitoring validation)

### Runtime and supervision
- GET /admin/retrieval/profile
- POST /admin/retrieval/recommend
- GET /admin/supervision/conversations

### Chat surface
- POST /v1/chat (client-key path)
- POST /webhook/ai-agent (platform-key path)

### Analytics and governance
- GET /tenant-analytics/overview
- GET /tenant-analytics/user-performance
- GET /tenant-analytics/ai-performance
- GET /tenant-analytics/kb-performance
- GET /tenant-analytics/channel-performance
- GET /tenant-analytics/team-performance
- GET /tenant-analytics/governance/usage
- GET /tenant-analytics/governance/quota
- GET /tenant-analytics/alerts/events

## 6. Go/No-Go Criteria
Use these criteria for business rollout:

1. Go
- All required endpoint checks pass for selected integration mode
- No unauthorized cross-tenant data exposure observed
- End-to-end chat request returns expected response contract
- Supervision and governance endpoints return valid responses

2. Conditional go
- Health is degraded but issue and workaround are known
- Optional endpoints fail but not required for initial launch scope

3. No-go
- Health check consistently failing
- Auth model not reliable
- Tenant/workspace isolation uncertain
- Chat endpoints failing for intended integration mode

## 7. Pilot Rollout Plan
1. Internal staging pilot (1 tenant, 1 workspace)
2. Controlled production pilot (1-3 business units)
3. Enable supervision and alerting thresholds
4. Review analytics weekly for 2 cycles
5. Expand channels after stable pilot

## 8. Operational Ownership
1. Product owner: validates business KPIs and rollout gates
2. Engineering owner: validates endpoint reliability and auth
3. Support owner: validates supervision workflows and queue handling
4. Security owner: validates key handling, auditability, and tenant isolation

## 9. Recommended Next Step
Run the scripted readiness audit and archive the output JSON as your integration sign-off artifact.
