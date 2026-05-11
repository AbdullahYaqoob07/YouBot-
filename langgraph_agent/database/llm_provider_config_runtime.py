"""Workspace LLM provider configuration operations."""

import uuid
from datetime import datetime
from typing import Any, Optional

from loguru import logger
from sqlalchemy import String as SAString, and_, cast, delete, inspect, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import LLMProviderConfig, get_async_session
from database.workspace_provisioning import ensure_workspace_provisioned
from llm.factory import LLMRuntimeConfig, normalize_provider
from utils.secret_crypto import decrypt_secret, encrypt_secret, mask_secret

_TENANT_SCOPE_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_DNS,
    "langgraph_agent.llm_provider_configs.tenant_id",
)
_WORKSPACE_SCOPE_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_DNS,
    "langgraph_agent.llm_provider_configs.workspace_id",
)


def _canonical_uuid(value: str, namespace: uuid.UUID) -> str:
    value_str = str(value)
    try:
        return str(uuid.UUID(value_str))
    except (ValueError, TypeError, AttributeError):
        return str(uuid.uuid5(namespace, value_str))


def _scope_variants(tenant_id: str, workspace_id: str) -> list[tuple[str, str]]:
    raw_variant = (str(tenant_id), str(workspace_id))
    uuid_variant = (
        _canonical_uuid(tenant_id, _TENANT_SCOPE_NAMESPACE),
        _canonical_uuid(workspace_id, _WORKSPACE_SCOPE_NAMESPACE),
    )
    if uuid_variant == raw_variant:
        return [raw_variant]
    return [raw_variant, uuid_variant]


def _scope_clause(tenant_id: str, workspace_id: str):
    predicates = []
    for resolved_tenant, resolved_workspace in _scope_variants(tenant_id, workspace_id):
        predicates.append(
            and_(
                cast(LLMProviderConfig.tenant_id, SAString) == str(resolved_tenant),
                cast(LLMProviderConfig.workspace_id, SAString) == str(resolved_workspace),
            )
        )
    return predicates[0] if len(predicates) == 1 else or_(*predicates)


def _is_uuid_mismatch(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "uuid" in msg
        and (
            "is of type uuid but expression is of type character varying" in msg
            or "invalid input syntax for type uuid" in msg
            or "cannot cast type character varying to uuid" in msg
        )
    )


async def _table_uuid_flags(session: AsyncSession, table_name: str) -> dict[str, bool]:
    conn = await session.connection()
    columns = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_columns(table_name))
    flags: dict[str, bool] = {}
    for column in columns:
        name = str(column.get("name", "")).lower()
        col_type = column.get("type")
        type_name = col_type.__class__.__name__.lower() if col_type is not None else ""
        flags[name] = "uuid" in type_name
    return flags


async def _resolve_workspace_organization_id(
    session: AsyncSession,
    workspace_value: str,
) -> Optional[str]:
    try:
        async with session.begin_nested():
            workspace_columns = await _table_uuid_flags(session, "workspaces")
    except Exception as exc:
        logger.warning("Could not introspect workspaces table for organization lookup: {}", exc)
        return None

    if "organization_id" not in workspace_columns:
        return None

    value = str(workspace_value)
    lookups = []
    if "id" in workspace_columns:
        lookups.append(
            text(
                """
                SELECT CAST(organization_id AS TEXT)
                FROM workspaces
                WHERE CAST(id AS TEXT) = :workspace_value
                LIMIT 1
                """
            )
        )
    if "workspace_key" in workspace_columns:
        lookups.append(
            text(
                """
                SELECT CAST(organization_id AS TEXT)
                FROM workspaces
                WHERE workspace_key = :workspace_value
                LIMIT 1
                """
            )
        )
    if "workspace_id" in workspace_columns:
        lookups.append(
            text(
                """
                SELECT CAST(organization_id AS TEXT)
                FROM workspaces
                WHERE CAST(workspace_id AS TEXT) = :workspace_value
                LIMIT 1
                """
            )
        )

    for stmt in lookups:
        try:
            async with session.begin_nested():
                resolved = (await session.execute(stmt, {"workspace_value": value})).scalar_one_or_none()
        except Exception:
            continue
        if resolved:
            return str(resolved)

    return None


async def _scope_uuid_flags(session: AsyncSession) -> tuple[bool, bool, bool, bool]:
    try:
        async with session.begin_nested():
            llm_columns = await _table_uuid_flags(session, "llm_provider_configs")
        return (
            bool(llm_columns.get("tenant_id", False)),
            bool(llm_columns.get("workspace_id", False)),
            "organization_id" in llm_columns,
            bool(llm_columns.get("organization_id", False)),
        )
    except Exception as exc:
        logger.warning(
            "Could not introspect llm_provider_configs scope column types (defaulting to text): {}",
            exc,
        )
        return False, False, False, False


def _coerce_scope(raw_value: str, as_uuid: bool, namespace: uuid.UUID) -> str:
    return _canonical_uuid(raw_value, namespace) if as_uuid else str(raw_value)


def _insert_stmt(
    tenant_uuid: bool,
    workspace_uuid: bool,
    include_organization: bool = False,
    organization_uuid: bool = False,
):
    # Use ANSI CAST(...) syntax instead of ::uuid shorthand.
    # psycopg misparses `:param_name::type` as two colon-prefixed tokens
    # which causes "syntax error at or near ':'" at runtime.
    tenant_expr = "CAST(:tenant_id AS UUID)" if tenant_uuid else ":tenant_id"
    workspace_expr = "CAST(:workspace_id AS UUID)" if workspace_uuid else ":workspace_id"
    organization_expr = "CAST(:organization_id AS UUID)" if organization_uuid else ":organization_id"

    columns = [
        "tenant_id",
        "workspace_id",
        "provider",
        "model_name",
        "encrypted_api_key",
        "is_active",
        "created_by",
        "created_at",
        "updated_at",
    ]
    values = [
        tenant_expr,
        workspace_expr,
        ":provider",
        ":model_name",
        ":encrypted_api_key",
        ":is_active",
        ":created_by",
        ":created_at",
        ":updated_at",
    ]

    if include_organization:
        columns.insert(1, "organization_id")
        values.insert(1, organization_expr)

    columns_sql = ",\n            ".join(columns)
    values_sql = ",\n            ".join(values)

    return text(
        f"""
        INSERT INTO llm_provider_configs (
            {columns_sql}
        ) VALUES (
            {values_sql}
        )
        RETURNING provider, model_name, updated_at
        """
    )


def _delete_stmt(tenant_id: str, workspace_id: str):
    return (
        delete(LLMProviderConfig)
        .where(_scope_clause(tenant_id, workspace_id))
        .returning(
            LLMProviderConfig.provider,
            LLMProviderConfig.model_name,
            LLMProviderConfig.updated_at,
            LLMProviderConfig.created_at,
        )
    )


def _update_stmt(
    tenant_id: str,
    workspace_id: str,
    provider: str,
    model_name: str,
    encrypted_api_key: str,
    updated_at: datetime,
    actor: Optional[str] = None,
):
    values = {
        "provider": provider,
        "model_name": model_name,
        "encrypted_api_key": encrypted_api_key,
        "is_active": True,
        "updated_at": updated_at,
    }
    if actor is not None:
        values["created_by"] = actor

    return (
        update(LLMProviderConfig)
        .where(_scope_clause(tenant_id, workspace_id))
        .values(**values)
        .returning(
            LLMProviderConfig.provider,
            LLMProviderConfig.model_name,
            LLMProviderConfig.updated_at,
            LLMProviderConfig.created_at,
        )
    )


def _as_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def _default_model_for_provider(provider: str) -> str:
    normalized = normalize_provider(provider)
    if normalized == "groq":
        return settings.GROQ_MODEL
    if normalized == "openai":
        return settings.OPENAI_MODEL
    if normalized == "anthropic":
        return settings.ANTHROPIC_MODEL
    if normalized == "gemini":
        return settings.GEMINI_MODEL
    if settings.DEFAULT_LLM_MODEL:
        return settings.DEFAULT_LLM_MODEL
    raise RuntimeError(
        f"No default model configured for provider '{normalized}'. "
        "Set DEFAULT_LLM_MODEL or save a workspace-specific model first."
    )


def _default_api_key_for_provider(provider: str) -> Optional[str]:
    normalized = normalize_provider(provider)
    if normalized == "groq":
        return settings.GROQ_API_KEY
    if normalized == "openai":
        return settings.OPENAI_API_KEY
    if normalized == "anthropic":
        return settings.ANTHROPIC_API_KEY
    if normalized == "gemini":
        return settings.GEMINI_API_KEY
    return None


async def upsert_workspace_llm_config(
    tenant_id: str,
    workspace_id: str,
    provider: str,
    model_name: str,
    api_key: str,
    actor: Optional[str] = None,
) -> dict:
    normalized_provider = normalize_provider(provider)
    encrypted_key = encrypt_secret(api_key)
    now = datetime.utcnow()

    async with get_async_session() as session:
        tenant_is_uuid, workspace_is_uuid, has_organization_id, organization_is_uuid = await _scope_uuid_flags(
            session
        )
        persisted_row: Optional[dict[str, Any]] = None

        update_result = await session.execute(
            _update_stmt(
                tenant_id,
                workspace_id,
                normalized_provider,
                model_name,
                encrypted_key,
                now,
                actor,
            )
        )
        updated_row = update_result.mappings().first()
        if updated_row is not None:
            persisted_row = dict(updated_row)
            await session.commit()
        else:
            insert_tenant_id = _coerce_scope(tenant_id, tenant_is_uuid, _TENANT_SCOPE_NAMESPACE)
            insert_workspace_id = _coerce_scope(workspace_id, workspace_is_uuid, _WORKSPACE_SCOPE_NAMESPACE)

            insert_values = {
                "tenant_id": insert_tenant_id,
                "workspace_id": insert_workspace_id,
                "provider": normalized_provider,
                "model_name": model_name,
                "encrypted_api_key": encrypted_key,
                "is_active": True,
                "created_by": actor,
                "created_at": now,
                "updated_at": now,
            }

            resolved_organization_id: Optional[str] = None
            include_organization = False
            if has_organization_id:
                resolved_organization_id = await _resolve_workspace_organization_id(session, insert_workspace_id)
                if not resolved_organization_id and str(workspace_id) != str(insert_workspace_id):
                    resolved_organization_id = await _resolve_workspace_organization_id(session, str(workspace_id))

                if not resolved_organization_id:
                    try:
                        async with session.begin_nested():
                            org_stmt = text("SELECT CAST(id AS TEXT) FROM organizations WHERE tenant_id = :tenant_id LIMIT 1")
                            org_id = (await session.execute(org_stmt, {"tenant_id": str(tenant_id)})).scalar_one_or_none()
                            if org_id:
                                resolved_organization_id = str(org_id)
                    except Exception:
                        pass

                if not resolved_organization_id:
                    try:
                        async with session.begin_nested():
                            org_stmt = text("SELECT CAST(id AS TEXT) FROM organizations WHERE slug = :tenant_id LIMIT 1")
                            org_id = (await session.execute(org_stmt, {"tenant_id": str(tenant_id)})).scalar_one_or_none()
                            if org_id:
                                resolved_organization_id = str(org_id)
                    except Exception:
                        pass

                if not resolved_organization_id:
                    try:
                        async with session.begin_nested():
                            org_stmt = text("SELECT CAST(id AS TEXT) FROM organizations LIMIT 1")
                            org_id = (await session.execute(org_stmt)).scalar_one_or_none()
                            if org_id:
                                resolved_organization_id = str(org_id)
                    except Exception:
                        pass

                if resolved_organization_id:
                    include_organization = True
                    insert_values["organization_id"] = _coerce_scope(
                        resolved_organization_id,
                        organization_is_uuid,
                        _TENANT_SCOPE_NAMESPACE,
                    )

            # Ensure workspace row exists before FK-constrained INSERT.
            # workspaces.organization_id is NOT NULL, so pass the resolved org id.
            await ensure_workspace_provisioned(
                session,
                tenant_id,
                insert_workspace_id,
                organization_id=resolved_organization_id,
            )

            inserted: Optional[dict[str, Any]] = None
            try:
                result = await session.execute(
                    _insert_stmt(
                        tenant_is_uuid,
                        workspace_is_uuid,
                        include_organization,
                        organization_is_uuid,
                    ),
                    insert_values,
                )
                mapping = result.mappings().first()
                inserted = dict(mapping) if mapping else None
                await session.commit()
            except Exception as exc:
                await session.rollback()
                if not _is_uuid_mismatch(exc):
                    raise

                msg = str(exc).lower()
                retry_tenant_uuid = tenant_is_uuid or "tenant_id" in msg
                retry_workspace_uuid = workspace_is_uuid or "workspace_id" in msg
                if retry_tenant_uuid == tenant_is_uuid and retry_workspace_uuid == workspace_is_uuid:
                    raise

                retry_values = dict(insert_values)
                retry_values["tenant_id"] = _coerce_scope(
                    tenant_id,
                    retry_tenant_uuid,
                    _TENANT_SCOPE_NAMESPACE,
                )
                retry_values["workspace_id"] = _coerce_scope(
                    workspace_id,
                    retry_workspace_uuid,
                    _WORKSPACE_SCOPE_NAMESPACE,
                )
                result = await session.execute(
                    _insert_stmt(
                        retry_tenant_uuid,
                        retry_workspace_uuid,
                        include_organization,
                        organization_is_uuid,
                    ),
                    retry_values,
                )
                mapping = result.mappings().first()
                inserted = dict(mapping) if mapping else None
                await session.commit()

            persisted_row = inserted

    persisted_provider = normalized_provider
    persisted_model = model_name
    persisted_updated_at = now
    if persisted_row:
        persisted_provider = str(persisted_row.get("provider", normalized_provider))
        persisted_model = str(persisted_row.get("model_name", model_name))
        persisted_updated_at = _as_datetime(persisted_row.get("updated_at")) or now

    return {
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "provider": persisted_provider,
        "model": persisted_model,
        "has_api_key": True,
        "masked_api_key": mask_secret(api_key),
        "updated_at": persisted_updated_at.isoformat() if persisted_updated_at else None,
    }


async def delete_workspace_llm_config(
    tenant_id: str,
    workspace_id: str,
) -> dict[str, Any]:
    async with get_async_session() as session:
        result = await session.execute(_delete_stmt(tenant_id, workspace_id))
        row = result.mappings().first()
        if row is None:
            raise ValueError("No workspace LLM configuration found")

        deleted_provider = str(row.get("provider") or "")
        deleted_model = str(row.get("model_name") or "")
        updated_at = _as_datetime(row.get("updated_at")) or _as_datetime(row.get("created_at"))

        await session.commit()

    return {
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "provider": deleted_provider,
        "model": deleted_model,
        "deleted": True,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


async def get_workspace_llm_config(tenant_id: str, workspace_id: str) -> Optional[dict]:
    try:
        async with get_async_session() as session:
            query = select(LLMProviderConfig).where(
                _scope_clause(tenant_id, workspace_id),
                LLMProviderConfig.is_active.is_(True),
            )
            row = (await session.execute(query)).scalar_one_or_none()
            if row is None:
                return None

            try:
                raw_key = decrypt_secret(str(row.encrypted_api_key))
                masked_key = mask_secret(raw_key)
            except Exception:
                masked_key = "***invalid***"

            updated_at = getattr(row, "updated_at", None)
            return {
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "provider": str(row.provider),
                "model": str(row.model_name),
                "has_api_key": True,
                "masked_api_key": masked_key,
                "created_by": str(row.created_by) if getattr(row, "created_by", None) else None,
                "updated_at": updated_at.isoformat() if updated_at else None,
            }
    except Exception as exc:
        logger.warning(
            "Workspace LLM config lookup failed for tenant {} workspace {}: {}",
            tenant_id,
            workspace_id,
            exc,
        )
        return None


async def get_workspace_llm_runtime_config(tenant_id: str, workspace_id: str) -> LLMRuntimeConfig:
    try:
        async with get_async_session() as session:
            query = select(LLMProviderConfig).where(
                _scope_clause(tenant_id, workspace_id),
                LLMProviderConfig.is_active.is_(True),
            )
            row = (await session.execute(query)).scalar_one_or_none()
            if row is not None:
                return LLMRuntimeConfig(
                    provider=normalize_provider(str(row.provider)),
                    model=str(row.model_name),
                    api_key=decrypt_secret(str(row.encrypted_api_key)),
                )
    except Exception as exc:
        logger.warning(
            "Workspace runtime LLM lookup failed for tenant {} workspace {}: {}",
            tenant_id,
            workspace_id,
            exc,
        )

    provider = normalize_provider(settings.DEFAULT_LLM_PROVIDER)
    model = settings.DEFAULT_LLM_MODEL or _default_model_for_provider(provider)
    api_key = _default_api_key_for_provider(provider)
    if not api_key:
        raise RuntimeError(f"No API key configured for default provider: {provider}")
    return LLMRuntimeConfig(provider=provider, model=model, api_key=api_key)