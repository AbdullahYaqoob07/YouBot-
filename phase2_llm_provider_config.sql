-- Phase 2: Workspace LLM Provider Configuration
-- Adds BYOK/BYOM storage for workspace-level provider + model + encrypted API key.

START TRANSACTION;

CREATE TABLE IF NOT EXISTS llm_provider_configs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    workspace_id VARCHAR(80) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    model_name VARCHAR(120) NOT NULL,
    encrypted_api_key TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by VARCHAR(255) NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NULL,
    UNIQUE KEY uq_llm_provider_config_tenant_workspace (tenant_id, workspace_id),
    INDEX idx_llm_provider_configs_tenant (tenant_id),
    INDEX idx_llm_provider_configs_workspace (workspace_id),
    INDEX idx_llm_provider_configs_updated (updated_at)
);

COMMIT;
