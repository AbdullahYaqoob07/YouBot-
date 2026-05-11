-- ============================================================================
-- Phase 3: Retrieval Modes + Ingestion Pipeline Schema (Postgres/Supabase)
-- Idempotent migration script
-- ============================================================================

CREATE TABLE IF NOT EXISTS knowledge_sources (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    workspace_id VARCHAR(80) NOT NULL,
    source_name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    source_uri TEXT,
    source_config JSONB,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    last_sync_at TIMESTAMPTZ,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_knowledge_sources_tenant_workspace
    ON knowledge_sources (tenant_id, workspace_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_status
    ON knowledge_sources (status);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    workspace_id VARCHAR(80) NOT NULL,
    source_id INTEGER REFERENCES knowledge_sources(id) ON DELETE SET NULL,
    source_type VARCHAR(50) NOT NULL,
    trigger_type VARCHAR(50) NOT NULL DEFAULT 'manual',
    status VARCHAR(50) NOT NULL DEFAULT 'queued',
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    total_records INTEGER NOT NULL DEFAULT 0,
    processed_records INTEGER NOT NULL DEFAULT 0,
    success_records INTEGER NOT NULL DEFAULT 0,
    failed_records INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT,
    details_json JSONB,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_tenant_workspace
    ON ingestion_jobs (tenant_id, workspace_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status
    ON ingestion_jobs (status);

CREATE TABLE IF NOT EXISTS retrieval_profiles (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    workspace_id VARCHAR(80) NOT NULL,
    default_mode VARCHAR(50) NOT NULL DEFAULT 'rag',
    allowed_modes JSONB NOT NULL DEFAULT '["rag"]'::jsonb,
    page_window_limit INTEGER NOT NULL DEFAULT 4,
    compliance_criticality DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    average_document_pages INTEGER NOT NULL DEFAULT 10,
    query_complexity DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    latency_budget_ms INTEGER NOT NULL DEFAULT 2500,
    cost_sensitivity DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_retrieval_profile_tenant_workspace
    ON retrieval_profiles (tenant_id, workspace_id);

CREATE TABLE IF NOT EXISTS retrieval_recommendation_events (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    workspace_id VARCHAR(80) NOT NULL,
    query_hash VARCHAR(64) NOT NULL,
    query_preview VARCHAR(500),
    recommended_mode VARCHAR(50) NOT NULL,
    selected_mode VARCHAR(50) NOT NULL,
    reason_summary TEXT,
    expected_latency_band VARCHAR(50),
    expected_cost_band VARCHAR(50),
    override_applied BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_retrieval_events_tenant_workspace
    ON retrieval_recommendation_events (tenant_id, workspace_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_events_query_hash
    ON retrieval_recommendation_events (query_hash);

CREATE TABLE IF NOT EXISTS document_pages (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    workspace_id VARCHAR(80) NOT NULL,
    source_id INTEGER REFERENCES knowledge_sources(id) ON DELETE SET NULL,
    document_id VARCHAR(255) NOT NULL,
    page_number INTEGER NOT NULL,
    page_text TEXT NOT NULL,
    section_headings TEXT,
    metadata_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_document_page_workspace_doc_page
    ON document_pages (workspace_id, document_id, page_number);
CREATE INDEX IF NOT EXISTS idx_document_pages_tenant_workspace
    ON document_pages (tenant_id, workspace_id);

CREATE TABLE IF NOT EXISTS page_index_entries (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    workspace_id VARCHAR(80) NOT NULL,
    source_id INTEGER REFERENCES knowledge_sources(id) ON DELETE SET NULL,
    document_id VARCHAR(255) NOT NULL,
    page_number INTEGER NOT NULL,
    embedding_vector_ref VARCHAR(255) NOT NULL,
    keyword_vector_ref VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_page_index_entries_tenant_workspace
    ON page_index_entries (tenant_id, workspace_id);
CREATE INDEX IF NOT EXISTS idx_page_index_entries_doc_page
    ON page_index_entries (document_id, page_number);

SELECT 'Phase 3 retrieval/ingestion schema applied' AS status;
