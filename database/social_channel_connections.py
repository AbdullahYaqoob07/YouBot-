"""Social channel connection persistence helpers."""

from __future__ import annotations

import json
import secrets
from datetime import datetime
from typing import Any, Optional

from loguru import logger
from sqlalchemy import String as SAString, cast, select

from database.models import SocialChannelConnection, get_async_session
from database.workspace_provisioning import ensure_workspace_provisioned
from utils.secret_crypto import decrypt_secret, encrypt_secret, mask_secret


def _scope_filters(tenant_id: str, workspace_id: str):
    """Build scope filters compatible with both TEXT and UUID column types."""
    return (
        cast(SocialChannelConnection.tenant_id, SAString) == str(tenant_id),
        cast(SocialChannelConnection.workspace_id, SAString) == str(workspace_id),
    )


def _optional_encrypt(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return encrypt_secret(value)


def _optional_decrypt(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return decrypt_secret(value)


def _serialize_connection(row: Any) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "tenant_id": str(row.tenant_id),
        "workspace_id": str(row.workspace_id),
        "name": str(row.name),
        "provider": str(row.provider),
        "channel": str(row.channel),
        "connection_key": str(row.connection_key),
        "is_active": bool(row.is_active),
        "outbound_webhook_url": str(row.outbound_webhook_url) if row.outbound_webhook_url else None,
        "has_verify_token": bool(row.verify_token_encrypted),
        "has_access_token": bool(row.access_token_encrypted),
        "has_app_secret": bool(row.app_secret_encrypted),
        "created_by": str(row.created_by) if row.created_by else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "last_event_at": row.last_event_at.isoformat() if row.last_event_at else None,
        "last_error": str(row.last_error) if row.last_error else None,
        "metadata_json": row.metadata_json if row.metadata_json else {},
    }


async def create_social_channel_connection(
    *,
    tenant_id: str,
    workspace_id: str,
    name: str,
    provider: str,
    channel: str,
    verify_token: Optional[str],
    access_token: Optional[str],
    app_secret: Optional[str],
    outbound_webhook_url: Optional[str],
    outbound_auth_headers: Optional[dict[str, str]],
    metadata_json: Optional[dict[str, Any]],
    created_by: Optional[str],
    is_active: bool = True,
) -> dict[str, Any]:
    connection_key = f"sc_{secrets.token_urlsafe(24)}"

    encrypted_verify_token = _optional_encrypt(verify_token)
    encrypted_access_token = _optional_encrypt(access_token)
    encrypted_app_secret = _optional_encrypt(app_secret)

    encrypted_headers = None
    if outbound_auth_headers:
        encrypted_headers = encrypt_secret(json.dumps(outbound_auth_headers))

    now = datetime.utcnow()

    async with get_async_session() as session:
        await ensure_workspace_provisioned(session, tenant_id, workspace_id)
        row = SocialChannelConnection(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name,
            provider=provider,
            channel=channel,
            connection_key=connection_key,
            verify_token_encrypted=encrypted_verify_token,
            access_token_encrypted=encrypted_access_token,
            app_secret_encrypted=encrypted_app_secret,
            outbound_webhook_url=outbound_webhook_url,
            outbound_auth_headers_encrypted=encrypted_headers,
            metadata_json=metadata_json or {},
            is_active=is_active,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        await session.commit()

        return _serialize_connection(row)


async def list_social_channel_connections(tenant_id: str, workspace_id: str) -> list[dict[str, Any]]:
    scope_filters = _scope_filters(tenant_id, workspace_id)
    async with get_async_session() as session:
        stmt = (
            select(SocialChannelConnection)
            .where(*scope_filters)
            .order_by(SocialChannelConnection.created_at.desc())
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [_serialize_connection(row) for row in rows]


async def update_social_channel_connection_status(
    tenant_id: str,
    workspace_id: str,
    connection_id: int,
    is_active: bool,
) -> Optional[dict[str, Any]]:
    scope_filters = _scope_filters(tenant_id, workspace_id)

    async with get_async_session() as session:
        stmt = select(SocialChannelConnection).where(
            *scope_filters,
            SocialChannelConnection.id == connection_id,
        )
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return None

        row.is_active = is_active
        row.updated_at = datetime.utcnow()
        await session.commit()
        return _serialize_connection(row)


async def delete_social_channel_connection(
    tenant_id: str,
    workspace_id: str,
    connection_id: int,
) -> dict[str, Any]:
    scope_filters = _scope_filters(tenant_id, workspace_id)

    async with get_async_session() as session:
        stmt = select(SocialChannelConnection).where(
            *scope_filters,
            SocialChannelConnection.id == connection_id,
        )
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            raise ValueError("Social connection not found")

        deleted_name = str(row.name)
        deleted_connection_key = str(row.connection_key)

        await session.delete(row)
        await session.commit()

    return {
        "deleted_connection_id": connection_id,
        "name": deleted_name,
        "connection_key": deleted_connection_key,
    }


async def get_social_connection_runtime_by_key(
    connection_key: str,
    provider: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    async with get_async_session() as session:
        stmt = select(SocialChannelConnection).where(
            SocialChannelConnection.connection_key == connection_key,
            SocialChannelConnection.is_active.is_(True),
        )
        if provider:
            stmt = stmt.where(SocialChannelConnection.provider == provider)

        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return None

        outbound_headers = None
        if row.outbound_auth_headers_encrypted:
            try:
                outbound_headers = json.loads(decrypt_secret(str(row.outbound_auth_headers_encrypted)))
            except Exception as exc:
                logger.warning("Failed decrypting outbound headers for social connection {}: {}", row.id, exc)

        return {
            "id": int(row.id),
            "tenant_id": str(row.tenant_id),
            "workspace_id": str(row.workspace_id),
            "name": str(row.name),
            "provider": str(row.provider),
            "channel": str(row.channel),
            "connection_key": str(row.connection_key),
            "verify_token": _optional_decrypt(str(row.verify_token_encrypted)) if row.verify_token_encrypted else None,
            "access_token": _optional_decrypt(str(row.access_token_encrypted)) if row.access_token_encrypted else None,
            "app_secret": _optional_decrypt(str(row.app_secret_encrypted)) if row.app_secret_encrypted else None,
            "outbound_webhook_url": str(row.outbound_webhook_url) if row.outbound_webhook_url else None,
            "outbound_auth_headers": outbound_headers,
            "metadata_json": row.metadata_json if row.metadata_json else {},
        }


async def touch_social_connection_event(connection_id: int, error_message: Optional[str] = None) -> None:
    async with get_async_session() as session:
        stmt = select(SocialChannelConnection).where(SocialChannelConnection.id == connection_id)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return

        row.last_event_at = datetime.utcnow()
        row.last_error = error_message
        row.updated_at = datetime.utcnow()
        await session.commit()


def mask_social_connection_secrets(connection: dict[str, Any]) -> dict[str, Any]:
    """Mask secrets in runtime connection dictionaries for safe logs/debugging."""
    redacted = dict(connection)
    if redacted.get("verify_token"):
        redacted["verify_token"] = mask_secret(redacted["verify_token"])
    if redacted.get("access_token"):
        redacted["access_token"] = mask_secret(redacted["access_token"])
    if redacted.get("app_secret"):
        redacted["app_secret"] = mask_secret(redacted["app_secret"])
    return redacted
