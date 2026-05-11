import json
from contextlib import AsyncExitStack
from typing import Any, List, Optional, Dict
from loguru import logger
from pydantic import BaseModel, Field, create_model

from langchain_core.tools import StructuredTool
from sqlalchemy import select

from mcp import ClientSession
from mcp.client.sse import sse_client

from database.models import TenantMCPServer, get_async_session
from utils.secret_crypto import decrypt_secret

def create_model_from_schema(schema: dict) -> type[BaseModel]:
    """Dynamically converts a JSON Schema to a Pydantic Model for Langchain Tools."""
    fields = {}
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    
    for prop_name, prop_info in properties.items():
        ptype = Any
        prop_type = prop_info.get("type", "string")
        if prop_type == "string":
            ptype = str
        elif prop_type == "integer":
            ptype = int
        elif prop_type == "number":
            ptype = float
        elif prop_type == "boolean":
            ptype = bool
        elif prop_type == "array":
            ptype = list
        elif prop_type == "object":
            ptype = dict
            
        default = ... if prop_name in required else None
        fields[prop_name] = (ptype, Field(description=prop_info.get("description", ""), default=default))
        
    return create_model("DynamicMCPSchema", **fields)


class MCPClientManager:
    """Manages an active pool of MCP Server connections for a single workspace context."""
    def __init__(self, tenant_id: str, workspace_id: str):
        self.tenant_id = tenant_id
        self.workspace_id = workspace_id
        self.exit_stack = AsyncExitStack()
        self.sessions: List[ClientSession] = []
        self.tools: List[StructuredTool] = []

    async def initialize_tools(self):
        """Fetch db config, connect to MCP servers, and compile LangGraph native tools."""
        try:
            async with get_async_session() as db_session:
                query = select(TenantMCPServer).where(
                    TenantMCPServer.tenant_id == self.tenant_id,
                    TenantMCPServer.workspace_id == self.workspace_id,
                    TenantMCPServer.is_active == True
                )
                result = await db_session.execute(query)
                servers = result.scalars().all()

            for server in servers:
                try:
                    await self._connect_server(server)
                except Exception as e:
                    logger.opt(exception=True).error("Failed to connect to MCP server '{server.name}': {}", e)
                    self._inject_dummy_tool(server.name)
        except Exception as e:
            logger.opt(exception=True).error("MCP Initialization error: {}", e)

    async def _connect_server(self, server: TenantMCPServer):
        env_vars = {}
        if server.config_json_encrypted:
            try:
                decrypted = decrypt_secret(server.config_json_encrypted)
                env_vars = json.loads(decrypted)
            except Exception as e:
                logger.error(f"Failed to decrypt MCP auth env for {server.name}: {e}")

        if server.connection_type == "sse":
            options = {"headers": env_vars} if env_vars else {}
            read_stream, write_stream = await self.exit_stack.enter_async_context(
                sse_client(url=server.connection_url, **options)
            )
        else:
            raise ValueError(f"Security: Subprocess stdio disabled. Type [{server.connection_type}] strictly forbidden.")

        session = await self.exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()
        self.sessions.append(session)

        mcp_tools_response = await session.list_tools()
        
        for mcp_tool in mcp_tools_response.tools:
            langchain_tool = self._create_langchain_wrapper(mcp_tool, session, server.name)
            self.tools.append(langchain_tool)
            logger.info(f"Loaded MCP Tool [{mcp_tool.name}] from server [{server.name}]")

    def _inject_dummy_tool(self, server_name: str):
        """Injects a Mock Tool signaling that the integration failed to connect."""
        async def _mock_tool(**kwargs):
            return f"SYSTEM ALERT: The MCP server '{server_name}' is currently offline and cannot process this request. Notify the user."

        dummy = StructuredTool(
            name=f"{server_name}_status".lower().replace("-", "_"),
            description=f"Status handler for {server_name}",
            func=None,
            coroutine=_mock_tool,
        )
        self.tools.append(dummy)
        logger.warning(f"Injected offline dummy callback for {server_name}")

    def _create_langchain_wrapper(self, mcp_tool, session: ClientSession, server_name: str) -> StructuredTool:
        """Converts an MCP Tool into a LangChain StructuredTool."""
        clean_name = f"{server_name}_{mcp_tool.name}".replace("-", "_").replace(" ", "_").lower()
        args_schema = create_model_from_schema(mcp_tool.inputSchema)

        async def _invoke_mcp(**kwargs):
            try:
                response = await session.call_tool(mcp_tool.name, arguments=kwargs)
                text_contents = [c.text for c in response.content if hasattr(c, 'text')]
                if not text_contents and response.content:
                    text_contents = [str(c) for c in response.content]
                return "\n".join(text_contents)
            except Exception as e:
                return f"Error executing tool {mcp_tool.name}: {str(e)}"

        return StructuredTool(
            name=clean_name,
            description=mcp_tool.description or "External MCP Tool",
            args_schema=args_schema,
            func=None,
            coroutine=_invoke_mcp,
        )

class MCPClientPool:
    """Global in-memory Connection Pool managing cross-tenant MCP server states."""
    
    def __init__(self):
        self._pool: Dict[str, MCPClientManager] = {}

    async def get_tools_for_tenant(self, tenant_id: str, workspace_id: str) -> List[StructuredTool]:
        """Provides instant memory-cached access to Tenant's available LangChain mapped Tools."""
        key = f"{tenant_id}:{workspace_id}"
        if key not in self._pool:
            manager = MCPClientManager(tenant_id, workspace_id)
            await manager.initialize_tools()
            self._pool[key] = manager
        return self._pool[key].tools

    async def clear_cache(self, tenant_id: str, workspace_id: str):
        """Invoke this via Admin Webhooks to force a tool refresh."""
        key = f"{tenant_id}:{workspace_id}"
        if key in self._pool:
            manager = self._pool.pop(key)
            try:
                await manager.exit_stack.aclose()
            except Exception:
                pass

# Export Singleton
mcp_pool = MCPClientPool()
