import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from database.models import get_async_session, LangGraphCheckpoint
from database.checkpointer import AsyncMySQLSaver
from tools.mcp_manager import mcp_pool
import json
import asyncio
from sqlalchemy import select

ADMIN_HEADERS = {
    "X-Admin-Key": "test-admin-key",
    "X-Tenant-Id": "tenant_test",
    "X-Workspace-Id": "workspace_test",
}

@pytest.fixture
def app_client(monkeypatch):
    import app as app_module
    
    monkeypatch.setattr(app_module.settings, "ADMIN_API_KEY", "test-admin-key")

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

def test_admin_mcp_server_rejection_stdio(app_client):
    client, app_module = app_client
    
    # Try creating an stdio server
    post_payload = {
        "name": "Local Shell Server",
        "connection_type": "stdio",
        "connection_url": "python -m some_local_server",
        "config_json": {}
    }
    post_resp = client.post("/admin/workspaces/workspace_test/mcp-servers", headers=ADMIN_HEADERS, json=post_payload)
    
    # It must be rejected because standard I/O opens unmonitored sub-processes
    assert post_resp.status_code == 400
    assert "disabled" in post_resp.json()["detail"].lower()

@pytest.mark.asyncio
async def test_mcp_client_pool_is_singleton():
    from tools.mcp_manager import mcp_pool as pool1
    from tools.mcp_manager import mcp_pool as pool2
    assert pool1 is pool2, "MCPClientPool must be a generic Singleton to cache correctly"

@pytest.mark.asyncio
async def test_async_mysql_saver_checkpointing():
    import uuid
    unique_thread_id = f"test_thread_{uuid.uuid4().hex}"
    # Because we are testing against a LIVE DB context as requested by the user:
    saver = AsyncMySQLSaver()
    thread_config = {"configurable": {"thread_id": unique_thread_id}}
    
    checkpoint_mock = {
        "v": 1,
        "id": "chk_001",
        "ts": "2026-04-18T10:00:00Z",
        "channel_values": {"messages": []},
        "channel_versions": {},
        "versions_seen": {}
    }
    
    metadata_mock = {
        "source": "loop", "step": 1
    }
    
    # Save the blob into the database (MySQL / Supabase active daemon)
    res = await saver.aput(thread_config, checkpoint_mock, metadata_mock, {})
    assert res["configurable"]["checkpoint_id"] == "chk_001"

    # Save intermediate writes for the same checkpoint.
    await saver.aput_writes(
        res,
        [("messages", {"role": "assistant", "content": "hello"})],
        task_id="task_001",
    )
    
    # Retrieve it back
    fetched = await saver.aget_tuple(thread_config)
    assert fetched is not None
    assert fetched.checkpoint["id"] == "chk_001"
    assert fetched.metadata["step"] == 1
    assert fetched.pending_writes is not None
    assert fetched.pending_writes[0][0] == "task_001"
    assert fetched.pending_writes[0][1] == "messages"
    assert fetched.pending_writes[0][2]["content"] == "hello"
    
    # Verify exact DB row via independent session
    async with get_async_session() as session:
        result = await session.execute(
            select(LangGraphCheckpoint).where(LangGraphCheckpoint.thread_id == unique_thread_id)
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.checkpoint_id == "chk_001"

