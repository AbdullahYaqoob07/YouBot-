"""
Apply Supabase schema and list created tables.

Usage:
  python tools/apply_supabase_schema.py
  python tools/apply_supabase_schema.py --schema supabase_comprehensive_schema.sql

Behavior:
1) Verifies REST connection using SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY.
2) Applies SQL via direct Postgres if SUPABASE_DB_URL is set.
3) Falls back to rpc('exec_sql') attempt if available.
4) Prints visible tables/endpoints so you can verify in Supabase.
"""

from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote_plus, urlparse

# Ensure project root is importable when script is executed directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from utils.mcp_transport import http_get_json, http_post_json


def _headers() -> dict[str, str]:
    key = settings.SUPABASE_SERVICE_ROLE_KEY
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not configured")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _verify_rest_connection() -> list[str]:
    if not settings.SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL is not configured")

    url = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/"
    response = http_get_json(url, headers=_headers(), timeout_seconds=20)
    if not response.ok:
        raise RuntimeError(
            f"Supabase REST root request failed ({response.status_code}): {(response.text or '')[:300]}"
        )

    # Root endpoint usually returns OpenAPI with paths.
    payload = response.json_data if isinstance(response.json_data, dict) else {}

    paths = payload.get("paths") if isinstance(payload, dict) else None
    if not isinstance(paths, dict):
        return []

    table_paths: list[str] = []
    for route in sorted(paths.keys()):
        if not route.startswith("/"):
            continue
        if route == "/":
            continue
        if route.startswith("/rpc/"):
            continue
        # ignore path params and nested generated docs
        if "{" in route or "/" in route[1:]:
            continue
        table_paths.append(route.lstrip("/"))

    return table_paths


def _resolve_direct_db_url() -> tuple[str | None, str]:
    """Resolve direct Postgres URL from full URL or component settings."""
    if settings.SUPABASE_DB_URL and settings.SUPABASE_DB_URL.strip():
        return settings.SUPABASE_DB_URL.strip(), "SUPABASE_DB_URL"

    host = (settings.SUPABASE_DB_HOST or "").strip()
    password = settings.SUPABASE_DB_PASSWORD or ""
    if host and password:
        user = settings.SUPABASE_DB_USER or "postgres"
        db_name = settings.SUPABASE_DB_NAME or "postgres"
        port = settings.SUPABASE_DB_PORT or 5432
        safe_password = quote_plus(password)
        return (
            f"postgresql://{user}:{safe_password}@{host}:{port}/{db_name}",
            "SUPABASE_DB_HOST/PORT/NAME/USER/PASSWORD",
        )

    if host and not password:
        return None, "SUPABASE_DB_PASSWORD is missing"
    return None, "SUPABASE_DB_URL is not configured"


def _diagnose_db_host(db_url: str) -> tuple[bool, str]:
    """Quick DNS check for the direct DB host to produce actionable diagnostics."""
    parsed = urlparse(db_url)
    host = parsed.hostname
    if not host:
        return False, "Could not parse host from direct Postgres URL"

    try:
        socket.getaddrinfo(host, None)
        return True, f"Resolved DB host: {host}"
    except OSError as exc:
        return (
            False,
            (
                f"Failed to resolve DB host '{host}': {exc}. "
                "Check DNS/network access or use the Supabase pooler host from your dashboard connection string."
            ),
        )


def _apply_with_postgres(sql_text: str, db_url: str) -> list[str]:

    try:
        import psycopg
    except Exception as exc:
        raise RuntimeError(
            "psycopg is required for direct Postgres schema apply. Install requirements first."
        ) from exc

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(cast(Any, sql_text))
        conn.commit()

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select table_name
                from information_schema.tables
                where table_schema = 'public'
                  and table_type = 'BASE TABLE'
                order by table_name;
                """
            )
            rows = cur.fetchall()

    return [r[0] for r in rows]


def _apply_with_rpc_exec_sql(sql_text: str) -> bool:
    """
    Optional fallback when a custom rpc function exec_sql exists in Supabase.
    """
    if not settings.SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL is not configured")

    url = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/rpc/exec_sql"
    response = http_post_json(
        url,
        payload={"query": sql_text},
        headers=_headers(),
        timeout_seconds=90,
    )
    if response.status_code in (404, 400):
        return False
    if not response.ok:
        raise RuntimeError(
            f"RPC exec_sql failed ({response.status_code}): {(response.text or '')[:300]}"
        )
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--schema",
        default="supabase_comprehensive_schema.sql",
        help="Schema SQL file path",
    )
    args = parser.parse_args()

    schema_path = Path(args.schema)
    if not schema_path.is_file():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    print("[1/4] Verifying Supabase REST connection...")
    visible_before = _verify_rest_connection()
    print("Connected to Supabase REST.")
    if visible_before:
        print("Visible REST table endpoints before apply:")
        for t in visible_before:
            print(f"  - {t}")
    else:
        print("No public table endpoints visible from REST root yet.")

    sql_text = schema_path.read_text(encoding="utf-8")

    applied = False
    tables: list[str] = []

    print("[2/4] Applying schema...")
    direct_db_url, direct_source = _resolve_direct_db_url()
    if direct_db_url:
        dns_ok, dns_message = _diagnose_db_host(direct_db_url)
        print(dns_message)
        if dns_ok:
            try:
                tables = _apply_with_postgres(sql_text, direct_db_url)
                applied = True
                print(f"Schema applied via direct Postgres connection ({direct_source}).")
            except Exception as exc:
                print(f"Direct Postgres apply failed: {exc}")
        else:
            print("Skipping direct Postgres apply because DNS check failed.")

    if not applied:
        if direct_db_url is None:
            print(f"Direct DB config unavailable: {direct_source}; trying rpc('exec_sql') fallback...")
        else:
            print("Trying rpc('exec_sql') fallback...")
        try:
            if _apply_with_rpc_exec_sql(sql_text):
                applied = True
                print("Schema applied via rpc('exec_sql').")
            else:
                print("rpc('exec_sql') is not available in this project.")
        except Exception as exc:
            print(f"rpc('exec_sql') failed: {exc}")

    print("[3/4] Re-checking REST visibility...")
    visible_after = _verify_rest_connection()
    if visible_after:
        print("Visible REST table endpoints after apply:")
        for t in visible_after:
            print(f"  - {t}")

    print("[4/4] Result summary")
    if applied and tables:
        print("Tables in public schema:")
        for t in tables:
            print(f"  - {t}")
    elif applied:
        print("Schema apply attempted successfully, but direct SQL table listing was unavailable.")
    else:
        print(
            "Schema was NOT applied automatically. Configure a reachable direct DB connection "
            "(SUPABASE_DB_URL or SUPABASE_DB_HOST/PORT/NAME/USER/PASSWORD), "
            "or run supabase_comprehensive_schema.sql in Supabase SQL Editor."
        )


if __name__ == "__main__":
    main()
