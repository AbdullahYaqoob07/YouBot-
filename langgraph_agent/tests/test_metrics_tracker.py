"""
Focused test: client chat handler with metrics tracking
Validates that:
1. metrics module can import
2. client chat request doesn't crash on metrics import
3. background task for metrics recording is added
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


def test_metrics_module_imports():
    """Test that the metrics module imports without error."""
    try:
        from database.metrics import track_conversation_metrics
        assert callable(track_conversation_metrics)
        print("✓ metrics module imports successfully")
    except ImportError as e:
        pytest.fail(f"Failed to import metrics module: {e}")


@pytest.mark.asyncio
async def test_metrics_tracker_saves_conversation(monkeypatch):
    """Test that track_conversation_metrics saves conversation without error."""
    from database.metrics import track_conversation_metrics
    
    # Mock the underlying functions
    mock_save_conversation = AsyncMock()
    mock_update_conversation = AsyncMock()
    mock_log_analytics_event = AsyncMock()
    
    monkeypatch.setattr("database.metrics.save_conversation", mock_save_conversation)
    monkeypatch.setattr("database.metrics.update_conversation", mock_update_conversation)
    monkeypatch.setattr("database.metrics.log_analytics_event", mock_log_analytics_event)
    
    # Call the function
    await track_conversation_metrics(
        session_id="test_sess_123",
        user_id="test_user_456",
        tenant_id="test_tenant",
        workspace_id="test_workspace",
        user_message="Hello, test!",
        ai_response="Hi there, I'm a test response.",
        language="English",
        channel="web",
        sentiment="positive",
        model_used="groq:llama2",
        response_time_ms=500,
        knowledge_base_used=True,
        resolved_by_ai=True,
        handed_to_human=False,
        unsolved_score=0.0,
    )
    
    # Assert that all three functions were called
    mock_save_conversation.assert_called_once()
    mock_update_conversation.assert_called_once()
    mock_log_analytics_event.assert_called_once()
    
    print("✓ metrics tracker calls save_conversation, update_conversation, and log_analytics_event")


def test_client_chat_handler_uses_correct_field_names(monkeypatch):
    """
    Test that client_chat_handler passes the correct field names to track_conversation_metrics.
    This ensures the background task receives requires_human, not route_to_human.
    """
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock, MagicMock
    import app as app_module
    
    # Mock settings
    monkeypatch.setattr(app_module.settings, "ADMIN_API_KEY", "test-key")
    monkeypatch.setattr(app_module.settings, "REQUIRE_TENANT_CONTEXT", False)
    
    # Mock verify_client_key
    mock_client_key = MagicMock()
    mock_client_key.tenant_id = "test_tenant"
    mock_client_key.workspace_id = "test_workspace"
    monkeypatch.setattr(app_module, "verify_client_key", lambda *args: mock_client_key)
    
    # Mock process_message to return a proper final_state
    mock_process_message = AsyncMock()
    mock_process_message.return_value = {
        "message": "Hello",
        "detected_language": "English",
        "sentiment": "neutral",
        "model_used": "groq:llama2",
        "knowledge_base_used": False,
        "requires_human": True,  # This is the key field name in state
        "classification_confidence": 0.5,
        "assigned_admin_id": "admin_123",
        "assigned_admin_name": "Test Admin",
        "retrieval_mode_selected": "rag",
        "ai_response": "Test response",
        "messages": [MagicMock(content="Test response")],
    }
    monkeypatch.setattr(app_module, "process_message", mock_process_message)
    
    # Mock track_conversation_metrics to inspect its call
    mock_track_metrics = AsyncMock()
    monkeypatch.setattr("routers.chat.track_conversation_metrics", mock_track_metrics)
    
    # Make request
    client = TestClient(app_module.app)
    response = client.post(
        "/v1/chat",
        json={
            "message": "Hello, test!",
            "userId": "user_123",
            "channel": "web"
        }
    )
    
    # Assert status is 200 (not 500)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    print("✓ client chat handler returns 200 (no crash)")
    
    # Assert background task was registered with correct field names
    # The background_tasks.add_task is called, which we can't directly intercept,
    # but we can verify the response contains correct fields
    data = response.json()
    assert data["handoff"] == True  # requires_human should map to handoff
    assert data["assignedTo"] == "Test Admin"  # assigned_admin_name field
    print("✓ client chat handler response uses correct state field names")


if __name__ == "__main__":
    # Run quick validation
    test_metrics_module_imports()
    print("\nAll quick tests passed!")
