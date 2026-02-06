"""
Admin Queue Database Operations
"""
from datetime import datetime
from typing import Optional, Dict, List
from sqlalchemy import select, and_
from database.models import AdminQueue, AdminAvailability, get_async_session
from loguru import logger


async def assign_to_admin(
    session_id: str,
    user_id: str,
    user_message: str,
    ai_response: str,
    language: str,
    channel: str,
    handoff_reason: str,
    unsolved_score: float
) -> Optional[Dict]:
    """
    Assign query to available admin using ROUND-ROBIN LOAD BALANCING
    
    Algorithm:
    1. Find all admins with status='online'
    2. Filter admins with current_queue_count < max_queue_size
    3. Sort by current_queue_count (ascending) - least loaded first
    4. Assign to admin with lowest queue count
    5. Increment admin's queue count
    6. If no admin available, add to pending queue
    
    This ensures fair distribution of queries across available admins.
    
    Args:
        session_id: Session identifier
        user_id: User identifier
        user_message: User's message
        ai_response: AI's response
        language: Detected language
        channel: Communication channel
        handoff_reason: Reason for handoff
        unsolved_score: Confidence score
        
    Returns:
        Admin info dict if assigned, None otherwise
    """
    try:
        async with get_async_session() as session:
            # Use a short transaction & row-level lock to avoid race conditions
            assigned_admin = None
            async with session.begin():
                # Select a candidate admin and lock the row for update
                query = (
                    select(AdminAvailability)
                    .where(
                        and_(
                            AdminAvailability.status == 'online',
                            AdminAvailability.current_queue_count < AdminAvailability.max_queue_size
                        )
                    )
                    .order_by(AdminAvailability.current_queue_count, AdminAvailability.last_assigned_at)
                    .limit(1)
                    .with_for_update()
                )

                result = await session.execute(query)
                admin = result.scalar_one_or_none()

                if admin:
                    # Update admin counters and insert assigned queue entry atomically
                    admin.current_queue_count += 1
                    admin.last_assigned_at = datetime.utcnow()

                    queue_entry = AdminQueue(
                        session_id=session_id,
                        user_id=user_id,
                        admin_id=admin.admin_id,
                        user_message=user_message,
                        ai_response=ai_response,
                        status='assigned',
                        priority='normal',
                        language=language,
                        channel=channel,
                        handoff_reason=handoff_reason,
                        unsolved_score=unsolved_score,
                        assigned_at=datetime.utcnow(),
                        created_at=datetime.utcnow()
                    )
                    session.add(queue_entry)

                    assigned_admin = {
                        "admin_id": admin.admin_id,
                        "admin_name": admin.admin_name,
                        "admin_email": admin.admin_email
                    }
                    logger.info(f"Assigned to admin {admin.admin_name}")
                else:
                    # No admin available - insert pending queue entry
                    queue_entry = AdminQueue(
                        session_id=session_id,
                        user_id=user_id,
                        user_message=user_message,
                        ai_response=ai_response,
                        status='pending',
                        priority='normal',
                        language=language,
                        channel=channel,
                        handoff_reason=handoff_reason,
                        unsolved_score=unsolved_score,
                        created_at=datetime.utcnow()
                    )
                    session.add(queue_entry)
                    logger.warning("No admin available - added to pending queue")

            # transaction committed here
            return assigned_admin
            
    except Exception as e:
        logger.error(f"Error assigning to admin: {str(e)}")
        return None


async def get_admin_queue(status: Optional[str] = None) -> List[Dict]:
    """
    Get admin queue entries
    
    Args:
        status: Filter by status (pending, assigned, resolved)
        
    Returns:
        List of queue entries
    """
    try:
        async with get_async_session() as session:
            query = select(AdminQueue)
            
            if status:
                query = query.where(AdminQueue.status == status)
            
            query = query.order_by(AdminQueue.created_at.desc())
            
            result = await session.execute(query)
            entries = result.scalars().all()
            
            return [
                {
                    "id": entry.id,
                    "session_id": entry.session_id,
                    "user_id": entry.user_id,
                    "admin_id": entry.admin_id,
                    "user_message": entry.user_message,
                    "status": entry.status,
                    "priority": entry.priority,
                    "language": entry.language,
                    "handoff_reason": entry.handoff_reason,
                    "created_at": entry.created_at.isoformat() if entry.created_at else None
                }
                for entry in entries
            ]
            
    except Exception as e:
        logger.error(f"Error fetching admin queue: {str(e)}")
        return []


async def update_queue_status(
    queue_id: int,
    status: str,
    admin_id: Optional[str] = None
):
    """
    Update queue entry status
    
    Args:
        queue_id: Queue entry ID
        status: New status
        admin_id: Admin ID (for assignment)
    """
    try:
        async with get_async_session() as session:
            query = select(AdminQueue).where(AdminQueue.id == queue_id)
            result = await session.execute(query)
            entry = result.scalar_one_or_none()
            
            if entry:
                entry.status = status
                if admin_id:
                    entry.admin_id = admin_id
                    entry.assigned_at = datetime.utcnow()
                if status == 'resolved':
                    entry.resolved_at = datetime.utcnow()
                
                await session.commit()
                logger.info(f"Updated queue entry {queue_id} to status {status}")
                
    except Exception as e:
        logger.error(f"Error updating queue status: {str(e)}")
        raise
