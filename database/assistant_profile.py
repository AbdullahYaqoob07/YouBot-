"""Workspace assistant identity / behavioural profile."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, cast

from loguru import logger
from sqlalchemy import select

from database.models import AssistantProfile, get_async_session

ALLOWED_TONES = {"warm", "professional", "casual", "formal"}


def _normalize_tone(value: Optional[str]) -> str:
    cleaned = (value or "").strip().lower()
    return cleaned if cleaned in ALLOWED_TONES else "warm"


def _normalize_topic_list(value: Any, max_items: int = 30) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        candidates = [v.strip() for v in value.split(",")]
    elif isinstance(value, (list, tuple)):
        candidates = [str(v).strip() for v in value]
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for c in candidates:
        if not c or len(c) > 80:
            continue
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= max_items:
            break
    return out


def _serialize(row: AssistantProfile) -> dict[str, Any]:
    row_any = cast(Any, row)
    return {
        "tenant_id": row_any.tenant_id,
        "workspace_id": row_any.workspace_id,
        "business_name": row_any.business_name or "",
        "business_description": row_any.business_description or "",
        "service_topics": list(row_any.service_topics or []),
        "tone": row_any.tone or "warm",
        "website_url": row_any.website_url or "",
        "contact_email": row_any.contact_email or "",
        "handoff_message": row_any.handoff_message or "",
        "forbidden_topics": list(row_any.forbidden_topics or []),
        "updated_at": row_any.updated_at.isoformat() if row_any.updated_at else None,
    }


async def get_assistant_profile(
    tenant_id: str, workspace_id: str
) -> Optional[dict[str, Any]]:
    try:
        async with get_async_session() as session:
            stmt = select(AssistantProfile).where(
                AssistantProfile.tenant_id == tenant_id,
                AssistantProfile.workspace_id == workspace_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            return _serialize(row)
    except Exception as exc:
        logger.warning(
            "Assistant profile lookup failed for tenant {} workspace {}: {}",
            tenant_id,
            workspace_id,
            exc,
        )
        return None


async def upsert_assistant_profile(
    tenant_id: str,
    workspace_id: str,
    *,
    business_name: str,
    business_description: Optional[str] = None,
    service_topics: Optional[list[str]] = None,
    tone: Optional[str] = None,
    website_url: Optional[str] = None,
    contact_email: Optional[str] = None,
    handoff_message: Optional[str] = None,
    forbidden_topics: Optional[list[str]] = None,
) -> dict[str, Any]:
    business_name_clean = (business_name or "").strip()[:255] or "our team"
    description_clean = (business_description or "").strip()[:1000] or None
    topics_clean = _normalize_topic_list(service_topics)
    forbidden_clean = _normalize_topic_list(forbidden_topics, max_items=20)
    tone_clean = _normalize_tone(tone)
    website_clean = (website_url or "").strip()[:500] or None
    email_clean = (contact_email or "").strip()[:255] or None
    handoff_clean = (handoff_message or "").strip()[:2000] or None

    now = datetime.utcnow()

    # Avoid circular import at module load.
    from database.workspace_provisioning import ensure_workspace_provisioned

    async with get_async_session() as session:
        await ensure_workspace_provisioned(session, tenant_id, workspace_id)

        stmt = select(AssistantProfile).where(
            AssistantProfile.tenant_id == tenant_id,
            AssistantProfile.workspace_id == workspace_id,
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        row_any = cast(Any, row)

        if row_any is not None:
            row_any.business_name = business_name_clean
            row_any.business_description = description_clean
            row_any.service_topics = topics_clean
            row_any.tone = tone_clean
            row_any.website_url = website_clean
            row_any.contact_email = email_clean
            row_any.handoff_message = handoff_clean
            row_any.forbidden_topics = forbidden_clean
            row_any.updated_at = now
        else:
            row_any = AssistantProfile(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                business_name=business_name_clean,
                business_description=description_clean,
                service_topics=topics_clean,
                tone=tone_clean,
                website_url=website_clean,
                contact_email=email_clean,
                handoff_message=handoff_clean,
                forbidden_topics=forbidden_clean,
                created_at=now,
                updated_at=now,
            )
            session.add(row_any)

        await session.commit()
        await session.refresh(row_any)
        return _serialize(row_any)
