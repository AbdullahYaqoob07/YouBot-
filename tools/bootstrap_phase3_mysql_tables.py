"""
Create/verify Phase 3 MySQL tables used by retrieval and ingestion endpoints.

This script is safe to rerun.
"""

import asyncio
import sys
from pathlib import Path

# Make project root importable when run as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.models import (
    Base,
    DocumentPage,
    IngestionJob,
    KnowledgeSource,
    PageIndexEntry,
    RetrievalProfile,
    RetrievalRecommendationEvent,
    engine,
)


TABLES = [
    KnowledgeSource.__table__,
    IngestionJob.__table__,
    RetrievalProfile.__table__,
    RetrievalRecommendationEvent.__table__,
    DocumentPage.__table__,
    PageIndexEntry.__table__,
]


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(bind=sync_conn, tables=TABLES))
    await engine.dispose()
    print("created_or_verified:", ", ".join(table.name for table in TABLES))


if __name__ == "__main__":
    asyncio.run(main())
