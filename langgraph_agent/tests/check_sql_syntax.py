import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from database.models import settings
from loguru import logger
import os

async def check():
    engine = create_async_engine(settings.DATABASE_URL_RUNTIME, echo=False)
    
    with open("supabase_comprehensive_schema.sql", "r", encoding="utf-8") as f:
        sql_content = f.read()
        
    # very primitive split by ';' -- won't work well for do $$ blocks.
    # postgres asyncpg can execute multiple statements at once if we pass it directly
    
    try:
         async with engine.begin() as conn:
              await conn.execute(sqlalchemy.text(sql_content))
         logger.success("Supabase schema OK")
    except Exception as e:
         logger.error(f"Supabase schema error: {e}")
         
    with open("complete_database_schema.sql", "r", encoding="utf-8") as f:
        sql_content_2 = f.read()
        
    try:
         async with engine.begin() as conn:
              await conn.execute(sqlalchemy.text(sql_content_2))
         logger.success("MySQL schema OK")
    except Exception as e:
         logger.error(f"MySQL schema error: {e}")

if __name__ == "__main__":
    import sqlalchemy
    asyncio.run(check())
