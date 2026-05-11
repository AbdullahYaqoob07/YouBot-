"""
Check Phase 3 table visibility via Supabase REST.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from utils.mcp_transport import http_get


def main() -> None:
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        print("CONFIG_MISSING")
        return

    url = settings.SUPABASE_URL.rstrip("/")
    key = settings.SUPABASE_SERVICE_ROLE_KEY
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }

    tables = [
        "knowledge_sources",
        "ingestion_jobs",
        "retrieval_profiles",
        "retrieval_recommendation_events",
        "document_pages",
        "page_index_entries",
    ]

    for table in tables:
        try:
            resp = http_get(
                f"{url}/rest/v1/{table}",
                headers=headers,
                params={"select": "*", "limit": 1},
                timeout_seconds=20,
            )
            exists = resp.status_code in (200, 206)
            print(f"{table}|{resp.status_code}|{'exists' if exists else 'missing'}")
        except Exception as exc:  # pragma: no cover - connectivity diagnostics
            print(f"{table}|ERR|{type(exc).__name__}")


if __name__ == "__main__":
    main()
