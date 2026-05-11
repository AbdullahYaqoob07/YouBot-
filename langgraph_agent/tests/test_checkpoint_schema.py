import asyncio
from database.models import bootstrap_runtime_tables
from loguru import logger

import pytest

@pytest.mark.asyncio
async def test():
    logger.info("Initializing runtime tables...")
    await bootstrap_runtime_tables()
    logger.success("Schema validation successful!")

if __name__ == "__main__":
    asyncio.run(test())
