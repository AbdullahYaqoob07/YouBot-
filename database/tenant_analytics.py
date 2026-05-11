"""
Phase 5 Tenant Analytics Database Operations
Provides aggregated metrics for the tenant-facing analytics dashboard.
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import select, func, or_, and_, desc
from loguru import logger

from database.models import AnalyticsEvent, get_async_session

async def get_overview_metrics(
    tenant_id: str,
    workspace_id: str,
    days: int = 30
) -> Dict[str, Any]:
    """Get high-level KPIs for the tenant analytics dashboard."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    try:
        async with get_async_session() as session:
            # Base query filtered by tenant/workspace and timeframe
            base_stmt = select(
                func.count().label("total_events"),
                func.sum(func.cast(AnalyticsEvent.resolved_by_ai, func.INTEGER())).label("ai_resolved"),
                func.sum(func.cast(AnalyticsEvent.handed_to_human, func.INTEGER())).label("human_handoff"),
                func.avg(AnalyticsEvent.response_time_ms).label("avg_response_time")
            ).where(
                AnalyticsEvent.tenant_id == tenant_id,
                AnalyticsEvent.workspace_id == workspace_id,
                AnalyticsEvent.timestamp >= start_date,
                AnalyticsEvent.event_type == "query_processed"
            )
            
            result = await session.execute(base_stmt)
            row = result.first()
            
            total = row.total_events or 0
            ai_resolved = row.ai_resolved or 0
            human_handoff = row.human_handoff or 0
            
            # Simple fallback: if total is 0, avoid division by zero
            auto_resolution_rate = round((ai_resolved / total * 100), 2) if total > 0 else 0.0
            handoff_rate = round((human_handoff / total * 100), 2) if total > 0 else 0.0
            avg_response_ms = int(row.avg_response_time) if row.avg_response_time else 0
            
            return {
                "total_conversations": total,
                "auto_resolution_rate": auto_resolution_rate,
                "handoff_rate": handoff_rate,
                "avg_response_time_ms": avg_response_ms,
                "health_score": min(100, max(0, 100 - handoff_rate)),  # Very naive health score
                "period": f"Last {days} days"
            }
            
    except Exception as e:
        logger.opt(exception=True).error("Error computing analytics overview: {}", str(e))
        # Return fallback zeros to not break dashboard
        return {
            "total_conversations": 0,
            "auto_resolution_rate": 0,
            "handoff_rate": 0,
            "avg_response_time_ms": 0,
            "health_score": 0,
            "period": f"Error"
        }

async def get_channel_performance(
    tenant_id: str,
    workspace_id: str,
    days: int = 30
) -> List[Dict[str, Any]]:
    """Get metrics grouped by channel (WhatsApp, web, etc.)."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    try:
        async with get_async_session() as session:
            stmt = select(
                func.coalesce(AnalyticsEvent.channel, 'unknown').label("channel"),
                func.count().label("volume"),
                func.avg(AnalyticsEvent.response_time_ms).label("avg_latency")
            ).where(
                AnalyticsEvent.tenant_id == tenant_id,
                AnalyticsEvent.workspace_id == workspace_id,
                AnalyticsEvent.timestamp >= start_date,
                AnalyticsEvent.event_type == "query_processed"
            ).group_by(
                func.coalesce(AnalyticsEvent.channel, 'unknown')
            ).order_by(desc("volume"))
            
            result = await session.execute(stmt)
            rows = result.all()
            
            return [
                {
                    "channel": row.channel,
                    "volume": row.volume,
                    "avg_latency_ms": int(row.avg_latency) if row.avg_latency else 0
                }
                for row in rows
            ]
            
    except Exception as e:
        logger.opt(exception=True).error("Error computing channel performance: {}", str(e))
        return []

async def get_ai_performance(
    tenant_id: str,
    workspace_id: str,
    days: int = 30
) -> Dict[str, Any]:
    """Get metrics specifically for AI and KB performance."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    try:
        async with get_async_session() as session:
            # Check knowledge base usage vs non-knowledge base
            stmt = select(
                func.sum(func.cast(AnalyticsEvent.knowledge_base_used, func.INTEGER())).label("kb_hits"),
                func.count().label("total")
            ).where(
                AnalyticsEvent.tenant_id == tenant_id,
                AnalyticsEvent.workspace_id == workspace_id,
                AnalyticsEvent.timestamp >= start_date,
                AnalyticsEvent.event_type == "query_processed"
            )
            
            result = await session.execute(stmt)
            row = result.first()
            
            total = row.total or 0
            kb_hits = row.kb_hits or 0
            
            retrieval_hit_rate = round((kb_hits / total * 100), 2) if total > 0 else 0.0
            
            return {
                "total_queries": total,
                "retrieval_hit_rate": retrieval_hit_rate,
                "kb_queries": kb_hits,
                "low_confidence_responses": 0  # Placeholder for deeper metric
            }
            
    except Exception as e:
        logger.opt(exception=True).error("Error computing ai performance: {}", str(e))
        return {
            "total_queries": 0,
            "retrieval_hit_rate": 0,
            "kb_queries": 0,
            "low_confidence_responses": 0
        }
