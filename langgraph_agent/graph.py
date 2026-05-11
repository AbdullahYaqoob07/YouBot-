"""
Main LangGraph workflow definition
Defines the complete AI agent graph with all nodes and edges
"""
from typing import Literal, Optional
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig
from loguru import logger
import asyncio

from state import AgentState
from nodes.rag_agent import rag_agent_node
from nodes.intent_classifier import intent_classification_node
from nodes.admin_handler import admin_handler_node, log_conversation_node
from config import settings


def create_workflow() -> StateGraph:
    """
    Create the main LangGraph workflow - STREAMLINED FOR SPEED
    
    Workflow Flow (Optimized - Logging moved to background):
    1. rag_agent - AI agent with knowledge base (checks cache first, auto-detects language)
       - CACHE HIT → END immediately (skip intent classification!)
       - CACHE MISS → Continue to intent classification
    2. intent_classification - Classify user intent (only for cache misses)
    3. admin_handler - Handle human handoff (if needed)
    4. END → Response sent immediately
    
    NOTE: Database logging happens in background after response is returned!
    
    Performance optimizations:
    - Cache hits bypass intent classification (2x faster!)
    - Cache checked BEFORE KB search (instant response on cache hit)
    - Multilingual cache with translation (any language, instant)
    - AI auto-responds in user's language
    - Logging moved to background (no blocking)
    - Direct flow reduces latency
    """
    
    # Create workflow graph
    workflow = StateGraph(AgentState)
    
    # Add nodes (streamlined pipeline - log_conversation removed from main flow)
    workflow.add_node("rag_agent", rag_agent_node)
    workflow.add_node("intent_classification", intent_classification_node)
    workflow.add_node("admin_handler", admin_handler_node)
    # NOTE: log_conversation_node will be called as background task from app.py
    
    # Define routing functions
    def cache_router(state: AgentState) -> Literal["cached_admin", "cached_respond", "classify"]:
        """Route based on cache hit and confidence - ALWAYS classify if unsure"""
        is_cache_hit = state.get("cache_hit", False)
        needs_human = state.get("requires_human", False)
        ai_response = state.get("ai_response", "").lower()
        
        logger.debug(f"🔀 Cache router: cache_hit={is_cache_hit}, requires_human={needs_human}")
        
        # Already marked for admin - go directly
        if needs_human:
            logger.info("🔀 Routing: Requires human → Admin handler")
            return "cached_admin"
        
        # Check if AI response indicates lack of knowledge (quick keyword check)
        lack_indicators = [
            "don't have", "do not have", "no information", "no specific",
            "team will reach out", "team will assist", "connect you with",
            "can't help", "cannot help", "outside my", "beyond my"
        ]
        if any(indicator in ai_response for indicator in lack_indicators):
            logger.info("🔀 Routing: AI response indicates uncertainty → Intent classification")
            return "classify"  # Let classifier decide
        
        if is_cache_hit:
            logger.info("🔀 Routing: CACHE HIT → END (skipping classification!)")
            return "cached_respond"
        
        # Default: go to classification to be safe
        logger.info("🔀 Routing: → Intent classification")
        return "classify"
    
    def admin_router(state: AgentState) -> Literal["admin", "respond"]:
        """Route based on admin handoff decision"""
        return "admin" if state.get("requires_human", False) else "respond"
    
    # Set entry point - directly to RAG agent
    workflow.set_entry_point("rag_agent")
    
    # Add edges (streamlined flow - END immediately after admin/respond)
    
    # RAG agent → Smart routing based on confidence
    workflow.add_conditional_edges(
        "rag_agent",
        cache_router,
        {
            "cached_admin": "admin_handler",  # Needs admin
            "cached_respond": END,  # Cache hit - respond immediately!
            "classify": "intent_classification"  # Uncertain - let classifier decide
        }
    )
    
    # Intent classification → Admin or END
    workflow.add_conditional_edges(
        "intent_classification",
        admin_router,
        {
            "admin": "admin_handler",
            "respond": END  # Go straight to END, log in background
        }
    )
    
    # Admin handler → END (log in background)
    workflow.add_edge("admin_handler", END)
    
    return workflow


async def compile_graph(workflow: StateGraph) -> any:
    """
    Compile the workflow with distributed async checkpointing
    """
    from database.checkpointer import AsyncMySQLSaver
    
    # Create persistent distributed checkpoint saver
    checkpointer = AsyncMySQLSaver()
    
    # Compile with checkpointing
    graph = workflow.compile(checkpointer=checkpointer)
    
    return graph


# Create and compile the main graph
workflow = create_workflow()
agent_graph = None  # Will be initialized on first use


def _build_thread_id(session_id: str, tenant_id: str, workspace_id: str) -> str:
    """Build a tenant-scoped thread id for LangGraph checkpoint isolation."""
    return f"{tenant_id}:{workspace_id}:{session_id}"


def _normalize_state(state: dict) -> dict:
    """
    Ensure all required AgentState fields are present.
    Fills in missing fields with defaults to prevent KeyError on checkpoint resume.
    This is critical for backward compatibility with old checkpoints.
    """
    from datetime import datetime
    
    state_defaults = {
        "language": None,
        "is_roman_script": True,
        "detected_language": None,
        "fast_path": False,
        "query_type": None,
        "is_spam": False,
        "spam_score": 0.0,
        "spam_reasons": [],
        "conversation_history": [],
        "history_count": 0,
        "knowledge_base_results": [],
        "knowledge_base_used": False,
        "cache_hit": False,
        "retrieval_mode_selected": None,
        "retrieval_mode_recommended": None,
        "retrieval_mode_reason": None,
        "retrieval_mode_override": None,
        "ai_response": "",
        "system_prompt": "",
        "user_wants_human": False,
        "is_genuine_relocation_question": False,
        "ai_lacks_knowledge": False,
        "classification_confidence": 0.0,
        "requires_human": False,
        "handoff_reason": None,
        "assigned_admin_id": None,
        "assigned_admin_name": None,
        "queue_status": None,
        "sentiment": "neutral",
        "response_time_ms": None,
        "error": "",
        "retry_count": 0,
        "next_node": None,
        "should_end": False,
    }
    
    # Fill in missing fields from defaults
    for key, default_value in state_defaults.items():
        if key not in state:
            state[key] = default_value
    
    return state


async def get_agent_graph():
    """Get or create the compiled agent graph"""
    global agent_graph
    if agent_graph is None:
        agent_graph = await compile_graph(workflow)
    return agent_graph


async def process_message(
    message: str,
    user_id: str,
    session_id: str,
    tenant_id: str,
    workspace_id: str,
    channel: str = "webhook",
    user_name: str = None,
    user_email: str = None,
    user_phone: str = None,
    retrieval_mode_override: Optional[str] = None,
) -> AgentState:
    """
    Process a user message through the workflow
    
    Args:
        message: User message
        user_id: Unique user identifier
        session_id: Unique session identifier
        tenant_id: Tenant identifier
        workspace_id: Workspace identifier
        channel: Communication channel
        user_name: Optional user name
        user_email: Optional user email
        user_phone: Optional user phone
        
    Returns:
        Final state after processing
    """
    from datetime import datetime
    import uuid
    
    # Create initial state with all required fields to prevent KeyError on resume
    initial_state: AgentState = {
        "message": message,
        "user_id": user_id,
        "session_id": session_id,
        "channel": channel,
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "user_name": user_name,
        "user_email": user_email,
        "user_phone": user_phone,

        # Defaults
        "language": None,
        "is_roman_script": True,
        "detected_language": None,
        "fast_path": False,
        "query_type": None,
        "is_spam": False,
        "spam_score": 0.0,
        "spam_reasons": [],
        "conversation_history": [],
        "history_count": 0,
        "knowledge_base_results": [],
        "knowledge_base_used": False,
        "cache_hit": False,
        "retrieval_mode_selected": None,
        "retrieval_mode_recommended": None,
        "retrieval_mode_reason": None,
        "retrieval_mode_override": retrieval_mode_override,
        "ai_response": "",
        "system_prompt": "",
        "user_wants_human": False,
        "is_genuine_relocation_question": False,
        "ai_lacks_knowledge": False,
        "classification_confidence": 0.0,
        "requires_human": False,
        "handoff_reason": None,
        "assigned_admin_id": None,
        "assigned_admin_name": None,
        "queue_status": None,
        "sentiment": "neutral",
        "response_time_ms": None,
        "model_used": f"{settings.DEFAULT_LLM_PROVIDER}:{settings.DEFAULT_LLM_MODEL or settings.GROQ_MODEL}",
        "error": "",
        "retry_count": 0,
        "request_id": str(uuid.uuid4()),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "next_node": None,
        "should_end": False
    }
    
    # Create tenant-scoped thread_id for checkpointing isolation
    config = RunnableConfig(
        configurable={"thread_id": _build_thread_id(session_id, tenant_id, workspace_id)},
        recursion_limit=50
    )
    
    # Process through workflow
    try:
        graph = await get_agent_graph()
        # Normalize state to ensure all fields present (critical for checkpoint resume)
        normalized_state = _normalize_state(initial_state)
        
        # ainvoke returns only channels that nodes wrote to during this run.
        # Merging with normalized_state ensures every key is always present,
        # eliminating KeyError for channels never touched (e.g. 'error' on cache-hit fast path).
        graph_output = await graph.ainvoke(normalized_state, config)
        final_state = {**normalized_state, **graph_output}
        return final_state

    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Error in process_message for {user_id}: {type(e).__name__}: {str(e)}")
        initial_state["error"] = f"{type(e).__name__}: {str(e)}"
        initial_state["ai_response"] = "I apologize, but I encountered an error. Let me connect you with our team."
        initial_state["requires_human"] = True
        return initial_state


async def resume_conversation(
    session_id: str,
    tenant_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> AgentState:
    """
    Resume a conversation from last checkpoint
    
    Args:
        session_id: Session identifier
        
    Returns:
        Final state after resuming
    """
    resolved_tenant = tenant_id or settings.DEFAULT_TENANT_ID
    resolved_workspace = workspace_id or settings.DEFAULT_WORKSPACE_ID
    config = RunnableConfig(
        configurable={"thread_id": _build_thread_id(session_id, resolved_tenant, resolved_workspace)}
    )
    
    # Resume from checkpoint
    graph = await get_agent_graph()
    final_state = await graph.ainvoke(None, config)
    return final_state


async def get_conversation_state(
    session_id: str,
    tenant_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> Optional[AgentState]:
    """
    Get current state of a conversation
    
    Args:
        session_id: Session identifier
        
    Returns:
        Current state or None if not found
    """
    resolved_tenant = tenant_id or settings.DEFAULT_TENANT_ID
    resolved_workspace = workspace_id or settings.DEFAULT_WORKSPACE_ID
    config = RunnableConfig(
        configurable={"thread_id": _build_thread_id(session_id, resolved_tenant, resolved_workspace)}
    )
    
    try:
        graph = await get_agent_graph()
        state = await graph.aget_state(config)
        return state.values if state else None
    except Exception:
        return None
