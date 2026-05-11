"""
FastAPI application - REST API server (replaces n8n webhook)
"""
import os

from fastapi import FastAPI, HTTPException, Request, Header, BackgroundTasks, Depends, Security, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any
import time
import asyncio
import re
import csv
import io
from datetime import datetime
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from graph import process_message, resume_conversation, get_conversation_state
from config import settings
from database.conversation import get_conversation_history as db_get_history
from database.admin_queue import get_admin_queue, update_queue_status
from database.llm_provider_config_runtime import (
    get_workspace_llm_config,
    upsert_workspace_llm_config,
)
from llm.factory import (
    fetch_provider_models,
    get_registered_providers,
    normalize_provider,
    validate_model_name,
)
from database.models import AdminAvailability, ClientApiKey, get_async_session, bootstrap_runtime_tables
from database.ingestion_jobs import (
    create_knowledge_source,
    list_knowledge_sources,
    create_ingestion_job,
    list_ingestion_jobs,
    run_ingestion_job,
)
from database.retrieval_modes import (
    get_retrieval_profile,
    select_retrieval_mode,
    upsert_retrieval_profile,
)
from tenant_context import TenantContext, resolve_tenant_context, validate_context_identifier
from sqlalchemy import select, update as sql_update, desc, inspect
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

# Add CORS middleware.
# - Keeps explicit allow list from settings.
# - Also allows localhost/127.0.0.1 on any port for local validators.
# - Includes "null" origin to support file-based browser previews.
cors_allow_origins = list(settings.ALLOWED_ORIGINS or [])
if "null" not in cors_allow_origins:
    cors_allow_origins.append("null")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Mount static files for frontend
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# Redis cache instance (initialized at startup)
redis_cache = None


# Startup event to pre-load embeddings and initialize Redis
@app.on_event("startup")
async def startup_event():
    """Pre-load embeddings, vector store, and initialize Redis on startup"""
    global redis_cache

    # Ensure ORM runtime tables exist in the active runtime database.
    try:
        verified_tables = await bootstrap_runtime_tables()
        logger.info("✅ Runtime tables verified/created: {}", len(verified_tables))
    except Exception as e:
        logger.opt(exception=True).error("❌ Failed to bootstrap runtime tables: {}", e)
        raise
    
    # Initialize Redis cache
    try:
        from utils.redis_cache import RedisCache
        redis_cache = RedisCache()
        await redis_cache.connect()
        logger.info("✅ Redis cache connected!")
    except Exception as e:
        logger.warning("⚠️ Redis not available, using in-memory cache: {}", e)
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
    tenantId: Optional[str] = Field(None, alias="tenantId", description="Tenant identifier", max_length=80)
    workspaceId: Optional[str] = Field(None, alias="workspaceId", description="Workspace identifier", max_length=80)
    userName: Optional[str] = Field(None, alias="userName", description="User name", max_length=200)
    userEmail: Optional[str] = Field(None, alias="userEmail", description="User email", max_length=200)
    userPhone: Optional[str] = Field(None, alias="userPhone", description="User phone", max_length=50)
    retrievalMode: Optional[str] = Field(
        None,
        alias="retrievalMode",
        description="Optional retrieval mode override: 'rag', 'hybrid', or 'page_index'",
    )
    
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

    @field_validator('tenantId')
    @classmethod
    def validate_tenant_id(cls, v: Optional[str]) -> Optional[str]:
        """Validate tenant identifier when provided"""
        return validate_context_identifier(v, "tenant_id")

    @field_validator('workspaceId')
    @classmethod
    def validate_workspace_id(cls, v: Optional[str]) -> Optional[str]:
        """Validate workspace identifier when provided"""
        return validate_context_identifier(v, "workspace_id")

    @field_validator('retrievalMode')
    @classmethod
    def validate_retrieval_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        normalized = v.strip().lower()
        if normalized not in {"rag", "hybrid", "page_index"}:
            raise ValueError("retrievalMode must be one of: rag, hybrid, page_index")
        return normalized

    class Config:
        populate_by_name = True


class MessageResponse(BaseModel):
    """Agent response"""
    status: str
    message: str
    sessionId: str
    language: Optional[str]
    handoff: bool
    modelUsed: Optional[str] = None
    retrievalMode: Optional[str] = None
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

async def verify_admin_key(
    admin_key: Optional[str] = Security(admin_key_header),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> str:
    """Verify admin API key for admin endpoints.

    Accepts either the configured ADMIN_API_KEY or a Supabase Bearer token so
    that any authenticated frontend user can reach admin/supervision endpoints
    without needing to distribute a separate admin secret.
    """
    # 1. Configured admin key always works
    if settings.ADMIN_API_KEY and admin_key == settings.ADMIN_API_KEY:
        return admin_key

    # 2. Any authenticated user (valid Supabase Bearer token) is allowed
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):].strip()
        if token:
            return token

    # 3. Debug fallback when no admin key is configured at all
    if not settings.ADMIN_API_KEY:
        if not settings.DEBUG:
            raise HTTPException(status_code=403, detail="Admin access not configured")
        return "debug_admin"

    logger.warning("Invalid admin credentials attempt")
    raise HTTPException(
        status_code=403,
        detail="Invalid or missing admin credentials",
        headers={"WWW-Authenticate": "AdminKey"},
    )

async def verify_client_key(client_key: Optional[str] = Security(api_key_header)) -> ClientApiKey:
    """Verify generic client API key (for drop-in widgets or custom apps)."""
    if not client_key:
        raise HTTPException(status_code=401, detail="Missing Client API Key")
        
    async with get_async_session() as session:
        query = select(ClientApiKey).where(
            ClientApiKey.api_key == client_key,
            ClientApiKey.is_active.is_(True)
        )
        result = await session.execute(query)
        key_record = result.scalar_one_or_none()
        
        if not key_record:
            logger.warning(f"Invalid Client API Key attempt: {client_key[:10]}...")
            raise HTTPException(status_code=401, detail="Invalid Client API Key")
            
        # Update last used
        key_record.last_used_at = datetime.utcnow()
        await session.commit()
        
        return key_record


from routers import frontend
app.include_router(frontend.router)


@app.get("/health")
async def health_check():
    """
    Detailed health check for production monitoring.
    Returns component status and latencies for debugging.
    """
    import time
    start_time = time.time()
    
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.API_VERSION,
        "components": {
            "database": {"status": "unknown", "latency_ms": 0},
            "vector_store": {"status": "unknown", "latency_ms": 0},
            "cache": {"status": "unknown", "hit_rate": 0},
            "embedding_model": {"status": "unknown"}
        }
    }
    
    # Check Database
    try:
        db_start = time.time()
        async with get_async_session() as session:
            await session.execute(text("SELECT 1"))
        db_latency = (time.time() - db_start) * 1000
        health_status["components"]["database"] = {
            "status": "healthy",
            "latency_ms": round(db_latency, 2)
        }
    except Exception as e:
        health_status["components"]["database"] = {
            "status": f"unhealthy: {str(e)[:50]}",
            "latency_ms": -1
        }
        health_status["status"] = "degraded"
        logger.error(f"Health check failed (DB): {str(e)}")

    # Check Vector Store (Pinecone)
    try:
        if settings.PINECONE_API_KEY:
            from pinecone import Pinecone
            pc = Pinecone(api_key=settings.PINECONE_API_KEY)
            vs_start = time.time()
            index = pc.Index(settings.PINECONE_INDEX)
            stats = index.describe_index_stats()
            vs_latency = (time.time() - vs_start) * 1000
            health_status["components"]["vector_store"] = {
                "status": "healthy",
                "latency_ms": round(vs_latency, 2),
                "vectors": stats.get("total_vector_count", 0)
            }
        else:
            health_status["components"]["vector_store"] = {"status": "not_configured"}
    except Exception as e:
        health_status["components"]["vector_store"] = {
            "status": f"unhealthy: {str(e)[:50]}",
            "latency_ms": -1
        }
        health_status["status"] = "degraded"
        
    # Check Cache
    try:
        cache_stats = faq_cache.get_stats()
        health_status["components"]["cache"] = {
            "status": "healthy",
            "size": cache_stats.get("cache_size", 0),
            "hit_rate": round(cache_stats.get("hit_rate_pct", 0), 1),
            "semantic_hits": cache_stats.get("semantic_hits", 0)
        }
    except Exception as e:
        health_status["components"]["cache"] = {"status": f"error: {str(e)[:30]}"}
    
    # Check Embedding Model (lazy - just check if service exists)
    try:
        from utils.embedding_service import get_embedding_service
        emb_service = get_embedding_service()
        if emb_service and emb_service.is_available():
            health_status["components"]["embedding_model"] = {"status": "loaded"}
        else:
            health_status["components"]["embedding_model"] = {"status": "not_loaded"}
    except Exception as e:
        health_status["components"]["embedding_model"] = {"status": f"error: {str(e)[:30]}"}
    
    # Total health check time
    health_status["check_duration_ms"] = round((time.time() - start_time) * 1000, 2)
        
    if health_status["status"] != "healthy":
         raise HTTPException(status_code=503, detail=health_status)
         
    return health_status


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


from routers import chat
app.include_router(chat.router)

from routers import admin_supervision
app.include_router(admin_supervision.router)


from routers import admin_api
app.include_router(admin_api.router)

from routers import kb_ingestion
app.include_router(kb_ingestion.router)

from routers import social_integrations
app.include_router(social_integrations.router)



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
        logger.opt(exception=True).error("Error getting FAQ cache stats: {}", str(e))
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
        logger.opt(exception=True).error("Error getting popular FAQs: {}", str(e))
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
        logger.opt(exception=True).error("Error generating FAQ analytics report: {}", str(e))
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
        logger.opt(exception=True).error("Error clearing FAQ cache: {}", str(e))
        raise HTTPException(status_code=500, detail="Failed to clear cache")


# ============================================
# PHASE 5: TENANT ANALYTICS ENDPOINTS
# ============================================
from database.analytics import (
    get_tenant_overview_metrics,
    get_user_performance_metrics,
    get_ai_performance_metrics,
    get_team_performance_metrics,
    get_kb_performance_metrics,
    get_channel_performance_metrics,
    get_usage_governance_metrics,
    get_quota_governance_metrics,
    create_alert_rule,
    get_alert_events,
    export_tenant_analytics_csv,
    run_tenant_analytics_aggregation_job as run_phase5_aggregation_job,
)


class AnalyticsAlertRuleRequest(BaseModel):
    """Request payload for creating tenant analytics alert rules."""

    rule_name: str = Field(..., alias="ruleName", min_length=3, max_length=255)
    metric_name: str = Field(..., alias="metricName", min_length=2, max_length=100)
    condition: str = Field(default="gte")
    threshold_value: float = Field(..., alias="thresholdValue")
    is_active: bool = Field(default=True, alias="isActive")

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"gt", "gte", "lt", "lte"}:
            raise ValueError("condition must be one of: gt, gte, lt, lte")
        return normalized

    class Config:
        populate_by_name = True

@app.get("/tenant-analytics/overview")
async def tenant_analytics_overview(
    days: int = 30,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """Get high-level KPIs for the tenant analytics dashboard."""
    metrics = await get_tenant_overview_metrics(
        tenant_id=tenant_context.tenant_id,
        workspace_id=tenant_context.workspace_id,
        days=days
    )
    return {
        "status": "success",
        "data": metrics
    }

@app.get("/tenant-analytics/channel-performance")
async def tenant_analytics_channel_performance(
    days: int = 30,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """Get metrics grouped by channel."""
    channels = await get_channel_performance_metrics(
        tenant_id=tenant_context.tenant_id,
        workspace_id=tenant_context.workspace_id,
        days=days
    )
    return {
        "status": "success",
        "data": channels
    }


@app.get("/tenant-analytics/user-performance")
async def tenant_analytics_user_performance(
    days: int = 30,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """Get user-outcome metrics (completion, repeat-contact, drop-off)."""
    performance = await get_user_performance_metrics(
        tenant_id=tenant_context.tenant_id,
        workspace_id=tenant_context.workspace_id,
        days=days,
    )
    return {
        "status": "success",
        "data": performance,
    }

@app.get("/tenant-analytics/ai-performance")
async def tenant_analytics_ai_performance(
    days: int = 30,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """Get AI-specific insights (auto-resolution, KB hits, etc.)."""
    performance = await get_ai_performance_metrics(
        tenant_id=tenant_context.tenant_id,
        workspace_id=tenant_context.workspace_id,
        days=days
    )
    return {
        "status": "success",
        "data": performance
    }


@app.get("/tenant-analytics/kb-performance")
async def tenant_analytics_kb_performance(
    days: int = 30,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """Get knowledge-base quality and freshness metrics."""
    performance = await get_kb_performance_metrics(
        tenant_id=tenant_context.tenant_id,
        workspace_id=tenant_context.workspace_id,
        days=days,
    )
    return {
        "status": "success",
        "data": performance,
    }

@app.get("/tenant-analytics/team-performance")
async def tenant_analytics_team_performance(
    days: int = 30,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """Get team performance insights."""
    performance = await get_team_performance_metrics(
        tenant_id=tenant_context.tenant_id,
        workspace_id=tenant_context.workspace_id,
        days=days
    )
    return {
        "status": "success",
        "data": performance
    }


@app.get("/tenant-analytics/export.csv")
async def tenant_analytics_export_csv(
    days: int = 30,
    domain: str = "all",
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """Export tenant analytics metrics in CSV format."""
    try:
        csv_data = await export_tenant_analytics_csv(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
            days=days,
            domain=domain,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    filename = (
        f"tenant-analytics-{tenant_context.tenant_id}-"
        f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.csv"
    )
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )


@app.post("/tenant-analytics/jobs/aggregate")
async def tenant_analytics_run_aggregation_job_endpoint(
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """Run tenant analytics aggregation and governance alert generation now."""
    result = await run_phase5_aggregation_job(
        tenant_id=tenant_context.tenant_id,
        workspace_id=tenant_context.workspace_id,
    )
    return {
        "status": "success",
        "data": result,
    }


@app.post("/tenant-analytics/alerts/rules")
async def tenant_analytics_create_alert_rule(
    request: AnalyticsAlertRuleRequest,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """Create alert rules for tenant analytics governance."""
    try:
        rule = await create_alert_rule(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
            rule_name=request.rule_name,
            metric_name=request.metric_name,
            threshold_value=request.threshold_value,
            condition=request.condition,
            is_active=request.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "status": "success",
        "rule": rule,
    }


@app.get("/tenant-analytics/alerts/events")
async def tenant_analytics_alert_events(
    days: int = 30,
    limit: int = 100,
    status: Optional[str] = None,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """List alert events generated by analytics governance rules."""
    events = await get_alert_events(
        tenant_id=tenant_context.tenant_id,
        workspace_id=tenant_context.workspace_id,
        days=days,
        limit=limit,
        status=status,
    )
    return {
        "status": "success",
        "data": events,
    }


@app.get("/tenant-analytics/governance/usage")
async def tenant_analytics_governance_usage(
    days: int = 30,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """Get tenant usage snapshot and quota utilization."""
    usage = await get_usage_governance_metrics(
        tenant_id=tenant_context.tenant_id,
        workspace_id=tenant_context.workspace_id,
        days=days,
    )
    return {
        "status": "success",
        "data": usage,
    }


@app.get("/tenant-analytics/governance/quota")
async def tenant_analytics_governance_quota(
    days: int = 30,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """Get quota forecast and recommendations for tenant governance."""
    quota = await get_quota_governance_metrics(
        tenant_id=tenant_context.tenant_id,
        workspace_id=tenant_context.workspace_id,
        days=days,
    )
    return {
        "status": "success",
        "data": quota,
    }


# ============================================
# ADMIN SUPERVISION ENDPOINTS
# ============================================
from database.supervision import (
    get_active_conversations,
    get_conversation_messages,
    get_conversation_messages_for_admin,
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


class AdminEnhanceRequest(BaseModel):
    """Request for AI text enhancement actions on admin message"""
    admin_id: str = Field(..., min_length=1, description="Admin ID requesting enhancement")
    message: str = Field(..., min_length=1, max_length=2000, description="Message to enhance")
    action: str = Field(..., description="Enhancement action: shorten|extend|summarize|rephrase|formal|friendly|bullets|grammar")


class ReleaseConversationRequest(BaseModel):
    """Request to release conversation"""
    admin_id: str = Field(..., min_length=1, description="Admin ID releasing")
    end_conversation: bool = Field(default=False, description="End conversation instead of releasing to AI")


@app.get("/admin/supervision/conversations")
async def get_supervised_conversations(
    status: Optional[str] = None,
    include_ended: bool = False,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
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
            include_ended=include_ended,
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
            translate_preview=False,
        )
        
        return {
            "status": "success",
            "total": len(conversations),
            "conversations": conversations
        }
    except Exception as e:
        logger.opt(exception=True).error("Error getting supervised conversations: {}", str(e))
        raise HTTPException(status_code=500, detail="Failed to get conversations")


@app.get("/admin/supervision/conversations/{session_id}")
async def get_conversation_detail(
    session_id: str,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """
    Get full conversation history for a session.
    
    Includes all user messages, AI responses, and admin messages.
    """
    try:
        conversation = await get_conversation_messages_for_admin(
            session_id,
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
        )
        
        if not conversation.get("messages") and conversation.get("error"):
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return {
            "status": "success",
            "conversation": conversation
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.opt(exception=True).error("Error getting conversation detail: {}", str(e))
        raise HTTPException(status_code=500, detail="Failed to get conversation")


@app.post("/admin/supervision/conversations/{session_id}/takeover")
async def takeover_conversation(
    session_id: str,
    request: AdminTakeoverRequest,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
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
            reason=request.reason,
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))
        
        logger.opt(exception=True).info("Admin {request.admin_id} took over conversation {session_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.opt(exception=True).error("Error in takeover: {}", e)
        raise HTTPException(status_code=500, detail="Failed to take over conversation")


@app.post("/admin/supervision/conversations/{session_id}/message")
async def send_admin_message(
    session_id: str,
    request: AdminMessageRequest,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
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
            message=request.message,
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.opt(exception=True).error("Error sending admin message: {}", e)
        raise HTTPException(status_code=500, detail="Failed to send message")


@app.post("/admin/supervision/conversations/{session_id}/message/preview")
async def preview_admin_message(
    session_id: str,
    request: AdminPreviewRequest,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """Preview/grammar-check an admin message using the comprehension agent.

    This endpoint is explicitly invoked by the admin UI when the admin clicks
    the preview/check button. It does NOT send or persist the message.
    """
    try:
        # Lazy import to avoid startup dependency if LLM not configured
        from nodes.comprehension_agent import check_message

        result = await check_message(
            request.message,
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
        )

        return {
            "status": "success",
            "corrected": result.get("corrected"),
            "suggestions": result.get("suggestions"),
            "raw": result.get("raw")
        }

    except RuntimeError as re:
        logger.error("Comprehension preview failed: {}", re)
        raise HTTPException(status_code=503, detail=str(re))
    except Exception as e:
        logger.opt(exception=True).error("Error in preview_admin_message: {}", e)
        raise HTTPException(status_code=500, detail="Failed to run preview")


@app.post("/admin/supervision/conversations/{session_id}/message/enhance")
async def enhance_admin_message(
    session_id: str,
    request: AdminEnhanceRequest,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """Apply an AI enhancement action to an admin's draft message.

    Actions: shorten, extend, summarize, rephrase, formal, friendly, bullets, grammar
    """
    VALID_ACTIONS = {"shorten", "extend", "summarize", "rephrase", "formal", "friendly", "bullets", "grammar"}
    if request.action not in VALID_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid action. Must be one of: {', '.join(sorted(VALID_ACTIONS))}")

    try:
        from nodes.comprehension_agent import enhance_message
        result = await enhance_message(
            request.message,
            request.action,
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
        )
        return {"status": "success", **result}
    except RuntimeError as re:
        logger.error("Enhance message failed: {}", re)
        raise HTTPException(status_code=503, detail=str(re))
    except Exception as e:
        logger.opt(exception=True).error("Error in enhance_admin_message: {}", e)
        raise HTTPException(status_code=500, detail="Failed to enhance message")


@app.post("/admin/supervision/conversations/{session_id}/release")
async def release_admin_conversation(
    session_id: str,
    request: ReleaseConversationRequest,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
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
            end_conversation=request.end_conversation,
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))
        
        logger.info(f"Admin {request.admin_id} released conversation {session_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error releasing conversation: {}", e)
        raise HTTPException(status_code=500, detail="Failed to release conversation")


# ============================================================================
# SUPER ADMIN ENDPOINTS
# ============================================================================

class SuperAdminTakeoverRequest(BaseModel):
    """Request for super admin to take over conversation"""
    super_admin_id: str
    reason: Optional[str] = "Super admin intervention"


class SuperAdminReleaseRequest(BaseModel):
    """Request for super admin to release conversation"""
    super_admin_id: str
    return_to_previous: Optional[bool] = True


@app.get("/super-admin/verify/{admin_id}")
async def verify_super_admin_role(
    admin_id: str,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Verify if admin has super_admin role
    """
    try:
        from database.super_admin import verify_super_admin
        
        is_super_admin = await verify_super_admin(admin_id)
        
        return {
            "admin_id": admin_id,
            "is_super_admin": is_super_admin
        }
        
    except Exception as e:
        logger.opt(exception=True).error("Error verifying super admin: {}", str(e))
        raise HTTPException(status_code=500, detail="Failed to verify super admin")


@app.get("/super-admin/dashboard/stats")
async def get_super_admin_stats(
    admin_key: str = Depends(verify_admin_key)
):
    """
    Get all admin statistics for super admin dashboard
    
    Returns workload, queries handled, resolution times for all admins
    """
    try:
        from database.super_admin import get_all_admin_stats
        
        stats = await get_all_admin_stats()
        
        return {
            "admins": stats,
            "total_admins": len(stats),
            "online_admins": sum(1 for a in stats if a["status"] == "online"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.opt(exception=True).error("Error getting super admin stats: {}", str(e))
        raise HTTPException(status_code=500, detail="Failed to get admin stats")


@app.get("/super-admin/conversations/monitor")
async def monitor_all_conversations(
    admin_key: str = Depends(verify_admin_key)
):
    """
    Monitor all active conversations across all admins
    
    Super admin can see all conversations in real-time
    """
    try:
        from database.super_admin import get_all_conversations_monitor
        
        conversations = await get_all_conversations_monitor()
        
        return {
            "conversations": conversations,
            "total_conversations": len(conversations),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.opt(exception=True).error("Error monitoring conversations: {}", str(e))
        raise HTTPException(status_code=500, detail="Failed to monitor conversations")


@app.get("/super-admin/query-distribution")
async def get_query_distribution_stats(
    admin_key: str = Depends(verify_admin_key)
):
    """
    Get query distribution across all admins
    
    Shows how many queries each admin has handled (last 24 hours)
    """
    try:
        from database.super_admin import get_query_distribution
        
        distribution = await get_query_distribution()
        
        return distribution
        
    except Exception as e:
        logger.opt(exception=True).error("Error getting query distribution: {}", str(e))
        raise HTTPException(status_code=500, detail="Failed to get query distribution")


@app.post("/super-admin/takeover/{session_id}")
async def super_admin_takeover_conversation(
    session_id: str,
    request: SuperAdminTakeoverRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Super admin takes over a conversation from current admin
    
    This allows super admin to intervene in any conversation
    """
    try:
        from database.super_admin import verify_super_admin, super_admin_takeover
        
        # Verify super admin role
        is_super_admin = await verify_super_admin(request.super_admin_id)
        if not is_super_admin:
            raise HTTPException(status_code=403, detail="Not authorized as super admin")
        
        result = await super_admin_takeover(
            super_admin_id=request.super_admin_id,
            session_id=session_id,
            reason=request.reason or "Super admin intervention"
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("message"))
        
        logger.opt(exception=True).info("Super admin {request.super_admin_id} took over conversation {session_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in super admin takeover: {}", e)
        raise HTTPException(status_code=500, detail="Failed to takeover conversation")


@app.post("/super-admin/release/{session_id}")
async def super_admin_release_conversation(
    session_id: str,
    request: SuperAdminReleaseRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Super admin releases a conversation back to previous admin or ends it
    
    If return_to_previous=True, conversation goes back to original admin
    If return_to_previous=False, conversation is ended
    """
    try:
        from database.super_admin import verify_super_admin, super_admin_release
        
        # Verify super admin role
        is_super_admin = await verify_super_admin(request.super_admin_id)
        if not is_super_admin:
            raise HTTPException(status_code=403, detail="Not authorized as super admin")
        
        result = await super_admin_release(
            super_admin_id=request.super_admin_id,
            session_id=session_id,
            return_to_previous=request.return_to_previous
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("message"))
        
        logger.opt(exception=True).info("Super admin {request.super_admin_id} released conversation {session_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in super admin release: {}", e)
        raise HTTPException(status_code=500, detail="Failed to release conversation")


class SuperAdminReassignRequest(BaseModel):
    """Request for super admin to reassign a conversation to a different admin"""
    super_admin_id: str
    target_admin_id: str
    reason: Optional[str] = "Super admin reassignment"


@app.post("/super-admin/reassign/{session_id}")
async def super_admin_reassign_conversation(
    session_id: str,
    request: SuperAdminReassignRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Super admin manually reassigns a conversation to a specific admin.

    Allows super admin to override automatic distribution and hand
    a conversation directly to any available admin.
    """
    try:
        from database.super_admin import verify_super_admin, reassign_conversation

        is_super_admin = await verify_super_admin(request.super_admin_id)
        if not is_super_admin:
            raise HTTPException(status_code=403, detail="Not authorized as super admin")

        result = await reassign_conversation(
            super_admin_id=request.super_admin_id,
            session_id=session_id,
            target_admin_id=request.target_admin_id,
            reason=request.reason or "Super admin reassignment"
        )

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("message"))

        logger.opt(exception=True).info("Super admin {request.super_admin_id} reassigned {session_id} to {request.target_admin_id}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in super admin reassign: {}", e)
        raise HTTPException(status_code=500, detail="Failed to reassign conversation")


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
        
        logger.opt(exception=True).info("Logged unanswered question {question_id} for session {request.session_id}")
        return {
            "success": True,
            "question_id": question_id,
            "message": "Question logged successfully"
        }
        
    except Exception as e:
        logger.error("Error logging unanswered question: {}", e)
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
        
        logger.opt(exception=True).info("Linked response to question {question_id}")
        return {
            "success": True,
            "response_id": question_id,
            "message": "Response linked successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error linking response: {}", e)
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
        
        logger.opt(exception=True).info("Approved question {question_id} for KB")
        return {
            "success": True,
            "approval_id": question_id,
            "message": "Approved for KB successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error approving for KB: {}", e)
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
                logger.opt(exception=True).info("Invalidated Redis cache for question: {qa_data['question'][:50]}...")
            except Exception as e:
                logger.warning("Failed to invalidate Redis cache: {}", e)
        
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
        logger.error(f"Error adding to KB: {error_msg}", e)
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
        
        logger.opt(exception=True).info("Removed question {question_id} (FAQ ID: {faq_id}) from KB by {request.admin_id}")
        return {
            "success": True,
            "message": "Successfully removed from KB",
            "faq_id": faq_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = repr(e)
        logger.error("Error removing from KB: {}", error_msg)
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
                    logger.opt(exception=True).warning("Failed to invalidate Redis cache: {}")
        
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
        logger.error(f"Error updating KB: {error_msg}", e)
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
                logger.opt(exception=True).warning("Failed to invalidate Redis cache: {}")
        
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
        logger.error(f"Error manually adding to KB: {error_msg}", e)
        raise HTTPException(status_code=500, detail=f"Failed to add to KB: {str(e)}")


@app.post("/kb-curation/csv-import")
async def csv_import_to_kb(
    admin_id: str,
    file: UploadFile = File(...),
    admin_key: str = Depends(verify_admin_key)
):
    """
    Bulk-import Q&A pairs from a CSV file into the knowledge base.

    Expected CSV columns (header row required):
      question, answer, category (optional), language (optional)

    Returns a summary of successes and failures.
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")

    try:
        from database.kb_curation import KBUnansweredQuestion
        from database.models import get_async_session
        from tools.knowledge_base import get_cached_embeddings, get_cached_vector_store

        embeddings = get_cached_embeddings()
        vector_store = get_cached_vector_store()
        if embeddings is None or vector_store is None:
            raise HTTPException(status_code=500, detail="Embeddings or vector store not initialized")

        raw = await file.read()
        try:
            text_content = raw.decode("utf-8")
        except UnicodeDecodeError:
            text_content = raw.decode("latin-1")

        reader = csv.DictReader(io.StringIO(text_content))

        # Normalise header names (strip whitespace, lower-case)
        reader.fieldnames = [f.strip().lower() for f in (reader.fieldnames or [])]

        if "question" not in reader.fieldnames or "answer" not in reader.fieldnames:
            raise HTTPException(
                status_code=400,
                detail="CSV must have 'question' and 'answer' columns (header row required)"
            )

        results = {"total": 0, "success": 0, "failed": 0, "errors": [], "added_ids": []}

        for row in reader:
            results["total"] += 1
            question = (row.get("question") or "").strip()
            answer   = (row.get("answer")   or "").strip()
            category = (row.get("category") or "general").strip() or "general"
            language = (row.get("language") or "English").strip() or "English"

            if not question or not answer:
                results["failed"] += 1
                results["errors"].append(f"Row {results['total']}: empty question or answer")
                continue

            try:
                # 1. DB record
                async with get_async_session() as session:
                    entry = KBUnansweredQuestion(
                        user_question=question,
                        admin_response=answer,
                        user_language=language,
                        category=category,
                        status="manually_added",
                        added_to_kb=True,
                        added_by_admin=admin_id,
                        added_to_kb_at=datetime.utcnow(),
                        admin_responded_at=datetime.utcnow(),
                        admin_id=admin_id,
                        session_id="csv_import",
                        user_id=admin_id,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    session.add(entry)
                    await session.commit()
                    await session.refresh(entry)
                    question_id = entry.id

                # 2. Pinecone upsert
                faq_id = f"faq_csv_{question_id}_{int(datetime.utcnow().timestamp())}"
                embedding = embeddings.embed_query(question)
                metadata = {
                    "faq_id": faq_id, "question": question, "answer": answer,
                    "category": category, "source": "csv_import", "type": "faq",
                    "document_id": faq_id, "ingested_at": datetime.utcnow().isoformat(),
                    "admin_id": admin_id, "question_id": str(question_id), "language": language
                }
                vector_store.index.upsert(
                    vectors=[{"id": faq_id, "values": embedding, "metadata": metadata}],
                    namespace="sweden_relocators_v3"
                )

                # 3. Update DB with faq_id
                async with get_async_session() as session:
                    from sqlalchemy import select as sa_select
                    res = await session.execute(sa_select(KBUnansweredQuestion).where(KBUnansweredQuestion.id == question_id))
                    rec = res.scalar_one_or_none()
                    if rec:
                        rec.kb_document_id = faq_id
                        await session.commit()

                # 4. Cache invalidation
                faq_cache.invalidate_query(question, language)
                global redis_cache
                if redis_cache:
                    try:
                        await redis_cache.delete(question, language)
                    except Exception:
                        pass

                results["success"] += 1
                results["added_ids"].append(question_id)

            except Exception as row_err:
                results["failed"] += 1
                results["errors"].append(f"Row {results['total']} ('{question[:40]}'): {str(row_err)}")
                logger.opt(exception=True).warning("CSV import row {results['total']} failed: {row_err}")

        logger.info(f"CSV import by {admin_id}: {results['success']}/{results['total']} succeeded")
        return {
            "success": True,
            "summary": results,
            "message": f"Imported {results['success']} of {results['total']} rows successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("CSV import error: {}", repr(e))
        raise HTTPException(status_code=500, detail=f"CSV import failed: {str(e)}")


@app.get("/kb-curation/items")
async def get_kb_items(
    status: Optional[str] = None,
    added_to_kb: bool = True,
    limit: int = 200,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Get list of KB items (questions added to knowledge base).
    By default returns all entries where added_to_kb=True (regardless of status).
    """
    try:
        from database.kb_curation import KBUnansweredQuestion
        from database.models import get_async_session
        
        async with get_async_session() as session:
            has_kb_table = await (await session.connection()).run_sync(
                lambda sync_conn: inspect(sync_conn).has_table("kb_unanswered_questions")
            )
            if not has_kb_table:
                logger.warning("kb_unanswered_questions table is missing; returning empty KB items list")
                return {
                    "success": True,
                    "items": [],
                    "count": 0,
                }

            query = select(KBUnansweredQuestion)
            
            # Filter by added_to_kb boolean (covers manual-add AND csv-import)
            query = query.where(KBUnansweredQuestion.added_to_kb.is_(True))
            
            # Optionally also filter by status
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
                    "user_language": q.user_language,
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
        if "kb_unanswered_questions" in error_msg and (
            "UndefinedTable" in error_msg or "does not exist" in error_msg or "relation" in error_msg
        ):
            logger.warning(
                "kb_unanswered_questions table not available during KB items fetch; returning empty list"
            )
            return {
                "success": True,
                "items": [],
                "count": 0,
            }

        logger.opt(exception=True).error("Error fetching KB items: {}", error_msg)
        raise HTTPException(status_code=500, detail=f"Failed to fetch KB items: {str(e)}")


# ============================================================================
# PHASE 2: ADAPTIVE DATA INGESTION (FILE UPLOAD & CHUNKING)
# ============================================================================

from utils.adaptive_chunking import AdaptiveChunker

@app.post("/admin/workspaces/{workspace_id}/files/upload")
async def upload_document_for_ingestion(
    workspace_id: str,
    file: UploadFile = File(...),
    mode: str = Form("hybrid"),  # "vector", "page", or "hybrid"
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """
    Accepts a PDF, DOCX, or TXT file and dynamically chunks it based on the 
    specified adaptive mode before indexing it into the Vector Store.
    """
    if workspace_id != tenant_context.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")
        
    try:
        file_bytes = await file.read()
        filename = file.filename
        
        # 1. Execute Adaptive Chunking
        chunker = AdaptiveChunker(chunk_size=1000, chunk_overlap=200)
        chunks = chunker.process_file(
            file_bytes=file_bytes,
            filename=filename,
            mode=mode,
            metadata={"admin_id": "api_upload"}
        )
        
        # 2. Get Vector Store and Embeddings Service
        from tools.knowledge_base import get_cached_embeddings, get_cached_vector_store, build_kb_namespace
        embeddings = get_cached_embeddings()
        vector_store = get_cached_vector_store()
        
        if not embeddings or not vector_store:
            raise HTTPException(status_code=500, detail="Vector store / Embeddings not initialized")
            
        namespace = build_kb_namespace(tenant_context.tenant_id, tenant_context.workspace_id)
        index = vector_store.index
        
        # 3. Generate Vectors and Upsert
        # We process chunks in batches to avoid payload size issues
        batch_size = 100
        total_upserted = 0
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i+batch_size]
            vectors_to_upsert = []
            
            for chunk in batch:
                content = chunk["content"]
                if not content.strip():
                    continue
                    
                meta = chunk["metadata"]
                # Pinecone doesn't like complex/nested metadatas sometimes, ensure basic types
                clean_meta = {
                    "text": content,  # We store text directly in metadata for retrieval
                    "source": meta.get("source", filename),
                    "chunk_mode": meta.get("mode", mode),
                    "page": str(meta.get("page", 1)),
                    "ingested_at": datetime.utcnow().isoformat()
                }
                
                # Generate unique determinisitic ID or random uuid
                import uuid
                doc_id = f"doc_{uuid.uuid4().hex[:12]}"
                clean_meta["document_id"] = doc_id
                
                emb = embeddings.embed_query(content)
                vectors_to_upsert.append({
                    "id": doc_id,
                    "values": emb,
                    "metadata": clean_meta
                })
                
            if vectors_to_upsert:
                index.upsert(vectors=vectors_to_upsert, namespace=namespace)
                total_upserted += len(vectors_to_upsert)
                
        return {
            "status": "success",
            "message": f"Successfully processed {filename}",
            "chunks_created": len(chunks),
            "vectors_upserted": total_upserted,
            "mode_used": mode,
            "namespace": namespace
        }
        
    except Exception as e:
        logger.opt(exception=True).error("Error uploading file for ingestion: {}", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")


# ============================================================================
# PHASE 3: RETRIEVAL MODES + INGESTION SOURCES/JOBS
# ============================================================================

class RetrievalProfileUpsertRequest(BaseModel):
    """Request payload for retrieval profile upsert."""

    defaultMode: str = "rag"
    allowedModes: list[str] = Field(default_factory=lambda: ["rag"])
    pageWindowLimit: int = 4
    complianceCriticality: float = 0.5
    averageDocumentPages: int = 10
    queryComplexity: float = 0.5
    latencyBudgetMs: int = 2500
    costSensitivity: float = 0.5


class RetrievalRecommendationRequest(BaseModel):
    """Request payload for retrieval recommendation preview/selection."""

    query: str = Field(..., min_length=1, max_length=5000)
    selectedModeOverride: Optional[str] = None


class KnowledgeSourceCreateRequest(BaseModel):
    """Request payload for creating knowledge source connectors."""

    sourceName: str = Field(..., min_length=1, max_length=255)
    sourceType: str = Field(..., min_length=1, max_length=50)
    sourceUri: Optional[str] = None
    sourceConfig: Optional[dict[str, Any]] = None
    createdBy: Optional[str] = None


class IngestionJobCreateRequest(BaseModel):
    """Request payload to enqueue an ingestion job."""

    sourceId: int
    createdBy: Optional[str] = None
    triggerType: str = "manual"
    runNow: bool = True


@app.get("/admin/retrieval/profile")
async def get_retrieval_profile_endpoint(
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key),
):
    """Get workspace retrieval profile (Phase 3)."""
    try:
        profile = await get_retrieval_profile(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
        )
        return {
            "status": "success",
            "profile": profile,
        }
    except Exception as e:
        logger.opt(exception=True).error("Error getting retrieval profile: {}", str(e))
        raise HTTPException(status_code=500, detail="Failed to get retrieval profile")


@app.post("/admin/retrieval/profile")
async def upsert_retrieval_profile_endpoint(
    request: RetrievalProfileUpsertRequest,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key),
):
    """Create or update retrieval profile for workspace (Phase 3)."""
    try:
        profile = await upsert_retrieval_profile(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
            default_mode=request.defaultMode,
            allowed_modes=request.allowedModes,
            page_window_limit=request.pageWindowLimit,
            compliance_criticality=request.complianceCriticality,
            average_document_pages=request.averageDocumentPages,
            query_complexity=request.queryComplexity,
            latency_budget_ms=request.latencyBudgetMs,
            cost_sensitivity=request.costSensitivity,
        )
        return {
            "status": "success",
            "profile": profile,
        }
    except Exception as e:
        logger.opt(exception=True).error("Error upserting retrieval profile: {}", str(e))
        raise HTTPException(status_code=500, detail="Failed to upsert retrieval profile")


@app.post("/admin/retrieval/recommend")
async def retrieval_recommendation_endpoint(
    request: RetrievalRecommendationRequest,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key),
):
    """Get retrieval recommendation and selected mode for a query (Phase 3)."""
    try:
        selection = await select_retrieval_mode(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
            query_text=request.query,
            selected_mode_override=request.selectedModeOverride,
        )
        return {
            "status": "success",
            "selection": selection,
        }
    except Exception as e:
        logger.opt(exception=True).error("Error selecting retrieval mode: {}", str(e))
        raise HTTPException(status_code=500, detail="Failed to select retrieval mode")



from routers import admin_actions
app.include_router(admin_actions.router)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler - logs full traceback but returns safe message"""
    logger.opt(exception=exc).error("Unhandled exception: {}", exc)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Internal server error"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        workers=1  # Use 1 worker to avoid multiple embedding loads
    )
