"""
Tenant context resolution utilities.
"""
from dataclasses import dataclass
from typing import Optional
import re

from fastapi import Header, HTTPException

from config import settings


ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,79}$")


@dataclass(frozen=True)
class TenantContext:
    """Resolved tenant and workspace context for a request."""
    tenant_id: str
    workspace_id: str


def validate_context_identifier(value: Optional[str], field_name: str) -> Optional[str]:
    """Normalize and validate tenant/workspace identifiers."""
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    if not ID_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must match pattern ^[A-Za-z0-9][A-Za-z0-9._-]{{1,79}}$"
        )

    return normalized


async def resolve_workspace_alias(workspace_alias: str) -> str:
    import uuid
    try:
        uuid.UUID(workspace_alias)
        return workspace_alias
    except ValueError:
        pass

    from database.models import get_async_session
    from sqlalchemy import text
    try:
        async with get_async_session() as session:
            stmt = text("SELECT CAST(id AS TEXT) FROM workspaces WHERE workspace_key = :key LIMIT 1")
            real_id = (await session.execute(stmt, {"key": workspace_alias})).scalar_one_or_none()
            if real_id:
                return str(real_id)
    except Exception as e:
        from loguru import logger
        logger.warning(f"Failed to resolve workspace alias '{workspace_alias}': {e}")

    return workspace_alias

async def resolve_tenant_alias(tenant_alias: str) -> str:
    import uuid
    try:
        uuid.UUID(tenant_alias)
        return tenant_alias
    except ValueError:
        pass

    from database.models import get_async_session
    from sqlalchemy import text
    try:
        async with get_async_session() as session:
            stmt = text("SELECT CAST(id AS TEXT) FROM organizations WHERE slug = :slug LIMIT 1")
            real_id = (await session.execute(stmt, {"slug": tenant_alias})).scalar_one_or_none()
            if real_id:
                return str(real_id)
    except Exception as e:
        from loguru import logger
        logger.warning(f"Failed to resolve tenant alias '{tenant_alias}': {e}")

    return tenant_alias

async def resolve_tenant_context(
    tenant_header: Optional[str] = Header(None, alias="X-Tenant-Id"),
    workspace_header: Optional[str] = Header(None, alias="X-Workspace-Id"),
) -> TenantContext:
    """
    Resolve tenant/workspace context from headers.

    Defaults are used when tenant context is optional; strict mode requires both headers.
    """
    try:
        tenant_id = validate_context_identifier(tenant_header, "tenant_id")
        workspace_id = validate_context_identifier(workspace_header, "workspace_id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if settings.REQUIRE_TENANT_CONTEXT and (not tenant_id or not workspace_id):
        raise HTTPException(
            status_code=400,
            detail="Missing tenant context headers: X-Tenant-Id and X-Workspace-Id"
        )

    resolved_tenant = await resolve_tenant_alias(tenant_id or settings.DEFAULT_TENANT_ID)
    resolved_workspace = await resolve_workspace_alias(workspace_id or settings.DEFAULT_WORKSPACE_ID)

    return TenantContext(
        tenant_id=resolved_tenant,
        workspace_id=resolved_workspace,
    )