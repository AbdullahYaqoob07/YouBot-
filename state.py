"""
State schema for LangGraph workflow
Defines the complete state that flows through all nodes
"""
from typing import TypedDict, Optional, List, Dict, Any
from datetime import datetime


class ConversationMessage(TypedDict):
    """Single conversation message"""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime


class AgentState(TypedDict, total=False):
    """
    Complete state for the AI agent workflow
    This state is persisted in checkpoints and flows through all nodes
    """
    # Input Data
    message: str
    user_id: str
    session_id: str
    channel: str  # whatsapp, instagram, email, webhook
    tenant_id: str
    workspace_id: str
    
    # User Information
    user_name: Optional[str]
    user_email: Optional[str]
    user_phone: Optional[str]
    
    # Detected Metadata
    language: Optional[str]
    is_roman_script: bool
    detected_language: Optional[str]
    
    # Fast Path Routing (NEW - for performance)
    fast_path: bool  # True if query can skip RAG
    query_type: Optional[str]  # 'greeting', 'farewell', 'admin_request', 'complex'
    
    # Spam Detection
    is_spam: bool
    spam_score: float
    spam_reasons: List[str]
    
    # Conversation History
    conversation_history: List[ConversationMessage]
    history_count: int
    
    # RAG & Knowledge Base
    knowledge_base_results: List[Dict[str, Any]]
    knowledge_base_used: bool
    cache_hit: bool  # True if response came from FAQ cache
    retrieval_mode_selected: Optional[str]
    retrieval_mode_recommended: Optional[str]
    retrieval_mode_reason: Optional[str]
    
    # AI Response
    ai_response: str
    system_prompt: str
    
    # Intent Classification
    user_wants_human: bool
    is_genuine_relocation_question: bool
    ai_lacks_knowledge: bool
    classification_confidence: float
    
    # Admin Handoff
    requires_human: bool
    handoff_reason: Optional[str]
    assigned_admin_id: Optional[str]
    assigned_admin_name: Optional[str]
    queue_status: Optional[str]
    
    # Sentiment Analysis
    sentiment: str  # positive, neutral, negative, frustrated
    
    # Analytics
    response_time_ms: Optional[int]
    model_used: str
    
    # Error Handling
    error: Optional[str]
    retry_count: int
    
    # Metadata
    request_id: str
    created_at: datetime
    updated_at: datetime
    
    # Control Flow
    next_node: Optional[str]  # For dynamic routing
    should_end: bool


class AdminQueueEntry(TypedDict):
    """Admin queue entry for human handoff"""
    queue_id: int
    session_id: str
    user_id: str
    user_message: str
    ai_response: str
    language: str
    channel: str
    handoff_reason: str
    unsolved_score: float
    priority: str
    status: str
    assigned_admin_id: Optional[str]
    assigned_admin_name: Optional[str]
    created_at: datetime


class AnalyticsEvent(TypedDict):
    """Analytics event for tracking"""
    event_type: str
    session_id: str
    user_id: str
    language: str
    channel: str
    sentiment: str
    model_used: str
    response_time_ms: int
    knowledge_base_used: bool
    resolved_by_ai: bool
    handed_to_human: bool
    unsolved_score: Optional[float]
    timestamp: datetime
