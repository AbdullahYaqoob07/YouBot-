from fastapi import APIRouter, Depends, HTTPException
from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from loguru import logger
from sqlalchemy import select

from database.assistant_profile import (
    get_assistant_profile,
    upsert_assistant_profile,
)
from database.models import AdminAvailability, ClientApiKey, get_async_session
from database.workspace_provisioning import ensure_workspace_provisioned
from tenant_context import TenantContext, resolve_tenant_context, resolve_workspace_alias

from app import verify_admin_key, verify_api_key

from llm.factory import get_registered_providers, normalize_provider, validate_model_name
from database.llm_provider_config_runtime import delete_workspace_llm_config, upsert_workspace_llm_config
import asyncio
from config import settings

router = APIRouter(tags=["Admin API"])

class AdminCreateRequest(BaseModel):
    """Admin creation request"""
    adminId: str
    adminName: str
    adminEmail: str
    maxQueueSize: int = 10

class ClientApiKeyCreateRequest(BaseModel):
    """Request to create a new Client API Key"""
    name: str = Field(..., description="Name for the API Key")
    key_type: str = Field(default="public_widget", description="Type of key: public_widget or secret_api")
    allowed_domains: Optional[list[str]] = Field(default=None, description="List of allowed CORS domains")

class ClientApiKeyResponse(BaseModel):
    """Response model for Client API Key"""
    id: int
    name: str
    key_type: str
    api_key: str
    allowed_domains: Optional[list[str]] = None
    is_active: bool
    created_at: str
    last_used_at: Optional[str] = None

class WorkspaceLLMConfigRequest(BaseModel):
    """Workspace LLM provider/model/key configuration request."""
    provider: str = Field(..., description="LLM provider identifier")
    model: str = Field(..., min_length=1, max_length=200, description="Provider model identifier")
    apiKey: str = Field(..., alias="apiKey", min_length=16, description="Provider API key")

    @field_validator('provider')
    @classmethod
    def validate_provider(cls, v: str) -> str:
        try:
            return normalize_provider(v)
        except ValueError as exc:
            supported = get_registered_providers()
            raise ValueError(f"{exc}. Supported providers: {supported}") from exc

    class Config:
        populate_by_name = True

class WorkspaceLLMConfigResponse(BaseModel):
    """Sanitized workspace LLM configuration response."""
    tenantId: str
    workspaceId: str
    provider: str
    model: str
    hasApiKey: bool
    maskedApiKey: str
    updatedAt: Optional[str] = None


async def delete_client_api_key(
    tenant_id: str,
    workspace_id: str,
    key_id: int,
) -> dict[str, Any]:
    async with get_async_session() as session:
        stmt = select(ClientApiKey).where(
            ClientApiKey.id == key_id,
            ClientApiKey.tenant_id == tenant_id,
            ClientApiKey.workspace_id == workspace_id,
        )
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            raise ValueError("Client API key not found for this workspace")

        deleted_name = str(row.name)
        deleted_key_type = str(row.key_type)

        await session.delete(row)
        await session.commit()

    return {
        "deleted_key_id": key_id,
        "name": deleted_name,
        "key_type": deleted_key_type,
    }

@router.post("/admin/create")
async def create_admin(
    request: AdminCreateRequest,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    try:
        async with get_async_session() as session:
            query = select(AdminAvailability).where(
                AdminAvailability.admin_id == request.adminId,
                AdminAvailability.tenant_id == tenant_context.tenant_id,
                AdminAvailability.workspace_id == tenant_context.workspace_id,
            )
            result = await session.execute(query)
            admin = result.scalar_one_or_none()
            
            if admin:
                admin.admin_name = request.adminName
                admin.admin_email = request.adminEmail
                admin.max_queue_size = request.maxQueueSize
                admin.status = 'online'
                admin.updated_at = datetime.utcnow()
            else:
                admin = AdminAvailability(
                    admin_id=request.adminId,
                    admin_name=request.adminName,
                    admin_email=request.adminEmail,
                    tenant_id=tenant_context.tenant_id,
                    workspace_id=tenant_context.workspace_id,
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
        logger.opt(exception=True).error("Error creating admin: {}", e)
        raise HTTPException(status_code=500, detail="Failed to create admin")

@router.get("/admin/workspaces/{workspace_id}/client-keys", response_model=list[ClientApiKeyResponse])
async def list_client_keys(
    workspace_id: str,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    api_key: str = Depends(verify_api_key)
):
    resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
    if resolved_path_workspace_id != tenant_context.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")
        
    try:
        async with get_async_session() as session:
            stmt = select(ClientApiKey).where(
                ClientApiKey.tenant_id == tenant_context.tenant_id,
                ClientApiKey.workspace_id == tenant_context.workspace_id
            )
            result = await session.execute(stmt)
            keys = result.scalars().all()
            
            return [
                ClientApiKeyResponse(
                    id=k.id, name=k.name, key_type=k.key_type, api_key=k.api_key,
                    allowed_domains=k.allowed_domains, is_active=k.is_active,
                    created_at=k.created_at.isoformat() if k.created_at else "",
                    last_used_at=k.last_used_at.isoformat() if k.last_used_at else None
                ) for k in keys
            ]
    except Exception as e:
        logger.opt(exception=True).error("Error listing client keys: {}", e)
        raise HTTPException(status_code=500, detail="Failed to list client API keys")
        
@router.post("/admin/workspaces/{workspace_id}/client-keys", response_model=ClientApiKeyResponse)
async def create_client_key(
    workspace_id: str,
    request: ClientApiKeyCreateRequest,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    api_key: str = Depends(verify_api_key)
):
    resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
    if resolved_path_workspace_id != tenant_context.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")
        
    try:
        import secrets
        prefix = "pk_" if request.key_type == "public_widget" else "sk_"
        new_api_key = f"{prefix}{secrets.token_urlsafe(32)}"
        
        async with get_async_session() as session:
            await ensure_workspace_provisioned(
                session, tenant_context.tenant_id, tenant_context.workspace_id
            )
            client_key = ClientApiKey(
                tenant_id=tenant_context.tenant_id, workspace_id=tenant_context.workspace_id,
                name=request.name, key_type=request.key_type, api_key=new_api_key,
                allowed_domains=request.allowed_domains, is_active=True,
                created_at=datetime.utcnow()
            )
            session.add(client_key)
            await session.commit()
            
            return ClientApiKeyResponse(
                id=client_key.id, name=client_key.name, key_type=client_key.key_type,
                api_key=client_key.api_key, allowed_domains=client_key.allowed_domains,
                is_active=client_key.is_active, created_at=client_key.created_at.isoformat(), last_used_at=None
            )
    except Exception as e:
        logger.opt(exception=True).error("Error creating client key: {}", e)
        raise HTTPException(status_code=500, detail="Failed to create client API key")


@router.delete("/admin/workspaces/{workspace_id}/client-keys/{key_id}")
async def delete_client_key(
    workspace_id: str,
    key_id: int,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    api_key: str = Depends(verify_api_key),
):
    resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
    if resolved_path_workspace_id != tenant_context.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")

    try:
        result = await delete_client_api_key(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
            key_id=key_id,
        )
        return {"status": "success", **result}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as e:
        logger.opt(exception=True).error("Error deleting client API key {}: {}", key_id, e)
        raise HTTPException(status_code=500, detail="Failed to delete client API key")

@router.post("/admin/workspaces/{workspace_id}/llm-config", response_model=WorkspaceLLMConfigResponse)
async def upsert_workspace_llm_provider_config_endpoint(
    workspace_id: str,
    request: WorkspaceLLMConfigRequest,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    try:
        resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
        if resolved_path_workspace_id != tenant_context.workspace_id:
            raise HTTPException(status_code=400, detail="workspace_id path and context header do not match")

        if settings.LLM_MODEL_VALIDATION_REQUIRED:
            try:
                is_valid, catalog_models, suggestions = await asyncio.to_thread(
                    validate_model_name,
                    request.provider,
                    request.model,
                    request.apiKey,
                )
                if not is_valid:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": f"Model '{request.model}' is invalid or not accessible for provider '{request.provider}'.",
                            "suggestions": suggestions,
                        },
                    )
            except Exception as valid_err:
                if isinstance(valid_err, HTTPException):
                    raise valid_err
                logger.warning(
                    "Could not validate model '{}' for provider '{}': {}",
                    request.model,
                    request.provider,
                    valid_err,
                )

        config_result = await upsert_workspace_llm_config(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
            provider=request.provider,
            model_name=request.model,
            api_key=request.apiKey,
            actor="admin_api"
        )
        return WorkspaceLLMConfigResponse(
            tenantId=config_result["tenant_id"],
            workspaceId=config_result["workspace_id"],
            provider=config_result["provider"],
            model=config_result["model"],
            hasApiKey=config_result["has_api_key"],
            maskedApiKey=config_result["masked_api_key"],
            updatedAt=config_result["updated_at"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.opt(exception=True).error("Error saving workspace LLM config: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/admin/workspaces/{workspace_id}/llm-config")
async def delete_workspace_llm_provider_config_endpoint(
    workspace_id: str,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key),
):
    try:
        resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
        if resolved_path_workspace_id != tenant_context.workspace_id:
            raise HTTPException(status_code=400, detail="workspace_id path and context header do not match")

        result = await delete_workspace_llm_config(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
        )
        return {"status": "success", **result}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as e:
        logger.opt(exception=True).error("Error deleting workspace LLM config: {}", e)
        raise HTTPException(status_code=500, detail="Failed to delete workspace LLM configuration")

class AdminStatusRequest(BaseModel):
    status: str

class ProviderModelsRequest(BaseModel):
    apiKey: str = Field(..., alias="apiKey")
    forceRefresh: bool = Field(default=False, alias="forceRefresh")
    class Config:
        populate_by_name = True

class ProviderModelsResponse(BaseModel):
    provider: str
    models: list[str]
    total: int

@router.get("/admin/workspaces/{workspace_id}/llm-config", response_model=WorkspaceLLMConfigResponse)
async def read_workspace_llm_provider_config(
    workspace_id: str,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    try:
        from database.llm_provider_config_runtime import get_workspace_llm_config
        
        resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
        if resolved_path_workspace_id != tenant_context.workspace_id:
            raise HTTPException(status_code=400, detail="workspace_id mismatch")
            
        cfg = await get_workspace_llm_config(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
        )
        if not cfg:
            raise HTTPException(status_code=404, detail="No workspace LLM configuration found")
        return WorkspaceLLMConfigResponse(
            tenantId=cfg["tenant_id"],
            workspaceId=cfg["workspace_id"],
            provider=cfg["provider"],
            model=cfg["model"],
            hasApiKey=cfg["has_api_key"],
            maskedApiKey=cfg["masked_api_key"],
            updatedAt=cfg.get("updated_at"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.opt(exception=True).error("Error reading workspace LLM config: {}", e)
        raise HTTPException(status_code=500, detail="Failed to load workspace LLM configuration")

@router.post("/admin/llm/providers/{provider}/models", response_model=ProviderModelsResponse)
async def get_provider_model_catalog(
    provider: str,
    request: ProviderModelsRequest,
    admin_key: str = Depends(verify_admin_key),
):
    try:
        from llm.factory import fetch_provider_models
        normalized = normalize_provider(provider)
        models = await asyncio.to_thread(
            fetch_provider_models,
            normalized,
            request.apiKey,
            settings.LLM_PROVIDER_CATALOG_TIMEOUT_SECONDS,
            request.forceRefresh,
        )
        return ProviderModelsResponse(provider=normalized, models=models, total=len(models))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as e:
        logger.opt(exception=True).error("Error fetching provider model catalog: {}", e)
        raise HTTPException(status_code=502, detail="Failed to fetch provider model catalog")

@router.put("/admin/{admin_id}/status")
async def update_admin_status(
    admin_id: str, 
    request: AdminStatusRequest,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    try:
        from sqlalchemy import update as sql_update
        async with get_async_session() as session:
            stmt = (
                sql_update(AdminAvailability)
                .where(
                    AdminAvailability.admin_id == admin_id,
                    AdminAvailability.tenant_id == tenant_context.tenant_id,
                    AdminAvailability.workspace_id == tenant_context.workspace_id,
                )
                .values(status=request.status, updated_at=datetime.utcnow())
            )
            await session.execute(stmt)
            await session.commit()
            return {"status": "success", "adminId": admin_id, "newStatus": request.status}
    except Exception as e:
        logger.opt(exception=True).error("Error updating admin status: {}", e)
        raise HTTPException(status_code=500, detail="Failed to update admin status")

@router.get("/admin/list")
async def list_admins(
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    try:
        async with get_async_session() as session:
            query = select(AdminAvailability).where(
                AdminAvailability.tenant_id == tenant_context.tenant_id,
                AdminAvailability.workspace_id == tenant_context.workspace_id,
            )
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
        logger.opt(exception=True).error("Error listing admins: {}", e)
        raise HTTPException(status_code=500, detail="Failed to list admins")


# -----------------------------------------------------------------------------
# Admin Test Chat — for the Bot Testing Sandbox in the console.
# Lets the admin send arbitrary messages to their bot with a chosen retrieval
# mode and inspect rich diagnostic state (selected vs recommended mode, KB
# usage, handoff, latency) without needing a client API key.
# -----------------------------------------------------------------------------

class AdminTestChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    retrievalMode: Optional[str] = Field(
        default=None,
        description="One of 'rag', 'hybrid', 'page_index', or null for auto.",
    )
    sessionId: Optional[str] = Field(default=None)
    userId: Optional[str] = Field(default=None)
    channel: str = Field(default="admin_test")

    @field_validator("retrievalMode")
    @classmethod
    def _validate_mode(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        normalized = value.strip().lower()
        if normalized not in {"rag", "hybrid", "page_index"}:
            raise ValueError("retrievalMode must be one of: rag, hybrid, page_index")
        return normalized


@router.post("/admin/workspaces/{workspace_id}/test-chat")
async def admin_test_chat(
    workspace_id: str,
    request: AdminTestChatRequest,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key),
):
    """
    Run a test message through the bot scoped to the admin's workspace and
    return both the customer-facing reply and diagnostic state.
    """
    resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
    if resolved_path_workspace_id != tenant_context.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")

    import re
    import time
    import uuid as _uuid

    from graph import process_message

    safe_tenant = re.sub(r"[^A-Za-z0-9_-]", "_", tenant_context.tenant_id)
    safe_workspace = re.sub(r"[^A-Za-z0-9_-]", "_", tenant_context.workspace_id)
    user_id = request.userId or f"admin_test_{safe_tenant}"
    safe_user = re.sub(r"[^A-Za-z0-9_-]", "_", user_id)
    session_id = (
        request.sessionId
        or f"sess_admintest_{safe_tenant}_{safe_workspace}_{safe_user}_{_uuid.uuid4().hex[:8]}"
    )

    started = time.time()
    try:
        final_state = await process_message(
            message=request.message,
            user_id=user_id,
            session_id=session_id,
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
            channel=request.channel,
            retrieval_mode_override=request.retrievalMode,
        )
    except Exception as exc:
        logger.opt(exception=True).error("Admin test chat failed: {}", exc)
        raise HTTPException(status_code=500, detail="Test chat run failed") from exc

    elapsed_ms = int((time.time() - started) * 1000)

    return {
        "ok": True,
        "sessionId": session_id,
        "userId": user_id,
        "response": final_state.get("ai_response") or "",
        "language": final_state.get("detected_language"),
        "modelUsed": final_state.get("model_used"),
        "knowledgeBaseUsed": bool(final_state.get("knowledge_base_used", False)),
        "cacheHit": bool(final_state.get("cache_hit", False)),
        "requiresHuman": bool(final_state.get("requires_human", False)),
        "handoffReason": final_state.get("handoff_reason"),
        "retrieval": {
            "requestedOverride": request.retrievalMode,
            "selectedMode": final_state.get("retrieval_mode_selected"),
            "recommendedMode": final_state.get("retrieval_mode_recommended"),
            "reason": final_state.get("retrieval_mode_reason"),
        },
        "elapsedMs": elapsed_ms,
    }


# -----------------------------------------------------------------------------
# Assistant Profile — per-workspace bot identity & behaviour.
# Drives the dynamic system prompt so the same backend can serve any company.
# -----------------------------------------------------------------------------

class AssistantProfileUpsertRequest(BaseModel):
    businessName: str = Field(..., min_length=1, max_length=255)
    businessDescription: Optional[str] = Field(default=None, max_length=1000)
    serviceTopics: list[str] = Field(default_factory=list)
    tone: str = Field(default="warm")
    websiteUrl: Optional[str] = Field(default=None, max_length=500)
    contactEmail: Optional[str] = Field(default=None, max_length=255)
    handoffMessage: Optional[str] = Field(default=None, max_length=2000)
    forbiddenTopics: list[str] = Field(default_factory=list)

    @field_validator("tone")
    @classmethod
    def _validate_tone(cls, value: str) -> str:
        cleaned = (value or "").strip().lower()
        if cleaned not in {"warm", "professional", "casual", "formal"}:
            raise ValueError("tone must be one of: warm, professional, casual, formal")
        return cleaned


@router.get("/admin/workspaces/{workspace_id}/assistant-profile")
async def get_workspace_assistant_profile_endpoint(
    workspace_id: str,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key),
):
    resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
    if resolved_path_workspace_id != tenant_context.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")

    profile = await get_assistant_profile(
        tenant_id=tenant_context.tenant_id,
        workspace_id=tenant_context.workspace_id,
    )
    return {"status": "success", "profile": profile}


@router.post("/admin/workspaces/{workspace_id}/assistant-profile")
async def upsert_workspace_assistant_profile_endpoint(
    workspace_id: str,
    request: AssistantProfileUpsertRequest,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key),
):
    resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
    if resolved_path_workspace_id != tenant_context.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")

    try:
        profile = await upsert_assistant_profile(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
            business_name=request.businessName,
            business_description=request.businessDescription,
            service_topics=request.serviceTopics,
            tone=request.tone,
            website_url=request.websiteUrl,
            contact_email=request.contactEmail,
            handoff_message=request.handoffMessage,
            forbidden_topics=request.forbiddenTopics,
        )
        return {"status": "success", "profile": profile}
    except Exception as exc:
        logger.opt(exception=True).error("Assistant profile upsert failed: {}", exc)
        raise HTTPException(status_code=500, detail="Failed to save assistant profile") from exc
