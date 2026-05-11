import asyncio
import json
from datetime import datetime

from config import settings
from database.analytics import (
    get_ai_performance_metrics,
    get_channel_performance_metrics,
    get_kb_performance_metrics,
    get_team_performance_metrics,
    get_tenant_overview_metrics,
    get_user_performance_metrics,
)


async def main() -> None:
    tenant_id = settings.DEFAULT_TENANT_ID
    workspace_id = settings.DEFAULT_WORKSPACE_ID
    days = 30

    results: dict[str, object] = {
        "generated_at": datetime.utcnow().isoformat(),
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "window_days": days,
        "database_url_runtime": settings.DATABASE_URL_RUNTIME,
        "domains": {},
    }

    collectors = {
        "overview": get_tenant_overview_metrics,
        "user_performance": get_user_performance_metrics,
        "ai_performance": get_ai_performance_metrics,
        "team_performance": get_team_performance_metrics,
        "kb_performance": get_kb_performance_metrics,
        "channel_performance": get_channel_performance_metrics,
    }

    for name, collector in collectors.items():
        try:
            payload = await collector(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                days=days,
            )
            results["domains"][name] = payload
        except Exception as exc:  # pragma: no cover - probe utility
            results["domains"][name] = {
                "error": str(exc),
                "collector": collector.__name__,
            }

    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
