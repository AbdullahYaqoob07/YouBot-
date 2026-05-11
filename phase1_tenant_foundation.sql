-- Phase 1: Tenant Foundation Migration
-- Purpose: establish tenant/workspace entities and scope existing operational tables.

START TRANSACTION;

-- -----------------------------------------------------------------------------
-- Core tenant entities
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS organizations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    plan VARCHAR(50) NOT NULL DEFAULT 'starter',
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NULL,
    INDEX idx_org_created_at (created_at)
);

CREATE TABLE IF NOT EXISTS workspaces (
    id INT AUTO_INCREMENT PRIMARY KEY,
    workspace_id VARCHAR(80) NOT NULL UNIQUE,
    tenant_id VARCHAR(80) NOT NULL,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    default_provider VARCHAR(50) NULL,
    default_model VARCHAR(120) NULL,
    default_retrieval_mode VARCHAR(50) NOT NULL DEFAULT 'rag',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NULL,
    INDEX idx_workspaces_tenant (tenant_id),
    INDEX idx_workspaces_created_at (created_at),
    CONSTRAINT fk_workspaces_tenant FOREIGN KEY (tenant_id) REFERENCES organizations(tenant_id)
);

CREATE TABLE IF NOT EXISTS workspace_members (
    id INT AUTO_INCREMENT PRIMARY KEY,
    workspace_id VARCHAR(80) NOT NULL,
    tenant_id VARCHAR(80) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    email VARCHAR(255) NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'member',
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NULL,
    INDEX idx_workspace_members_workspace (workspace_id),
    INDEX idx_workspace_members_tenant (tenant_id),
    INDEX idx_workspace_members_user (user_id),
    UNIQUE KEY uq_workspace_members_workspace_user (workspace_id, user_id),
    CONSTRAINT fk_workspace_members_workspace FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
);

-- -----------------------------------------------------------------------------
-- Existing tables: add tenant/workspace scope columns
-- -----------------------------------------------------------------------------
ALTER TABLE conversation_logs
    ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(80) NULL,
    ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(80) NULL;

ALTER TABLE admin_availability
    ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(80) NULL,
    ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(80) NULL;

ALTER TABLE admin_queue
    ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(80) NULL,
    ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(80) NULL;

ALTER TABLE analytics_events
    ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(80) NULL,
    ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(80) NULL;

ALTER TABLE active_conversations
    ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(80) NULL,
    ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(80) NULL;

ALTER TABLE admin_messages
    ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(80) NULL,
    ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(80) NULL;

-- -----------------------------------------------------------------------------
-- Backfill defaults for existing rows
-- -----------------------------------------------------------------------------
UPDATE conversation_logs
SET tenant_id = COALESCE(tenant_id, 'public'),
    workspace_id = COALESCE(workspace_id, 'default')
WHERE tenant_id IS NULL OR workspace_id IS NULL;

UPDATE admin_availability
SET tenant_id = COALESCE(tenant_id, 'public'),
    workspace_id = COALESCE(workspace_id, 'default')
WHERE tenant_id IS NULL OR workspace_id IS NULL;

UPDATE admin_queue
SET tenant_id = COALESCE(tenant_id, 'public'),
    workspace_id = COALESCE(workspace_id, 'default')
WHERE tenant_id IS NULL OR workspace_id IS NULL;

UPDATE analytics_events
SET tenant_id = COALESCE(tenant_id, 'public'),
    workspace_id = COALESCE(workspace_id, 'default')
WHERE tenant_id IS NULL OR workspace_id IS NULL;

UPDATE active_conversations
SET tenant_id = COALESCE(tenant_id, 'public'),
    workspace_id = COALESCE(workspace_id, 'default')
WHERE tenant_id IS NULL OR workspace_id IS NULL;

UPDATE admin_messages
SET tenant_id = COALESCE(tenant_id, 'public'),
    workspace_id = COALESCE(workspace_id, 'default')
WHERE tenant_id IS NULL OR workspace_id IS NULL;

-- -----------------------------------------------------------------------------
-- Indexes for tenant/workspace scoped access
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_conversation_logs_tenant_workspace_created
    ON conversation_logs (tenant_id, workspace_id, created_at);

CREATE INDEX IF NOT EXISTS idx_admin_availability_tenant_workspace
    ON admin_availability (tenant_id, workspace_id);

CREATE INDEX IF NOT EXISTS idx_admin_queue_tenant_workspace_status_created
    ON admin_queue (tenant_id, workspace_id, status, created_at);

CREATE INDEX IF NOT EXISTS idx_analytics_events_tenant_workspace_timestamp
    ON analytics_events (tenant_id, workspace_id, timestamp);

CREATE INDEX IF NOT EXISTS idx_active_conversations_tenant_workspace_status
    ON active_conversations (tenant_id, workspace_id, status);

CREATE INDEX IF NOT EXISTS idx_admin_messages_tenant_workspace_created
    ON admin_messages (tenant_id, workspace_id, created_at);

-- Seed default public tenant/workspace for backward compatibility
INSERT IGNORE INTO organizations (tenant_id, name, plan, status, created_at)
VALUES ('public', 'Public Default Tenant', 'starter', 'active', UTC_TIMESTAMP());

INSERT IGNORE INTO workspaces (workspace_id, tenant_id, name, status, default_retrieval_mode, created_at)
VALUES ('default', 'public', 'Default Workspace', 'active', 'rag', UTC_TIMESTAMP());

COMMIT;
