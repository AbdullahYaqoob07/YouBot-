"""
Super Admin Database Operations
Handles super admin dashboard, monitoring, and takeover functionality
"""
from datetime import datetime
from typing import Optional, Dict, List
from sqlalchemy import select, and_, or_, text, func
from database.models import (
    AdminAvailability, 
    AdminQueue, 
    ActiveConversation,
    AdminMessage,
    get_async_session
)
from loguru import logger


async def verify_super_admin(admin_id: str) -> bool:
    """
    Verify if admin has super_admin role
    
    Args:
        admin_id: Admin identifier
        
    Returns:
        True if super admin, False otherwise
    """
    try:
        async with get_async_session() as session:
            query = select(AdminAvailability).where(
                and_(
                    AdminAvailability.admin_id == admin_id,
                    AdminAvailability.role == 'super_admin'
                )
            )
            result = await session.execute(query)
            admin = result.scalar_one_or_none()
            return admin is not None
    except Exception as e:
        logger.error(f"Error verifying super admin: {str(e)}")
        return False


async def get_all_admin_stats() -> List[Dict]:
    """
    Get statistics for all admins (workload, queries handled, etc.)
    
    Returns:
        List of admin stats dictionaries
    """
    try:
        async with get_async_session() as session:
            # Use the view created in super_admin_schema.sql
            query = text("""
                SELECT 
                    admin_id,
                    admin_name,
                    admin_email,
                    role,
                    status,
                    current_queue_count,
                    max_queue_size,
                    total_queries_handled,
                    active_conversations,
                    assigned_queries,
                    pending_queries,
                    avg_resolution_time_minutes,
                    last_assigned_at
                FROM v_super_admin_dashboard
            """)
            
            result = await session.execute(query)
            rows = result.fetchall()
            
            return [
                {
                    "admin_id": row[0],
                    "admin_name": row[1],
                    "admin_email": row[2],
                    "role": row[3],
                    "status": row[4],
                    "current_queue_count": row[5],
                    "max_queue_size": row[6],
                    "total_queries_handled": row[7],
                    "active_conversations": row[8],
                    "assigned_queries": row[9],
                    "pending_queries": row[10],
                    "avg_resolution_time_minutes": float(row[11]) if row[11] else 0.0,
                    "last_assigned_at": row[12].isoformat() if row[12] else None
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Error getting admin stats: {str(e)}")
        return []


async def get_all_conversations_monitor() -> List[Dict]:
    """
    Get all active conversations across all admins for monitoring
    
    Returns:
        List of conversation dictionaries
    """
    try:
        async with get_async_session() as session:
            query = text("""
                SELECT 
                    id,
                    session_id,
                    user_id,
                    channel,
                    language,
                    status,
                    admin_id,
                    admin_name,
                    admin_role,
                    super_admin_id,
                    super_admin_name,
                    previous_admin_id,
                    previous_admin_name,
                    admin_takeover,
                    super_admin_takeover,
                    message_count,
                    last_message,
                    last_ai_response,
                    started_at,
                    last_activity,
                    takeover_at,
                    super_admin_takeover_at,
                    duration_minutes
                FROM v_all_conversations_monitor
                LIMIT 100
            """)
            
            result = await session.execute(query)
            rows = result.fetchall()
            
            return [
                {
                    "id": row[0],
                    "session_id": row[1],
                    "user_id": row[2],
                    "channel": row[3],
                    "language": row[4],
                    "status": row[5],
                    "admin_id": row[6],
                    "admin_name": row[7],
                    "admin_role": row[8],
                    "super_admin_id": row[9],
                    "super_admin_name": row[10],
                    "previous_admin_id": row[11],
                    "previous_admin_name": row[12],
                    "admin_takeover": bool(row[13]),
                    "super_admin_takeover": bool(row[14]),
                    "message_count": row[15],
                    "last_message": row[16],
                    "last_ai_response": row[17],
                    "started_at": row[18].isoformat() if row[18] else None,
                    "last_activity": row[19].isoformat() if row[19] else None,
                    "takeover_at": row[20].isoformat() if row[20] else None,
                    "super_admin_takeover_at": row[21].isoformat() if row[21] else None,
                    "duration_minutes": row[22]
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Error getting conversations monitor: {str(e)}")
        return []


async def super_admin_takeover(
    super_admin_id: str,
    session_id: str,
    reason: str = "Super admin intervention"
) -> Dict:
    """
    Super admin takes over a conversation from current admin
    
    Args:
        super_admin_id: Super admin identifier
        session_id: Conversation session ID
        reason: Reason for takeover
        
    Returns:
        Result dictionary
    """
    try:
        async with get_async_session() as session:
            async with session.begin():
                # Get conversation with lock
                query = (
                    select(ActiveConversation)
                    .where(ActiveConversation.session_id == session_id)
                    .with_for_update()
                )
                result = await session.execute(query)
                conversation = result.scalar_one_or_none()
                
                if not conversation:
                    return {
                        "success": False,
                        "message": "Conversation not found"
                    }
                
                # Store previous admin
                previous_admin_id = conversation.admin_id
                
                # Update conversation
                conversation.previous_admin_id = previous_admin_id
                conversation.super_admin_id = super_admin_id
                conversation.super_admin_takeover = 1
                conversation.super_admin_takeover_at = datetime.utcnow()
                conversation.takeover_reason = reason
                conversation.admin_id = super_admin_id  # Super admin becomes current handler
                conversation.last_activity = datetime.utcnow()
                
                # If there was a previous admin, decrement their queue count
                if previous_admin_id:
                    admin_query = select(AdminAvailability).where(
                        AdminAvailability.admin_id == previous_admin_id
                    )
                    admin_result = await session.execute(admin_query)
                    prev_admin = admin_result.scalar_one_or_none()
                    
                    if prev_admin and prev_admin.current_queue_count > 0:
                        prev_admin.current_queue_count -= 1
                
                # Increment super admin queue count
                super_admin_query = select(AdminAvailability).where(
                    AdminAvailability.admin_id == super_admin_id
                )
                super_admin_result = await session.execute(super_admin_query)
                super_admin = super_admin_result.scalar_one_or_none()
                
                if super_admin:
                    super_admin.current_queue_count += 1
                
                # Log audit trail
                audit_query = text("""
                    INSERT INTO super_admin_audit_log 
                    (super_admin_id, action, target_entity_type, conversation_id, previous_admin_id, details, created_at)
                    VALUES (:super_admin_id, 'takeover', 'conversation', :conversation_id, :previous_admin_id, :details, NOW())
                """)
                await session.execute(audit_query, {
                    "super_admin_id": super_admin_id,
                    "conversation_id": session_id,
                    "previous_admin_id": previous_admin_id,
                    "details": reason
                })
                
            logger.info(f"Super admin {super_admin_id} took over conversation {session_id} from {previous_admin_id}")
            return {
                "success": True,
                "message": "Takeover successful",
                "previous_admin_id": previous_admin_id,
                "super_admin_id": super_admin_id
            }
            
    except Exception as e:
        logger.error(f"Error in super admin takeover: {str(e)}")
        return {
            "success": False,
            "message": f"Takeover failed: {str(e)}"
        }


async def super_admin_release(
    super_admin_id: str,
    session_id: str,
    return_to_previous: bool = True
) -> Dict:
    """
    Super admin releases a conversation back to previous admin or ends it
    
    Args:
        super_admin_id: Super admin identifier
        session_id: Conversation session ID
        return_to_previous: If True, return to previous admin; if False, end conversation
        
    Returns:
        Result dictionary
    """
    try:
        async with get_async_session() as session:
            async with session.begin():
                # Get conversation with lock
                query = (
                    select(ActiveConversation)
                    .where(ActiveConversation.session_id == session_id)
                    .with_for_update()
                )
                result = await session.execute(query)
                conversation = result.scalar_one_or_none()
                
                if not conversation:
                    return {
                        "success": False,
                        "message": "Conversation not found"
                    }
                
                if conversation.super_admin_id != super_admin_id:
                    return {
                        "success": False,
                        "message": "This conversation is not assigned to you"
                    }
                
                previous_admin_id = conversation.previous_admin_id
                
                # Decrement super admin queue count
                super_admin_query = select(AdminAvailability).where(
                    AdminAvailability.admin_id == super_admin_id
                )
                super_admin_result = await session.execute(super_admin_query)
                super_admin = super_admin_result.scalar_one_or_none()
                
                if super_admin and super_admin.current_queue_count > 0:
                    super_admin.current_queue_count -= 1
                    super_admin.total_queries_handled += 1
                
                # Mark queue entry as resolved
                queue_query = select(AdminQueue).where(
                    and_(
                        AdminQueue.session_id == session_id,
                        AdminQueue.admin_id == super_admin_id,
                        AdminQueue.status == 'assigned'
                    )
                ).order_by(AdminQueue.created_at.desc()).limit(1)
                queue_result = await session.execute(queue_query)
                queue_entry = queue_result.scalar_one_or_none()
                
                if queue_entry:
                    queue_entry.status = 'resolved'
                    queue_entry.resolved_at = datetime.utcnow()
                
                if return_to_previous and previous_admin_id:
                    # Return to previous admin
                    conversation.admin_id = previous_admin_id
                    conversation.super_admin_id = None
                    conversation.super_admin_takeover = 0
                    conversation.last_activity = datetime.utcnow()
                    
                    # Increment previous admin queue count
                    prev_admin_query = select(AdminAvailability).where(
                        AdminAvailability.admin_id == previous_admin_id
                    )
                    prev_admin_result = await session.execute(prev_admin_query)
                    prev_admin = prev_admin_result.scalar_one_or_none()
                    
                    if prev_admin:
                        prev_admin.current_queue_count += 1
                    
                    message = f"Conversation returned to {previous_admin_id}"
                else:
                    # End conversation
                    conversation.status = 'ended'
                    conversation.ended_at = datetime.utcnow()
                    conversation.super_admin_id = None
                    conversation.super_admin_takeover = 0
                    message = "Conversation ended"
                
                # Log audit trail
                audit_query = text("""
                    INSERT INTO super_admin_audit_log 
                    (super_admin_id, action, target_entity_type, conversation_id, previous_admin_id, details, created_at)
                    VALUES (:super_admin_id, 'release', 'conversation', :conversation_id, :previous_admin_id, :details, NOW())
                """)
                await session.execute(audit_query, {
                    "super_admin_id": super_admin_id,
                    "conversation_id": session_id,
                    "previous_admin_id": previous_admin_id,
                    "details": message
                })
                
            logger.info(f"Super admin {super_admin_id} released conversation {session_id}")
            return {
                "success": True,
                "message": message
            }
            
    except Exception as e:
        logger.error(f"Error in super admin release: {str(e)}")
        return {
            "success": False,
            "message": f"Release failed: {str(e)}"
        }


async def get_query_distribution() -> Dict:
    """
    Get query distribution statistics across all admins
    
    Returns:
        Distribution statistics dictionary
    """
    try:
        async with get_async_session() as session:
            # Total queries by admin (last 24 hours)
            query = text("""
                SELECT 
                    aa.admin_id,
                    aa.admin_name,
                    aa.role,
                    aa.status,
                    COUNT(aq.id) as total_queries,
                    COUNT(CASE WHEN aq.status = 'assigned' THEN 1 END) as active_queries,
                    COUNT(CASE WHEN aq.status = 'resolved' THEN 1 END) as resolved_queries,
                    AVG(CASE WHEN aq.resolved_at IS NOT NULL 
                        THEN TIMESTAMPDIFF(MINUTE, aq.assigned_at, aq.resolved_at) 
                        END) as avg_resolution_minutes
                FROM admin_availability aa
                LEFT JOIN admin_queue aq ON aa.admin_id = aq.admin_id 
                    AND aq.created_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
                GROUP BY aa.admin_id, aa.admin_name, aa.role, aa.status
                ORDER BY total_queries DESC
            """)
            
            result = await session.execute(query)
            rows = result.fetchall()
            
            distribution = [
                {
                    "admin_id": row[0],
                    "admin_name": row[1],
                    "role": row[2],
                    "status": row[3],
                    "total_queries": row[4],
                    "active_queries": row[5],
                    "resolved_queries": row[6],
                    "avg_resolution_minutes": float(row[7]) if row[7] else 0.0
                }
                for row in rows
            ]
            
            # Get pending count
            pending_query = text("SELECT COUNT(*) FROM admin_queue WHERE status = 'pending'")
            pending_result = await session.execute(pending_query)
            pending_count = pending_result.scalar()
            
            return {
                "distribution": distribution,
                "pending_queries": pending_count,
                "total_online_admins": sum(1 for d in distribution if d["status"] == "online"),
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Error getting query distribution: {str(e)}")
        return {
            "distribution": [],
            "pending_queries": 0,
            "total_online_admins": 0,
            "error": str(e)
        }


async def reassign_conversation(
    super_admin_id: str,
    session_id: str,
    target_admin_id: str,
    reason: str = "Super admin reassignment"
) -> dict:
    """
    Super admin manually reassigns a conversation to a different admin.

    Args:
        super_admin_id: Super admin performing the reassignment
        session_id: Conversation session ID
        target_admin_id: Admin to reassign the conversation to
        reason: Reason for reassignment

    Returns:
        Result dictionary
    """
    try:
        async with get_async_session() as session:
            async with session.begin():
                # Get conversation
                conv_query = (
                    select(ActiveConversation)
                    .where(ActiveConversation.session_id == session_id)
                    .with_for_update()
                )
                conv_result = await session.execute(conv_query)
                conversation = conv_result.scalar_one_or_none()

                if not conversation:
                    return {"success": False, "message": "Conversation not found"}

                # Get target admin
                target_query = select(AdminAvailability).where(
                    AdminAvailability.admin_id == target_admin_id
                )
                target_result = await session.execute(target_query)
                target_admin = target_result.scalar_one_or_none()

                if not target_admin:
                    return {"success": False, "message": f"Admin '{target_admin_id}' not found"}

                previous_admin_id = conversation.admin_id

                # Decrement previous admin queue count
                if previous_admin_id and previous_admin_id != target_admin_id:
                    prev_query = select(AdminAvailability).where(
                        AdminAvailability.admin_id == previous_admin_id
                    )
                    prev_result = await session.execute(prev_query)
                    prev_admin = prev_result.scalar_one_or_none()
                    if prev_admin and prev_admin.current_queue_count > 0:
                        prev_admin.current_queue_count -= 1

                # Assign to target admin
                conversation.admin_id = target_admin_id
                conversation.admin_takeover = 1
                conversation.takeover_at = datetime.utcnow()
                conversation.takeover_reason = reason
                # Clear any super admin takeover state
                conversation.super_admin_takeover = 0
                conversation.super_admin_id = None
                conversation.last_activity = datetime.utcnow()

                # Increment target admin queue count
                target_admin.current_queue_count += 1
                target_admin.last_assigned_at = datetime.utcnow()

                # Update or create queue entry for the target admin
                queue_query = (
                    select(AdminQueue)
                    .where(
                        and_(
                            AdminQueue.session_id == session_id,
                            AdminQueue.status == 'assigned'
                        )
                    )
                    .order_by(AdminQueue.created_at.desc())
                    .limit(1)
                )
                queue_result = await session.execute(queue_query)
                queue_entry = queue_result.scalar_one_or_none()

                if queue_entry:
                    # Reassign the existing active queue entry
                    queue_entry.admin_id = target_admin_id
                    queue_entry.assigned_at = datetime.utcnow()
                else:
                    # Create a new queue entry for the target admin
                    new_entry = AdminQueue(
                        session_id=session_id,
                        admin_id=target_admin_id,
                        status='assigned',
                        assigned_at=datetime.utcnow(),
                        reason=reason
                    )
                    session.add(new_entry)

                # Log audit trail
                audit_query = text("""
                    INSERT INTO super_admin_audit_log
                    (super_admin_id, action, target_entity_type, conversation_id, previous_admin_id, details, created_at)
                    VALUES (:super_admin_id, 'reassign', 'conversation', :conversation_id, :previous_admin_id, :details, NOW())
                """)
                await session.execute(audit_query, {
                    "super_admin_id": super_admin_id,
                    "conversation_id": session_id,
                    "previous_admin_id": previous_admin_id,
                    "details": f"Reassigned from {previous_admin_id} to {target_admin_id}. Reason: {reason}"
                })

        logger.info(f"Super admin {super_admin_id} reassigned {session_id} from {previous_admin_id} to {target_admin_id}")
        return {
            "success": True,
            "message": f"Conversation reassigned to {target_admin_id}",
            "previous_admin_id": previous_admin_id,
            "target_admin_id": target_admin_id
        }

    except Exception as e:
        logger.error(f"Error reassigning conversation: {str(e)}")
        return {"success": False, "message": f"Reassignment failed: {str(e)}"}
