"""Auto-provisioning for tenant workspaces on first use.

The actual Supabase production schema differs from the ORM bootstrap models:
- `workspaces.id` is the UUID PK (FK target for `llm_provider_configs.workspace_id`)
- `workspaces.organization_id` is NOT NULL
- `organizations` has no `tenant_id` column

So this provisioner accepts an `organization_id` from the caller (which has already
resolved it via the same lookup path used for `llm_provider_configs.organization_id`)
and only inserts a workspace row keyed on the FK-target column.
"""

from datetime import datetime
from typing import Any, Optional

from loguru import logger
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession


async def _table_columns(session: AsyncSession, table: str) -> dict[str, dict]:
    try:
        conn = await session.connection()
        cols = await conn.run_sync(lambda c: inspect(c).get_columns(table))
        out: dict[str, dict] = {}
        for col in cols:
            name = str(col.get("name", "")).lower()
            col_type = col.get("type")
            type_name = col_type.__class__.__name__.lower() if col_type is not None else ""
            out[name] = {
                "is_uuid": "uuid" in type_name,
                "nullable": bool(col.get("nullable", True)),
                "default": col.get("default"),
            }
        return out
    except Exception as exc:
        logger.debug("Column introspection failed for {}: {}", table, exc)
        return {}


async def _resolve_fk_target_column(
    session: AsyncSession,
    source_table: str,
    source_column: str,
    target_table: str,
) -> Optional[str]:
    try:
        async with session.begin_nested():
            stmt = text(
                """
                SELECT ccu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON kcu.constraint_name = tc.constraint_name
                   AND kcu.table_schema   = tc.table_schema
                JOIN information_schema.constraint_column_usage ccu
                    ON ccu.constraint_name = tc.constraint_name
                   AND ccu.table_schema   = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_name      = :src_table
                  AND kcu.column_name    = :src_column
                  AND ccu.table_name     = :tgt_table
                LIMIT 1
                """
            )
            row = (
                await session.execute(
                    stmt,
                    {
                        "src_table": source_table,
                        "src_column": source_column,
                        "tgt_table": target_table,
                    },
                )
            ).scalar_one_or_none()
            return str(row) if row else None
    except Exception:
        return None


async def _fallback_organization_id(session: AsyncSession) -> Optional[str]:
    """Best-effort: pick any organization_id when the caller didn't supply one."""
    try:
        async with session.begin_nested():
            row = (
                await session.execute(
                    text("SELECT CAST(id AS TEXT) FROM organizations LIMIT 1")
                )
            ).scalar_one_or_none()
            return str(row) if row else None
    except Exception:
        return None


async def ensure_workspace_provisioned(
    session: AsyncSession,
    tenant_id: str,
    workspace_id: str,
    organization_id: Optional[str] = None,
    display_name: Optional[str] = None,
) -> bool:
    """
    Ensure a workspace row exists with the FK-target column set to `workspace_id`.

    Idempotent. Caller should pass `organization_id` when known so the row is
    linked to the correct organization (workspaces.organization_id is NOT NULL
    in the production schema).
    """
    now = datetime.utcnow()
    ws_name = display_name or "Default Workspace"

    cols = await _table_columns(session, "workspaces")
    if not cols:
        logger.warning("workspaces table not readable; skipping workspace provisioning")
        return False

    # Find the column that the llm_provider_configs.workspace_id FK references.
    fk_target = await _resolve_fk_target_column(
        session, "llm_provider_configs", "workspace_id", "workspaces"
    )
    target_col = (fk_target or "id").lower()
    if target_col not in cols:
        target_col = "id" if "id" in cols else "workspace_id"

    # Existence check by FK target.
    try:
        async with session.begin_nested():
            exists = (
                await session.execute(
                    text(
                        f"SELECT 1 FROM workspaces WHERE CAST({target_col} AS TEXT) = :wid LIMIT 1"
                    ),
                    {"wid": str(workspace_id)},
                )
            ).scalar_one_or_none()
    except Exception as exc:
        logger.warning("Could not query workspaces existence: {}", exc)
        return False

    if exists is not None:
        return False

    # workspaces.organization_id is NOT NULL — fetch a fallback if caller didn't pass one.
    if "organization_id" in cols and not organization_id:
        organization_id = await _fallback_organization_id(session)
        if not organization_id:
            logger.warning(
                "No organization available to attach workspace {}; skipping provisioning",
                workspace_id,
            )
            return False

    # Build a dynamic INSERT: only include columns that exist + values we can supply.
    insert_cols: list[str] = []
    insert_vals: list[str] = []
    params: dict[str, Any] = {}

    target_is_uuid = cols.get(target_col, {}).get("is_uuid", False)
    insert_cols.append(target_col)
    insert_vals.append("CAST(:target_value AS UUID)" if target_is_uuid else ":target_value")
    params["target_value"] = str(workspace_id)

    if target_col != "workspace_id" and "workspace_id" in cols:
        wid_uuid = cols["workspace_id"]["is_uuid"]
        insert_cols.append("workspace_id")
        insert_vals.append("CAST(:workspace_id AS UUID)" if wid_uuid else ":workspace_id")
        params["workspace_id"] = str(workspace_id)

    if target_col != "workspace_key" and "workspace_key" in cols:
        insert_cols.append("workspace_key")
        insert_vals.append(":workspace_key")
        params["workspace_key"] = str(workspace_id)

    if "slug" in cols:
        insert_cols.append("slug")
        insert_vals.append(":slug")
        params["slug"] = str(workspace_id)

    if "organization_id" in cols and organization_id:
        oid_uuid = cols["organization_id"]["is_uuid"]
        insert_cols.append("organization_id")
        insert_vals.append("CAST(:organization_id AS UUID)" if oid_uuid else ":organization_id")
        params["organization_id"] = str(organization_id)

    if "tenant_id" in cols:
        tid_uuid = cols["tenant_id"]["is_uuid"]
        insert_cols.append("tenant_id")
        insert_vals.append("CAST(:tenant_id AS UUID)" if tid_uuid else ":tenant_id")
        params["tenant_id"] = str(tenant_id)

    if "name" in cols:
        insert_cols.append("name")
        insert_vals.append(":name")
        params["name"] = ws_name

    if "status" in cols:
        insert_cols.append("status")
        insert_vals.append(":status")
        params["status"] = "active"

    if "created_at" in cols:
        insert_cols.append("created_at")
        insert_vals.append(":created_at")
        params["created_at"] = now

    if "updated_at" in cols:
        insert_cols.append("updated_at")
        insert_vals.append(":updated_at")
        params["updated_at"] = now

    sql = (
        f"INSERT INTO workspaces ({', '.join(insert_cols)}) "
        f"VALUES ({', '.join(insert_vals)}) "
        f"ON CONFLICT DO NOTHING"
    )

    try:
        async with session.begin_nested():
            await session.execute(text(sql), params)
        logger.info(
            "Auto-provisioned workspace {}={} (org={}) for tenant {}",
            target_col,
            workspace_id,
            organization_id,
            tenant_id,
        )
        return True
    except Exception as exc:
        logger.warning(
            "Could not ensure workspace {} for tenant {}: {}", workspace_id, tenant_id, exc
        )
        return False
