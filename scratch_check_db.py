import asyncio
from sqlalchemy import text
from database.models import get_async_session

async def main():
    async with get_async_session() as session:
        result = await session.execute(text("SELECT * FROM workspaces LIMIT 1;"))
        print("workspaces:", result.mappings().all())
        result2 = await session.execute(text("SELECT * FROM organizations LIMIT 1;"))
        print("organizations:", result2.mappings().all())
        result3 = await session.execute(text("SELECT * FROM llm_provider_configs LIMIT 1;"))
        print("llm_provider_configs:", result3.mappings().all())

if __name__ == "__main__":
    asyncio.run(main())
