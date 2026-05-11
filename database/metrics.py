"""
Conversation Metrics Tracking
Persists conversation data and analytics for admin dashboards and supervision.

This module is called from the chat handler as a background task to record
user messages, AI responses, and associated metadata without blocking the response.
"""
from datetime import datetime
from typing import Optional
from loguru import logger

from database.conversation import save_conversation
from database.analytics import log_analytics_event
from database.supervision import update_conversation


async def track_conversation_metrics(
    session_id: str,
    user_id: str,
    tenant_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    user_message: str = "",
    ai_response: str = "",
    language: Optional[str] = None,
    channel: Optional[str] = None,
    sentiment: Optional[str] = None,
    model_used: Optional[str] = None,
    response_time_ms: Optional[int] = None,
    knowledge_base_used: bool = False,
    resolved_by_ai: bool = False,
    handed_to_human: bool = False,
    assigned_admin: Optional[str] = None,
    unsolved_score: Optional[float] = None,
) -> None:
    """
    Track conversation metrics for a user message and AI response.

    This function:
    1. Persists the conversation to ConversationLog for admin/user history
    2. Updates ActiveConversation supervision status
    3. Logs analytics event for KPI tracking

    All operations are best-effort; failures are logged but do not raise.
    Intended for use as a BackgroundTask in FastAPI.

    Args:
        session_id: Unique session identifier
        user_id: Unique user identifier
        tenant_id: Tenant identifier (optional)
        workspace_id: Workspace identifier (optional)
        user_message: User's original message
        ai_response: AI's response or admin message
        language: Detected language (e.g., "English", "Spanish")
        channel: Communication channel (e.g., "web", "whatsapp", "facebook")
        sentiment: Detected sentiment (e.g., "positive", "neutral", "negative")
        model_used: LLM model used (e.g., "groq:llama2-7b")
        response_time_ms: Response time in milliseconds
        knowledge_base_used: Whether KB was used for response
        resolved_by_ai: Whether query was resolved by AI
        handed_to_human: Whether conversation was handed to human
        assigned_admin: Admin ID if assigned (optional)
        unsolved_score: Confidence score for unresolved queries (0.0-1.0)

    Returns:
        None (all errors are logged but not raised)
    """
    try:
        # Step 1: Save conversation to ConversationLog table
        # This ensures the user message and AI response are stored for history/audit
        handoff_reason = "Handed to admin" if handed_to_human and assigned_admin else "Unresolved query" if handed_to_human else None

        await save_conversation(
            session_id=session_id,
            user_id=user_id,
            user_message=user_message,
            assistant_response=ai_response,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            language=language or "English",
            channel=channel,
            sentiment=sentiment or "neutral",
            resolved=resolved_by_ai,
            handed_to_human=handed_to_human,
            model_used=model_used,
            knowledge_base_used=knowledge_base_used,
            handoff_reason=handoff_reason,
            unsolved_score=unsolved_score,
        )
        logger.opt(exception=True).debug("Saved conversation metrics for user {user_id}")

        # Step 2: Update supervision status (for real-time admin dashboard)
        await update_conversation(
            session_id=session_id,
            user_message=user_message,
            ai_response=ai_response,
            language=language or "English",
            ai_triggered_handoff=handed_to_human,
            handoff_reason=handoff_reason,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        logger.debug(f"Updated supervision for session {session_id}")

        # Step 3: Log analytics event for KPI dashboards
        event_type = "query_resolved_by_ai" if resolved_by_ai else "query_handed_to_human" if handed_to_human else "query_processed"

        await log_analytics_event(
            event_type=event_type,
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            language=language or "English",
            channel=channel,
            sentiment=sentiment or "neutral",
            model_used=model_used,
            response_time_ms=response_time_ms,
            knowledge_base_used=knowledge_base_used,
            resolved_by_ai=resolved_by_ai,
            handed_to_human=handed_to_human,
            unsolved_score=unsolved_score,
        )
        logger.debug(f"Logged analytics event: {event_type}")

    except Exception as e:
        logger.error("Error tracking conversation metrics: {}", e)
        # Do NOT raise - this is a background task; swallow the error
