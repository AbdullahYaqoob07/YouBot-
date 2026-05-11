# Retrieval Modes Playbook

## 1) Why this exists
Not all support use-cases need the same retrieval strategy.
- RAG is fast and cost-efficient for FAQs and short policy answers.
- Page Index is stronger when answers depend on document-wide context.
- Hybrid gives better accuracy for complex enterprise content.

This playbook defines when to use each mode and how to recommend it.

## 2) Retrieval Modes

### A. RAG Mode
Use chunk embeddings and retrieve top chunks.

Best for:
- FAQ bots
- product support
- low latency requirements
- cost-sensitive workloads

Tradeoffs:
- may miss cross-page dependencies
- weaker for legal contract interpretation

### B. Page Index Mode
Use page-level indexing and retrieve contiguous page windows (for example pages 8 to 11 together).

Best for:
- legal, policy, compliance, insurance
- long documents where context spans many sections
- use-cases where citations and full context matter

Tradeoffs:
- higher token usage
- higher latency
- higher LLM cost

### C. Hybrid Mode
Use page index to narrow the right sections, then run chunk retrieval inside those sections.

Best for:
- large enterprise document sets
- high-accuracy environments with cost controls
- mixed workloads where some queries are broad and some are precise

Tradeoffs:
- highest system complexity
- requires stronger observability and routing logic

## 3) Plan-based availability

### Starter
- RAG Mode only
- hard token and latency limits

### Growth
- RAG Mode
- Page Index Mode with guardrails (limited pages per request)

### Enterprise
- RAG Mode
- Page Index Mode
- Hybrid Mode
- policy-driven routing and custom thresholds

## 4) Recommendation Engine (V1)
For every workspace, calculate a recommendation score per mode.

Inputs:
- average document length
- cross-page dependency score
- compliance criticality
- expected query complexity
- latency budget
- cost budget

Output:
- recommended_mode
- reason_summary
- expected_latency_band
- expected_cost_band

Admins can always override recommendation.

## 5) Practical rule set (first version)
Start with deterministic rules before ML routing.

Rule examples:
1. If compliance_criticality is high and avg_doc_pages is high, recommend Page Index.
2. If faq_ratio is high and latency_budget is strict, recommend RAG.
3. If both long_docs and strict cost controls exist, recommend Hybrid.
4. If query requests full clause interpretation, route to Page Index even if default is RAG.

## 6) Data model requirements
Add these entities:
- retrieval_profiles
- document_pages
- page_index_entries
- retrieval_recommendation_events

Recommended fields:
- retrieval_profiles: workspace_id, default_mode, allowed_modes, page_window_limit
- document_pages: document_id, page_number, page_text, section_headings
- page_index_entries: workspace_id, document_id, page_number, embedding_vector_ref
- retrieval_recommendation_events: workspace_id, query_hash, recommended_mode, selected_mode, outcome_score

## 7) Runtime routing
1. Resolve workspace retrieval policy.
2. Read recommended mode from rules.
3. Apply admin override if present.
4. Execute chosen retrieval strategy.
5. Emit mode usage event and quality signal.

## 8) KPIs to track
- answer acceptance rate by mode
- human escalation rate by mode
- token cost per resolved conversation
- median and p95 latency per mode
- citation correctness rate (for compliance workloads)

## 9) Recommended starting use-cases
Start with these pilots:
1. FAQ-heavy support tenant using RAG
2. Legal/compliance tenant using Page Index
3. Mixed enterprise tenant using Hybrid

Compare quality, cost, and latency for 2 to 4 weeks, then tune thresholds.

## 10) Guardrails
- Block Page Index on very large documents for low plans.
- Apply max context window per plan.
- Apply max pages per request.
- Fallback to RAG when model context limits are reached.
- Always return citations to source pages or chunks.
