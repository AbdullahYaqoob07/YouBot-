"""
Admin Handler Node
Handles human handoff and conversation logging
"""
from state import AgentState
from database.admin_queue import assign_to_admin
from database.conversation import save_conversation
from database.analytics import log_analytics_event
from config import settings
from loguru import logger
import time


async def admin_handler_node(state: AgentState) -> AgentState:
    """
    Admin Handler Node
    
    Handles human handoff - assigns to available admin
    """
    logger.info(f"Admin handoff for user {state['user_id']}")
    
    # ⚡ CHECK: If admin has actively taken over, skip auto-assignment message
    if state.get("handoff_reason", "").startswith("Admin takeover"):
        logger.info("Admin active - skipping auto-response")
        return state
    
    try:
        # Find available admin
        admin = await assign_to_admin(
            session_id=state["session_id"],
            user_id=state["user_id"],
            user_message=state["message"],
            ai_response=state["ai_response"],
            language=state.get("detected_language", "English"),
            channel=state["channel"],
            handoff_reason=state.get("handoff_reason", "Unknown"),
            unsolved_score=1.0 - state.get("classification_confidence", 0.5)
        )
        
        if admin:
            # Admin assigned
            state["assigned_admin_id"] = admin["admin_id"]
            state["assigned_admin_name"] = admin["admin_name"]
            state["queue_status"] = "assigned"
            
            # Update AI response to inform user
            lang = state.get("detected_language", "English")
            
            if lang == "Swedish":
                state["ai_response"] = (
                    f"Din förfrågan har vidarebefordrats till {admin['admin_name']}. "
                    f"De kommer att hjälpa dig inom kort. Uppskattad väntetid: 2-5 minuter."
                )
            elif lang == "Spanish":
                state["ai_response"] = (
                    f"Tu consulta ha sido asignada a {admin['admin_name']}. "
                    f"Te asistirán en breve. Tiempo estimado: 2-5 minutos."
                )
            else:  # English or others
                state["ai_response"] = (
                    f"Your query has been forwarded to {admin['admin_name']}. "
                    f"They will assist you shortly. Estimated wait time: 2-5 minutes."
                )
            
            logger.info(
                f"User {state['user_id']} assigned to admin {admin['admin_name']}"
            )
        else:
            # No admin available
            state["queue_status"] = "pending"
            
            lang = state.get("detected_language", "English")
            
            if lang == "Swedish":
                state["ai_response"] = (
                    "Alla våra representanter är upptagna just nu. "
                    "Din förfrågan har placerats i kön och någon kommer att hjälpa dig snart."
                )
            elif lang == "Spanish":
                state["ai_response"] = (
                    "Todos nuestros representantes están ocupados. "
                    "Tu consulta está en cola y alguien te ayudará pronto."
                )
            else:
                state["ai_response"] = (
                    "All our representatives are currently busy. "
                    "Your query has been queued and someone will assist you soon."
                )
            
            logger.warning(f"No admin available for user {state['user_id']}")
        
    except Exception as e:
        logger.error(f"Error in admin handler: {str(e)}")
        state["error"] = str(e)
        state["ai_response"] = (
            "We're experiencing technical difficulties. "
            "Please try again shortly or email us at support@swedenrelocators.com"
        )
    
    return state


async def log_conversation_node(state: AgentState) -> AgentState:
    """
    Log Conversation Node
    
    Saves conversation to database and logs analytics
    """
    logger.info(f"Logging conversation for user {state['user_id']}")
    
    # Import supervision update
    from database.supervision import update_conversation
    
    try:
        # Calculate response time
        if state.get("created_at"):
            from datetime import datetime
            response_time_ms = int(
                (datetime.utcnow() - state["created_at"]).total_seconds() * 1000
            )
            state["response_time_ms"] = response_time_ms
        
        # Save conversation to database
        await save_conversation(
            session_id=state["session_id"],
            user_id=state["user_id"],
            user_message=state["message"],
            assistant_response=state["ai_response"],
            language=state.get("detected_language"),
            channel=state["channel"],
            sentiment=state.get("sentiment", "neutral"),
            resolved=not state.get("requires_human", False),
            handed_to_human=state.get("requires_human", False),
            model_used=state["model_used"],
            knowledge_base_used=state.get("knowledge_base_used", False),
            handoff_reason=state.get("handoff_reason"),
            unsolved_score=1.0 - state.get("classification_confidence", 0.5)
        )
        
        # SUPERVISION: Update active conversation status
        await update_conversation(
            session_id=state["session_id"],
            user_message=state["message"],
            ai_response=state["ai_response"],
            language=state.get("detected_language"),
            ai_triggered_handoff=state.get("requires_human", False),
            handoff_reason=state.get("handoff_reason")
        )
        
        # Log analytics event
        event_type = "query_processed"
        if state.get("requires_human"):
            event_type = "query_handed_to_human"
        elif state.get("knowledge_base_used"):
            event_type = "query_resolved_by_ai"
        
        await log_analytics_event(
            event_type=event_type,
            session_id=state["session_id"],
            user_id=state["user_id"],
            language=state.get("detected_language"),
            channel=state["channel"],
            sentiment=state.get("sentiment", "neutral"),
            model_used=state["model_used"],
            response_time_ms=state.get("response_time_ms"),
            knowledge_base_used=state.get("knowledge_base_used", False),
            resolved_by_ai=not state.get("requires_human", False),
            handed_to_human=state.get("requires_human", False),
            unsolved_score=1.0 - state.get("classification_confidence", 0.5)
        )
        
        logger.info(f"Successfully logged conversation for user {state['user_id']}")
        
    except Exception as e:
        logger.error(f"Error logging conversation: {str(e)}")
        # Don't fail the request if logging fails
        state["error"] = f"Logging error: {str(e)}"
    
    return state
