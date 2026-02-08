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
from sqlalchemy import select, update as sql_update, desc
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


def clean_markup(text: str) -> str:
    """Simple sanitizer to remove common Markdown artifacts and make responses cleaner for chat UIs.

    - Removes triple/back ticks and inline code markers
    - Strips bold/italic markers (*, **, _, __)
    - Converts list markers ('*', '-') at line start to bullet points
    - Collapses multiple blank lines
    """
    if not text:
        return text

    import re

    # Remove code fences
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove inline code ticks
    text = text.replace('`', '')
    # Strip bold/italic markers
    text = text.replace('**', '').replace('__', '').replace('*', '').replace('_', '')

    # Convert lines starting with - or • to a consistent bullet
    def _convert_list(m):
        return '• ' + m.group(2).strip()

    text = re.sub(r'^(\s*[-\*\u2022]+)\s*(.*)$', _convert_list, text, flags=re.M)

    # Collapse multiple blank lines
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    # Trim
    return text.strip()

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


# Redis cache instance (initialized at startup)
redis_cache = None


# Startup event to pre-load embeddings and initialize Redis
@app.on_event("startup")
async def startup_event():
    """Pre-load embeddings, vector store, and initialize Redis on startup"""
    global redis_cache
    
    # Initialize Redis cache
    try:
        from utils.redis_cache import RedisCache
        redis_cache = RedisCache()
        await redis_cache.connect()
        logger.info("✅ Redis cache connected!")
    except Exception as e:
        logger.warning(f"⚠️ Redis not available, using in-memory cache: {e}")
        redis_cache = None
    
    # Pre-load embeddings
    from tools.knowledge_base import create_knowledge_base_tool
    logger.info("🚀 Pre-loading embeddings and vector store...")
    await create_knowledge_base_tool()
    logger.info("✅ Startup complete - embeddings cached!")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global redis_cache
    if redis_cache:
        await redis_cache.close()
        logger.info("Redis cache closed")


# Request/Response Models
class MessageRequest(BaseModel):
    """Incoming message request"""
    message: str = Field(..., description="User message", min_length=1, max_length=5000)
    userId: str = Field(..., alias="userId", description="Unique user identifier", min_length=1, max_length=100)
    sessionId: Optional[str] = Field(None, alias="sessionId", description="Session ID (auto-generated if not provided)")
    channel: str = Field(default="webhook", description="Channel: whatsapp, facebook, instagram, email, webhook")
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
        allowed = ['whatsapp', 'facebook','instagram', 'email', 'webhook', 'web']
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


@app.get("/kb-management")
async def kb_management():
    """Redirect to KB management page"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/kb-management.html")


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
        
        # Normalize AI response formatting for UI readability
        if final_state.get("ai_response"):
            final_state["ai_response"] = clean_markup(final_state.get("ai_response"))

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


class AdminPreviewRequest(BaseModel):
    """Request for admin to preview/grammar-check message before sending"""
    admin_id: str = Field(..., min_length=1, description="Admin ID requesting preview")
    message: str = Field(..., min_length=1, max_length=2000, description="Message to preview")


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


@app.post("/admin/supervision/conversations/{session_id}/message/preview")
async def preview_admin_message(
    session_id: str,
    request: AdminPreviewRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """Preview/grammar-check an admin message using the comprehension agent.

    This endpoint is explicitly invoked by the admin UI when the admin clicks
    the preview/check button. It does NOT send or persist the message.
    """
    try:
        # Lazy import to avoid startup dependency if LLM not configured
        from nodes.comprehension_agent import check_message

        result = await check_message(request.message)

        return {
            "status": "success",
            "corrected": result.get("corrected"),
            "suggestions": result.get("suggestions"),
            "raw": result.get("raw")
        }

    except RuntimeError as re:
        logger.error(f"Comprehension preview failed: {str(re)}")
        raise HTTPException(status_code=503, detail=str(re))
    except Exception as e:
        logger.error(f"Error in preview_admin_message: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to run preview")


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


# ============================================================================
# KB CURATION ENDPOINTS
# ============================================================================

class LogUnansweredRequest(BaseModel):
    """Request to log an unanswered question"""
    session_id: str
    question_text: str
    context: Optional[dict] = None


class LinkResponseRequest(BaseModel):
    """Request to link admin response"""
    response_text: str
    category: Optional[str] = None
    responder_name: Optional[str] = None


class ApproveKBRequest(BaseModel):
    """Request to approve for KB"""
    admin_id: str
    category: Optional[str] = None
    notes: Optional[str] = None


class AddToKBRequest(BaseModel):
    """Request to add to KB"""
    admin_id: str


class RemoveFromKBRequest(BaseModel):
    """Request to remove from KB"""
    admin_id: str
    reason: Optional[str] = None


class UpdateKBRequest(BaseModel):
    """Request to update KB entry"""
    admin_id: str
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None


class ManualAddKBRequest(BaseModel):
    """Request to manually add Q&A to KB"""
    admin_id: str
    question: str
    answer: str
    category: Optional[str] = "general"
    language: Optional[str] = "English"


@app.post("/kb-curation/log-unanswered")
async def log_unanswered_question_endpoint(
    request: LogUnansweredRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Log an unanswered question for KB curation (simplified for admin dashboard)
    """
    try:
        from database.kb_curation import KBUnansweredQuestion
        from database.models import get_async_session
        
        # Simple version for manual admin additions
        async with get_async_session() as session:
            question = KBUnansweredQuestion(
                session_id=request.session_id,
                user_id=request.context.get("admin_id", "unknown") if request.context else "unknown",
                user_question=request.question_text,
                user_language="unknown",
                ai_response="",
                handoff_reason="Admin manual addition",
                unsolved_score=0.0,
                status="pending",
                created_at=datetime.utcnow()
            )
            
            session.add(question)
            await session.commit()
            await session.refresh(question)
            
            question_id = question.id
        
        logger.info(f"Logged unanswered question {question_id} for session {request.session_id}")
        return {
            "success": True,
            "question_id": question_id,
            "message": "Question logged successfully"
        }
        
    except Exception as e:
        logger.error(f"Error logging unanswered question: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to log question: {str(e)}")


@app.post("/kb-curation/{question_id}/link-response")
async def link_admin_response_endpoint(
    question_id: int,
    request: LinkResponseRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Link admin response to a question
    """
    try:
        from database.kb_curation import KBUnansweredQuestion
        from database.models import get_async_session
        
        async with get_async_session() as session:
            query = select(KBUnansweredQuestion).where(
                KBUnansweredQuestion.id == question_id
            )
            
            result = await session.execute(query)
            question = result.scalar_one_or_none()
            
            if not question:
                raise HTTPException(status_code=404, detail="Question not found")
            
            question.admin_id = request.responder_name or "admin"
            question.admin_response = request.response_text
            question.admin_responded_at = datetime.utcnow()
            question.category = request.category
            question.status = "reviewed"
            question.updated_at = datetime.utcnow()
            
            await session.commit()
        
        logger.info(f"Linked response to question {question_id}")
        return {
            "success": True,
            "response_id": question_id,
            "message": "Response linked successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error linking response: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to link response: {str(e)}")


@app.post("/kb-curation/{question_id}/approve")
async def approve_for_kb_endpoint(
    question_id: int,
    request: ApproveKBRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Approve a Q&A pair for KB addition
    """
    try:
        from database.kb_curation import approve_for_kb
        
        success = await approve_for_kb(
            question_id=question_id,
            admin_id=request.admin_id,
            category=request.category,
            notes=request.notes
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to approve question")
        
        logger.info(f"Approved question {question_id} for KB")
        return {
            "success": True,
            "approval_id": question_id,
            "message": "Approved for KB successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving for KB: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to approve: {str(e)}")


@app.post("/kb-curation/add-to-kb/{question_id}")
async def add_to_kb(
    question_id: int,
    request: AddToKBRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Ingest approved Q&A into Pinecone knowledge base using existing embeddings
    """
    try:
        from database.kb_curation import get_qa_for_ingestion, mark_added_to_kb
        from tools.knowledge_base import get_cached_embeddings, get_cached_vector_store
        from pinecone import Pinecone
        
        # Get Q&A data
        qa_data = await get_qa_for_ingestion(question_id)
        
        if not qa_data:
            raise HTTPException(status_code=404, detail="Question not found or not approved")
        
        # Use cached embeddings (already initialized at startup)
        embeddings = get_cached_embeddings()
        if embeddings is None:
            raise HTTPException(status_code=500, detail="Embeddings not initialized")
        
        # Get cached vector store
        vector_store = get_cached_vector_store()
        if vector_store is None:
            raise HTTPException(status_code=500, detail="Vector store not initialized")
        
        # Generate FAQ ID
        faq_id = f"faq_{question_id}_{int(datetime.utcnow().timestamp())}"
        
        # Create embedding for the question using cached embeddings
        question_embedding = embeddings.embed_query(qa_data["question"])
        
        # Prepare metadata (matching your existing format)
        # Note: Pinecone doesn't accept None values, so we filter them out
        metadata = {
            "faq_id": faq_id,
            "question": qa_data["question"],
            "answer": qa_data["answer"],
            "category": qa_data.get("category") or "general",  # Default to "general" if None
            "source": "admin_curated",
            "type": "faq",
            "document_id": faq_id,
            "ingested_at": datetime.utcnow().isoformat(),
            "admin_id": request.admin_id,
            "question_id": str(question_id)  # Convert to string for Pinecone
        }
        
        # Remove None values (Pinecone doesn't accept null)
        metadata = {k: v for k, v in metadata.items() if v is not None}
        
        # Get index from cached vector store
        index = vector_store.index
        
        # Upsert to Pinecone
        index.upsert(
            vectors=[{
                "id": faq_id,
                "values": question_embedding,
                "metadata": metadata
            }],
            namespace="sweden_relocators_v3"
        )
        
        # Mark as added in database
        await mark_added_to_kb(
            question_id=question_id,
            faq_id=faq_id,
            admin_id=request.admin_id
        )
        
        # CRITICAL: Invalidate cache for this question
        # So next time it's asked, it searches the KB instead of returning cached "requires_human"
        faq_cache.invalidate_query(qa_data["question"], qa_data.get("language", "English"))
        
        # Also invalidate Redis cache if available
        global redis_cache
        if redis_cache:
            try:
                # Clear from Redis as well
                await redis_cache.delete(qa_data["question"], qa_data.get("language", "English"))
                logger.info(f"Invalidated Redis cache for question: {qa_data['question'][:50]}...")
            except Exception as e:
                logger.warning(f"Failed to invalidate Redis cache: {e}")
        
        logger.info(f"Added question {question_id} to KB with FAQ ID {faq_id} and invalidated cache")
        return {
            "success": True,
            "faq_id": faq_id,
            "message": "Successfully added to KB and cache invalidated",
            "nodes_added": 1
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # Use repr() to avoid formatting issues with curly braces in error messages
        error_msg = repr(e)
        logger.error(f"Error adding to KB: {error_msg}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to add to KB: {str(e)}")


@app.delete("/kb-curation/remove-from-kb/{question_id}")
async def remove_from_kb(
    question_id: int,
    request: RemoveFromKBRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Remove a Q&A from Pinecone knowledge base
    """
    try:
        from database.kb_curation import KBUnansweredQuestion
        from database.models import get_async_session
        from tools.knowledge_base import get_cached_vector_store
        
        # Get question record
        async with get_async_session() as session:
            query = select(KBUnansweredQuestion).where(
                KBUnansweredQuestion.id == question_id
            )
            result = await session.execute(query)
            question = result.scalar_one_or_none()
            
            if not question:
                raise HTTPException(status_code=404, detail="Question not found")
            
            if not question.added_to_kb or not question.kb_document_id:
                raise HTTPException(status_code=400, detail="Question not in KB")
            
            faq_id = question.kb_document_id
            
            # Get cached vector store
            vector_store = get_cached_vector_store()
            if vector_store is None:
                raise HTTPException(status_code=500, detail="Vector store not initialized")
            
            # Delete from Pinecone
            index = vector_store.index
            index.delete(
                ids=[faq_id],
                namespace="sweden_relocators_v3"
            )
            
            # Update database (soft delete - keep for audit trail)
            question.added_to_kb = False
            question.status = "removed_from_kb"
            question.updated_at = datetime.utcnow()
            if request.reason:
                question.notes = f"Removed: {request.reason}" + (f"\n{question.notes}" if question.notes else "")
            
            await session.commit()
        
        logger.info(f"Removed question {question_id} (FAQ ID: {faq_id}) from KB by {request.admin_id}")
        return {
            "success": True,
            "message": "Successfully removed from KB",
            "faq_id": faq_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = repr(e)
        logger.error(f"Error removing from KB: {error_msg}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to remove from KB: {str(e)}")


@app.put("/kb-curation/update-kb/{question_id}")
async def update_kb(
    question_id: int,
    request: UpdateKBRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Update an existing Q&A in Pinecone knowledge base
    
    Can update question text, answer text, and/or category.
    Re-generates embeddings if question text is changed.
    """
    try:
        from database.kb_curation import KBUnansweredQuestion
        from database.models import get_async_session
        from tools.knowledge_base import get_cached_vector_store, get_cached_embeddings
        
        # Validate at least one field is being updated
        if not any([request.question, request.answer, request.category]):
            raise HTTPException(status_code=400, detail="At least one field (question, answer, or category) must be provided")
        
        # Get question record
        async with get_async_session() as session:
            query = select(KBUnansweredQuestion).where(
                KBUnansweredQuestion.id == question_id
            )
            result = await session.execute(query)
            question = result.scalar_one_or_none()
            
            if not question:
                raise HTTPException(status_code=404, detail="Question not found")
            
            if not question.added_to_kb or not question.kb_document_id:
                raise HTTPException(status_code=400, detail="Question not in KB")
            
            faq_id = question.kb_document_id
            
            # Get cached embeddings and vector store
            embeddings = get_cached_embeddings()
            vector_store = get_cached_vector_store()
            
            if embeddings is None or vector_store is None:
                raise HTTPException(status_code=500, detail="Embeddings or vector store not initialized")
            
            # Update database record
            updated_fields = []
            if request.question:
                question.user_question = request.question
                updated_fields.append("question")
            if request.answer:
                question.admin_response = request.answer
                updated_fields.append("answer")
            if request.category:
                question.category = request.category
                updated_fields.append("category")
            
            question.updated_at = datetime.utcnow()
            await session.commit()
            
            # Get updated values for Pinecone
            updated_question = request.question or question.user_question
            updated_answer = request.answer or question.admin_response
            updated_category = request.category or question.category or "general"
            
            # Re-generate embedding if question text changed
            if request.question:
                question_embedding = embeddings.embed_query(updated_question)
            else:
                # Fetch existing embedding from Pinecone
                index = vector_store.index
                fetch_result = index.fetch(ids=[faq_id], namespace="sweden_relocators_v3")
                if faq_id not in fetch_result.get("vectors", {}):
                    raise HTTPException(status_code=404, detail="Vector not found in Pinecone")
                question_embedding = fetch_result["vectors"][faq_id]["values"]
            
            # Prepare updated metadata
            metadata = {
                "faq_id": faq_id,
                "question": updated_question,
                "answer": updated_answer,
                "category": updated_category,
                "source": "admin_curated",
                "type": "faq",
                "document_id": faq_id,
                "ingested_at": question.added_to_kb_at.isoformat() if question.added_to_kb_at else datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "updated_by": request.admin_id,
                "admin_id": request.admin_id,
                "question_id": str(question_id)
            }
            
            # Remove None values
            metadata = {k: v for k, v in metadata.items() if v is not None}
            
            # Update in Pinecone (upsert with same ID)
            index = vector_store.index
            index.upsert(
                vectors=[{
                    "id": faq_id,
                    "values": question_embedding,
                    "metadata": metadata
                }],
                namespace="sweden_relocators_v3"
            )
            
            # Invalidate cache for both old and new questions
            faq_cache.invalidate_query(question.user_question, question.user_language or "English")
            if request.question and request.question != question.user_question:
                faq_cache.invalidate_query(request.question, question.user_language or "English")
            
            # Also invalidate Redis cache if available
            global redis_cache
            if redis_cache:
                try:
                    await redis_cache.delete(question.user_question, question.user_language or "English")
                    if request.question:
                        await redis_cache.delete(request.question, question.user_language or "English")
                except Exception as e:
                    logger.warning(f"Failed to invalidate Redis cache: {e}")
        
        logger.info(f"Updated KB entry {question_id} (FAQ ID: {faq_id}) - fields: {', '.join(updated_fields)}")
        return {
            "success": True,
            "faq_id": faq_id,
            "message": f"Successfully updated KB entry ({', '.join(updated_fields)})",
            "updated_fields": updated_fields
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = repr(e)
        logger.error(f"Error updating KB: {error_msg}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update KB: {str(e)}")


@app.post("/kb-curation/manual-add")
async def manual_add_to_kb(
    request: ManualAddKBRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Manually add a Q&A directly to the knowledge base without going through the queue.
    Creates a new KB entry and ingests it into Pinecone.
    """
    try:
        from database.kb_curation import KBUnansweredQuestion
        from database.models import get_async_session
        from tools.knowledge_base import get_cached_embeddings, get_cached_vector_store
        from pinecone import Pinecone
        
        # Validate inputs
        if not request.question.strip() or not request.answer.strip():
            raise HTTPException(status_code=400, detail="Question and answer cannot be empty")
        
        # Get cached embeddings and vector store
        embeddings = get_cached_embeddings()
        vector_store = get_cached_vector_store()
        
        if embeddings is None or vector_store is None:
            raise HTTPException(status_code=500, detail="Embeddings or vector store not initialized")
        
        # Create database record
        async with get_async_session() as session:
            # Create new KB entry
            new_entry = KBUnansweredQuestion(
                user_question=request.question.strip(),
                admin_response=request.answer.strip(),
                user_language=request.language or "English",
                category=request.category or "general",
                status="manually_added",
                added_to_kb=True,
                added_by_admin=request.admin_id,
                added_to_kb_at=datetime.utcnow(),
                responded_by_admin=request.admin_id,
                responded_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            session.add(new_entry)
            await session.commit()
            await session.refresh(new_entry)
            
            question_id = new_entry.id
        
        # Generate FAQ ID
        faq_id = f"faq_manual_{question_id}_{int(datetime.utcnow().timestamp())}"
        
        # Create embedding for the question
        question_embedding = embeddings.embed_query(request.question)
        
        # Prepare metadata
        metadata = {
            "faq_id": faq_id,
            "question": request.question.strip(),
            "answer": request.answer.strip(),
            "category": request.category or "general",
            "source": "manual_entry",
            "type": "faq",
            "document_id": faq_id,
            "ingested_at": datetime.utcnow().isoformat(),
            "added_by": request.admin_id,
            "admin_id": request.admin_id,
            "question_id": str(question_id),
            "language": request.language or "English"
        }
        
        # Remove None values
        metadata = {k: v for k, v in metadata.items() if v is not None}
        
        # Insert into Pinecone
        index = vector_store.index
        index.upsert(
            vectors=[{
                "id": faq_id,
                "values": question_embedding,
                "metadata": metadata
            }],
            namespace="sweden_relocators_v3"
        )
        
        # Update database with FAQ ID
        async with get_async_session() as session:
            query = select(KBUnansweredQuestion).where(
                KBUnansweredQuestion.id == question_id
            )
            result = await session.execute(query)
            entry = result.scalar_one_or_none()
            
            if entry:
                entry.kb_document_id = faq_id
                await session.commit()
        
        # Invalidate cache
        faq_cache.invalidate_query(request.question, request.language or "English")
        
        # Also invalidate Redis cache if available
        global redis_cache
        if redis_cache:
            try:
                await redis_cache.delete(request.question, request.language or "English")
            except Exception as e:
                logger.warning(f"Failed to invalidate Redis cache: {e}")
        
        logger.info(f"Manually added KB entry {question_id} (FAQ ID: {faq_id}) by {request.admin_id}")
        return {
            "success": True,
            "faq_id": faq_id,
            "question_id": question_id,
            "message": "Successfully added to knowledge base"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = repr(e)
        logger.error(f"Error manually adding to KB: {error_msg}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to add to KB: {str(e)}")


@app.get("/kb-curation/items")
async def get_kb_items(
    status: Optional[str] = "added_to_kb",
    limit: int = 100,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Get list of KB items (questions added to knowledge base)
    """
    try:
        from database.kb_curation import KBUnansweredQuestion
        from database.models import get_async_session
        
        async with get_async_session() as session:
            # Build query
            query = select(KBUnansweredQuestion)
            
            if status:
                query = query.where(KBUnansweredQuestion.status == status)
            
            query = query.order_by(desc(KBUnansweredQuestion.added_to_kb_at)).limit(limit)
            
            result = await session.execute(query)
            questions = result.scalars().all()
            
            items = []
            for q in questions:
                items.append({
                    "id": q.id,
                    "user_question": q.user_question,
                    "admin_response": q.admin_response,
                    "category": q.category,
                    "kb_document_id": q.kb_document_id,
                    "added_to_kb_at": q.added_to_kb_at.isoformat() if q.added_to_kb_at else None,
                    "added_by_admin": q.added_by_admin,
                    "source": "admin_curated",
                    "status": q.status,
                    "created_at": q.created_at.isoformat() if q.created_at else None
                })
        
        return {
            "success": True,
            "items": items,
            "count": len(items)
        }
        
    except Exception as e:
        error_msg = repr(e)
        logger.error(f"Error fetching KB items: {error_msg}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch KB items: {str(e)}")


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
        workers=1  # Use 1 worker to avoid multiple embedding loads
    )
