from contextlib import asynccontextmanager

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
    monkeypatch.setattr(app_module.settings, "API_KEYS", [])
    monkeypatch.setattr(app_module.settings, "REQUIRE_TENANT_CONTEXT", False)

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


def test_phase4_supervision_flow_endpoints(app_client, monkeypatch):
    client, app_module = app_client

    async def fake_get_active_conversations(**kwargs):
        assert kwargs["tenant_id"] == "tenant_test"
        assert kwargs["workspace_id"] == "workspace_test"
        return [
            {
                "session_id": "sess_1",
                "status": "active",
                "admin_takeover": False,
            }
        ]

    async def fake_get_conversation_messages_for_admin(session_id, **kwargs):
        assert session_id == "sess_1"
        assert kwargs["tenant_id"] == "tenant_test"
        assert kwargs["workspace_id"] == "workspace_test"
        return {
            "session_id": session_id,
            "status": "active",
            "messages": [{"type": "user", "content": "hello"}],
        }

    async def fake_admin_takeover(**kwargs):
        assert kwargs["tenant_id"] == "tenant_test"
        assert kwargs["workspace_id"] == "workspace_test"
        return {
            "success": True,
            "session_id": kwargs["session_id"],
            "admin_id": kwargs["admin_id"],
        }

    async def fake_admin_send_message(**kwargs):
        assert kwargs["tenant_id"] == "tenant_test"
        assert kwargs["workspace_id"] == "workspace_test"
        return {
            "success": True,
            "session_id": kwargs["session_id"],
            "message": kwargs["message"],
            "translated": False,
        }

    async def fake_release_conversation(**kwargs):
        assert kwargs["tenant_id"] == "tenant_test"
        assert kwargs["workspace_id"] == "workspace_test"
        return {
            "success": True,
            "session_id": kwargs["session_id"],
            "action": "released to AI",
        }

    monkeypatch.setattr(app_module, "get_active_conversations", fake_get_active_conversations)
    monkeypatch.setattr(app_module, "get_conversation_messages_for_admin", fake_get_conversation_messages_for_admin)
    monkeypatch.setattr(app_module, "admin_takeover", fake_admin_takeover)
    monkeypatch.setattr(app_module, "admin_send_message", fake_admin_send_message)
    monkeypatch.setattr(app_module, "release_conversation", fake_release_conversation)

    list_resp = client.get("/admin/supervision/conversations", headers=ADMIN_HEADERS)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1

    detail_resp = client.get("/admin/supervision/conversations/sess_1", headers=ADMIN_HEADERS)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["conversation"]["session_id"] == "sess_1"

    takeover_resp = client.post(
        "/admin/supervision/conversations/sess_1/takeover",
        headers=ADMIN_HEADERS,
        json={"admin_id": "admin_1", "reason": "manual"},
    )
    assert takeover_resp.status_code == 200
    assert takeover_resp.json()["success"] is True

    message_resp = client.post(
        "/admin/supervision/conversations/sess_1/message",
        headers=ADMIN_HEADERS,
        json={"admin_id": "admin_1", "message": "Hello from admin"},
    )
    assert message_resp.status_code == 200
    assert message_resp.json()["success"] is True

    release_resp = client.post(
        "/admin/supervision/conversations/sess_1/release",
        headers=ADMIN_HEADERS,
        json={"admin_id": "admin_1", "end_conversation": False},
    )
    assert release_resp.status_code == 200
    assert release_resp.json()["success"] is True


def test_phase4_supervision_takeover_returns_400_on_domain_error(app_client, monkeypatch):
    client, app_module = app_client

    async def fake_admin_takeover(**_kwargs):
        return {"success": False, "error": "Conversation already taken over"}

    monkeypatch.setattr(app_module, "admin_takeover", fake_admin_takeover)

    resp = client.post(
        "/admin/supervision/conversations/sess_2/takeover",
        headers=ADMIN_HEADERS,
        json={"admin_id": "admin_2", "reason": "manual"},
    )
    assert resp.status_code == 400
    assert "already taken over" in resp.json()["detail"]


def test_phase4_channel_contract_validation(app_client):
    _, app_module = app_client

    valid = app_module.MessageRequest(
        message="hello",
        userId="u1",
        channel="WHATSAPP",
    )
    assert valid.channel == "whatsapp"

    with pytest.raises(Exception):
        app_module.MessageRequest(
            message="hello",
            userId="u1",
            channel="sms",
        )


def test_phase4_admin_key_required_for_supervision_routes(app_client):
    client, _ = app_client

    resp = client.get("/admin/supervision/conversations")
    assert resp.status_code == 403
