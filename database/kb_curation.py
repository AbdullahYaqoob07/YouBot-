"""
Knowledge Base Curation - Database Operations
Handles unanswered questions and KB improvement workflow
"""
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy import select, and_, desc, func
from sqlalchemy import Column, Integer, String, Text, Boolean, Float, DateTime
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Base, get_async_session
from loguru import logger


class KBUnansweredQuestion(Base):
    """Unanswered questions table for KB curation"""
    __tablename__ = "kb_unanswered_questions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    
    # Question details
    user_question = Column(Text, nullable=False)
    user_language = Column(String(50))
    
    # AI's attempt
    ai_response = Column(Text)
    handoff_reason = Column(Text)
    unsolved_score = Column(Float)
    
    # Admin response
    admin_id = Column(String(255))
    admin_response = Column(Text)
    admin_responded_at = Column(DateTime)
    
    # KB curation status
    status = Column(String(50), default="pending", index=True)
    reviewed_by_admin = Column(String(255))
    reviewed_at = Column(DateTime)
    
    # KB ingestion
    added_to_kb = Column(Boolean, default=False, index=True)
    kb_document_id = Column(String(255))
    added_to_kb_at = Column(DateTime)
    added_by_admin = Column(String(255))
    
    # Metadata
    category = Column(String(100))
    tags = Column(Text)  # JSON array
    priority = Column(String(50), default="normal", index=True)
    notes = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime)


class KBUpdateHistory(Base):
    """KB update history table"""
    __tablename__ = "kb_update_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Source
    source_type = Column(String(50), nullable=False, index=True)
    source_reference_id = Column(Integer)
    
    # Content
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    language = Column(String(50))
    category = Column(String(100), index=True)
    tags = Column(Text)
    
    # Vector store
    vector_store_type = Column(String(50))
    document_id = Column(String(255))
    namespace = Column(String(255))
    
    # Metadata
    added_by_admin = Column(String(255), nullable=False, index=True)
    added_at = Column(DateTime, nullable=False, index=True)
    embedding_model = Column(String(100))
    chunk_size = Column(Integer)


async def log_unanswered_question(
    session_id: str,
    user_id: str,
    user_question: str,
    user_language: str,
    ai_response: str,
    handoff_reason: str,
    unsolved_score: float
) -> int:
    """
    Log a question that wasn't found in KB (triggered admin handoff)
    
    Returns:
        Question ID
    """
    try:
        async with get_async_session() as session:
            question = KBUnansweredQuestion(
                session_id=session_id,
                user_id=user_id,
                user_question=user_question,
                user_language=user_language,
                ai_response=ai_response,
                handoff_reason=handoff_reason,
                unsolved_score=unsolved_score,
                status="pending",
                created_at=datetime.utcnow()
            )
            
            session.add(question)
            await session.commit()
            await session.refresh(question)
            
            logger.info(f"Logged unanswered question ID: {question.id}")
            return question.id
            
    except Exception as e:
        logger.error(f"Error logging unanswered question: {str(e)}")
        return 0


async def link_admin_response(
    session_id: str,
    admin_id: str,
    admin_response: str
) -> bool:
    """
    Link admin's response to the unanswered question
    Called when admin responds to a handoff
    """
    try:
        async with get_async_session() as session:
            # Find the most recent unanswered question for this session
            query = (
                select(KBUnansweredQuestion)
                .where(
                    and_(
                        KBUnansweredQuestion.session_id == session_id,
                        KBUnansweredQuestion.admin_response.is_(None)
                    )
                )
                .order_by(desc(KBUnansweredQuestion.created_at))
                .limit(1)
            )
            
            result = await session.execute(query)
            question = result.scalar_one_or_none()
            
            if question:
                question.admin_id = admin_id
                question.admin_response = admin_response
                question.admin_responded_at = datetime.utcnow()
                question.status = "reviewed"
                question.updated_at = datetime.utcnow()
                
                await session.commit()
                logger.info(f"Linked admin response to question ID: {question.id}")
                return True
            else:
                logger.warning(f"No unanswered question found for session: {session_id}")
                return False
                
    except Exception as e:
        logger.error(f"Error linking admin response: {str(e)}")
        return False


async def get_pending_kb_curation(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None
) -> Dict:
    """
    Get questions pending KB curation review
    
    Args:
        limit: Number of items to return
        offset: Pagination offset
        status: Filter by status (pending, reviewed, approved, rejected)
        priority: Filter by priority (low, normal, high, critical)
        category: Filter by category
        
    Returns:
        Dict with items and metadata
    """
    try:
        async with get_async_session() as session:
            # Build base query
            query = select(KBUnansweredQuestion).where(
                and_(
                    KBUnansweredQuestion.admin_response.isnot(None),
                    KBUnansweredQuestion.added_to_kb == False
                )
            )
            
            # Apply filters
            if status:
                query = query.where(KBUnansweredQuestion.status == status)
            if priority:
                query = query.where(KBUnansweredQuestion.priority == priority)
            if category:
                query = query.where(KBUnansweredQuestion.category == category)
            
            # Get total count
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await session.execute(count_query)
            total = total_result.scalar()
            
            # Order by priority and creation date
            priority_order = ['critical', 'high', 'normal', 'low']
            query = query.order_by(
                desc(KBUnansweredQuestion.created_at)
            ).limit(limit).offset(offset)
            
            result = await session.execute(query)
            questions = result.scalars().all()
            
            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "items": [
                    {
                        "id": q.id,
                        "session_id": q.session_id,
                        "user_id": q.user_id,
                        "user_question": q.user_question,
                        "user_language": q.user_language,
                        "ai_response": q.ai_response,
                        "handoff_reason": q.handoff_reason,
                        "admin_id": q.admin_id,
                        "admin_response": q.admin_response,
                        "admin_responded_at": q.admin_responded_at.isoformat() if q.admin_responded_at else None,
                        "status": q.status,
                        "category": q.category,
                        "tags": q.tags,
                        "priority": q.priority,
                        "notes": q.notes,
                        "created_at": q.created_at.isoformat(),
                        "unsolved_score": q.unsolved_score
                    }
                    for q in questions
                ]
            }
            
    except Exception as e:
        logger.error(f"Error getting pending KB curation: {str(e)}")
        return {"total": 0, "items": []}


async def approve_for_kb(
    question_id: int,
    admin_id: str,
    category: Optional[str] = None,
    tags: Optional[str] = None,
    notes: Optional[str] = None,
    priority: Optional[str] = None
) -> bool:
    """
    Approve a Q&A pair for addition to KB
    
    Args:
        question_id: ID of the unanswered question
        admin_id: Admin approving the addition
        category: Category for organization
        tags: JSON array of tags
        notes: Admin notes
        priority: Priority level
        
    Returns:
        Success status
    """
    try:
        async with get_async_session() as session:
            query = select(KBUnansweredQuestion).where(
                KBUnansweredQuestion.id == question_id
            )
            
            result = await session.execute(query)
            question = result.scalar_one_or_none()
            
            if not question:
                logger.error(f"Question ID {question_id} not found")
                return False
            
            if question.added_to_kb:
                logger.warning(f"Question ID {question_id} already added to KB")
                return False
            
            # Update question
            question.status = "approved"
            question.reviewed_by_admin = admin_id
            question.reviewed_at = datetime.utcnow()
            question.updated_at = datetime.utcnow()
            
            if category:
                question.category = category
            if tags:
                question.tags = tags
            if notes:
                question.notes = notes
            if priority:
                question.priority = priority
            
            await session.commit()
            logger.info(f"Approved question ID {question_id} for KB addition")
            return True
            
    except Exception as e:
        logger.error(f"Error approving question for KB: {str(e)}")
        return False


async def reject_for_kb(
    question_id: int,
    admin_id: str,
    reason: Optional[str] = None
) -> bool:
    """
    Reject a Q&A pair from KB addition
    """
    try:
        async with get_async_session() as session:
            query = select(KBUnansweredQuestion).where(
                KBUnansweredQuestion.id == question_id
            )
            
            result = await session.execute(query)
            question = result.scalar_one_or_none()
            
            if not question:
                return False
            
            question.status = "rejected"
            question.reviewed_by_admin = admin_id
            question.reviewed_at = datetime.utcnow()
            question.updated_at = datetime.utcnow()
            
            if reason:
                question.notes = reason
            
            await session.commit()
            logger.info(f"Rejected question ID {question_id} from KB")
            return True
            
    except Exception as e:
        logger.error(f"Error rejecting question: {str(e)}")
        return False


async def mark_added_to_kb(
    question_id: int,
    faq_id: str,
    admin_id: str
) -> bool:
    """
    Mark a question as successfully added to KB
    
    Args:
        question_id: ID of the question
        faq_id: FAQ/document ID in vector store
        admin_id: Admin who performed the addition
        
    Returns:
        Success status
    """
    try:
        async with get_async_session() as session:
            query = select(KBUnansweredQuestion).where(
                KBUnansweredQuestion.id == question_id
            )
            
            result = await session.execute(query)
            question = result.scalar_one_or_none()
            
            if not question:
                return False
            
            question.added_to_kb = True
            question.kb_document_id = faq_id
            question.added_to_kb_at = datetime.utcnow()
            question.added_by_admin = admin_id
            question.status = "added_to_kb"
            question.updated_at = datetime.utcnow()
            
            await session.commit()
            logger.info(f"Marked question ID {question_id} as added to KB")
            return True
            
    except Exception as e:
        logger.error(f"Error marking question as added to KB: {str(e)}")
        return False


async def get_qa_for_ingestion(question_id: int) -> Optional[Dict]:
    """
    Get Q&A data for ingestion into knowledge base
    
    Args:
        question_id: ID of the question
        
    Returns:
        Dictionary with question, answer, category, metadata
        None if not found or not approved
    """
    try:
        async with get_async_session() as session:
            # Get question with joined admin response
            query = select(KBUnansweredQuestion).where(
                and_(
                    KBUnansweredQuestion.id == question_id,
                    KBUnansweredQuestion.status == "approved"
                )
            )
            
            result = await session.execute(query)
            question = result.scalar_one_or_none()
            
            if not question:
                logger.warning(f"Question {question_id} not found or not approved")
                return None
            
            if not question.admin_response:
                logger.warning(f"Question {question_id} has no admin response")
                return None
            
            return {
                "question": question.user_question,
                "answer": question.admin_response,
                "category": question.category,
                "language": question.user_language,
                "metadata": {
                    "question_id": question_id,
                    "session_id": question.session_id,
                    "admin_id": question.admin_id,
                    "reviewed_at": question.reviewed_at.isoformat() if question.reviewed_at else None
                }
            }
            
    except Exception as e:
        logger.error(f"Error getting Q&A for ingestion: {str(e)}")
        return None



async def log_kb_update(
    source_type: str,
    question: str,
    answer: str,
    added_by_admin: str,
    vector_store_type: str,
    document_id: str,
    source_reference_id: Optional[int] = None,
    language: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[str] = None,
    namespace: Optional[str] = None,
    embedding_model: Optional[str] = None
) -> int:
    """
    Log KB update to history
    
    Returns:
        Update history ID
    """
    try:
        async with get_async_session() as session:
            update = KBUpdateHistory(
                source_type=source_type,
                source_reference_id=source_reference_id,
                question=question,
                answer=answer,
                language=language,
                category=category,
                tags=tags,
                vector_store_type=vector_store_type,
                document_id=document_id,
                namespace=namespace,
                added_by_admin=added_by_admin,
                added_at=datetime.utcnow(),
                embedding_model=embedding_model
            )
            
            session.add(update)
            await session.commit()
            await session.refresh(update)
            
            logger.info(f"Logged KB update ID: {update.id}")
            return update.id
            
    except Exception as e:
        logger.error(f"Error logging KB update: {str(e)}")
        return 0


async def get_kb_update_history(
    limit: int = 50,
    offset: int = 0,
    source_type: Optional[str] = None,
    added_by_admin: Optional[str] = None
) -> Dict:
    """
    Get KB update history
    """
    try:
        async with get_async_session() as session:
            query = select(KBUpdateHistory)
            
            if source_type:
                query = query.where(KBUpdateHistory.source_type == source_type)
            if added_by_admin:
                query = query.where(KBUpdateHistory.added_by_admin == added_by_admin)
            
            # Get total count
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await session.execute(count_query)
            total = total_result.scalar()
            
            query = query.order_by(desc(KBUpdateHistory.added_at)).limit(limit).offset(offset)
            
            result = await session.execute(query)
            updates = result.scalars().all()
            
            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "items": [
                    {
                        "id": u.id,
                        "source_type": u.source_type,
                        "source_reference_id": u.source_reference_id,
                        "question": u.question,
                        "answer": u.answer,
                        "language": u.language,
                        "category": u.category,
                        "tags": u.tags,
                        "vector_store_type": u.vector_store_type,
                        "document_id": u.document_id,
                        "added_by_admin": u.added_by_admin,
                        "added_at": u.added_at.isoformat()
                    }
                    for u in updates
                ]
            }
            
    except Exception as e:
        logger.error(f"Error getting KB update history: {str(e)}")
        return {"total": 0, "items": []}
