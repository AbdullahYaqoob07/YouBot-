# Tenant Analytics Blueprint

## 1) Objective
Give each client clear visibility into performance so they can improve support outcomes.

The dashboard must answer:
- Are users getting resolved quickly?
- Is AI helping enough or escalating too much?
- Is the support team meeting SLA?
- Is knowledge base quality improving?

## 2) KPI Domains

### A. User Performance
- Conversation completion rate
- Repeat contact rate (same issue within 24h/7d)
- User sentiment trend
- User drop-off rate before resolution
- Time to first meaningful response

### B. AI Performance
- AI auto-resolution rate
- Human handoff rate
- Fallback response rate
- Low-confidence response ratio
- Hallucination-risk proxy rate (policy and citation checks)

### C. Supervisor and Team Performance
- Queue wait time
- First takeover response time
- Average handling time
- Reopen rate after human resolution
- SLA breach rate

### D. Knowledge Base Performance
- Retrieval hit rate
- Citation coverage rate
- Unanswered question trend
- Knowledge freshness score
- Source quality score by connector

### E. Channel Performance
- Volume by channel
- Resolution rate by channel
- Escalation rate by channel
- p50/p95 response latency by channel

## 3) Dashboard Pages

### 3.1 Executive Overview
- Date range selector
- Global health score
- Top KPI cards
- Trend charts and alerts

### 3.2 User Outcomes
- Funnel: Started -> AI Responded -> Resolved -> Follow-up
- Cohorts by language, channel, and issue category
- Repeat-contact heatmap

### 3.3 AI Quality
- Auto-resolution trend
- Confidence distribution
- Fallback reason distribution
- Retrieval mode performance comparison (RAG vs Page Index vs Hybrid)

### 3.4 Team and SLA
- Live queue and SLA clock
- Supervisor workload
- Takeover effectiveness
- Breach root-cause summary

### 3.5 Knowledge Health
- Top unanswered intents
- Stale document detection
- Source sync success and failure rates
- Suggested curation actions

## 4) Data Model (Analytics Layer)
Create a metrics layer separate from raw conversation logs.

Required tables:
- conversation_metrics
- session_outcomes
- sla_events
- tenant_analytics_hourly
- tenant_analytics_daily
- analytics_alert_rules
- analytics_alert_events

Notes:
- Keep tenant_id and workspace_id on every row.
- Keep both event time and aggregation time.
- Use idempotent aggregation jobs.

## 5) Aggregation Strategy

### Real-time path
- Emit events from runtime and supervision actions.
- Update hot counters for dashboard cards.

### Batch path
- Hourly and daily aggregation jobs compute trends.
- Recompute correction window for delayed events.

## 6) API Contract (V1)

Tenant-facing endpoints:
- GET /tenant-analytics/overview
- GET /tenant-analytics/user-performance
- GET /tenant-analytics/ai-performance
- GET /tenant-analytics/team-performance
- GET /tenant-analytics/kb-performance
- GET /tenant-analytics/channel-performance
- GET /tenant-analytics/export.csv

Admin endpoints:
- POST /tenant-analytics/alerts/rules
- GET /tenant-analytics/alerts/events

All endpoints require tenant-scoped auth.

## 7) Alerting Rules (V1)
- SLA breach rate > threshold
- Auto-resolution drops below threshold
- Handoff rate spikes above baseline
- Retrieval hit rate drops below threshold
- Channel latency exceeds threshold

Alerts should support:
- Email
- Webhook
- In-dashboard notifications

## 8) Governance and Definitions
- Provide KPI glossary in dashboard UI.
- Version metric definitions (for trust and auditability).
- Keep audit log when KPI formulas change.

## 9) Rollout Plan

Phase 1:
- Executive overview
- User performance basics
- AI performance basics

Phase 2:
- Team and SLA analytics
- KB analytics and curation suggestions
- Alert rule engine

Phase 3:
- Forecasting and anomaly detection
- Cross-tenant benchmarks (anonymized and opt-in)

## 10) Success Criteria
- Tenants can identify top 3 performance issues within 5 minutes.
- KPI latency: near-real-time cards under 2 minutes.
- Daily reports generated with no data loss.
- At least one actionable recommendation per tenant per week.
