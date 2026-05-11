import pytest
from fastapi import HTTPException
import asyncio

from tenant_context import validate_context_identifier, resolve_tenant_context
from config import settings


def test_validate_context_identifier_accepts_valid_value():
    value = validate_context_identifier("tenant-main_01", "tenant_id")
    assert value == "tenant-main_01"


def test_validate_context_identifier_rejects_invalid_value():
    with pytest.raises(ValueError):
        validate_context_identifier("invalid value with spaces", "tenant_id")


def test_resolve_tenant_context_uses_defaults_when_optional(monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_TENANT_CONTEXT", False)
    monkeypatch.setattr(settings, "DEFAULT_TENANT_ID", "public")
    monkeypatch.setattr(settings, "DEFAULT_WORKSPACE_ID", "default")

    context = asyncio.run(resolve_tenant_context(None, None))

    assert context.tenant_id == "public"
    assert context.workspace_id == "default"


def test_resolve_tenant_context_accepts_headers(monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_TENANT_CONTEXT", False)

    context = asyncio.run(resolve_tenant_context("tenant-acme", "workspace-support"))

    assert context.tenant_id == "tenant-acme"
    assert context.workspace_id == "workspace-support"


def test_resolve_tenant_context_requires_headers_in_strict_mode(monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_TENANT_CONTEXT", True)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(resolve_tenant_context(None, None))

    assert exc.value.status_code == 400
    assert "Missing tenant context headers" in exc.value.detail
