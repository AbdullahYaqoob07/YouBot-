from datetime import datetime

from database.llm_provider_config_runtime import _delete_stmt, _insert_stmt, _update_stmt


def test_insert_stmt_includes_organization_column_when_enabled():
    statement = _insert_stmt(
        tenant_uuid=False,
        workspace_uuid=True,
        include_organization=True,
        organization_uuid=True,
    )
    sql = str(statement).lower()

    assert "organization_id" in sql
    assert "cast(:organization_id as uuid)" in sql


def test_insert_stmt_omits_organization_column_by_default():
    statement = _insert_stmt(
        tenant_uuid=False,
        workspace_uuid=True,
        include_organization=False,
        organization_uuid=True,
    )
    sql = str(statement).lower()

    assert "organization_id" not in sql


def test_delete_stmt_targets_workspace_scope_without_primary_key():
    statement = _delete_stmt("tenant-a", "workspace-b")
    sql = str(statement).lower()

    assert "delete from llm_provider_configs" in sql
    assert "llm_provider_configs.id" not in sql
    assert "returning" in sql


def test_update_stmt_targets_workspace_scope_without_primary_key():
    statement = _update_stmt(
        "tenant-a",
        "workspace-b",
        "openai",
        "gpt-4.1-mini",
        "encrypted-key",
        datetime.utcnow(),
        actor="admin@example.com",
    )
    sql = str(statement).lower()

    assert "update llm_provider_configs" in sql
    assert "llm_provider_configs.id" not in sql
    assert "returning" in sql