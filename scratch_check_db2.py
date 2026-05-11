import asyncio
from sqlalchemy import text
from database.models import get_async_session

async def main():
    async with get_async_session() as session:
        result = await session.execute(text("SELECT * FROM organizations;"))
        print("organizations:", result.mappings().all())
        result2 = await session.execute(text("SELECT * FROM workspaces;"))
        print("workspaces:", result2.mappings().all())

if __name__ == "__main__":
    asyncio.run(main())
