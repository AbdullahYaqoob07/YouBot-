from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types
import asyncio

# Simple mock server mapping to an imaginary external e-commerce platform
app = Server("mock-orders-mcp")

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """Exposes tool schemas over the MCP protocol to the SaaS."""
    return [
        types.Tool(
            name="check_order_status",
            description="Fetch up-to-date tracking and status information about a customer's order ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The unique order identifier assigned at checkout."
                    },
                },
                "required": ["order_id"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Execute the core logic mapped from the tool execution loop."""
    if name == "check_order_status":
        order_id = arguments.get("order_id", "unknown")
        
        # Simulate lookup payload
        if order_id in ["123", "38914"]:
            result_payload = f'Order {order_id} is currently "In Transit" via FedEx tracking #99814. Expected delivery tomorrow.'
        else:
            result_payload = f"I could not locate any active shipments for order #{order_id}. Please verify the number."

        # Pass context back to the AI!
        return [
            types.TextContent(
                type="text", 
                text=result_payload
            )
        ]
    
    raise ValueError(f"Tool {name} not Supported by this MCP server.")

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream, 
            write_stream, 
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
