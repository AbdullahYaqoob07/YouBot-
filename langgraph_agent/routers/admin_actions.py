from fastapi import APIRouter, Depends, HTTPException, Path
from typing import List, Optional, Dict
from pydantic import BaseModel

from tenant_context import TenantContext, resolve_tenant_context, resolve_workspace_alias
# Importing dependency from app avoids cyclic errors
from app import verify_admin_key  

from database.mcp_servers import get_tenant_mcp_servers, create_tenant_mcp_server, delete_tenant_mcp_server

router = APIRouter(prefix="/admin/workspaces/{workspace_id}/mcp-servers", tags=["MCP Configuration"])

class MCPServerCreateRequest(BaseModel):
    name: str
    connection_type: str = "sse" # "stdio" or "sse"
    connection_url: str
    config_json: Optional[Dict] = None

class MCPServerResponse(BaseModel):
    id: int
    name: str
    connection_type: str
    connection_url: str

@router.get("", response_model=List[MCPServerResponse])
async def list_mcp_servers(
    workspace_id: str,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
    if resolved_path_workspace_id != tenant_context.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    
    servers = await get_tenant_mcp_servers(tenant_context.tenant_id, tenant_context.workspace_id)
    return [
        MCPServerResponse(
            id=s.id, name=s.name, 
            connection_type=s.connection_type, connection_url=s.connection_url
        ) for s in servers
    ]

@router.post("", response_model=MCPServerResponse)
async def create_mcp_server(
    workspace_id: str,
    request: MCPServerCreateRequest,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
    if resolved_path_workspace_id != tenant_context.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")
        
    try:
        server_id = await create_tenant_mcp_server(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
            name=request.name,
            connection_type=request.connection_type,
            connection_url=request.connection_url,
            config_json=request.config_json
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return MCPServerResponse(
        id=server_id,
        name=request.name,
        connection_type=request.connection_type,
        connection_url=request.connection_url
    )

@router.delete("/{server_id}", response_model=dict)
async def delete_mcp_server(
    workspace_id: str,
    server_id: int = Path(...),
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
    if resolved_path_workspace_id != tenant_context.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")
        
    success = await delete_tenant_mcp_server(tenant_context.tenant_id, tenant_context.workspace_id, server_id)
    if not success:
        raise HTTPException(status_code=404, detail="MCP Server not found")
        
    return {"status": "success", "message": "Server deleted successfully"}
