"""Analytics database operations for Phase 5 KPI, governance, and exports."""
from datetime import datetime, timedelta, timezone
import csv
import io
import json
from typing import Any, Optional

from sqlalchemy import case, func, select, text

from database.models import (
    AdminQueue,
    AnalyticsAlertEvent,
    AnalyticsAlertRule,
    AnalyticsEvent,
    ConversationMetric,
    IngestionJob,
    KnowledgeSource,
    Organization,
    SessionOutcome,
    SLAEvent,
    TenantAnalyticsDaily,
    TenantAnalyticsHourly,
    get_async_session,
)
from loguru import logger


def _bounded_days(days: int) -> int:
    try:
        value = int(days)
    except Exception:
        value = 30
    return max(1, min(value, 365))


def _event_filters(tenant_id: str, workspace_id: Optional[str], window_start: datetime) -> list[Any]:
    filters: list[Any] = [
        AnalyticsEvent.tenant_id == tenant_id,
        AnalyticsEvent.timestamp >= window_start,
    ]
    if workspace_id:
        filters.append(AnalyticsEvent.workspace_id == workspace_id)
    return filters


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    idx = (len(ordered) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return float(ordered[lo] * (1 - frac) + ordered[hi] * frac)


def _flatten_metric_rows(prefix: str, value: Any, rows: list[tuple[str, Any]]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            _flatten_metric_rows(next_prefix, item, rows)
        return
    if isinstance(value, list):
        rows.append((prefix, json.dumps(value, ensure_ascii=True)))
        return
    rows.append((prefix, value))


def _utc_aware_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


PLAN_QUOTAS: dict[str, dict[str, Optional[int]]] = {
    "starter": {
        "monthly_events": 10000,
        "monthly_conversations": 2000,
        "active_alert_rules": 5,
    },
    "growth": {
        "monthly_events": 100000,
        "monthly_conversations": 20000,
        "active_alert_rules": 25,
    },
    "enterprise": {
        "monthly_events": None,
        "monthly_conversations": None,
        "active_alert_rules": None,
    },
}

QUOTA_WARNING_THRESHOLD_PCT = 80.0

QUOTA_BREACH_MESSAGES: dict[str, str] = {
    "monthly_events_pct": "Monthly events quota breached (>=100%).",
    "monthly_conversations_pct": "Monthly conversations quota breached (>=100%).",
    "active_alert_rules_pct": "Active alert-rule quota breached (>=100%).",
}


def _utilization_pct(used: int, quota_limit: Optional[int]) -> Optional[float]:
    if quota_limit is None or quota_limit <= 0:
        return None
    return round((used / quota_limit) * 100.0, 2)


def _days_until_quota(used: int, quota_limit: Optional[int], avg_daily: float) -> Optional[float]:
    if quota_limit is None or quota_limit <= 0:
        return None
    if used >= quota_limit:
        return 0.0
    if avg_daily <= 0:
        return None
    return round((quota_limit - used) / avg_daily, 1)


def _quota_status(values: list[Optional[float]]) -> str:
    effective = [value for value in values if value is not None]
    if not effective:
        return "healthy"
    if any(value >= 100.0 for value in effective):
        return "breached"
    if any(value >= QUOTA_WARNING_THRESHOLD_PCT for value in effective):
        return "warning"
    return "healthy"


async def _resolve_tenant_plan(session: Any, tenant_id: str, workspace_id: Optional[str] = None) -> str:
    default_plan = "starter"
    try:
        org_columns_stmt = text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE lower(table_name) = 'organizations'
            """
        )
        org_columns_rows = (await session.execute(org_columns_stmt)).all()
        org_columns = {
            str(row[0]).strip().lower()
            for row in org_columns_rows
            if row and row[0]
        }

        plan: Optional[str] = None

        if "tenant_id" in org_columns:
            legacy_plan_stmt = text(
                """
                SELECT plan
                FROM organizations
                WHERE tenant_id = :tenant_id
                LIMIT 1
                """
            )
            plan = (await session.execute(legacy_plan_stmt, {"tenant_id": tenant_id})).scalar_one_or_none()
        elif "slug" in org_columns:
            supabase_plan_stmt = text(
                """
                SELECT plan
                FROM organizations
                WHERE slug = :tenant_id
                LIMIT 1
                """
            )
            plan = (await session.execute(supabase_plan_stmt, {"tenant_id": tenant_id})).scalar_one_or_none()
        elif "id" in org_columns and workspace_id:
            workspace_columns_stmt = text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE lower(table_name) = 'workspaces'
                """
            )
            workspace_columns_rows = (await session.execute(workspace_columns_stmt)).all()
            workspace_columns = {
                str(row[0]).strip().lower()
                for row in workspace_columns_rows
                if row and row[0]
            }

            if {"organization_id", "workspace_key"}.issubset(workspace_columns):
                workspace_plan_stmt = text(
                    """
                    SELECT o.plan
                    FROM organizations o
                    JOIN workspaces w ON w.organization_id = o.id
                    WHERE w.workspace_key = :workspace_id
                    LIMIT 1
                    """
                )
                plan = (await session.execute(workspace_plan_stmt, {"workspace_id": workspace_id})).scalar_one_or_none()
    except Exception as exc:
        try:
            await session.rollback()
        except Exception:
            pass
        logger.opt(exception=True).warning("Falling back to default tenant plan for {tenant_id}: {}")
        return default_plan

    normalized = str(plan or default_plan).strip().lower()
    if normalized not in PLAN_QUOTAS:
        return default_plan
    return normalized


def alert_condition_met(metric_value: float, condition: str, threshold_value: float) -> bool:
    normalized = (condition or "").strip().lower()
    if normalized in {"gt", ">"}:
        return metric_value > threshold_value
    if normalized in {"gte", ">="}:
        return metric_value >= threshold_value
    if normalized in {"lt", "<"}:
        return metric_value < threshold_value
    if normalized in {"lte", "<="}:
        return metric_value <= threshold_value
    raise ValueError("condition must be one of: gt, gte, lt, lte")


async def log_analytics_event(
    event_type: str,
    session_id: str,
    user_id: str,
    tenant_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    language: Optional[str] = None,
    channel: Optional[str] = None,
    sentiment: Optional[str] = None,
    model_used: Optional[str] = None,
    response_time_ms: Optional[int] = None,
    knowledge_base_used: bool = False,
    resolved_by_ai: bool = False,
    handed_to_human: bool = False,
    unsolved_score: Optional[float] = None,
):
    """Persist a raw analytics event; failures should not break user flow."""
    try:
        async with get_async_session() as session:
            event = AnalyticsEvent(
                event_type=event_type,
                session_id=session_id,
                user_id=user_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                language=language,
                channel=channel,
                sentiment=sentiment,
                model_used=model_used,
                response_time_ms=response_time_ms,
                knowledge_base_used=knowledge_base_used,
                resolved_by_ai=resolved_by_ai,
                handed_to_human=handed_to_human,
                unsolved_score=unsolved_score,
                timestamp=datetime.utcnow(),
            )
            session.add(event)
            await session.commit()
            logger.info(f"Logged analytics event: {event_type}")
    except Exception as e:
        logger.error(f"Error logging analytics: {str(e)}")


async def get_tenant_overview_metrics(
    tenant_id: str,
    workspace_id: Optional[str] = None,
    days: int = 30,
):
    """Get executive overview KPIs for tenant analytics dashboard."""
    days = _bounded_days(days)
    window_start = datetime.utcnow() - timedelta(days=days)
    filters = _event_filters(tenant_id, workspace_id, window_start)

    async with get_async_session() as session:
        stmt = select(
            func.count(AnalyticsEvent.id).label("total_events"),
            func.count(func.distinct(AnalyticsEvent.session_id)).label("total_conversations"),
            func.coalesce(func.avg(AnalyticsEvent.response_time_ms), 0.0).label("avg_response_time_ms"),
            func.coalesce(func.sum(case((AnalyticsEvent.resolved_by_ai.is_(True), 1), else_=0)), 0).label("ai_resolved_count"),
            func.coalesce(func.sum(case((AnalyticsEvent.handed_to_human.is_(True), 1), else_=0)), 0).label("handoff_count"),
            func.coalesce(func.sum(case((AnalyticsEvent.knowledge_base_used.is_(True), 1), else_=0)), 0).label("kb_hit_count"),
        ).where(*filters)
        row = (await session.execute(stmt)).one()

    total_events = int(row.total_events or 0)
    total_conversations = int(row.total_conversations or 0)
    avg_response_time_ms = round(float(row.avg_response_time_ms or 0.0), 2)
    ai_resolved_count = int(row.ai_resolved_count or 0)
    handoff_count = int(row.handoff_count or 0)
    kb_hit_count = int(row.kb_hit_count or 0)

    auto_resolution_rate = round((ai_resolved_count / total_events) * 100, 2) if total_events else 0.0
    fallback_rate = round((handoff_count / total_events) * 100, 2) if total_events else 0.0
    kb_hit_rate = round((kb_hit_count / total_events) * 100, 2) if total_events else 0.0

    response_component = max(0.0, 100.0 - min(avg_response_time_ms / 100.0, 100.0))
    health_score = round((auto_resolution_rate * 0.5) + (kb_hit_rate * 0.3) + (response_component * 0.2), 2)

    return {
        "window_days": days,
        "health_score": health_score,
        "total_events": total_events,
        "total_conversations": total_conversations,
        "ai_resolved_count": ai_resolved_count,
        "handoff_count": handoff_count,
        "auto_resolution_rate": auto_resolution_rate,
        "fallback_rate": fallback_rate,
        "kb_hit_rate": kb_hit_rate,
        "avg_response_time_ms": avg_response_time_ms,
    }


async def get_user_performance_metrics(
    tenant_id: str,
    workspace_id: Optional[str] = None,
    days: int = 30,
):
    """Get user outcome KPIs (completion, repeat-contact, sentiment, drop-off)."""
    days = _bounded_days(days)
    now = datetime.utcnow()
    window_start = now - timedelta(days=days)
    filters = _event_filters(tenant_id, workspace_id, window_start)

    users_filters = list(filters)
    users_filters.append(AnalyticsEvent.user_id.is_not(None))

    recent_24h_filters = _event_filters(tenant_id, workspace_id, now - timedelta(hours=24))
    recent_24h_filters.append(AnalyticsEvent.user_id.is_not(None))

    recent_7d_filters = _event_filters(tenant_id, workspace_id, now - timedelta(days=7))
    recent_7d_filters.append(AnalyticsEvent.user_id.is_not(None))

    queue_filters = [
        AdminQueue.tenant_id == tenant_id,
        AdminQueue.created_at >= window_start,
    ]
    if workspace_id:
        queue_filters.append(AdminQueue.workspace_id == workspace_id)

    async with get_async_session() as session:
        users_stmt = select(func.count(func.distinct(AnalyticsEvent.user_id))).where(*users_filters)
        total_users = int((await session.execute(users_stmt)).scalar_one() or 0)

        conversation_stmt = select(
            func.count(func.distinct(AnalyticsEvent.session_id)).label("total_conversations"),
            func.count(func.distinct(case((AnalyticsEvent.resolved_by_ai.is_(True), AnalyticsEvent.session_id)))).label("ai_resolved_sessions"),
            func.coalesce(func.avg(AnalyticsEvent.response_time_ms), 0.0).label("avg_first_response_ms"),
        ).where(*filters)
        conv_row = (await session.execute(conversation_stmt)).one()

        human_resolved_stmt = select(func.count(func.distinct(AdminQueue.session_id))).where(
            *queue_filters,
            AdminQueue.status.in_(["resolved", "completed", "closed"]),
        )
        human_resolved_sessions = int((await session.execute(human_resolved_stmt)).scalar_one() or 0)

        repeat_24h_subquery = (
            select(AnalyticsEvent.user_id)
            .where(*recent_24h_filters)
            .group_by(AnalyticsEvent.user_id)
            .having(func.count(func.distinct(AnalyticsEvent.session_id)) > 1)
            .subquery()
        )
        repeat_7d_subquery = (
            select(AnalyticsEvent.user_id)
            .where(*recent_7d_filters)
            .group_by(AnalyticsEvent.user_id)
            .having(func.count(func.distinct(AnalyticsEvent.session_id)) > 1)
            .subquery()
        )

        repeat_24h_stmt = select(func.count()).select_from(repeat_24h_subquery)
        repeat_7d_stmt = select(func.count()).select_from(repeat_7d_subquery)
        repeated_users_24h = int((await session.execute(repeat_24h_stmt)).scalar_one() or 0)
        repeated_users_7d = int((await session.execute(repeat_7d_stmt)).scalar_one() or 0)

        sentiment_stmt = (
            select(AnalyticsEvent.sentiment, func.count(AnalyticsEvent.id))
            .where(*filters)
            .group_by(AnalyticsEvent.sentiment)
        )
        sentiment_rows = (await session.execute(sentiment_stmt)).all()

        outcomes_filters = [
            SessionOutcome.tenant_id == tenant_id,
            SessionOutcome.created_at >= window_start,
        ]
        if workspace_id:
            outcomes_filters.append(SessionOutcome.workspace_id == workspace_id)
        outcome_stmt = (
            select(SessionOutcome.outcome_status, func.count(SessionOutcome.id))
            .where(*outcomes_filters)
            .group_by(SessionOutcome.outcome_status)
        )
        outcome_rows = (await session.execute(outcome_stmt)).all()

    total_conversations = int(conv_row.total_conversations or 0)
    ai_resolved_sessions = int(conv_row.ai_resolved_sessions or 0)
    resolved_sessions = min(total_conversations, ai_resolved_sessions + human_resolved_sessions)
    unresolved_sessions = max(total_conversations - resolved_sessions, 0)

    completion_rate = round((resolved_sessions / total_conversations) * 100, 2) if total_conversations else 0.0
    dropoff_rate = round((unresolved_sessions / total_conversations) * 100, 2) if total_conversations else 0.0
    repeat_contact_rate_24h = round((repeated_users_24h / total_users) * 100, 2) if total_users else 0.0
    repeat_contact_rate_7d = round((repeated_users_7d / total_users) * 100, 2) if total_users else 0.0

    sentiment_distribution = {
        str(sentiment or "unknown"): int(count or 0)
        for sentiment, count in sentiment_rows
    }
    outcomes_distribution = {
        str(status or "unknown"): int(count or 0)
        for status, count in outcome_rows
    }

    return {
        "window_days": days,
        "total_users": total_users,
        "total_conversations": total_conversations,
        "resolved_sessions": resolved_sessions,
        "completion_rate": completion_rate,
        "repeat_contact_rate_24h": repeat_contact_rate_24h,
        "repeat_contact_rate_7d": repeat_contact_rate_7d,
        "dropoff_rate": dropoff_rate,
        "time_to_first_meaningful_response_ms": round(float(conv_row.avg_first_response_ms or 0.0), 2),
        "sentiment_distribution": sentiment_distribution,
        "outcomes_distribution": outcomes_distribution,
    }


async def get_ai_performance_metrics(
    tenant_id: str,
    workspace_id: Optional[str] = None,
    days: int = 30,
):
    """Get AI quality metrics including auto-resolution and risk proxies."""
    days = _bounded_days(days)
    window_start = datetime.utcnow() - timedelta(days=days)
    filters = _event_filters(tenant_id, workspace_id, window_start)

    async with get_async_session() as session:
        summary_stmt = select(
            func.count(AnalyticsEvent.id).label("total_events"),
            func.coalesce(func.sum(case((AnalyticsEvent.resolved_by_ai.is_(True), 1), else_=0)), 0).label("ai_resolved_count"),
            func.coalesce(func.sum(case((AnalyticsEvent.handed_to_human.is_(True), 1), else_=0)), 0).label("handoff_count"),
            func.coalesce(func.sum(case((AnalyticsEvent.knowledge_base_used.is_(True), 1), else_=0)), 0).label("kb_hit_count"),
            func.coalesce(func.sum(case((AnalyticsEvent.unsolved_score >= 0.7, 1), else_=0)), 0).label("low_confidence_count"),
            func.coalesce(func.avg(AnalyticsEvent.unsolved_score), 0.0).label("avg_unsolved_score"),
            func.coalesce(func.avg(AnalyticsEvent.response_time_ms), 0.0).label("avg_response_time_ms"),
        ).where(*filters)
        summary_row = (await session.execute(summary_stmt)).one()

        by_model_stmt = (
            select(
                AnalyticsEvent.model_used,
                func.count(AnalyticsEvent.id).label("events"),
                func.coalesce(func.avg(AnalyticsEvent.response_time_ms), 0.0).label("avg_response_time_ms"),
                func.coalesce(func.sum(case((AnalyticsEvent.resolved_by_ai.is_(True), 1), else_=0)), 0).label("ai_resolved_count"),
                func.coalesce(func.sum(case((AnalyticsEvent.handed_to_human.is_(True), 1), else_=0)), 0).label("handoff_count"),
            )
            .where(*filters)
            .group_by(AnalyticsEvent.model_used)
            .order_by(func.count(AnalyticsEvent.id).desc())
        )
        model_rows = (await session.execute(by_model_stmt)).all()

    total_events = int(summary_row.total_events or 0)
    ai_resolved_count = int(summary_row.ai_resolved_count or 0)
    handoff_count = int(summary_row.handoff_count or 0)
    kb_hit_count = int(summary_row.kb_hit_count or 0)
    low_confidence_count = int(summary_row.low_confidence_count or 0)

    auto_resolution_rate = round((ai_resolved_count / total_events) * 100, 2) if total_events else 0.0
    fallback_rate = round((handoff_count / total_events) * 100, 2) if total_events else 0.0
    kb_hit_rate = round((kb_hit_count / total_events) * 100, 2) if total_events else 0.0
    low_confidence_ratio = round((low_confidence_count / total_events) * 100, 2) if total_events else 0.0

    models = []
    for row in model_rows:
        events = int(row.events or 0)
        models.append(
            {
                "model": row.model_used or "unknown",
                "events": events,
                "avg_response_time_ms": round(float(row.avg_response_time_ms or 0.0), 2),
                "auto_resolution_rate": round((int(row.ai_resolved_count or 0) / events) * 100, 2) if events else 0.0,
                "handoff_rate": round((int(row.handoff_count or 0) / events) * 100, 2) if events else 0.0,
            }
        )

    return {
        "window_days": days,
        "total_events": total_events,
        "auto_resolution_rate": auto_resolution_rate,
        "fallback_rate": fallback_rate,
        "kb_hit_rate": kb_hit_rate,
        "low_confidence_response_ratio": low_confidence_ratio,
        "hallucination_risk_proxy_rate": low_confidence_ratio,
        "avg_unsolved_score": round(float(summary_row.avg_unsolved_score or 0.0), 4),
        "avg_response_time_ms": round(float(summary_row.avg_response_time_ms or 0.0), 2),
        "models": models,
    }


async def get_team_performance_metrics(
    tenant_id: str,
    workspace_id: Optional[str] = None,
    days: int = 30,
):
    """Get team and SLA-oriented operational metrics."""
    days = _bounded_days(days)
    window_start = datetime.utcnow() - timedelta(days=days)

    queue_filters = [
        AdminQueue.tenant_id == tenant_id,
        AdminQueue.created_at >= window_start,
    ]
    if workspace_id:
        queue_filters.append(AdminQueue.workspace_id == workspace_id)

    event_filters = _event_filters(tenant_id, workspace_id, window_start)

    sla_filters = [
        SLAEvent.tenant_id == tenant_id,
        SLAEvent.event_time >= window_start,
    ]
    if workspace_id:
        sla_filters.append(SLAEvent.workspace_id == workspace_id)

    async with get_async_session() as session:
        handoff_stmt = select(func.coalesce(func.sum(case((AnalyticsEvent.handed_to_human.is_(True), 1), else_=0)), 0)).where(*event_filters)
        handoffs = int((await session.execute(handoff_stmt)).scalar_one() or 0)

        queue_status_stmt = (
            select(AdminQueue.status, func.count(AdminQueue.id))
            .where(*queue_filters)
            .group_by(AdminQueue.status)
        )
        status_rows = (await session.execute(queue_status_stmt)).all()

        queue_timing_stmt = select(
            AdminQueue.created_at,
            AdminQueue.assigned_at,
            AdminQueue.resolved_at,
        ).where(*queue_filters)
        queue_timing_rows = (await session.execute(queue_timing_stmt)).all()

        sla_summary_stmt = select(
            func.count(SLAEvent.id).label("total_sla_events"),
            func.coalesce(func.sum(case((SLAEvent.breached.is_(True), 1), else_=0)), 0).label("breach_count"),
        ).where(*sla_filters)
        sla_row = (await session.execute(sla_summary_stmt)).one()

        takeover_stmt = select(func.coalesce(func.avg(SLAEvent.actual_ms), 0.0)).where(
            *sla_filters,
            SLAEvent.event_type == "takeover_first_response",
        )
        avg_takeover_response_ms = float((await session.execute(takeover_stmt)).scalar_one() or 0.0)

    queue_status_counts = {str(status or "unknown"): int(count or 0) for status, count in status_rows}

    queue_wait_minutes: list[float] = []
    handling_minutes: list[float] = []
    for created_at, assigned_at, resolved_at in queue_timing_rows:
        if created_at and assigned_at and assigned_at >= created_at:
            queue_wait_minutes.append((assigned_at - created_at).total_seconds() / 60.0)
        if assigned_at and resolved_at and resolved_at >= assigned_at:
            handling_minutes.append((resolved_at - assigned_at).total_seconds() / 60.0)

    avg_queue_wait_minutes = round(sum(queue_wait_minutes) / len(queue_wait_minutes), 2) if queue_wait_minutes else 0.0
    avg_handling_time_minutes = round(sum(handling_minutes) / len(handling_minutes), 2) if handling_minutes else 0.0

    total_sla_events = int(sla_row.total_sla_events or 0)
    breach_count = int(sla_row.breach_count or 0)
    sla_breach_rate = round((breach_count / total_sla_events) * 100, 2) if total_sla_events else 0.0

    return {
        "window_days": days,
        "handoffs": handoffs,
        "queue_status_counts": queue_status_counts,
        "avg_queue_wait_minutes": avg_queue_wait_minutes,
        "first_takeover_response_time_minutes": round(avg_takeover_response_ms / 60000.0, 2),
        "avg_handling_time_minutes": avg_handling_time_minutes,
        "sla_breach_rate": sla_breach_rate,
        "resolved_count": len(handling_minutes),
    }


async def get_kb_performance_metrics(
    tenant_id: str,
    workspace_id: Optional[str] = None,
    days: int = 30,
):
    """Get knowledge-base quality and freshness metrics."""
    days = _bounded_days(days)
    window_start = datetime.utcnow() - timedelta(days=days)
    filters = _event_filters(tenant_id, workspace_id, window_start)

    metrics_filters = [
        ConversationMetric.tenant_id == tenant_id,
        ConversationMetric.aggregated_at >= window_start,
    ]
    if workspace_id:
        metrics_filters.append(ConversationMetric.workspace_id == workspace_id)

    source_filters = [KnowledgeSource.tenant_id == tenant_id]
    if workspace_id:
        source_filters.append(KnowledgeSource.workspace_id == workspace_id)

    ingestion_filters = [
        IngestionJob.tenant_id == tenant_id,
        IngestionJob.created_at >= window_start,
    ]
    if workspace_id:
        ingestion_filters.append(IngestionJob.workspace_id == workspace_id)

    async with get_async_session() as session:
        summary_stmt = select(
            func.count(AnalyticsEvent.id).label("total_events"),
            func.coalesce(func.sum(case((AnalyticsEvent.knowledge_base_used.is_(True), 1), else_=0)), 0).label("kb_hit_count"),
            func.coalesce(func.sum(case((AnalyticsEvent.unsolved_score >= 0.7, 1), else_=0)), 0).label("unanswered_count"),
        ).where(*filters)
        summary_row = (await session.execute(summary_stmt)).one()

        unanswered_trend_stmt = (
            select(
                func.date(AnalyticsEvent.timestamp).label("day"),
                func.coalesce(func.sum(case((AnalyticsEvent.unsolved_score >= 0.7, 1), else_=0)), 0).label("unanswered"),
            )
            .where(*filters)
            .group_by(func.date(AnalyticsEvent.timestamp))
            .order_by(func.date(AnalyticsEvent.timestamp))
        )
        unanswered_rows = (await session.execute(unanswered_trend_stmt)).all()

        citation_stmt = select(func.coalesce(func.avg(ConversationMetric.citation_coverage), 0.0)).where(*metrics_filters)
        citation_coverage = float((await session.execute(citation_stmt)).scalar_one() or 0.0)

        source_counts_stmt = (
            select(KnowledgeSource.source_type, func.count(KnowledgeSource.id))
            .where(*source_filters)
            .group_by(KnowledgeSource.source_type)
        )
        source_count_rows = (await session.execute(source_counts_stmt)).all()

        freshness_stmt = select(KnowledgeSource.last_sync_at).where(*source_filters)
        freshness_rows = (await session.execute(freshness_stmt)).all()

        ingestion_quality_stmt = (
            select(
                IngestionJob.source_type,
                func.count(IngestionJob.id).label("total_jobs"),
                func.coalesce(func.sum(case((IngestionJob.status == "completed", 1), else_=0)), 0).label("completed_jobs"),
                func.coalesce(func.sum(case((IngestionJob.status == "failed", 1), else_=0)), 0).label("failed_jobs"),
            )
            .where(*ingestion_filters)
            .group_by(IngestionJob.source_type)
        )
        ingestion_rows = (await session.execute(ingestion_quality_stmt)).all()

    total_events = int(summary_row.total_events or 0)
    kb_hit_count = int(summary_row.kb_hit_count or 0)
    unanswered_count = int(summary_row.unanswered_count or 0)
    retrieval_hit_rate = round((kb_hit_count / total_events) * 100, 2) if total_events else 0.0

    source_volume = {
        str(source_type or "unknown"): int(count or 0)
        for source_type, count in source_count_rows
    }

    sync_age_hours: list[float] = []
    now = datetime.now(timezone.utc)
    for (last_sync_at,) in freshness_rows:
        normalized_last_sync_at = _utc_aware_datetime(last_sync_at)
        if normalized_last_sync_at and now >= normalized_last_sync_at:
            sync_age_hours.append((now - normalized_last_sync_at).total_seconds() / 3600.0)
    avg_sync_age_hours = (sum(sync_age_hours) / len(sync_age_hours)) if sync_age_hours else 0.0
    knowledge_freshness_score = round(max(0.0, 100.0 - ((avg_sync_age_hours / 24.0) * 4.0)), 2)

    source_quality = []
    for source_type, total_jobs, completed_jobs, failed_jobs in ingestion_rows:
        total = int(total_jobs or 0)
        completed = int(completed_jobs or 0)
        failed = int(failed_jobs or 0)
        source_quality.append(
            {
                "source_type": source_type or "unknown",
                "total_jobs": total,
                "success_rate": round((completed / total) * 100, 2) if total else 0.0,
                "failure_rate": round((failed / total) * 100, 2) if total else 0.0,
            }
        )

    unanswered_trend = [
        {
            "day": str(day),
            "unanswered": int(unanswered or 0),
        }
        for day, unanswered in unanswered_rows
    ]

    return {
        "window_days": days,
        "total_events": total_events,
        "retrieval_hit_rate": retrieval_hit_rate,
        "citation_coverage_rate": round(citation_coverage * 100.0, 2),
        "unanswered_questions": unanswered_count,
        "unanswered_question_trend": unanswered_trend,
        "knowledge_freshness_score": knowledge_freshness_score,
        "source_volume": source_volume,
        "source_quality": source_quality,
    }


async def get_channel_performance_metrics(
    tenant_id: str,
    workspace_id: Optional[str] = None,
    days: int = 30,
):
    """Get channel-level volume, quality, and latency distribution metrics."""
    days = _bounded_days(days)
    window_start = datetime.utcnow() - timedelta(days=days)
    filters = _event_filters(tenant_id, workspace_id, window_start)

    async with get_async_session() as session:
        summary_stmt = (
            select(
                AnalyticsEvent.channel,
                func.count(AnalyticsEvent.id).label("events"),
                func.coalesce(func.avg(AnalyticsEvent.response_time_ms), 0.0).label("avg_response_time_ms"),
                func.coalesce(func.sum(case((AnalyticsEvent.resolved_by_ai.is_(True), 1), else_=0)), 0).label("ai_resolved_count"),
                func.coalesce(func.sum(case((AnalyticsEvent.handed_to_human.is_(True), 1), else_=0)), 0).label("handoff_count"),
            )
            .where(*filters)
            .group_by(AnalyticsEvent.channel)
            .order_by(func.count(AnalyticsEvent.id).desc())
        )
        summary_rows = (await session.execute(summary_stmt)).all()

        latency_stmt = select(AnalyticsEvent.channel, AnalyticsEvent.response_time_ms).where(
            *filters,
            AnalyticsEvent.response_time_ms.is_not(None),
        )
        latency_rows = (await session.execute(latency_stmt)).all()

    latencies_by_channel: dict[str, list[float]] = {}
    for channel, latency in latency_rows:
        key = str(channel or "unknown")
        latencies_by_channel.setdefault(key, []).append(float(latency or 0.0))

    channels = []
    total_events = 0
    for row in summary_rows:
        channel_name = str(row.channel or "unknown")
        events = int(row.events or 0)
        total_events += events
        channel_latencies = latencies_by_channel.get(channel_name, [])
        channels.append(
            {
                "channel": channel_name,
                "events": events,
                "avg_response_time_ms": round(float(row.avg_response_time_ms or 0.0), 2),
                "auto_resolution_rate": round((int(row.ai_resolved_count or 0) / events) * 100, 2) if events else 0.0,
                "handoff_rate": round((int(row.handoff_count or 0) / events) * 100, 2) if events else 0.0,
                "p50_response_latency_ms": round(_percentile(channel_latencies, 0.50), 2),
                "p95_response_latency_ms": round(_percentile(channel_latencies, 0.95), 2),
            }
        )

    return {
        "window_days": days,
        "total_events": total_events,
        "channels": channels,
    }


async def create_alert_rule(
    tenant_id: str,
    workspace_id: str,
    rule_name: str,
    metric_name: str,
    threshold_value: float,
    condition: str,
    is_active: bool = True,
):
    """Create a tenant-scoped alert rule for KPI governance."""
    normalized_condition = (condition or "").strip().lower()
    if normalized_condition not in {"gt", "gte", "lt", "lte"}:
        raise ValueError("condition must be one of: gt, gte, lt, lte")

    async with get_async_session() as session:
        rule = AnalyticsAlertRule(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            rule_name=rule_name,
            metric_name=metric_name,
            threshold_value=float(threshold_value),
            condition=normalized_condition,
            is_active=bool(is_active),
            created_at=datetime.utcnow(),
        )
        session.add(rule)
        await session.commit()
        await session.refresh(rule)

    return {
        "id": rule.id,
        "tenant_id": rule.tenant_id,
        "workspace_id": rule.workspace_id,
        "rule_name": rule.rule_name,
        "metric_name": rule.metric_name,
        "threshold_value": float(rule.threshold_value or 0.0),
        "condition": rule.condition,
        "is_active": bool(rule.is_active),
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }


async def get_alert_events(
    tenant_id: str,
    workspace_id: Optional[str] = None,
    days: int = 30,
    limit: int = 100,
    status: Optional[str] = None,
):
    """List tenant alert events with optional status filter."""
    days = _bounded_days(days)
    limit = max(1, min(int(limit), 500))
    window_start = datetime.utcnow() - timedelta(days=days)

    filters: list[Any] = [
        AnalyticsAlertEvent.tenant_id == tenant_id,
        AnalyticsAlertEvent.event_time >= window_start,
    ]
    if workspace_id:
        filters.append(AnalyticsAlertEvent.workspace_id == workspace_id)
    if status:
        filters.append(AnalyticsAlertEvent.status == status)

    async with get_async_session() as session:
        stmt = (
            select(AnalyticsAlertEvent, AnalyticsAlertRule.rule_name)
            .join(AnalyticsAlertRule, AnalyticsAlertRule.id == AnalyticsAlertEvent.rule_id, isouter=True)
            .where(*filters)
            .order_by(AnalyticsAlertEvent.event_time.desc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()

    events = []
    for event, rule_name in rows:
        events.append(
            {
                "id": event.id,
                "rule_id": event.rule_id,
                "rule_name": rule_name,
                "metric_value": float(event.metric_value or 0.0),
                "message": event.message,
                "status": event.status,
                "event_time": event.event_time.isoformat() if event.event_time else None,
            }
        )

    return {
        "window_days": days,
        "count": len(events),
        "events": events,
    }


def _normalize_metric_name(metric_name: str) -> str:
    normalized = (metric_name or "").strip().lower().replace(" ", "_").replace("-", "_")
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized


def _flatten_numeric_metrics(prefix: str, value: Any, out: dict[str, float]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            _flatten_numeric_metrics(next_prefix, item, out)
        return

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return

    numeric = float(value)
    if numeric != numeric:  # NaN guard
        return

    full_key = _normalize_metric_name(prefix)
    if full_key:
        out.setdefault(full_key, numeric)

    leaf_key = _normalize_metric_name(prefix.rsplit(".", 1)[-1]) if prefix else ""
    if leaf_key:
        out.setdefault(leaf_key, numeric)


async def _build_alert_metric_catalog(
    tenant_id: str,
    workspace_id: str,
    days: int,
) -> tuple[dict[str, float], dict[str, Any]]:
    overview, ai_metrics, team_metrics, kb_metrics, usage_metrics = await asyncio.gather(
        get_tenant_overview_metrics(tenant_id=tenant_id, workspace_id=workspace_id, days=days),
        get_ai_performance_metrics(tenant_id=tenant_id, workspace_id=workspace_id, days=days),
        get_team_performance_metrics(tenant_id=tenant_id, workspace_id=workspace_id, days=days),
        get_kb_performance_metrics(tenant_id=tenant_id, workspace_id=workspace_id, days=days),
        get_usage_governance_metrics(tenant_id=tenant_id, workspace_id=workspace_id, days=days),
    )

    metrics: dict[str, float] = {}
    _flatten_numeric_metrics("overview", overview, metrics)
    _flatten_numeric_metrics("ai", ai_metrics, metrics)
    _flatten_numeric_metrics("team", team_metrics, metrics)
    _flatten_numeric_metrics("kb", kb_metrics, metrics)
    _flatten_numeric_metrics("usage", usage_metrics, metrics)

    if "fallback_rate" in metrics and "handoff_rate" not in metrics:
        metrics["handoff_rate"] = metrics["fallback_rate"]
    if "kb_hit_rate" in metrics and "retrieval_hit_rate" not in metrics:
        metrics["retrieval_hit_rate"] = metrics["kb_hit_rate"]

    return metrics, usage_metrics


async def _load_active_alert_rules(session: Any, tenant_id: str, workspace_id: str) -> list[Any]:
    stmt = (
        select(AnalyticsAlertRule)
        .where(
            AnalyticsAlertRule.tenant_id == tenant_id,
            AnalyticsAlertRule.workspace_id == workspace_id,
            AnalyticsAlertRule.is_active.is_(True),
        )
        .order_by(AnalyticsAlertRule.id.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def _has_recent_rule_event(
    session: Any,
    tenant_id: str,
    workspace_id: str,
    rule_id: int,
    dedupe_window_start: datetime,
) -> bool:
    stmt = select(func.count(AnalyticsAlertEvent.id)).where(
        AnalyticsAlertEvent.tenant_id == tenant_id,
        AnalyticsAlertEvent.workspace_id == workspace_id,
        AnalyticsAlertEvent.rule_id == rule_id,
        AnalyticsAlertEvent.event_time >= dedupe_window_start,
    )
    count = int((await session.execute(stmt)).scalar_one() or 0)
    return count > 0


async def _has_recent_system_quota_event(
    session: Any,
    tenant_id: str,
    workspace_id: str,
    message: str,
    dedupe_window_start: datetime,
) -> bool:
    stmt = select(func.count(AnalyticsAlertEvent.id)).where(
        AnalyticsAlertEvent.tenant_id == tenant_id,
        AnalyticsAlertEvent.workspace_id == workspace_id,
        AnalyticsAlertEvent.rule_id.is_(None),
        AnalyticsAlertEvent.message == message,
        AnalyticsAlertEvent.event_time >= dedupe_window_start,
    )
    count = int((await session.execute(stmt)).scalar_one() or 0)
    return count > 0


async def run_governance_alert_generation_job(
    tenant_id: str,
    workspace_id: str,
    days: int = 30,
    dedupe_hours: int = 24,
):
    """Evaluate active rules and quota breaches, then create alert events."""
    days = _bounded_days(days)
    dedupe_hours = max(1, min(int(dedupe_hours), 24 * 14))

    metrics, usage_payload = await _build_alert_metric_catalog(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        days=days,
    )

    now = datetime.utcnow()
    dedupe_window_start = now - timedelta(hours=dedupe_hours)

    generated_rule_events = 0
    generated_quota_events = 0
    skipped_recent_duplicates = 0
    triggered_rule_matches = 0
    missing_metric_rules: list[str] = []
    breached_quota_metrics: list[str] = []

    async with get_async_session() as session:
        rules = await _load_active_alert_rules(session, tenant_id, workspace_id)

        for rule in rules:
            metric_name = str(rule.metric_name or "")
            metric_key = _normalize_metric_name(metric_name)
            metric_value = metrics.get(metric_key)

            if metric_value is None:
                missing_metric_rules.append(str(rule.rule_name or metric_name or rule.id))
                continue

            try:
                is_triggered = alert_condition_met(
                    metric_value=float(metric_value),
                    condition=str(rule.condition or ""),
                    threshold_value=float(rule.threshold_value or 0.0),
                )
            except ValueError:
                missing_metric_rules.append(str(rule.rule_name or metric_name or rule.id))
                continue

            if not is_triggered:
                continue

            triggered_rule_matches += 1
            if await _has_recent_rule_event(
                session=session,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                rule_id=int(rule.id),
                dedupe_window_start=dedupe_window_start,
            ):
                skipped_recent_duplicates += 1
                continue

            message = (
                f"Rule '{rule.rule_name}' triggered: "
                f"{metric_name}={round(float(metric_value), 4)} "
                f"({rule.condition} {round(float(rule.threshold_value or 0.0), 4)})"
            )
            session.add(
                AnalyticsAlertEvent(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    rule_id=int(rule.id),
                    event_time=now,
                    metric_value=float(metric_value),
                    message=message,
                    status="new",
                )
            )
            generated_rule_events += 1

        utilization = usage_payload.get("utilization", {}) if isinstance(usage_payload, dict) else {}
        for metric_name, message in QUOTA_BREACH_MESSAGES.items():
            metric_value_raw = utilization.get(metric_name)
            if metric_value_raw is None:
                continue

            metric_value = float(metric_value_raw)
            if metric_value < 100.0:
                continue

            breached_quota_metrics.append(metric_name)

            if await _has_recent_system_quota_event(
                session=session,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                message=message,
                dedupe_window_start=dedupe_window_start,
            ):
                skipped_recent_duplicates += 1
                continue

            session.add(
                AnalyticsAlertEvent(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    rule_id=None,
                    event_time=now,
                    metric_value=metric_value,
                    message=message,
                    status="new",
                )
            )
            generated_quota_events += 1

        if generated_rule_events or generated_quota_events:
            await session.commit()

    return {
        "status": "success",
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "window_days": days,
        "dedupe_hours": dedupe_hours,
        "available_metrics": len(metrics),
        "evaluated_rules": len(rules),
        "triggered_rule_matches": triggered_rule_matches,
        "generated_rule_events": generated_rule_events,
        "generated_quota_events": generated_quota_events,
        "generated_events": generated_rule_events + generated_quota_events,
        "skipped_recent_duplicates": skipped_recent_duplicates,
        "missing_metric_rules": sorted(set(missing_metric_rules)),
        "breached_quota_metrics": sorted(set(breached_quota_metrics)),
    }


async def run_tenant_analytics_aggregation_job(
    tenant_id: str,
    workspace_id: str,
):
    """Aggregate current KPI snapshot into hourly and daily rollup tables."""
    overview = await get_tenant_overview_metrics(tenant_id=tenant_id, workspace_id=workspace_id, days=1)

    now = datetime.utcnow()
    hour_bucket = now.replace(minute=0, second=0, microsecond=0)
    day_bucket = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async with get_async_session() as session:
        hourly = TenantAnalyticsHourly(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            hour_timestamp=hour_bucket,
            total_conversations=int(overview.get("total_conversations", 0)),
            ai_resolved_conversations=int(overview.get("ai_resolved_count", 0)),
            handed_to_human=int(overview.get("handoff_count", 0)),
            avg_human_response_time_ms=int(round(float(overview.get("avg_response_time_ms", 0.0)))),
            created_at=now,
        )
        daily = TenantAnalyticsDaily(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            date=day_bucket,
            total_conversations=int(overview.get("total_conversations", 0)),
            ai_resolved_conversations=int(overview.get("ai_resolved_count", 0)),
            handed_to_human=int(overview.get("handoff_count", 0)),
            avg_human_response_time_ms=int(round(float(overview.get("avg_response_time_ms", 0.0)))),
            created_at=now,
        )
        session.add(hourly)
        session.add(daily)
        await session.commit()

    try:
        governance_alerts = await run_governance_alert_generation_job(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            days=30,
        )
    except Exception as exc:
        logger.error(f"Governance alert generation job failed for tenant={tenant_id}: {exc}", exc)
        governance_alerts = {
            "status": "error",
            "message": "Governance alert generation failed",
        }

    return {
        "status": "success",
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "hour_bucket": hour_bucket.isoformat(),
        "day_bucket": day_bucket.isoformat(),
        "overview_snapshot": overview,
        "governance_alerts": governance_alerts,
    }


async def export_tenant_analytics_csv(
    tenant_id: str,
    workspace_id: str,
    days: int = 30,
    domain: str = "all",
) -> str:
    """Export tenant analytics metrics as CSV for reporting and governance."""
    normalized_domain = (domain or "all").strip().lower()
    valid_domains = {"all", "overview", "user", "ai", "team", "kb", "channel"}
    if normalized_domain not in valid_domains:
        raise ValueError(f"domain must be one of: {', '.join(sorted(valid_domains))}")

    payload: dict[str, Any] = {}
    if normalized_domain in {"all", "overview"}:
        payload["overview"] = await get_tenant_overview_metrics(tenant_id, workspace_id, days)
    if normalized_domain in {"all", "user"}:
        payload["user"] = await get_user_performance_metrics(tenant_id, workspace_id, days)
    if normalized_domain in {"all", "ai"}:
        payload["ai"] = await get_ai_performance_metrics(tenant_id, workspace_id, days)
    if normalized_domain in {"all", "team"}:
        payload["team"] = await get_team_performance_metrics(tenant_id, workspace_id, days)
    if normalized_domain in {"all", "kb"}:
        payload["kb"] = await get_kb_performance_metrics(tenant_id, workspace_id, days)
    if normalized_domain in {"all", "channel"}:
        payload["channel"] = await get_channel_performance_metrics(tenant_id, workspace_id, days)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["domain", "metric", "value"])

    for section, section_payload in payload.items():
        rows: list[tuple[str, Any]] = []
        _flatten_metric_rows("", section_payload, rows)
        for metric, value in rows:
            metric_name = metric or "value"
            writer.writerow([section, metric_name, value])

    return output.getvalue()


async def get_usage_governance_metrics(
    tenant_id: str,
    workspace_id: Optional[str] = None,
    days: int = 30,
):
    """Return usage snapshot with plan quotas and utilization status."""
    days = _bounded_days(days)
    now = datetime.utcnow()
    requested_window_start = now - timedelta(days=days)
    rolling_window_start = now - timedelta(days=30)

    requested_filters = _event_filters(tenant_id, workspace_id, requested_window_start)
    rolling_filters = _event_filters(tenant_id, workspace_id, rolling_window_start)

    alert_rule_filters = [
        AnalyticsAlertRule.tenant_id == tenant_id,
        AnalyticsAlertRule.is_active.is_(True),
    ]
    if workspace_id:
        alert_rule_filters.append(AnalyticsAlertRule.workspace_id == workspace_id)

    async with get_async_session() as session:
        tenant_plan = await _resolve_tenant_plan(session, tenant_id, workspace_id)

        requested_stmt = select(
            func.count(AnalyticsEvent.id).label("events"),
            func.count(func.distinct(AnalyticsEvent.session_id)).label("conversations"),
            func.count(func.distinct(AnalyticsEvent.user_id)).label("active_users"),
        ).where(*requested_filters)
        requested_row = (await session.execute(requested_stmt)).one()

        rolling_stmt = select(
            func.count(AnalyticsEvent.id).label("events"),
            func.count(func.distinct(AnalyticsEvent.session_id)).label("conversations"),
        ).where(*rolling_filters)
        rolling_row = (await session.execute(rolling_stmt)).one()

        active_rules_stmt = select(func.count(AnalyticsAlertRule.id)).where(*alert_rule_filters)
        active_alert_rules = int((await session.execute(active_rules_stmt)).scalar_one() or 0)

    quotas = PLAN_QUOTAS.get(tenant_plan, PLAN_QUOTAS["starter"])

    usage = {
        "window_days": days,
        "events": int(requested_row.events or 0),
        "conversations": int(requested_row.conversations or 0),
        "active_users": int(requested_row.active_users or 0),
        "rolling_30d_events": int(rolling_row.events or 0),
        "rolling_30d_conversations": int(rolling_row.conversations or 0),
        "active_alert_rules": active_alert_rules,
    }

    utilization = {
        "monthly_events_pct": _utilization_pct(usage["rolling_30d_events"], quotas["monthly_events"]),
        "monthly_conversations_pct": _utilization_pct(usage["rolling_30d_conversations"], quotas["monthly_conversations"]),
        "active_alert_rules_pct": _utilization_pct(usage["active_alert_rules"], quotas["active_alert_rules"]),
    }

    status = _quota_status([
        utilization["monthly_events_pct"],
        utilization["monthly_conversations_pct"],
        utilization["active_alert_rules_pct"],
    ])

    near_limit = [
        metric
        for metric, value in utilization.items()
        if value is not None and QUOTA_WARNING_THRESHOLD_PCT <= value < 100.0
    ]
    exceeded = [
        metric
        for metric, value in utilization.items()
        if value is not None and value >= 100.0
    ]

    return {
        "tenant_plan": tenant_plan,
        "usage": usage,
        "quota": quotas,
        "utilization": utilization,
        "status": status,
        "near_limit": near_limit,
        "exceeded": exceeded,
    }


async def get_quota_governance_metrics(
    tenant_id: str,
    workspace_id: Optional[str] = None,
    days: int = 30,
):
    """Return quota forecast and recommendations derived from usage metrics."""
    usage_payload = await get_usage_governance_metrics(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        days=days,
    )

    usage = usage_payload["usage"]
    quota = usage_payload["quota"]

    rolling_events = int(usage.get("rolling_30d_events", 0))
    rolling_conversations = int(usage.get("rolling_30d_conversations", 0))
    active_alert_rules = int(usage.get("active_alert_rules", 0))

    avg_daily_events = round(rolling_events / 30.0, 2)
    avg_daily_conversations = round(rolling_conversations / 30.0, 2)

    forecast = {
        "avg_daily_events": avg_daily_events,
        "avg_daily_conversations": avg_daily_conversations,
        "events_days_until_quota": _days_until_quota(rolling_events, quota.get("monthly_events"), avg_daily_events),
        "conversations_days_until_quota": _days_until_quota(
            rolling_conversations,
            quota.get("monthly_conversations"),
            avg_daily_conversations,
        ),
        "alert_rule_slots_remaining": (
            None
            if quota.get("active_alert_rules") is None
            else max(int(quota["active_alert_rules"]) - active_alert_rules, 0)
        ),
    }

    recommendations: list[str] = []
    if usage_payload["status"] == "breached":
        recommendations.append("Quota exceeded. Upgrade plan or reduce event throughput immediately.")
    elif usage_payload["status"] == "warning":
        recommendations.append("Approaching quota limits. Plan capacity changes before next billing window.")
    else:
        recommendations.append("Quota usage is healthy for current plan.")

    if forecast["events_days_until_quota"] is not None and forecast["events_days_until_quota"] <= 7:
        recommendations.append("Event quota may be reached within 7 days based on recent trend.")
    if forecast["conversations_days_until_quota"] is not None and forecast["conversations_days_until_quota"] <= 7:
        recommendations.append("Conversation quota may be reached within 7 days based on recent trend.")

    return {
        "tenant_plan": usage_payload["tenant_plan"],
        "status": usage_payload["status"],
        "usage": usage,
        "quota": quota,
        "utilization": usage_payload["utilization"],
        "forecast": forecast,
        "recommendations": recommendations,
    }
