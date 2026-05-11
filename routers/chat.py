from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from typing import Optional
from loguru import logger
import time
import re

from app import verify_api_key, verify_client_key, limiter, clean_markup
from tenant_context import TenantContext, resolve_tenant_context
from database.models import ClientApiKey
from config import settings

from graph import process_message, resume_conversation, get_conversation_state
from app import MessageRequest, MessageResponse
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "ai_agent_chat_request_count", 
    "Total number of requests", 
    ["method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "ai_agent_chat_request_latency_seconds", 
    "Request latency in seconds",
    ["method", "endpoint"]
)

router = APIRouter(tags=["Chat APIs"])

@router.get("/chat/{session_id}/history")
async def get_chat_history(
    session_id: str,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    api_key: str = Depends(verify_api_key)
):
    """
    Get conversation history for polling by user frontend.
    """
    try:
        from database.supervision import get_conversation_messages
        conversation = await get_conversation_messages(
            session_id,
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
        )
        return conversation
    except Exception as e:
        logger.opt(exception=True).error("Error fetching history: {}")
        raise HTTPException(status_code=500, detail="Failed to fetch history")

@router.post("/v1/chat", response_model=MessageResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def client_chat_handler(
    request: Request,
    message_request: MessageRequest,
    background_tasks: BackgroundTasks,
    client_key: ClientApiKey = Depends(verify_client_key)
):
    """
    Generic chat endpoint for external clients (Web Widgets, Mobile Apps).
    """
    start_time = time.time()
    
    try:
        tenant_id = client_key.tenant_id
        workspace_id = client_key.workspace_id

        if message_request.sessionId:
            session_id = message_request.sessionId
        else:
            safe_tenant = re.sub(r"[^A-Za-z0-9_-]", "_", tenant_id)
            safe_workspace = re.sub(r"[^A-Za-z0-9_-]", "_", workspace_id)
            safe_user = re.sub(r"[^A-Za-z0-9_-]", "_", message_request.userId)
            session_id = f"sess_{safe_tenant}_{safe_workspace}_{message_request.channel}_{safe_user}_{int(time.time())}"
        
        logger.info(
            f"Processing message via POST /v1/chat from {message_request.userId} via {message_request.channel} "
            f"for tenant={tenant_id}, workspace={workspace_id}"
        )
        
        final_state = await process_message(
            message=message_request.message,
            user_id=message_request.userId,
            session_id=session_id,
            channel=message_request.channel,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            retrieval_mode_override=message_request.retrievalMode,
        )
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        # Priority: explicit ai_response from state, fallback to last message in thread
        ai_response = final_state.get('ai_response')
        if not ai_response:
            session_messages = final_state.get('messages', [])
            ai_response = session_messages[-1].content if session_messages else ""
        
        from database.metrics import track_conversation_metrics
        background_tasks.add_task(
            track_conversation_metrics,
            session_id=session_id,
            user_id=message_request.userId,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_message=message_request.message,
            ai_response=ai_response,
            language=final_state.get('detected_language'),
            channel=message_request.channel,
            sentiment=final_state.get('sentiment'),
            model_used=final_state.get('model_used'),
            response_time_ms=processing_time_ms,
            knowledge_base_used=bool(final_state.get('knowledge_base_used', False)),
            resolved_by_ai=not final_state.get('requires_human', False),
            handed_to_human=final_state.get('requires_human', False),
            assigned_admin=final_state.get('assigned_admin_id') if final_state.get('requires_human') else None,
            unsolved_score=1.0 - final_state.get('classification_confidence', 0.5)
        )
        
        queue_status = None
        if final_state.get('requires_human') and not final_state.get('assigned_admin_id'):
            queue_status = "pending"
        elif final_state.get('assigned_admin_id'):
            queue_status = "assigned"

        return MessageResponse(
            status="success",
            message=ai_response,
            sessionId=session_id,
            language=final_state.get('detected_language'),
            handoff=final_state.get('requires_human', False),
            modelUsed=final_state.get('model_used'),
            retrievalMode=final_state.get('retrieval_mode_selected'),
            assignedTo=final_state.get('assigned_admin_name') if final_state.get('requires_human') else None,
            queueStatus=queue_status,
            processingTimeMs=processing_time_ms
        )
    except Exception as e:
        logger.error(f"Error processing generic client chat: {str(e)}", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/webhook/ai-agent", response_model=MessageResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def webhook_handler(
    request: Request,
    message_request: MessageRequest,
    background_tasks: BackgroundTasks,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    api_key: str = Depends(verify_api_key)
):
    """
    Main webhook endpoint for processing messages
    """
    start_time = time.time()
    
    try:
        tenant_id = message_request.tenantId or tenant_context.tenant_id
        workspace_id = message_request.workspaceId or tenant_context.workspace_id

        if message_request.sessionId:
            session_id = message_request.sessionId
        else:
            safe_tenant = re.sub(r"[^A-Za-z0-9_-]", "_", tenant_id)
            safe_workspace = re.sub(r"[^A-Za-z0-9_-]", "_", workspace_id)
            safe_user = re.sub(r"[^A-Za-z0-9_-]", "_", message_request.userId)
            session_id = f"sess_{safe_tenant}_{safe_workspace}_{message_request.channel}_{safe_user}_{int(time.time())}"
        
        logger.info(
            f"Processing message from {message_request.userId} via {message_request.channel} "
            f"for tenant={tenant_id}, workspace={workspace_id}"
        )
        
        final_state = await process_message(
            message=message_request.message,
            user_id=message_request.userId,
            session_id=session_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            channel=message_request.channel,
            user_name=message_request.userName,
            user_email=message_request.userEmail,
            user_phone=message_request.userPhone,
            retrieval_mode_override=message_request.retrievalMode,
        )
        
        processing_time = (time.time() - start_time)
        processing_time_ms = int(processing_time * 1000)
        
        REQUEST_COUNT.labels(method="POST", endpoint="/webhook/ai-agent", status="success").inc()
        REQUEST_LATENCY.labels(method="POST", endpoint="/webhook/ai-agent").observe(processing_time)
        
        from nodes.admin_handler import log_conversation_node
        async def background_log():
            try:
                await log_conversation_node(final_state)
                logger.opt(exception=True).debug("Background logging completed for {message_request.userId}")
            except Exception as log_error:
                logger.error(f"Background logging failed: {str(log_error)}")
        
        background_tasks.add_task(background_log)
        
        if final_state.get("ai_response"):
            final_state["ai_response"] = clean_markup(final_state.get("ai_response"))

        if final_state.get("is_spam"):
            logger.warning(f"Spam detected for user {message_request.userId}")
            return MessageResponse(
                status="blocked",
                message="This message was identified as spam and has been blocked.",
                sessionId=session_id,
                language=final_state.get("language"),
                handoff=False,
                modelUsed=final_state.get("model_used"),
                retrievalMode=final_state.get("retrieval_mode_selected"),
                processingTimeMs=processing_time_ms
            )
        
        response = MessageResponse(
            status="success",
            message=final_state.get("ai_response", ""),
            sessionId=session_id,
            language=final_state.get("detected_language"),
            handoff=final_state.get("requires_human", False),
            modelUsed=final_state.get("model_used"),
            retrievalMode=final_state.get("retrieval_mode_selected"),
            assignedTo=final_state.get("assigned_admin_name"),
            queueStatus=final_state.get("queue_status"),
            processingTimeMs=processing_time_ms
        )
        
        logger.info(f"Completed processing for {message_request.userId} in {processing_time_ms}ms")
        return response
        
    except Exception as e:
        logger.error("Error processing message: {}", e)
        raise HTTPException(status_code=500, detail="An error occurred processing your message")

@router.post("/conversations/{session_id}/resume")
async def resume_session(
    session_id: str,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
):
    """Resume a conversation from last checkpoint"""
    try:
        logger.opt(exception=True).info("Resuming conversation: {session_id}")
        final_state = await resume_conversation(
            session_id,
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
        )
        
        return {
            "status": "resumed",
            "sessionId": session_id,
            "message": final_state.get("ai_response"),
            "state": final_state
        }
    except Exception as e:
        logger.error("Error resuming conversation: {}", e)
        raise HTTPException(status_code=500, detail="Failed to resume conversation")

@router.get("/conversations/{session_id}/state")
async def get_session_state_endpoint(
    session_id: str,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
):
    """Get current state of a conversation"""
    try:
        state = await get_conversation_state(
            session_id,
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
        )
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"sessionId": session_id, "state": state}
    except HTTPException:
        raise
    except Exception as e:
        logger.opt(exception=True).error("Error fetching state: {}", str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch session state")
