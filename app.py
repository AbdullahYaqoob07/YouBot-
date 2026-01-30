"""
FastAPI application - REST API server (replaces n8n webhook)
"""
from fastapi import FastAPI, HTTPException, Request, Header, BackgroundTasks, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, field_validator
from typing import Optional
import time
import asyncio
import re
from datetime import datetime
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from graph import process_message, resume_conversation, get_conversation_state
from config import settings
from database.conversation import get_conversation_history as db_get_history
from database.admin_queue import get_admin_queue, update_queue_status
from database.models import AdminAvailability, get_async_session
from sqlalchemy import select, update as sql_update
from loguru import logger
from utils.faq_cache import faq_cache
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
from sqlalchemy import text

# Prometheus Metrics
REQUEST_COUNT = Counter(
    "ai_agent_request_count", 
    "Total number of requests", 
    ["method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "ai_agent_request_latency_seconds", 
    "Request latency in seconds",
    ["method", "endpoint"]
)
LLM_ERROR_COUNT = Counter(
    "ai_agent_llm_errors",
    "Total LLM/Agent errors",
    ["type"]
)

# Rate Limiter
limiter = Limiter(key_func=get_remote_address)

# Security - API Key headers
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)

# Input sanitization patterns
PROMPT_INJECTION_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?previous\s+instructions?",
    r"(?i)you\s+are\s+now\s+a",
    r"(?i)system\s*prompt",
    r"(?i)disregard\s+(all\s+)?above",
    r"(?i)forget\s+(all\s+)?instructions?",
    r"(?i)new\s+instructions?\s*:",
]

def sanitize_input(message: str, max_length: int = None) -> str:
    """Sanitize user input to prevent prompt injection and limit length"""
    if max_length is None:
        max_length = settings.MAX_MESSAGE_LENGTH
    
    # Truncate to max length
    message = message[:max_length]
    
    # Remove potential prompt injection patterns
    for pattern in PROMPT_INJECTION_PATTERNS:
        message = re.sub(pattern, '[filtered]', message)
    
    return message.strip()

# Configure logger
logger.add(
    settings.LOG_FILE,
    rotation="500 MB",
    level=settings.LOG_LEVEL,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.API_VERSION,
    description="LangGraph-powered AI agent for Sweden Relocators"
)

# Add rate limit exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware - RESTRICTED to allowed origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Mount static files for frontend
app.mount("/static", StaticFiles(directory="static"), name="static")


# Request/Response Models
class MessageRequest(BaseModel):
    """Incoming message request"""
    message: str = Field(..., description="User message", min_length=1, max_length=5000)
    userId: str = Field(..., alias="userId", description="Unique user identifier", min_length=1, max_length=100)
    sessionId: Optional[str] = Field(None, alias="sessionId", description="Session ID (auto-generated if not provided)")
    channel: str = Field(default="webhook", description="Channel: whatsapp, instagram, email, webhook")
    userName: Optional[str] = Field(None, alias="userName", description="User name", max_length=200)
    userEmail: Optional[str] = Field(None, alias="userEmail", description="User email", max_length=200)
    userPhone: Optional[str] = Field(None, alias="userPhone", description="User phone", max_length=50)
    
    @field_validator('message')
    @classmethod
    def sanitize_message(cls, v: str) -> str:
        """Sanitize message input"""
        return sanitize_input(v)
    
    @field_validator('channel')
    @classmethod
    def validate_channel(cls, v: str) -> str:
        """Validate channel is allowed"""
        allowed = ['whatsapp', 'instagram', 'email', 'webhook', 'web']
        if v.lower() not in allowed:
            raise ValueError(f'Channel must be one of: {allowed}')
        return v.lower()
    
    class Config:
        populate_by_name = True


class MessageResponse(BaseModel):
    """Agent response"""
    status: str
    message: str
    sessionId: str
    language: Optional[str]
    handoff: bool
    assignedTo: Optional[str] = None
    queueStatus: Optional[str] = None
    processingTimeMs: int


# API Key validation
async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> Optional[str]:
    """Verify API key for public endpoints"""
    # If API keys are configured, require valid key
    if settings.API_KEYS:
        # Robust handling for env var parsing issues
        valid_keys = settings.API_KEYS
        # If single element formatted as list, try to parse
        if len(valid_keys) == 1 and isinstance(valid_keys[0], str) and valid_keys[0].startswith('[') and valid_keys[0].endswith(']'):
            try:
                import json
                parsed = json.loads(valid_keys[0])
                if isinstance(parsed, list):
                    valid_keys = parsed
            except:
                pass

        if not api_key or api_key not in valid_keys:
            logger.warning(f"Invalid API key attempt: {api_key}. Allowed: {valid_keys}")
            raise HTTPException(
                status_code=401, 
                detail="Invalid or missing API key",
                headers={"WWW-Authenticate": "ApiKey"}
             )
    return api_key

async def verify_admin_key(admin_key: Optional[str] = Security(admin_key_header)) -> str:
    """Verify admin API key for admin endpoints"""
    if not settings.ADMIN_API_KEY:
        # If no admin key configured, deny all admin access in production
        if not settings.DEBUG:
            raise HTTPException(status_code=403, detail="Admin access not configured")
        return "debug_admin"
    
    if not admin_key or admin_key != settings.ADMIN_API_KEY:
        logger.warning(f"Invalid admin key attempt")
        raise HTTPException(
            status_code=403, 
            detail="Invalid or missing admin key",
            headers={"WWW-Authenticate": "AdminKey"}
        )
    return admin_key


@app.get("/")
async def root():
    """Redirect to test frontend"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")


@app.get("/admin")
async def admin_dashboard():
    """Redirect to admin supervision dashboard"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/admin_dashboard.html")


@app.get("/health")
async def health_check():
    """Detailed health check"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "database": "unknown",
            "vector_store": "unknown"
        }
    }
    
    # Check Database
    try:
        async with get_async_session() as session:
            await session.execute(text("SELECT 1"))
        health_status["components"]["database"] = "healthy"
    except Exception as e:
        health_status["components"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
        logger.error(f"Health check failed (DB): {str(e)}")

    # Check Vector Store (Pinecone/Chroma)
    try:
        # Simple check if configured - in real prod, perform a list_indexes or similar
        if settings.VECTOR_STORE_TYPE:
             health_status["components"]["vector_store"] = "connected"
    except Exception as e:
        health_status["components"]["vector_store"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
        
    if health_status["status"] != "healthy":
         raise HTTPException(status_code=503, detail=health_status)
         
    return health_status


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/chat/{session_id}/history")
async def get_chat_history(
    session_id: str,
    api_key: str = Depends(verify_api_key)
):
    """
    Get conversation history for polling by user frontend.
    Returns messages and current status (active/takeover).
    """
    try:
        from database.supervision import get_conversation_messages
        conversation = await get_conversation_messages(session_id)
        return conversation
    except Exception as e:
        logger.error(f"Error fetching history: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch history")


@app.post("/webhook/ai-agent", response_model=MessageResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def webhook_handler(
    request: Request,
    message_request: MessageRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """
    Main webhook endpoint for processing messages
    
    Rate limited and API key protected.
    Returns response immediately, logs in background for speed.
    """
    start_time = time.time()
    
    try:
        # Generate session ID if not provided
        session_id = message_request.sessionId or f"sess_{message_request.channel}_{message_request.userId}_{int(time.time())}"
        
        logger.info(f"Processing message from {message_request.userId} via {message_request.channel}")
        
        # Process message through LangGraph workflow
        final_state = await process_message(
            message=message_request.message,
            user_id=message_request.userId,
            session_id=session_id,
            channel=message_request.channel,
            user_name=message_request.userName,
            user_email=message_request.userEmail,
            user_phone=message_request.userPhone
        )
        
        # Calculate processing time
        processing_time = (time.time() - start_time)
        processing_time_ms = int(processing_time * 1000)
        
        # Record metrics
        REQUEST_COUNT.labels(method="POST", endpoint="/webhook/ai-agent", status="success").inc()
        REQUEST_LATENCY.labels(method="POST", endpoint="/webhook/ai-agent").observe(processing_time)
        
        # ⚡ PERFORMANCE: Log conversation in background (non-blocking)
        from nodes.admin_handler import log_conversation_node
        async def background_log():
            try:
                await log_conversation_node(final_state)
                logger.debug(f"Background logging completed for {message_request.userId}")
            except Exception as log_error:
                logger.error(f"Background logging failed: {str(log_error)}")
        
        # Fire and forget - don't wait for logging
        background_tasks.add_task(background_log)
        
        # Handle spam case
        if final_state.get("is_spam"):
            logger.warning(f"Spam detected for user {message_request.userId}")
            return MessageResponse(
                status="blocked",
                message="This message was identified as spam and has been blocked.",
                sessionId=session_id,
                language=final_state.get("language"),
                handoff=False,
                processingTimeMs=processing_time_ms
            )
        
        # Build response
        response = MessageResponse(
            status="success",
            message=final_state.get("ai_response", ""),
            sessionId=session_id,
            language=final_state.get("detected_language"),
            handoff=final_state.get("requires_human", False),
            assignedTo=final_state.get("assigned_admin_name"),
            queueStatus=final_state.get("queue_status"),
            processingTimeMs=processing_time_ms
        )
        
        logger.info(f"Completed processing for {message_request.userId} in {processing_time_ms}ms")
        
        return response
        
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred processing your message")


@app.get("/conversations/{user_id}")
async def get_user_conversations(
    user_id: str, 
    limit: int = 10,
    admin_key: str = Depends(verify_admin_key)
):
    """Get conversation history for a user (admin only)"""
    try:
        history = await db_get_history(user_id, limit=limit)
        return {"userId": user_id, "conversations": history}
    except Exception as e:
        logger.error(f"Error fetching conversations: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch conversations")


@app.post("/conversations/{session_id}/resume")
async def resume_session(session_id: str):
    """Resume a conversation from last checkpoint"""
    try:
        logger.info(f"Resuming conversation: {session_id}")
        final_state = await resume_conversation(session_id)
        
        return {
            "status": "resumed",
            "sessionId": session_id,
            "message": final_state.get("ai_response"),
            "state": final_state
        }
    except Exception as e:
        logger.error(f"Error resuming conversation: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to resume conversation")


@app.get("/conversations/{session_id}/state")
async def get_session_state(session_id: str):
    """Get current state of a conversation"""
    try:
        state = await get_conversation_state(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"sessionId": session_id, "state": state}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching state: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch session state")


@app.get("/admin/queue")
async def admin_queue(
    status: Optional[str] = None,
    admin_key: str = Depends(verify_admin_key)
):
    """Get admin queue entries (admin only)"""
    try:
        queue = await get_admin_queue(status=status)
        return {"queue": queue}
    except Exception as e:
        logger.error(f"Error fetching admin queue: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch queue")


@app.put("/admin/queue/{queue_id}")
async def update_queue(
    queue_id: int, 
    status: str, 
    admin_id: Optional[str] = None,
    admin_key: str = Depends(verify_admin_key)
):
    """Update admin queue entry (admin only)"""
    try:
        await update_queue_status(queue_id, status, admin_id)
        return {"status": "updated", "queueId": queue_id}
    except Exception as e:
        logger.error(f"Error updating queue: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update queue")


# Admin Management Endpoints
class AdminCreateRequest(BaseModel):
    """Admin creation request"""
    adminId: str
    adminName: str
    adminEmail: str
    maxQueueSize: int = 10


class AdminStatusRequest(BaseModel):
    """Admin status update request"""
    status: str  # 'online' or 'offline'


@app.post("/admin/create")
async def create_admin(
    request: AdminCreateRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """Create or update admin availability (admin only)"""
    try:
        async with get_async_session() as session:
            # Check if admin exists
            query = select(AdminAvailability).where(
                AdminAvailability.admin_id == request.adminId
            )
            result = await session.execute(query)
            admin = result.scalar_one_or_none()
            
            if admin:
                # Update existing admin
                admin.admin_name = request.adminName
                admin.admin_email = request.adminEmail
                admin.max_queue_size = request.maxQueueSize
                admin.status = 'online'
                admin.updated_at = datetime.utcnow()
            else:
                # Create new admin
                admin = AdminAvailability(
                    admin_id=request.adminId,
                    admin_name=request.adminName,
                    admin_email=request.adminEmail,
                    max_queue_size=request.maxQueueSize,
                    status='online',
                    current_queue_count=0,
                    total_queries_handled=0,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                session.add(admin)
            
            await session.commit()
            
            logger.info(f"Admin created/updated: {request.adminId}")
            return {
                "status": "success",
                "adminId": request.adminId,
                "adminName": request.adminName,
                "message": "Admin is now online"
            }
            
    except Exception as e:
        logger.error(f"Error creating admin: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create admin")


@app.put("/admin/{admin_id}/status")
async def update_admin_status(
    admin_id: str, 
    request: AdminStatusRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """Update admin online/offline status (admin only)"""
    try:
        async with get_async_session() as session:
            stmt = (
                sql_update(AdminAvailability)
                .where(AdminAvailability.admin_id == admin_id)
                .values(status=request.status, updated_at=datetime.utcnow())
            )
            await session.execute(stmt)
            await session.commit()
            
            logger.info(f"Admin {admin_id} status updated to {request.status}")
            return {"status": "success", "adminId": admin_id, "newStatus": request.status}
            
    except Exception as e:
        logger.error(f"Error updating admin status: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update admin status")


@app.get("/admin/list")
async def list_admins(admin_key: str = Depends(verify_admin_key)):
    """List all admins with their status (admin only)"""
    try:
        async with get_async_session() as session:
            query = select(AdminAvailability)
            result = await session.execute(query)
            admins = result.scalars().all()
            
            return {
                "admins": [
                    {
                        "adminId": admin.admin_id,
                        "adminName": admin.admin_name,
                        "status": admin.status,
                        "currentQueue": admin.current_queue_count,
                        "maxQueue": admin.max_queue_size,
                        "totalHandled": admin.total_queries_handled
                    }
                    for admin in admins
                ]
            }
    except Exception as e:
        logger.error(f"Error listing admins: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list admins")


@app.get("/analytics/faq/cache")
async def get_faq_cache_stats(admin_key: str = Depends(verify_admin_key)):
    """Get FAQ cache statistics (admin only)"""
    try:
        stats = faq_cache.get_stats()
        return {
            "status": "success",
            "stats": stats,
            "message": f"Cache hit rate: {stats['hit_rate_pct']:.1f}%, Size: {stats['cache_size']}/{stats['max_size']}"
        }
    except Exception as e:
        logger.error(f"Error getting FAQ cache stats: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get cache stats")


@app.get("/analytics/faq/popular")
async def get_popular_faqs(limit: int = 20, admin_key: str = Depends(verify_admin_key)):
    """Get most popular FAQs (admin only)"""
    try:
        popular = faq_cache.get_popular_faqs(limit)
        stats = faq_cache.get_stats()
        
        return {
            "status": "success",
            "total_faqs": len(popular),
            "cache_hit_rate": f"{stats['hit_rate_pct']:.1f}%",
            "popular_faqs": popular
        }
    except Exception as e:
        logger.error(f"Error getting popular FAQs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get popular FAQs")


@app.get("/analytics/faq/report")
async def get_faq_analytics_report(admin_key: str = Depends(verify_admin_key)):
    """Get comprehensive FAQ analytics report (admin only)"""
    try:
        analytics = faq_cache.export_analytics()
        return {
            "status": "success",
            "report": analytics
        }
    except Exception as e:
        logger.error(f"Error generating FAQ analytics report: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate report")


@app.post("/analytics/faq/cache/clear")
async def clear_faq_cache(admin_key: str = Depends(verify_admin_key)):
    """Clear FAQ cache (admin only)"""
    try:
        faq_cache.clear()
        logger.info("FAQ cache cleared by admin")
        return {
            "status": "success",
            "message": "FAQ cache cleared successfully"
        }
    except Exception as e:
        logger.error(f"Error clearing FAQ cache: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to clear cache")


# ============================================
# ADMIN SUPERVISION ENDPOINTS
# ============================================
from database.supervision import (
    get_active_conversations,
    get_conversation_messages,
    admin_takeover,
    admin_send_message,
    release_conversation
)


class AdminTakeoverRequest(BaseModel):
    """Request for admin to take over conversation"""
    admin_id: str = Field(..., min_length=1, description="Admin ID taking over")
    reason: str = Field(default="Manual intervention", description="Reason for takeover")


class AdminMessageRequest(BaseModel):
    """Request for admin to send message"""
    admin_id: str = Field(..., min_length=1, description="Admin ID sending message")
    message: str = Field(..., min_length=1, max_length=2000, description="Message to send")


class ReleaseConversationRequest(BaseModel):
    """Request to release conversation"""
    admin_id: str = Field(..., min_length=1, description="Admin ID releasing")
    end_conversation: bool = Field(default=False, description="End conversation instead of releasing to AI")


@app.get("/admin/supervision/conversations")
async def get_supervised_conversations(
    status: Optional[str] = None,
    include_ended: bool = False,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Get all active conversations for supervision.
    
    Admin can see ALL conversations in real-time.
    Filter by status: active, admin_watching, admin_takeover, pending_handoff, ended
    """
    try:
        conversations = await get_active_conversations(
            status_filter=status,
            include_ended=include_ended
        )
        
        return {
            "status": "success",
            "total": len(conversations),
            "conversations": conversations
        }
    except Exception as e:
        logger.error(f"Error getting supervised conversations: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get conversations")


@app.get("/admin/supervision/conversations/{session_id}")
async def get_conversation_detail(
    session_id: str,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Get full conversation history for a session.
    
    Includes all user messages, AI responses, and admin messages.
    """
    try:
        conversation = await get_conversation_messages(session_id)
        
        if not conversation.get("messages") and conversation.get("error"):
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return {
            "status": "success",
            "conversation": conversation
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation detail: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get conversation")


@app.post("/admin/supervision/conversations/{session_id}/takeover")
async def takeover_conversation(
    session_id: str,
    request: AdminTakeoverRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Admin takes over a conversation.
    
    After takeover:
    - AI stops responding to this conversation
    - Admin can send messages directly
    - Admin can release back to AI or end conversation
    """
    try:
        result = await admin_takeover(
            session_id=session_id,
            admin_id=request.admin_id,
            reason=request.reason
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))
        
        logger.info(f"Admin {request.admin_id} took over conversation {session_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in takeover: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to take over conversation")


@app.post("/admin/supervision/conversations/{session_id}/message")
async def send_admin_message(
    session_id: str,
    request: AdminMessageRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Admin sends a message to the user.
    
    Only works if admin has taken over the conversation.
    """
    try:
        result = await admin_send_message(
            session_id=session_id,
            admin_id=request.admin_id,
            message=request.message
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending admin message: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to send message")


@app.post("/admin/supervision/conversations/{session_id}/release")
async def release_admin_conversation(
    session_id: str,
    request: ReleaseConversationRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Admin releases conversation back to AI or ends it.
    
    - end_conversation=False: AI will continue handling
    - end_conversation=True: Conversation is marked as ended
    """
    try:
        result = await release_conversation(
            session_id=session_id,
            admin_id=request.admin_id,
            end_conversation=request.end_conversation
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))
        
        logger.info(f"Admin {request.admin_id} released conversation {session_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error releasing conversation: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to release conversation")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler - logs full traceback but returns safe message"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Internal server error"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=5678,
        reload=settings.DEBUG,
        workers=1 if settings.DEBUG else settings.WORKERS
    )
