# Frontend Delivery Plan (Backend-First, Next.js Later)

## 1) Product Direction
This system is a separate SaaS product with full flexibility.

Delivery strategy:
1. Build and stabilize backend capabilities first.
2. Validate workflows using simple HTML test dashboards.
3. Migrate to a production Next.js frontend once APIs and behavior are stable.

This reduces rework and helps you learn each layer cleanly.

## 2) Phase A: Backend Stability First
Goal: a reliable, testable API and workflow engine before frontend complexity.

Must be stable before Next.js work starts:
- Tenant and workspace isolation
- BYOK and BYOM configuration
- Retrieval mode routing (RAG, Page Index, Hybrid)
- Supervision and takeover flows
- Ingestion jobs and KB updates
- Analytics endpoints

Done criteria for Phase A:
- Core APIs pass integration tests
- Error handling and validation are consistent
- Key workflows are testable from API clients and HTML pages

## 3) Phase B: HTML Validation Layer
Goal: validate real user flows quickly with minimal frontend abstraction.

Use lightweight HTML pages to test:
- Tenant onboarding and settings
- LLM provider and model selection
- API key setup and key rotation
- Data source connection (CSV, scrape, upload)
- Chat runtime and takeover controls
- Analytics visibility and export

Why this matters:
- Faster debugging of API contract issues
- Faster iteration for backend changes
- Clear UX learning before framework lock-in

## 4) Phase C: Next.js Frontend Build
Goal: build a clean, modern UI on top of stable backend contracts.

Recommended app modules:
- Authentication and workspace selection
- LLM settings and model policies
- Knowledge sources and ingestion jobs
- Conversations and live supervision
- Analytics and alerting
- Billing and plan usage

Suggested structure:
- Route groups by product area
- Shared design system and component library
- Server-side API route wrappers for secure token handling
- Strong typing for API contracts

## 5) UI Principles (Simple, Clean, Great)
- Keep navigation shallow and task-oriented.
- Use clear KPI summaries and drill-down details.
- Prefer readable layouts over dense dashboards.
- Keep forms guided and safe with defaults.
- Emphasize operational clarity: status, health, and actions.

## 6) Migration Strategy (HTML to Next.js)
1. Freeze API contracts used by HTML pages.
2. Rebuild each validated flow in Next.js module-by-module.
3. Keep old HTML pages available behind admin/debug routes during migration.
4. Remove old pages only after flow parity tests pass.

## 7) Learning Plan for a Junior Engineer
Build in this order:
1. API contract discipline and backend test coverage
2. Basic HTML flow testing and debugging
3. Next.js app routing and data fetching patterns
4. Design system and reusable components
5. Frontend performance and accessibility checks

## 8) Execution Checklist
- Define backend API readiness checklist
- Build/refresh HTML validation pages for all critical flows
- Track flow parity checklist for Next.js migration
- Add end-to-end tests for top workflows
- Release Next.js in stages, not all at once
