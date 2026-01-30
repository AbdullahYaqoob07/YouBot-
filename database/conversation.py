"""
Conversation Database Operations
"""
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy import select, desc
from database.models import ConversationLog, get_async_session
from loguru import logger


async def get_conversation_history(
    user_id: str,
    limit: int = 10
) -> List[Dict]:
    """
    Get conversation history for a user
    
    Args:
        user_id: User identifier
        limit: Number of conversations to retrieve
        
    Returns:
        List of conversation messages
    """
    try:
        async with get_async_session() as session:
            query = (
                select(ConversationLog)
                .where(ConversationLog.user_id == user_id)
                .order_by(desc(ConversationLog.created_at))
                .limit(limit)
            )
            
            result = await session.execute(query)
            conversations = result.scalars().all()
            
            return [
                {
                    "user_message": conv.user_message,
                    "assistant_response": conv.assistant_response,
                    "created_at": conv.created_at,
                    "language": conv.language,
                    "sentiment": conv.sentiment
                }
                for conv in reversed(conversations)  # Oldest first
            ]
            
    except Exception as e:
        logger.error(f"Error fetching conversation history: {str(e)}")
        return []


async def save_conversation(
    session_id: str,
    user_id: str,
    user_message: str,
    assistant_response: str,
    language: Optional[str] = None,
    channel: Optional[str] = None,
    sentiment: str = "neutral",
    resolved: bool = False,
    handed_to_human: bool = False,
    model_used: Optional[str] = None,
    knowledge_base_used: bool = False,
    handoff_reason: Optional[str] = None,
    unsolved_score: Optional[float] = None
):
    """
    Save conversation to database
    
    Args:
        session_id: Session identifier
        user_id: User identifier
        user_message: User's message
        assistant_response: AI's response
        language: Detected language
        channel: Communication channel
        sentiment: Sentiment analysis result
        resolved: Whether query was resolved
        handed_to_human: Whether handed to human
        model_used: LLM model used
        knowledge_base_used: Whether knowledge base was used
        handoff_reason: Reason for handoff
        unsolved_score: Confidence score for unresolved queries
    """
    try:
        async with get_async_session() as session:
            conversation = ConversationLog(
                session_id=session_id,
                user_id=user_id,
                user_message=user_message,
                assistant_response=assistant_response,
                language=language,
                channel=channel,
                sentiment=sentiment,
                resolved=resolved,
                handed_to_human=handed_to_human,
                model_used=model_used,
                knowledge_base_used=knowledge_base_used,
                handoff_reason=handoff_reason,
                unsolved_score=unsolved_score,
                created_at=datetime.utcnow()
            )
            
            session.add(conversation)
            await session.commit()
            
            logger.info(f"Saved conversation for user {user_id}")
            
    except Exception as e:
        logger.error(f"Error saving conversation: {str(e)}")
        raise
