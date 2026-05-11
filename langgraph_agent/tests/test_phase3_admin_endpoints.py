from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


ADMIN_HEADERS = {
    "X-Admin-Key": "test-admin-key",
    "X-Tenant-Id": "tenant_test",
    "X-Workspace-Id": "workspace_test",
}


@pytest.fixture
def app_client(monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module.settings, "ADMIN_API_KEY", "test-admin-key")

    # Keep endpoint tests fast and deterministic by disabling startup preload hooks.
    original_startup = list(app_module.app.router.on_startup)
    original_shutdown = list(app_module.app.router.on_shutdown)
    app_module.app.router.on_startup = []
    app_module.app.router.on_shutdown = []

    client = TestClient(app_module.app)
    try:
        yield client, app_module
    finally:
        client.close()
        app_module.app.router.on_startup = original_startup
        app_module.app.router.on_shutdown = original_shutdown


def test_retrieval_profile_endpoints(app_client, monkeypatch):
    client, app_module = app_client

    async def fake_get_profile(tenant_id: str, workspace_id: str):
        assert tenant_id == "tenant_test"
        assert workspace_id == "workspace_test"
        return {
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "default_mode": "rag",
            "allowed_modes": ["rag", "hybrid"],
        }

    async def fake_upsert_profile(**kwargs):
        return {
            "tenant_id": kwargs["tenant_id"],
            "workspace_id": kwargs["workspace_id"],
            "default_mode": kwargs["default_mode"],
            "allowed_modes": kwargs["allowed_modes"],
        }

    monkeypatch.setattr(app_module, "get_retrieval_profile", fake_get_profile)
    monkeypatch.setattr(app_module, "upsert_retrieval_profile", fake_upsert_profile)

    get_resp = client.get("/admin/retrieval/profile", headers=ADMIN_HEADERS)
    assert get_resp.status_code == 200
    assert get_resp.json()["profile"]["default_mode"] == "rag"

    post_payload = {
        "defaultMode": "hybrid",
        "allowedModes": ["rag", "hybrid"],
        "pageWindowLimit": 6,
        "complianceCriticality": 0.8,
        "averageDocumentPages": 22,
        "queryComplexity": 0.7,
        "latencyBudgetMs": 2500,
        "costSensitivity": 0.5,
    }
    post_resp = client.post("/admin/retrieval/profile", headers=ADMIN_HEADERS, json=post_payload)
    assert post_resp.status_code == 200
    assert post_resp.json()["profile"]["default_mode"] == "hybrid"


def test_retrieval_recommendation_endpoint(app_client, monkeypatch):
    client, app_module = app_client

    async def fake_select_mode(tenant_id: str, workspace_id: str, query_text: str, selected_mode_override=None):
        assert tenant_id == "tenant_test"
        assert workspace_id == "workspace_test"
        return {
            "recommended_mode": "page_index",
            "selected_mode": selected_mode_override or "page_index",
            "reason_summary": "Compliance-heavy query",
            "allowed_modes": ["rag", "page_index", "hybrid"],
        }

    monkeypatch.setattr(app_module, "select_retrieval_mode", fake_select_mode)

    resp = client.post(
        "/admin/retrieval/recommend",
        headers=ADMIN_HEADERS,
        json={"query": "check compliance clause", "selectedModeOverride": "hybrid"},
    )
    assert resp.status_code == 200
    assert resp.json()["selection"]["selected_mode"] == "hybrid"


def test_knowledge_source_and_ingestion_job_endpoints(app_client, monkeypatch):
    client, app_module = app_client

    async def fake_create_source(**kwargs):
        return {
            "id": 11,
            "tenant_id": kwargs["tenant_id"],
            "workspace_id": kwargs["workspace_id"],
            "source_name": kwargs["source_name"],
            "source_type": kwargs["source_type"],
            "status": "active",
        }

    async def fake_list_sources(tenant_id: str, workspace_id: str, limit: int = 100):
        return [{"id": 11, "source_name": "policy-csv", "source_type": "csv", "status": "active"}]

    async def fake_create_job(**kwargs):
        return {
            "id": 31,
            "source_id": kwargs["source_id"],
            "source_type": "csv",
            "status": "queued",
        }

    async def fake_list_jobs(tenant_id: str, workspace_id: str, limit: int = 100):
        return [{"id": 31, "source_id": 11, "status": "queued"}]

    async def fake_delete_source(tenant_id: str, workspace_id: str, source_id: int):
        assert tenant_id == "tenant_test"
        assert workspace_id == "workspace_test"
        assert source_id == 11
        return {
            "deleted_source_id": source_id,
            "detached_jobs": 1,
            "removed_page_records": 4,
            "removed_index_records": 8,
            "vector_cleanup_attempted": True,
            "vector_cleanup_succeeded": True,
        }

    monkeypatch.setattr("routers.kb_ingestion.create_knowledge_source", fake_create_source)
    monkeypatch.setattr("routers.kb_ingestion.list_knowledge_sources", fake_list_sources)
    monkeypatch.setattr("routers.kb_ingestion.create_ingestion_job", fake_create_job)
    monkeypatch.setattr("routers.kb_ingestion.list_ingestion_jobs", fake_list_jobs)
    monkeypatch.setattr("routers.kb_ingestion.delete_knowledge_source", fake_delete_source)

    list_sources_resp = client.get("/admin/workspaces/workspace_test/knowledge-sources", headers=ADMIN_HEADERS)
    assert list_sources_resp.status_code == 200
    assert list_sources_resp.json()["count"] == 1

    create_job_resp = client.post(
        "/admin/ingestion-jobs",
        headers=ADMIN_HEADERS,
        json={"sourceId": 11, "createdBy": "admin_1", "triggerType": "manual", "runNow": False},
    )
    assert create_job_resp.status_code == 200
    assert create_job_resp.json()["job"]["id"] == 31
    assert create_job_resp.json()["started"] is False

    list_jobs_resp = client.get("/admin/workspaces/workspace_test/ingestion-jobs", headers=ADMIN_HEADERS)
    assert list_jobs_resp.status_code == 200
    assert list_jobs_resp.json()["count"] == 1

    delete_source_resp = client.delete("/admin/workspaces/workspace_test/knowledge-sources/11", headers=ADMIN_HEADERS)
    assert delete_source_resp.status_code == 200
    assert delete_source_resp.json()["deleted_source_id"] == 11


def test_delete_configuration_endpoints(app_client, monkeypatch):
    client, app_module = app_client

    async def fake_delete_client_key(tenant_id: str, workspace_id: str, key_id: int):
        assert tenant_id == "tenant_test"
        assert workspace_id == "workspace_test"
        assert key_id == 7
        return {"deleted_key_id": key_id, "name": "Main Website Widget", "key_type": "public_widget"}

    async def fake_delete_llm_config(tenant_id: str, workspace_id: str):
        assert tenant_id == "tenant_test"
        assert workspace_id == "workspace_test"
        return {"tenant_id": tenant_id, "workspace_id": workspace_id, "provider": "openai", "model": "gpt-4o-mini", "deleted": True}

    async def fake_delete_social_connection(tenant_id: str, workspace_id: str, connection_id: int):
        assert tenant_id == "tenant_test"
        assert workspace_id == "workspace_test"
        assert connection_id == 9
        return {"deleted_connection_id": connection_id, "name": "Meta Connector", "connection_key": "sc_test"}

    monkeypatch.setattr("routers.admin_api.delete_client_api_key", fake_delete_client_key)
    monkeypatch.setattr("routers.admin_api.delete_workspace_llm_config", fake_delete_llm_config)
    monkeypatch.setattr("routers.social_integrations.delete_social_channel_connection", fake_delete_social_connection)

    client_key_resp = client.delete("/admin/workspaces/workspace_test/client-keys/7", headers=ADMIN_HEADERS)
    assert client_key_resp.status_code == 200
    assert client_key_resp.json()["deleted_key_id"] == 7

    llm_delete_resp = client.delete("/admin/workspaces/workspace_test/llm-config", headers=ADMIN_HEADERS)
    assert llm_delete_resp.status_code == 200
    assert llm_delete_resp.json()["deleted"] is True

    social_delete_resp = client.delete("/admin/workspaces/workspace_test/social-connections/9", headers=ADMIN_HEADERS)
    assert social_delete_resp.status_code == 200
    assert social_delete_resp.json()["deleted_connection_id"] == 9


def test_ingestion_job_detail_endpoint(app_client, monkeypatch):
    client, app_module = app_client

    row = SimpleNamespace(
        id=31,
        source_id=11,
        source_type="csv",
        trigger_type="manual",
        status="completed",
        total_records=10,
        processed_records=10,
        success_records=10,
        failed_records=0,
        error_summary=None,
        details_json={"namespace": "t_tenant_test__w_workspace_test"},
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        tenant_id="tenant_test",
        workspace_id="workspace_test",
    )

    class FakeResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class FakeSession:
        async def execute(self, _query):
            return FakeResult(row)

    @asynccontextmanager
    async def fake_get_async_session():
        yield FakeSession()

    monkeypatch.setattr("routers.kb_ingestion.get_async_session", fake_get_async_session)

    resp = client.get("/admin/ingestion-jobs/31", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["job"]["id"] == 31
    assert resp.json()["job"]["status"] == "completed"


def test_admin_key_required_for_phase3_endpoints(app_client):
    client, _ = app_client
    resp = client.get("/admin/retrieval/profile")
    assert resp.status_code == 403
