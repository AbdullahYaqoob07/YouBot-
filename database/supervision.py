"""
Admin Supervision Database Operations
Handles real-time conversation monitoring and admin intervention
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from sqlalchemy import select, and_, or_, update as sql_update, desc
from database.models import (
    ActiveConversation, 
    AdminMessage, 
    ConversationLog,
    AdminAvailability,
    AdminQueue,
    get_async_session
)
from loguru import logger


async def _translate_to_en(text: str, language: str) -> str:
    """Translate text to English using comprehension agent. Returns original on failure."""
    try:
        from nodes.comprehension_agent import translate_to_english
        return await translate_to_english(text, language)
    except Exception as e:
        logger.warning(f"Translation to English failed: {e}")
        return text


async def _translate_from_en(text: str, language: str) -> str:
    """Translate English text to target language. Returns original on failure."""
    try:
        from nodes.comprehension_agent import translate_from_english
        return await translate_from_english(text, language)
    except Exception as e:
        logger.warning(f"Translation from English failed: {e}")
        return text


async def start_conversation(
    session_id: str,
    user_id: str,
    channel: str = "webhook",
    language: str = None
) -> bool:
    """
    Register a new conversation for supervision.
    Called when a user starts chatting.
    """
    try:
        async with get_async_session() as session:
            # Check if conversation already exists
            query = select(ActiveConversation).where(
                ActiveConversation.session_id == session_id
            )
            result = await session.execute(query)
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update last activity
                existing.last_activity = datetime.utcnow()
                existing.status = "active"
                await session.commit()
                return True
            
            # Create new active conversation
            conv = ActiveConversation(
                session_id=session_id,
                user_id=user_id,
                channel=channel,
                language=language,
                status="active",
                is_supervised=True,
                admin_takeover=False,
                message_count=0,
                started_at=datetime.utcnow(),
                last_activity=datetime.utcnow()
            )
            session.add(conv)
            await session.commit()
            
            logger.info(f"Started supervised conversation: {session_id}")
            return True
            
    except Exception as e:
        logger.error(f"Error starting conversation: {str(e)}")
        return False


async def update_conversation(
    session_id: str,
    user_message: str,
    ai_response: str,
    language: str = None,
    ai_triggered_handoff: bool = False,
    handoff_reason: str = None
) -> bool:
    """
    Update conversation with latest message.
    Called after each AI response.
    """
    try:
        async with get_async_session() as session:
            query = select(ActiveConversation).where(
                ActiveConversation.session_id == session_id
            )
            result = await session.execute(query)
            conv = result.scalar_one_or_none()
            
            if not conv:
                logger.warning(f"Conversation not found for update: {session_id}")
                return False
            
            conv.message_count += 1
            conv.last_message = user_message[:500]  # Truncate for storage
            conv.last_ai_response = ai_response[:500]
            conv.last_activity = datetime.utcnow()
            
            if language:
                conv.language = language
            
            if ai_triggered_handoff:
                conv.ai_triggered_handoff = True
                conv.handoff_reason = handoff_reason
                conv.status = "pending_handoff"
            
            await session.commit()
            return True
            
    except Exception as e:
        logger.error(f"Error updating conversation: {str(e)}")
        return False


async def get_active_conversations(
    status_filter: str = None,
    include_ended: bool = False
) -> List[Dict]:
    """
    Get all active/supervised conversations for admin dashboard.
    
    Args:
        status_filter: Filter by status (active, admin_watching, admin_takeover, pending_handoff)
        include_ended: Include ended conversations
    """
    try:
        async with get_async_session() as session:
            query = select(ActiveConversation)
            
            if status_filter:
                query = query.where(ActiveConversation.status == status_filter)
            elif not include_ended:
                query = query.where(ActiveConversation.status != "ended")
            
            query = query.order_by(desc(ActiveConversation.last_activity))
            
            result = await session.execute(query)
            conversations = result.scalars().all()
            
            return [
                {
                    "id": conv.id,
                    "session_id": conv.session_id,
                    "user_id": conv.user_id,
                    "channel": conv.channel,
                    "language": conv.language,
                    "status": conv.status,
                    "admin_takeover": conv.admin_takeover,
                    "admin_id": conv.admin_id,
                    "ai_triggered_handoff": conv.ai_triggered_handoff,
                    "handoff_reason": conv.handoff_reason,
                    "message_count": conv.message_count,
                    "last_message": conv.last_message,
                    "last_ai_response": conv.last_ai_response,
                    "started_at": conv.started_at.isoformat() if conv.started_at else None,
                    "last_activity": conv.last_activity.isoformat() if conv.last_activity else None,
                    "takeover_at": conv.takeover_at.isoformat() if conv.takeover_at else None
                }
                for conv in conversations
            ]
            
    except Exception as e:
        logger.error(f"Error getting active conversations: {str(e)}")
        return []


async def get_conversation_messages(
    session_id: str,
    limit: int = 50
) -> Dict:
    """
    Get full conversation history including admin messages for a session.
    """
    try:
        async with get_async_session() as session:
            # Get conversation logs
            conv_query = (
                select(ConversationLog)
                .where(ConversationLog.session_id == session_id)
                .order_by(ConversationLog.created_at)
                .limit(limit)
            )
            conv_result = await session.execute(conv_query)
            conv_logs = conv_result.scalars().all()
            
            # Get admin messages
            admin_query = (
                select(AdminMessage)
                .where(AdminMessage.session_id == session_id)
                .order_by(AdminMessage.created_at)
            )
            admin_result = await session.execute(admin_query)
            admin_msgs = admin_result.scalars().all()
            
            # Get active conversation status
            status_query = select(ActiveConversation).where(
                ActiveConversation.session_id == session_id
            )
            status_result = await session.execute(status_query)
            active_conv = status_result.scalar_one_or_none()
            
            # Combine and sort all messages
            all_messages = []
            user_language = active_conv.language if active_conv else "English"
            
            for log in conv_logs:
                all_messages.append({
                    "type": "user",
                    "content": log.user_message,      # Original language (for user)
                    "timestamp": log.created_at.isoformat()
                })
                all_messages.append({
                    "type": "ai",
                    "content": log.assistant_response, # Original language (for user)
                    "timestamp": log.created_at.isoformat()
                })
            
            for msg in admin_msgs:
                all_messages.append({
                    "type": "admin",
                    "admin_id": msg.admin_id,
                    "content": msg.message,             # Stored as user's language
                    "timestamp": msg.created_at.isoformat()
                })
            
            # Sort by timestamp
            all_messages.sort(key=lambda x: x["timestamp"])
            
            return {
                "session_id": session_id,
                "status": active_conv.status if active_conv else "unknown",
                "admin_takeover": active_conv.admin_takeover if active_conv else False,
                "admin_id": active_conv.admin_id if active_conv else None,
                "user_id": active_conv.user_id if active_conv else None,
                "channel": active_conv.channel if active_conv else None,
                "language": user_language,
                "messages": all_messages
            }
            
    except Exception as e:
        logger.error(f"Error getting conversation messages: {str(e)}")
        return {"session_id": session_id, "messages": [], "error": str(e)}


async def get_conversation_messages_for_admin(
    session_id: str,
    limit: int = 50
) -> Dict:
    """
    Admin-facing version of get_conversation_messages.
    - All user/AI messages are translated to English for admin readability.
    - Admin messages are shown in English (they wrote them in English;
      the translated copy was stored for the user).
    - Each message includes original_content and a translated flag so the
      admin dashboard can show both if desired.
    """
    base = await get_conversation_messages(session_id, limit)
    if base.get("error"):
        return base

    user_language = base.get("language", "English")
    needs_translation = user_language and user_language.lower() not in ("english", "en")

    if not needs_translation:
        # Already English — just add translated=False flags
        for msg in base.get("messages", []):
            msg.setdefault("original_content", msg["content"])
            msg["translated"] = False
        return base

    translated_messages = []
    for msg in base.get("messages", []):
        content = msg["content"]
        original = content

        if msg["type"] in ("user", "ai"):
            en_content = await _translate_to_en(content, user_language)
        elif msg["type"] == "admin":
            # Stored as user's language — translate back to English for admin
            en_content = await _translate_to_en(content, user_language)
        else:
            en_content = content

        translated_messages.append({
            **msg,
            "content": en_content,           # English for admin
            "original_content": original,    # User's language preserved
            "translated": en_content != original,
        })

    base["messages"] = translated_messages
    return base


async def admin_takeover(
    session_id: str,
    admin_id: str,
    reason: str = "Manual intervention"
) -> Dict:
    """
    Admin takes over a conversation.
    AI will stop responding, admin sends messages directly.
    """
    try:
        async with get_async_session() as session:
            # Get conversation
            query = select(ActiveConversation).where(
                ActiveConversation.session_id == session_id
            )
            result = await session.execute(query)
            conv = result.scalar_one_or_none()
            
            if not conv:
                return {"success": False, "error": "Conversation not found"}
            
            # Check if super admin has taken over - prevent regular admin takeover
            if conv.super_admin_takeover:
                return {
                    "success": False, 
                    "error": f"Conversation is under super admin control. Regular admins cannot take over."
                }
            
            if conv.admin_takeover and conv.admin_id != admin_id:
                return {
                    "success": False, 
                    "error": f"Conversation already taken over by admin {conv.admin_id}"
                }
            
            # Update conversation for takeover
            conv.admin_takeover = True
            conv.admin_id = admin_id
            conv.takeover_reason = reason
            conv.takeover_at = datetime.utcnow()
            conv.status = "admin_takeover"
            conv.last_activity = datetime.utcnow()
            
            # Update admin queue count
            admin_query = select(AdminAvailability).where(
                AdminAvailability.admin_id == admin_id
            )
            admin_result = await session.execute(admin_query)
            admin = admin_result.scalar_one_or_none()
            
            if admin:
                admin.current_queue_count += 1
                admin.last_assigned_at = datetime.utcnow()
            
            await session.commit()
            
            logger.info(f"Admin {admin_id} took over conversation {session_id}")
            
            return {
                "success": True,
                "session_id": session_id,
                "admin_id": admin_id,
                "message": f"You have taken over conversation with user {conv.user_id}"
            }
            
    except Exception as e:
        logger.error(f"Error in admin takeover: {str(e)}")
        return {"success": False, "error": str(e)}


async def admin_send_message(
    session_id: str,
    admin_id: str,
    message: str
) -> Dict:
    """
    Admin sends a message to the user.
    Only works if admin has taken over the conversation.
    """
    try:
        async with get_async_session() as session:
            # Verify admin has taken over
            query = select(ActiveConversation).where(
                ActiveConversation.session_id == session_id
            )
            result = await session.execute(query)
            conv = result.scalar_one_or_none()
            
            if not conv:
                return {"success": False, "error": "Conversation not found"}
            
            if not conv.admin_takeover:
                return {"success": False, "error": "You must take over the conversation first"}
            
            if conv.admin_id != admin_id:
                return {"success": False, "error": "You are not assigned to this conversation"}
            
            # Translate admin's English reply to user's language
            user_language = conv.language or "English"
            needs_translation = user_language.lower() not in ("english", "en")
            message_for_user = await _translate_from_en(message, user_language) if needs_translation else message
            
            # Save admin message:
            # Store the TRANSLATED version in DB (what the user will read).
            # The English original is returned in the API response for admin-side display only.
            admin_msg = AdminMessage(
                session_id=session_id,
                admin_id=admin_id,
                message=message_for_user,         # Translated (user sees this)
                created_at=datetime.utcnow()
            )
            session.add(admin_msg)
            
            # Update conversation
            conv.last_activity = datetime.utcnow()
            conv.message_count += 1
            
            await session.commit()
            
            logger.info(f"Admin {admin_id} sent message in {session_id} (user language: {user_language})")
            
            return {
                "success": True,
                "session_id": session_id,
                "message": message,                  # English (for admin display)
                "message_for_user": message_for_user, # Translated (for user display)
                "user_language": user_language,
                "translated": needs_translation,
                "timestamp": admin_msg.created_at.isoformat()
            }
            
    except Exception as e:
        logger.error(f"Error sending admin message: {str(e)}")
        return {"success": False, "error": str(e)}


async def release_conversation(
    session_id: str,
    admin_id: str,
    end_conversation: bool = False
) -> Dict:
    """
    Admin releases conversation back to AI or ends it.
    """
    try:
        async with get_async_session() as session:
            query = select(ActiveConversation).where(
                ActiveConversation.session_id == session_id
            )
            result = await session.execute(query)
            conv = result.scalar_one_or_none()
            
            if not conv:
                return {"success": False, "error": "Conversation not found"}
            
            if conv.admin_id != admin_id:
                return {"success": False, "error": "You are not assigned to this conversation"}
            
            # Update admin queue count
            admin_query = select(AdminAvailability).where(
                AdminAvailability.admin_id == admin_id
            )
            admin_result = await session.execute(admin_query)
            admin = admin_result.scalar_one_or_none()
            
            if admin and admin.current_queue_count > 0:
                admin.current_queue_count -= 1
                admin.total_queries_handled += 1
            
            # Mark queue entry as resolved
            queue_query = select(AdminQueue).where(
                and_(
                    AdminQueue.session_id == session_id,
                    AdminQueue.admin_id == admin_id,
                    AdminQueue.status == 'assigned'
                )
            ).order_by(AdminQueue.created_at.desc()).limit(1)
            queue_result = await session.execute(queue_query)
            queue_entry = queue_result.scalar_one_or_none()
            
            if queue_entry:
                queue_entry.status = 'resolved'
                queue_entry.resolved_at = datetime.utcnow()
            
            if end_conversation:
                conv.status = "ended"
                conv.ended_at = datetime.utcnow()
            else:
                # Release back to AI
                conv.admin_takeover = False
                conv.status = "active"
            
            conv.last_activity = datetime.utcnow()
            
            await session.commit()
            
            action = "ended" if end_conversation else "released to AI"
            logger.info(f"Admin {admin_id} {action} conversation {session_id}")
            
            return {
                "success": True,
                "session_id": session_id,
                "action": action
            }
            
    except Exception as e:
        logger.error(f"Error releasing conversation: {str(e)}")
        return {"success": False, "error": str(e)}


async def is_admin_takeover(session_id: str) -> tuple[bool, str]:
    """
    Check if a conversation is under admin takeover.
    Used by RAG agent to skip AI response if admin is handling.
    
    Returns:
        (is_takeover: bool, admin_id: str or None)
    """
    try:
        async with get_async_session() as session:
            query = select(ActiveConversation).where(
                ActiveConversation.session_id == session_id
            )
            result = await session.execute(query)
            conv = result.scalar_one_or_none()
            
            if conv and conv.admin_takeover:
                return (True, conv.admin_id)
            return (False, None)
            
    except Exception as e:
        logger.error(f"Error checking admin takeover: {str(e)}")
        return (False, None)
