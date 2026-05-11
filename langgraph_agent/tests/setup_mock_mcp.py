import asyncio
import os
from database.models import TenantMCPServer, get_async_session
from config import settings
from loguru import logger
from sqlalchemy import select

async def inject_mcp_to_db():
    tenant_id = settings.DEFAULT_TENANT_ID or "tenant_test"
    workspace_id = settings.DEFAULT_WORKSPACE_ID or "workspace_test"
    
    # Path to the mock python script we just created
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "mock_mcp_server.py"))
    
    async with get_async_session() as session:
        # Check if already exists
        query = select(TenantMCPServer).where(
            TenantMCPServer.tenant_id == tenant_id,
            TenantMCPServer.workspace_id == workspace_id,
            TenantMCPServer.name == "local_mock_mcp"
        )
        result = await session.execute(query)
        existing = result.scalar_one_or_none()
        
        if not existing:
            # Insert
            server = TenantMCPServer(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                name="local_mock_mcp",
                connection_type="stdio",
                connection_url=f"python {script_path}"
            )
            session.add(server)
            await session.commit()
            logger.success("✅ Mock MCP Server Config injected into MySQL!")
        else:
            logger.info("ℹ️ MCP Server Config already exists in DB.")

if __name__ == "__main__":
    asyncio.run(inject_mcp_to_db())
