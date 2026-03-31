"""
Database Models using SQLAlchemy
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, Float, DateTime, ForeignKey, JSON
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from contextlib import asynccontextmanager
from config import settings

Base = declarative_base()


class ConversationLog(Base):
    """Conversation logs table"""
    __tablename__ = "conversation_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    user_message = Column(Text, nullable=False)
    assistant_response = Column(Text, nullable=False)
    language = Column(String(50))
    channel = Column(String(50))
    sentiment = Column(String(50), default="neutral")
    resolved = Column(Boolean, default=False)
    handed_to_human = Column(Boolean, default=False)
    model_used = Column(String(100))
    knowledge_base_used = Column(Boolean, default=False)
    action_items = Column(Text)
    handoff_reason = Column(Text)
    unsolved_score = Column(Float)
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime)


class AdminAvailability(Base):
    """Admin availability table"""
    __tablename__ = "admin_availability"
    
    admin_id = Column(String(255), primary_key=True)
    admin_name = Column(String(255), nullable=False)
    admin_email = Column(String(255), nullable=False)
    role = Column(String(50), default="admin", index=True)  # 'admin' or 'super_admin'
    status = Column(String(50), nullable=False, default="offline", index=True)
    current_queue_count = Column(Integer, default=0)
    max_queue_size = Column(Integer, default=10)
    last_assigned_at = Column(DateTime)
    total_queries_handled = Column(Integer, default=0)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime)


class AdminQueue(Base):
    """Admin queue table"""
    __tablename__ = "admin_queue"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False)
    user_id = Column(String(255), nullable=False)
    admin_id = Column(String(255), ForeignKey("admin_availability.admin_id"))
    user_message = Column(Text, nullable=False)
    ai_response = Column(Text)
    status = Column(String(50), default="pending", index=True)
    priority = Column(String(50), default="normal")
    language = Column(String(50))
    channel = Column(String(50))
    handoff_reason = Column(Text)
    unsolved_score = Column(Float)
    assigned_at = Column(DateTime)
    resolved_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime)


class AnalyticsEvent(Base):
    """Analytics events table"""
    __tablename__ = "analytics_events"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(100), nullable=False, index=True)
    session_id = Column(String(255))
    user_id = Column(String(255))
    language = Column(String(50))
    channel = Column(String(50))
    sentiment = Column(String(50))
    model_used = Column(String(100))
    response_time_ms = Column(Integer)
    knowledge_base_used = Column(Boolean, default=False)
    resolved_by_ai = Column(Boolean, default=False)
    handed_to_human = Column(Boolean, default=False)
    unsolved_score = Column(Float)
    timestamp = Column(DateTime, nullable=False, index=True)


class ActiveConversation(Base):
    """
    Track all active conversations for admin supervision.
    Every conversation is logged here for real-time monitoring.
    """
    __tablename__ = "active_conversations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False, unique=True, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    channel = Column(String(50))
    language = Column(String(50))
    
    # Conversation status
    status = Column(String(50), default="active", index=True)  # active, admin_watching, admin_takeover, ended
    is_supervised = Column(Boolean, default=True)  # All conversations supervised by default
    
    # Admin intervention
    admin_id = Column(String(255), ForeignKey("admin_availability.admin_id"), nullable=True)
    admin_takeover = Column(Boolean, default=False)  # True if admin has taken over
    takeover_reason = Column(Text, nullable=True)
    takeover_at = Column(DateTime, nullable=True)
    
    # Super admin intervention (NEW)
    super_admin_id = Column(String(255), ForeignKey("admin_availability.admin_id"), nullable=True)
    previous_admin_id = Column(String(255), nullable=True)
    super_admin_takeover = Column(Boolean, default=False)
    super_admin_takeover_at = Column(DateTime, nullable=True)
    
    # AI handoff (when AI triggers handoff)
    ai_triggered_handoff = Column(Boolean, default=False)
    handoff_reason = Column(Text, nullable=True)
    
    # Message counts
    message_count = Column(Integer, default=0)
    last_message = Column(Text)
    last_ai_response = Column(Text)
    
    # Timestamps
    started_at = Column(DateTime, nullable=False)
    last_activity = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)


class AdminMessage(Base):
    """
    Messages sent by admin during intervention.
    Separate from AI responses so we can track admin vs AI messages.
    """
    __tablename__ = "admin_messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False, index=True)
    admin_id = Column(String(255), ForeignKey("admin_availability.admin_id"), nullable=False)
    message = Column(Text, nullable=False)
    is_super_admin = Column(Boolean, default=False)  # Track if message from super admin
    created_at = Column(DateTime, nullable=False)


# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    echo=settings.DEBUG
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


@asynccontextmanager
async def get_async_session():
    """Get async database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
