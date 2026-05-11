"""
Phase 3 retrieval-mode profile, recommendation, and routing operations.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Optional, cast

from sqlalchemy import select

from database.models import (
    RetrievalProfile,
    RetrievalRecommendationEvent,
    get_async_session,
)

VALID_RETRIEVAL_MODES = {"rag", "page_index", "hybrid"}


def normalize_retrieval_mode(mode: Optional[str], default: str = "rag") -> str:
    normalized = (mode or "").strip().lower()
    if normalized in VALID_RETRIEVAL_MODES:
        return normalized
    return default


def normalize_allowed_modes(modes: Optional[list[str]]) -> list[str]:
    cleaned: list[str] = []
    for mode in modes or []:
        normalized = normalize_retrieval_mode(mode, default="")
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned or ["rag"]


def _band_for_latency(mode: str) -> str:
    if mode == "rag":
        return "low"
    if mode == "hybrid":
        return "medium"
    return "high"


def _band_for_cost(mode: str) -> str:
    if mode == "rag":
        return "low"
    if mode == "hybrid":
        return "medium"
    return "high"


def recommend_retrieval_mode(query_text: str, profile: dict[str, Any]) -> dict[str, str]:
    """Deterministic recommendation rules for Phase 3 V1."""
    query = (query_text or "").lower().strip()
    compliance = float(profile.get("compliance_criticality", 0.5) or 0.5)
    avg_pages = int(profile.get("average_document_pages", 10) or 10)
    complexity = float(profile.get("query_complexity", 0.5) or 0.5)
    latency_budget = int(profile.get("latency_budget_ms", 2500) or 2500)
    cost_sensitivity = float(profile.get("cost_sensitivity", 0.5) or 0.5)

    legal_signals = (
        "clause",
        "policy",
        "compliance",
        "legal",
        "regulation",
        "contract",
        "terms",
        "section",
    )
    broad_context_signals = (
        "full document",
        "entire document",
        "across pages",
        "compare sections",
        "page",
        "context",
    )

    if compliance >= 0.75 and avg_pages >= 20:
        mode = "page_index"
        reason = "High compliance criticality and long documents favor full-page context retrieval"
    elif any(token in query for token in legal_signals + broad_context_signals):
        mode = "page_index"
        reason = "Query indicates legal or cross-page context requirements"
    elif avg_pages >= 40 and cost_sensitivity >= 0.7:
        mode = "hybrid"
        reason = "Long documents with cost sensitivity favor page narrowing plus chunk retrieval"
    elif latency_budget <= 1500 and complexity <= 0.45:
        mode = "rag"
        reason = "Strict latency budget with moderate complexity favors fast chunk retrieval"
    elif complexity >= 0.75 and avg_pages >= 20:
        mode = "hybrid"
        reason = "Higher query complexity on longer documents favors hybrid retrieval"
    else:
        mode = "rag"
        reason = "Default recommendation for balanced latency and cost"

    return {
        "recommended_mode": mode,
        "reason_summary": reason,
        "expected_latency_band": _band_for_latency(mode),
        "expected_cost_band": _band_for_cost(mode),
    }


async def get_retrieval_profile(tenant_id: str, workspace_id: str) -> Optional[dict[str, Any]]:
    async with get_async_session() as session:
        result = await session.execute(
            select(RetrievalProfile).where(
                RetrievalProfile.tenant_id == tenant_id,
                RetrievalProfile.workspace_id == workspace_id,
            )
        )
        row = cast(Any, result.scalar_one_or_none())
        if not row:
            return None

        allowed_modes = normalize_allowed_modes(list(getattr(row, "allowed_modes", None) or []))
        return {
            "tenant_id": row.tenant_id,
            "workspace_id": row.workspace_id,
            "default_mode": normalize_retrieval_mode(row.default_mode),
            "allowed_modes": allowed_modes,
            "page_window_limit": row.page_window_limit,
            "compliance_criticality": row.compliance_criticality,
            "average_document_pages": row.average_document_pages,
            "query_complexity": row.query_complexity,
            "latency_budget_ms": row.latency_budget_ms,
            "cost_sensitivity": row.cost_sensitivity,
            "updated_at": row.updated_at.isoformat() if row.updated_at is not None else None,
        }


async def upsert_retrieval_profile(
    tenant_id: str,
    workspace_id: str,
    default_mode: str,
    allowed_modes: list[str],
    page_window_limit: int,
    compliance_criticality: float,
    average_document_pages: int,
    query_complexity: float,
    latency_budget_ms: int,
    cost_sensitivity: float,
) -> dict[str, Any]:
    normalized_default = normalize_retrieval_mode(default_mode)
    normalized_allowed = normalize_allowed_modes(allowed_modes)
    if normalized_default not in normalized_allowed:
        normalized_allowed.append(normalized_default)

    now = datetime.utcnow()
    async with get_async_session() as session:
        result = await session.execute(
            select(RetrievalProfile).where(
                RetrievalProfile.tenant_id == tenant_id,
                RetrievalProfile.workspace_id == workspace_id,
            )
        )
        row = cast(Any, result.scalar_one_or_none())

        if row:
            row.default_mode = normalized_default
            row.allowed_modes = normalized_allowed
            row.page_window_limit = max(1, min(20, int(page_window_limit)))
            row.compliance_criticality = max(0.0, min(1.0, float(compliance_criticality)))
            row.average_document_pages = max(1, int(average_document_pages))
            row.query_complexity = max(0.0, min(1.0, float(query_complexity)))
            row.latency_budget_ms = max(300, int(latency_budget_ms))
            row.cost_sensitivity = max(0.0, min(1.0, float(cost_sensitivity)))
            row.updated_at = now
        else:
            row = RetrievalProfile(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                default_mode=normalized_default,
                allowed_modes=normalized_allowed,
                page_window_limit=max(1, min(20, int(page_window_limit))),
                compliance_criticality=max(0.0, min(1.0, float(compliance_criticality))),
                average_document_pages=max(1, int(average_document_pages)),
                query_complexity=max(0.0, min(1.0, float(query_complexity))),
                latency_budget_ms=max(300, int(latency_budget_ms)),
                cost_sensitivity=max(0.0, min(1.0, float(cost_sensitivity))),
                created_at=now,
                updated_at=now,
            )
            session.add(row)

        await session.commit()

    saved = await get_retrieval_profile(tenant_id, workspace_id)
    return saved or {
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "default_mode": normalized_default,
        "allowed_modes": normalized_allowed,
    }


async def select_retrieval_mode(
    tenant_id: str,
    workspace_id: str,
    query_text: str,
    selected_mode_override: Optional[str] = None,
) -> dict[str, Any]:
    profile = await get_retrieval_profile(tenant_id, workspace_id)
    if profile is None:
        workspace_default = "rag"

        profile = {
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "default_mode": workspace_default,
            "allowed_modes": [workspace_default],
            "page_window_limit": 4,
            "compliance_criticality": 0.5,
            "average_document_pages": 10,
            "query_complexity": 0.5,
            "latency_budget_ms": 2500,
            "cost_sensitivity": 0.5,
        }

    recommendation = recommend_retrieval_mode(query_text, profile)
    allowed = normalize_allowed_modes(profile.get("allowed_modes"))
    default_mode = normalize_retrieval_mode(profile.get("default_mode"), default="rag")
    recommended = recommendation["recommended_mode"]

    override_mode = normalize_retrieval_mode(selected_mode_override, default="") if selected_mode_override else ""
    if override_mode and override_mode in allowed:
        selected_mode = override_mode
        override_applied = True
    elif default_mode in allowed:
        selected_mode = default_mode
        override_applied = False
    elif recommended in allowed:
        selected_mode = recommended
        override_applied = False
    else:
        selected_mode = allowed[0]
        override_applied = False

    query_hash = hashlib.sha256((query_text or "").encode("utf-8")).hexdigest()
    now = datetime.utcnow()
    async with get_async_session() as session:
        event = RetrievalRecommendationEvent(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            query_hash=query_hash,
            query_preview=(query_text or "")[:500],
            recommended_mode=recommended,
            selected_mode=selected_mode,
            reason_summary=recommendation["reason_summary"],
            expected_latency_band=recommendation["expected_latency_band"],
            expected_cost_band=recommendation["expected_cost_band"],
            override_applied=override_applied,
            created_at=now,
        )
        session.add(event)
        await session.commit()

    return {
        "profile": profile,
        "recommended_mode": recommended,
        "selected_mode": selected_mode,
        "reason_summary": recommendation["reason_summary"],
        "expected_latency_band": recommendation["expected_latency_band"],
        "expected_cost_band": recommendation["expected_cost_band"],
        "override_applied": override_applied,
        "allowed_modes": allowed,
    }
