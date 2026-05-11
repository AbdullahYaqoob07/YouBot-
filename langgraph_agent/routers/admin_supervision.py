from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from loguru import logger

from tenant_context import TenantContext, resolve_tenant_context
from app import verify_admin_key
from database.admin_queue import get_admin_queue, update_queue_status
from database.conversation import get_conversation_history as db_get_history

router = APIRouter(tags=["Admin Supervision Hand-off"])

@router.get("/conversations/{user_id}")
async def get_user_conversations(
    user_id: str, 
    limit: int = 10,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """Get conversation history for a user (admin only)"""
    try:
        history = await db_get_history(
            user_id,
            limit=limit,
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
        )
        return {"userId": user_id, "conversations": history}
    except Exception as e:
        logger.opt(exception=True).error("Error fetching conversations: {}", str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch conversations")

@router.get("/admin/queue")
async def admin_queue(
    status: Optional[str] = None,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """Get admin queue entries (admin only)"""
    try:
        queue = await get_admin_queue(
            status=status,
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
        )
        return {"queue": queue}
    except Exception as e:
        logger.opt(exception=True).error("Error fetching admin queue: {}", str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch queue")

@router.put("/admin/queue/{queue_id}")
async def update_queue(
    queue_id: int, 
    status: str, 
    admin_id: Optional[str] = None,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """Update admin queue entry (admin only)"""
    try:
        await update_queue_status(
            queue_id,
            status,
            admin_id,
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
        )
        return {"status": "updated", "queueId": queue_id}
    except Exception as e:
        logger.opt(exception=True).error("Error updating queue: {}", str(e))
        raise HTTPException(status_code=500, detail="Failed to update queue")
