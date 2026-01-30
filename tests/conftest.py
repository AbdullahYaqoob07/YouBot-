import pytest
from unittest.mock import AsyncMock, MagicMock
import sys
import os

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from state import AgentState
import uuid
from datetime import datetime

@pytest.fixture
def mock_agent_state():
    """Create a default mock agent state"""
    return {
        "message": "Test message",
        "user_id": "test_user",
        "session_id": "test_session",
        "channel": "webhook",
        "is_spam": False,
        "is_roman_script": True,
        "detected_language": "English",
        "conversation_history": [],
        "ai_response": None,
        "requires_human": False,
        "knowledge_base_used": False,
        "request_id": str(uuid.uuid4()),
        "created_at": datetime.utcnow()
    }

@pytest.fixture
def mock_llm_response():
    """Mock LLM response"""
    mock = MagicMock()
    mock.content = "This is a mock AI response."
    return mock

@pytest.fixture
def mock_kb_tool():
    """Mock knowledge base tool"""
    mock = AsyncMock()
    mock.ainvoke.return_value = "Mock KB result"
    return mock
