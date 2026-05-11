from typing import List, Dict, Optional
from sqlalchemy import select
from datetime import datetime

from database.models import TenantCustomAction, get_async_session
from loguru import logger
import json
from utils.secret_crypto import encrypt_secret, decrypt_secret

async def get_tenant_custom_actions(tenant_id: str, workspace_id: str) -> List[TenantCustomAction]:
    """Retrieve all active custom actions for a workspace."""
    async with get_async_session() as session:
        query = select(TenantCustomAction).where(
            TenantCustomAction.tenant_id == tenant_id,
            TenantCustomAction.workspace_id == workspace_id,
            TenantCustomAction.is_active.is_(True)
        )
        result = await session.execute(query)
        actions = result.scalars().all()
        return list(actions)

async def create_tenant_custom_action(
    tenant_id: str,
    workspace_id: str,
    name: str,
    description: str,
    api_endpoint: str,
    method: str = "GET",
    auth_headers_json: Optional[Dict] = None,
    payload_schema_json: Optional[Dict] = None
) -> int:
    """Create a new custom action for a tenant workspace."""
    async with get_async_session() as session:
        encrypted_headers = None
        if auth_headers_json:
            encrypted_headers = encrypt_secret(json.dumps(auth_headers_json))
            
        action = TenantCustomAction(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name,
            description=description,
            api_endpoint=api_endpoint,
            method=method.upper(),
            auth_headers_encrypted=encrypted_headers,
            payload_schema_json=payload_schema_json or {},
            created_at=datetime.utcnow()
        )
        session.add(action)
        await session.commit()
        await session.refresh(action)
        logger.info(f"Created custom action {name} for workspace {workspace_id}")
        return action.id
