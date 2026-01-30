"""
Analytics Database Operations
"""
from datetime import datetime
from typing import Optional
from database.models import AnalyticsEvent, get_async_session
from loguru import logger


async def log_analytics_event(
    event_type: str,
    session_id: str,
    user_id: str,
    language: Optional[str] = None,
    channel: Optional[str] = None,
    sentiment: Optional[str] = None,
    model_used: Optional[str] = None,
    response_time_ms: Optional[int] = None,
    knowledge_base_used: bool = False,
    resolved_by_ai: bool = False,
    handed_to_human: bool = False,
    unsolved_score: Optional[float] = None
):
    """
    Log analytics event
    
    Args:
        event_type: Type of event (query_processed, query_handed_to_human, etc.)
        session_id: Session identifier
        user_id: User identifier
        language: Detected language
        channel: Communication channel
        sentiment: Sentiment analysis result
        model_used: LLM model used
        response_time_ms: Response time in milliseconds
        knowledge_base_used: Whether knowledge base was used
        resolved_by_ai: Whether AI resolved the query
        handed_to_human: Whether handed to human
        unsolved_score: Confidence score for unresolved queries
    """
    try:
        async with get_async_session() as session:
            event = AnalyticsEvent(
                event_type=event_type,
                session_id=session_id,
                user_id=user_id,
                language=language,
                channel=channel,
                sentiment=sentiment,
                model_used=model_used,
                response_time_ms=response_time_ms,
                knowledge_base_used=knowledge_base_used,
                resolved_by_ai=resolved_by_ai,
                handed_to_human=handed_to_human,
                unsolved_score=unsolved_score,
                timestamp=datetime.utcnow()
            )
            
            session.add(event)
            await session.commit()
            
            logger.info(f"Logged analytics event: {event_type}")
            
    except Exception as e:
        logger.error(f"Error logging analytics: {str(e)}")
        # Don't raise - analytics logging should not break the workflow
