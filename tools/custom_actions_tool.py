from typing import List
import httpx
from langchain.tools import DynamicStructuredTool
from pydantic import create_model, Field, BaseModel
from loguru import logger

async def build_tenant_action_tools(tenant_id: str, workspace_id: str) -> List[DynamicStructuredTool]:
    """
    Fetch all custom actions for the tenant and convert them into LangChain tools.
    """
    from database.custom_actions import get_tenant_custom_actions

    try:
        actions = await get_tenant_custom_actions(tenant_id, workspace_id)
    except Exception as e:
        logger.error(f"Failed to fetch tenant custom actions: {e}")
        return []

    tools = []
    
    for action in actions:
        fields = {}
        schema_def = action.payload_schema_json or {}
        for key, prop in schema_def.get("properties", {}).items():
            prop_type = str
            if prop.get("type", "string") == "integer":
                prop_type = int
            elif prop.get("type", "string") == "boolean":
                prop_type = bool
                
            required = key in schema_def.get("required", [])
            default = ... if required else None
            fields[key] = (prop_type, Field(default=default, description=prop.get("description", "")))
            
        if not fields:
            class EmptyModel(BaseModel):
                pass
            pydantic_schema = EmptyModel
        else:
            pydantic_schema = create_model(f"{action.name}_Schema", **fields)
            
        def _create_sync_function(action_config):
            async def _execute_tool(**kwargs) -> str:
                try:
                    url = action_config.api_endpoint
                    method = action_config.method
                    
                    import json
                    from utils.secret_crypto import decrypt_secret
                    
                    headers = {}
                    if action_config.auth_headers_encrypted:
                        try:
                            decrypted = decrypt_secret(action_config.auth_headers_encrypted)
                            headers = json.loads(decrypted)
                        except Exception as dec_err:
                            logger.error(f"Failed to decrypt headers for action {action_config.name}: {dec_err}")
                            
                    async with httpx.AsyncClient() as client:
                        if method == "GET":
                            response = await client.get(url, params=kwargs, headers=headers, timeout=10.0)
                        else:
                            response = await client.request(method, url, json=kwargs, headers=headers, timeout=10.0)
                            
                        response.raise_for_status()
                        return response.text
                except Exception as e:
                    logger.error(f"Custom action {action_config.name} failed: {e}")
                    return f"Action {action_config.name} failed to execute."
            return _execute_tool
            
        tool = DynamicStructuredTool(
            name=action.name,
            description=action.description,
            args_schema=pydantic_schema,
            coroutine=_create_sync_function(action),
        )
        tools.append(tool)
        
    return tools
