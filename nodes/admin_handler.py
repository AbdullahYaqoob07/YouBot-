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
from datetime import datetime
import pytz
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage


def is_within_office_hours() -> bool:
    """
    Check if current time is within office hours
    Office hours: Monday to Friday, 10:00 AM – 6:00 PM Swedish Standard Time
    """
    sweden_tz = pytz.timezone('Europe/Stockholm')
    now = datetime.now(sweden_tz)
    
    # Check if weekday (0=Monday, 6=Sunday)
    if now.weekday() >= 5:  # Saturday or Sunday
        return False
    
    # Check if within 10 AM - 6 PM
    office_start = now.replace(hour=10, minute=0, second=0, microsecond=0)
    office_end = now.replace(hour=18, minute=0, second=0, microsecond=0)
    
    return office_start <= now <= office_end


async def translate_admin_message(user_message: str, english_template: str, admin_name: str = None, is_social_media: bool = False) -> str:
    """
    Use LLM to translate admin handler messages to user's language
    
    Args:
        user_message: The original message from the user (to detect language)
        english_template: The English message template
        admin_name: Admin name to include if applicable
        is_social_media: Whether to append website URL
    
    Returns:
        Translated message in user's language
    """
    try:
        llm = ChatGroq(
            model=settings.GROQ_MODEL,
            temperature=0.1,  # Low temperature for consistent translation
            max_tokens=300,
            api_key=settings.GROQ_API_KEY
        )
        
        # Build translation prompt
        website_instruction = ""
        if is_social_media:
            website_instruction = "\n\nIMPORTANT: Also add at the end on a new line: '🌐 [Translate: Visit our website for more information / to submit your application]: https://swedenrelocators.se'"
        
        admin_instruction = ""
        if admin_name:
            admin_instruction = f"\n\nNote: Include admin name '{admin_name}' in the translation."
        
        prompt = f"""Translate this message to match the user's language. Be natural, warm, and professional like a customer support agent.

User's message (detect language from this): "{user_message}"

Message to translate: "{english_template}"{admin_instruction}

IMPORTANT: After the main message, add a helpful follow-up question naturally in their language, such as:
- "Is there anything else I can help you with?"
- "Do you have any other questions?"
- Or any similar supportive question that fits the context.{website_instruction}

Respond ONLY with the translated message, nothing else."""
        
        result = await llm.ainvoke([HumanMessage(content=prompt)])
        translated = result.content.strip()
        
        logger.info(f"Translated admin message to user's language")
        return translated
        
    except Exception as e:
        logger.error(f"Translation failed, using English: {str(e)}")
        # Fallback to English
        msg = english_template + "\n\nIs there anything else I can help you with?"
        if is_social_media:
            msg += "\n\n---\n🌐 Visit our website for more information: https://swedenrelocators.se"
        return msg


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
            
            # Translate message to user's language using LLM
            channel = state.get("channel", "").lower()
            social_media_channels = ["instagram", "facebook", "whatsapp", "twitter", "linkedin", "tiktok"]
            is_social_media = any(social in channel for social in social_media_channels)
            
            english_msg = f"Your query has been forwarded to {admin['admin_name']}. They will assist you shortly. Estimated wait time: 2-5 minutes."
            
            state["ai_response"] = await translate_admin_message(
                user_message=state["message"],
                english_template=english_msg,
                admin_name=admin['admin_name'],
                is_social_media=is_social_media
            )
            
            logger.info(
                f"User {state['user_id']} assigned to admin {admin['admin_name']}"
            )
        else:
            # No admin available
            state["queue_status"] = "pending"
            
            channel = state.get("channel", "").lower()
            social_media_channels = ["instagram", "facebook", "whatsapp", "twitter", "linkedin", "tiktok"]
            is_social_media = any(social in channel for social in social_media_channels)
            within_hours = is_within_office_hours()
            
            if within_hours:
                # During office hours - show estimated time
                english_msg = "All our representatives are currently busy. Your query has been queued and someone will assist you soon. Estimated wait time: 2-5 minutes."
            else:
                # Outside office hours - no time estimate
                english_msg = "Your query has been forwarded to our team. We will respond during our office hours (Monday-Friday, 10:00 AM - 6:00 PM Swedish time)."
            
            state["ai_response"] = await translate_admin_message(
                user_message=state["message"],
                english_template=english_msg,
                is_social_media=is_social_media
            )
            
            logger.warning(f"No admin available for user {state['user_id']} (office_hours={within_hours})")
        
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
