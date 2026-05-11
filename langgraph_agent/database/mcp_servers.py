from typing import List, Dict, Optional
from sqlalchemy import select, delete
from datetime import datetime
import json

from database.models import TenantMCPServer, get_async_session
from loguru import logger
from utils.secret_crypto import encrypt_secret

async def get_tenant_mcp_servers(tenant_id: str, workspace_id: str) -> List[TenantMCPServer]:
    """Retrieve all active MCP servers mapped to a workspace."""
    async with get_async_session() as session:
        query = select(TenantMCPServer).where(
            TenantMCPServer.tenant_id == tenant_id,
            TenantMCPServer.workspace_id == workspace_id,
        )
        result = await session.execute(query)
        return list(result.scalars().all())

async def create_tenant_mcp_server(
    tenant_id: str,
    workspace_id: str,
    name: str,
    connection_type: str,
    connection_url: str,
    config_json: Optional[Dict] = None
) -> int:
    """Register a new MCP server. Securely encrypts the config dictionary (e.g., API keys)."""
    
    if connection_type.lower() == "stdio":
        raise ValueError("Security violation: 'stdio' connection types are disabled for tenant deployments. Use 'sse' only.")
        
    async with get_async_session() as session:
        encrypted_config = None
        if config_json:
            encrypted_config = encrypt_secret(json.dumps(config_json))
            
        server = TenantMCPServer(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name,
            connection_type=connection_type,
            connection_url=connection_url,
            config_json_encrypted=encrypted_config,
            created_at=datetime.utcnow()
        )
        session.add(server)
        await session.commit()
        await session.refresh(server)
        logger.info(f"Registered MCP server {name} for workspace {workspace_id}")
        return server.id

async def delete_tenant_mcp_server(tenant_id: str, workspace_id: str, server_id: int) -> bool:
    """Remove an MCP server from the workspace routing configurations."""
    async with get_async_session() as session:
        query = delete(TenantMCPServer).where(
            TenantMCPServer.id == server_id,
            TenantMCPServer.tenant_id == tenant_id,
            TenantMCPServer.workspace_id == workspace_id
        )
        result = await session.execute(query)
        await session.commit()
        return result.rowcount > 0
