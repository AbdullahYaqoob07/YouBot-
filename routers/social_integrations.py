from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from app import clean_markup, verify_admin_key
from config import settings
from database.social_channel_connections import (
    create_social_channel_connection,
    delete_social_channel_connection,
    get_social_connection_runtime_by_key,
    list_social_channel_connections,
    touch_social_connection_event,
    update_social_channel_connection_status,
)
from graph import process_message
from tenant_context import TenantContext, resolve_tenant_context, resolve_workspace_alias

router = APIRouter(tags=["Social Integrations"])

ALLOWED_PROVIDERS = {"meta", "generic"}
ALLOWED_CHANNELS = {"whatsapp", "facebook", "instagram", "social", "custom"}


class SocialConnectionCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    provider: str = Field(..., description="meta or generic")
    channel: str = Field(..., description="whatsapp, instagram, facebook, social, custom")
    verifyToken: Optional[str] = Field(default=None, alias="verifyToken")
    accessToken: Optional[str] = Field(default=None, alias="accessToken")
    appSecret: Optional[str] = Field(default=None, alias="appSecret")
    outboundWebhookUrl: Optional[str] = Field(default=None, alias="outboundWebhookUrl")
    outboundAuthHeaders: Optional[dict[str, str]] = Field(default=None, alias="outboundAuthHeaders")
    metadata: Optional[dict[str, Any]] = Field(default=None)
    isActive: bool = Field(default=True, alias="isActive")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ALLOWED_PROVIDERS:
            raise ValueError(f"provider must be one of: {sorted(ALLOWED_PROVIDERS)}")
        return normalized

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ALLOWED_CHANNELS:
            raise ValueError(f"channel must be one of: {sorted(ALLOWED_CHANNELS)}")
        return normalized

    class Config:
        populate_by_name = True


class SocialConnectionStatusRequest(BaseModel):
    isActive: bool = Field(..., alias="isActive")

    class Config:
        populate_by_name = True


class SocialInboundMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    userId: str = Field(..., alias="userId", min_length=1, max_length=100)
    sessionId: Optional[str] = Field(default=None, alias="sessionId")
    channel: Optional[str] = Field(default=None)
    userName: Optional[str] = Field(default=None, alias="userName")
    userEmail: Optional[str] = Field(default=None, alias="userEmail")
    userPhone: Optional[str] = Field(default=None, alias="userPhone")
    metadata: Optional[dict[str, Any]] = Field(default=None)

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in ALLOWED_CHANNELS:
            raise ValueError(f"channel must be one of: {sorted(ALLOWED_CHANNELS)}")
        return normalized

    class Config:
        populate_by_name = True


def _safe_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", value)


def _build_session_id(
    tenant_id: str,
    workspace_id: str,
    channel: str,
    user_id: str,
    explicit_session_id: Optional[str] = None,
) -> str:
    if explicit_session_id:
        return explicit_session_id

    safe_tenant = _safe_slug(tenant_id)
    safe_workspace = _safe_slug(workspace_id)
    safe_channel = _safe_slug(channel)
    safe_user = _safe_slug(user_id)
    return f"sess_{safe_tenant}_{safe_workspace}_{safe_channel}_{safe_user}_{int(time.time())}"


def _extract_ai_response(final_state: dict[str, Any]) -> str:
    if final_state.get("ai_response"):
        return str(final_state.get("ai_response"))

    messages = final_state.get("messages") or []
    if messages:
        last = messages[-1]
        content = getattr(last, "content", None)
        if content:
            return str(content)

    return ""


def _is_handoff(final_state: dict[str, Any]) -> bool:
    return bool(final_state.get("route_to_human") or final_state.get("requires_human"))


def _selected_retrieval_mode(final_state: dict[str, Any]) -> Optional[str]:
    return final_state.get("retrieval_mode_selected") or final_state.get("retrieval_mode")


def _assigned_admin_name(final_state: dict[str, Any]) -> Optional[str]:
    if final_state.get("assigned_admin_name"):
        return str(final_state.get("assigned_admin_name"))

    assigned_admin = final_state.get("assigned_admin") or {}
    if isinstance(assigned_admin, dict) and assigned_admin.get("admin_name"):
        return str(assigned_admin.get("admin_name"))

    return None


def _verify_meta_signature(signature_header: Optional[str], body: bytes, app_secret: Optional[str]) -> None:
    # If no app secret configured, we accept unsigned events for dev/onboarding speed.
    if not app_secret:
        return

    if not signature_header:
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256 header")

    if not signature_header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Invalid signature header format")

    supplied_signature = signature_header.split("=", 1)[1]
    digest = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(supplied_signature, digest):
        raise HTTPException(status_code=401, detail="Invalid Meta webhook signature")


async def _dispatch_outbound_webhook(
    *,
    url: str,
    headers: Optional[dict[str, str]],
    payload: dict[str, Any],
) -> dict[str, Any]:
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload, headers=request_headers)
            response.raise_for_status()
            
        return {
            "mode": "outbound_webhook",
            "target": url,
            "status_code": response.status_code,
        }
    except Exception as e:
        return {
            "mode": "outbound_webhook",
            "target": url,
            "error": str(e)
        }


async def _send_meta_whatsapp_response(
    *,
    access_token: str,
    api_version: str,
    phone_number_id: str,
    to_user: str,
    text: str,
) -> dict[str, Any]:
    endpoint = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_user,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": text,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                endpoint,
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()

        return {
            "mode": "meta_whatsapp_api",
            "target": endpoint,
            "status_code": response.status_code,
        }
    except Exception as e:
        return {
            "mode": "meta_whatsapp_api",
            "target": endpoint,
            "error": str(e)
        }


async def _send_meta_messenger_response(
    *,
    access_token: str,
    api_version: str,
    recipient_id: str,
    text: str,
) -> dict[str, Any]:
    endpoint = f"https://graph.facebook.com/{api_version}/me/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "messaging_type": "RESPONSE",
        "message": {"text": text},
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                endpoint,
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()

        return {
            "mode": "meta_messenger_api",
            "target": endpoint,
            "status_code": response.status_code,
        }
    except Exception as e:
        return {
            "mode": "meta_messenger_api",
            "target": endpoint,
            "error": str(e)
        }


async def _dispatch_provider_response(
    connection: dict[str, Any],
    *,
    channel: str,
    user_id: str,
    ai_response: str,
    metadata: Optional[dict[str, Any]],
) -> dict[str, Any]:
    if connection.get("outbound_webhook_url"):
        payload = {
            "provider": connection["provider"],
            "channel": channel,
            "userId": user_id,
            "message": ai_response,
            "tenantId": connection["tenant_id"],
            "workspaceId": connection["workspace_id"],
            "metadata": metadata or {},
        }
        return await _dispatch_outbound_webhook(
            url=connection["outbound_webhook_url"],
            headers=connection.get("outbound_auth_headers"),
            payload=payload,
        )

    if connection.get("provider") != "meta":
        return {"mode": "none", "reason": "no outbound route configured"}

    access_token = connection.get("access_token")
    if not access_token:
        return {"mode": "none", "reason": "meta access token not configured"}

    connection_metadata = connection.get("metadata_json") or {}
    event_metadata = metadata or {}
    api_version = str(connection_metadata.get("graph_api_version") or "v21.0")

    if channel == "whatsapp":
        phone_number_id = str(
            event_metadata.get("phone_number_id")
            or connection_metadata.get("phone_number_id")
            or ""
        )
        if not phone_number_id:
            return {
                "mode": "none",
                "reason": "missing phone_number_id for whatsapp outbound dispatch",
            }
        return await _send_meta_whatsapp_response(
            access_token=access_token,
            api_version=api_version,
            phone_number_id=phone_number_id,
            to_user=user_id,
            text=ai_response,
        )

    if channel in {"facebook", "instagram"}:
        return await _send_meta_messenger_response(
            access_token=access_token,
            api_version=api_version,
            recipient_id=user_id,
            text=ai_response,
        )

    return {"mode": "none", "reason": f"unsupported channel '{channel}' for direct provider dispatch"}


async def _handle_social_message(
    connection: dict[str, Any],
    *,
    message: str,
    user_id: str,
    channel: str,
    session_id: Optional[str],
    user_name: Optional[str],
    user_email: Optional[str],
    user_phone: Optional[str],
    metadata: Optional[dict[str, Any]],
) -> dict[str, Any]:
    start_time = time.time()

    tenant_id = connection["tenant_id"]
    workspace_id = connection["workspace_id"]
    effective_channel = (channel or connection.get("channel") or "social").strip().lower()

    final_session_id = _build_session_id(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        channel=effective_channel,
        user_id=user_id,
        explicit_session_id=session_id,
    )

    final_state = await process_message(
        message=message,
        user_id=user_id,
        session_id=final_session_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        channel=effective_channel,
        user_name=user_name,
        user_email=user_email,
        user_phone=user_phone,
    )

    processing_time_ms = int((time.time() - start_time) * 1000)

    ai_response = clean_markup(_extract_ai_response(final_state))
    handoff = _is_handoff(final_state)

    dispatch = await _dispatch_provider_response(
        connection,
        channel=effective_channel,
        user_id=user_id,
        ai_response=ai_response,
        metadata=metadata,
    )

    return {
        "status": "success",
        "message": ai_response,
        "sessionId": final_session_id,
        "language": final_state.get("detected_language") or final_state.get("language"),
        "handoff": handoff,
        "modelUsed": final_state.get("model_used"),
        "retrievalMode": _selected_retrieval_mode(final_state),
        "assignedTo": _assigned_admin_name(final_state),
        "queueStatus": final_state.get("queue_status"),
        "processingTimeMs": processing_time_ms,
        "dispatch": dispatch,
    }


def _extract_meta_messages(payload: dict[str, Any], default_channel: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    object_type = str(payload.get("object") or "").lower()

    for entry in payload.get("entry", []):
        changes = entry.get("changes") or []
        for change in changes:
            value = change.get("value") or {}
            wa_messages = value.get("messages") or []
            for wa_msg in wa_messages:
                text = ((wa_msg.get("text") or {}).get("body") or "").strip()
                user_id = str(wa_msg.get("from") or "").strip()
                if not text or not user_id:
                    continue

                messages.append(
                    {
                        "message": text,
                        "user_id": user_id,
                        "channel": "whatsapp",
                        "session_id": wa_msg.get("id"),
                        "metadata": {
                            "message_id": wa_msg.get("id"),
                            "phone_number_id": (value.get("metadata") or {}).get("phone_number_id"),
                            "profile": (value.get("contacts") or [{}])[0].get("profile", {}),
                        },
                    }
                )

        messaging_events = entry.get("messaging") or []
        for event in messaging_events:
            msg = event.get("message") or {}
            text = str(msg.get("text") or "").strip()
            user_id = str((event.get("sender") or {}).get("id") or "").strip()
            if not text or not user_id:
                continue

            if object_type == "instagram":
                channel = "instagram"
            elif default_channel in {"instagram", "facebook"}:
                channel = default_channel
            else:
                channel = "facebook"

            messages.append(
                {
                    "message": text,
                    "user_id": user_id,
                    "channel": channel,
                    "session_id": msg.get("mid"),
                    "metadata": {
                        "message_id": msg.get("mid"),
                        "recipient_id": (event.get("recipient") or {}).get("id"),
                        "entry_id": entry.get("id"),
                    },
                }
            )

    return messages


@router.get("/admin/workspaces/{workspace_id}/social-connections")
async def list_social_connections_endpoint(
    workspace_id: str,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key),
):
    resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
    if resolved_path_workspace_id != tenant_context.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")

    rows = await list_social_channel_connections(
        tenant_id=tenant_context.tenant_id,
        workspace_id=tenant_context.workspace_id,
    )

    for row in rows:
        row["integrationPaths"] = {
            "generic": f"/integrations/social/{row['connection_key']}/messages",
            "metaWebhook": f"/integrations/social/meta/{row['connection_key']}/webhook",
        }

    return {"status": "success", "connections": rows}


@router.post("/admin/workspaces/{workspace_id}/social-connections")
async def create_social_connection_endpoint(
    workspace_id: str,
    request: SocialConnectionCreateRequest,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key),
):
    resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
    if resolved_path_workspace_id != tenant_context.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")

    if request.provider == "meta" and not request.verifyToken:
        raise HTTPException(status_code=400, detail="verifyToken is required for provider=meta")

    try:
        connection = await create_social_channel_connection(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
            name=request.name,
            provider=request.provider,
            channel=request.channel,
            verify_token=request.verifyToken,
            access_token=request.accessToken,
            app_secret=request.appSecret,
            outbound_webhook_url=request.outboundWebhookUrl,
            outbound_auth_headers=request.outboundAuthHeaders,
            metadata_json=request.metadata,
            created_by="admin_social_api",
            is_active=request.isActive,
        )
        connection["integrationPaths"] = {
            "generic": f"/integrations/social/{connection['connection_key']}/messages",
            "metaWebhook": f"/integrations/social/meta/{connection['connection_key']}/webhook",
        }
        return {"status": "success", "connection": connection}
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed creating social channel connection: {}", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create social connection") from exc


@router.put("/admin/workspaces/{workspace_id}/social-connections/{connection_id}")
async def update_social_connection_status_endpoint(
    workspace_id: str,
    connection_id: int,
    request: SocialConnectionStatusRequest,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key),
):
    resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
    if resolved_path_workspace_id != tenant_context.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")

    row = await update_social_channel_connection_status(
        tenant_id=tenant_context.tenant_id,
        workspace_id=tenant_context.workspace_id,
        connection_id=connection_id,
        is_active=request.isActive,
    )

    if not row:
        raise HTTPException(status_code=404, detail="Social connection not found")

    return {"status": "success", "connection": row}


@router.delete("/admin/workspaces/{workspace_id}/social-connections/{connection_id}")
async def delete_social_connection_endpoint(
    workspace_id: str,
    connection_id: int,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key),
):
    resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
    if resolved_path_workspace_id != tenant_context.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")

    try:
        row = await delete_social_channel_connection(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
            connection_id=connection_id,
        )
        return {"status": "success", **row}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed deleting social channel connection {}: {}", connection_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete social connection") from exc


@router.post("/integrations/social/{connection_key}/messages")
async def inbound_social_message(
    connection_key: str,
    payload: SocialInboundMessageRequest,
):
    connection = await get_social_connection_runtime_by_key(connection_key)
    if not connection:
        raise HTTPException(status_code=404, detail="Unknown or inactive social connection")

    try:
        result = await _handle_social_message(
            connection,
            message=payload.message,
            user_id=payload.userId,
            channel=payload.channel or connection.get("channel") or "social",
            session_id=payload.sessionId,
            user_name=payload.userName,
            user_email=payload.userEmail,
            user_phone=payload.userPhone,
            metadata=payload.metadata,
        )
        await touch_social_connection_event(connection["id"], None)
        return result
    except Exception as exc:
        logger.error("Social inbound processing failed: {}", exc, exc_info=True)
        await touch_social_connection_event(connection["id"], str(exc)[:800])
        raise HTTPException(status_code=500, detail="Failed to process social message") from exc


@router.get("/integrations/social/meta/{connection_key}/webhook")
async def verify_meta_webhook(
    connection_key: str,
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
):
    connection = await get_social_connection_runtime_by_key(connection_key, provider="meta")
    if not connection:
        raise HTTPException(status_code=404, detail="Unknown or inactive Meta connection")

    if hub_mode != "subscribe":
        raise HTTPException(status_code=400, detail="Unsupported hub.mode")

    if hub_verify_token != connection.get("verify_token"):
        raise HTTPException(status_code=403, detail="Meta verify token mismatch")

    await touch_social_connection_event(connection["id"], None)
    return PlainTextResponse(content=hub_challenge)


@router.post("/integrations/social/meta/{connection_key}/webhook")
async def handle_meta_webhook(
    connection_key: str,
    request: Request,
):
    connection = await get_social_connection_runtime_by_key(connection_key, provider="meta")
    if not connection:
        raise HTTPException(status_code=404, detail="Unknown or inactive Meta connection")

    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    _verify_meta_signature(signature, body, connection.get("app_secret"))

    try:
        payload = json.loads(body.decode("utf-8") if body else "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    extracted = _extract_meta_messages(payload, default_channel=connection.get("channel", "facebook"))
    if not extracted:
        await touch_social_connection_event(connection["id"], None)
        return {"status": "ignored", "reason": "no supported message events found"}

    processed: list[dict[str, Any]] = []

    for item in extracted:
        try:
            result = await _handle_social_message(
                connection,
                message=item["message"],
                user_id=item["user_id"],
                channel=item["channel"],
                session_id=item.get("session_id"),
                user_name=None,
                user_email=None,
                user_phone=None,
                metadata=item.get("metadata"),
            )
            processed.append(
                {
                    "userId": item["user_id"],
                    "channel": item["channel"],
                    "sessionId": result.get("sessionId"),
                    "status": "success",
                    "dispatch": result.get("dispatch"),
                }
            )
        except Exception as exc:
            logger.error("Meta webhook message processing failed: {}", exc, exc_info=True)
            processed.append(
                {
                    "userId": item.get("user_id"),
                    "channel": item.get("channel"),
                    "status": "failed",
                    "error": str(exc)[:400],
                }
            )

    failures = [entry for entry in processed if entry.get("status") == "failed"]
    await touch_social_connection_event(connection["id"], failures[0]["error"] if failures else None)

    return {
        "status": "accepted",
        "provider": "meta",
        "processed": len(processed),
        "failed": len(failures),
        "results": processed,
    }
