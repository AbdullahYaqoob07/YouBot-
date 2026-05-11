from __future__ import annotations

import pytest

from config import settings
from utils import mcp_transport


class _FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "", json_data=None, headers=None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data
        self.headers = headers or {}

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


def test_http_get_json_direct_when_mcp_disabled(monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", False)

    def fake_get(url, headers=None, params=None, timeout=20):
        assert url == "https://example.com/models"
        return _FakeResponse(
            status_code=200,
            text='{"data": [{"id": "m1"}]}',
            json_data={"data": [{"id": "m1"}]},
            headers={"content-type": "application/json"},
        )

    monkeypatch.setattr(mcp_transport.requests, "get", fake_get)

    result = mcp_transport.http_get_json("https://example.com/models", timeout_seconds=10)
    assert result.status_code == 200
    assert result.ok is True
    assert result.json_data["data"][0]["id"] == "m1"


def test_http_get_json_via_mcp_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_SERVER_URL", "http://127.0.0.1:8787")
    monkeypatch.setattr(settings, "MCP_API_KEY", None)
    monkeypatch.setattr(settings, "MCP_FAIL_OPEN", True)
    monkeypatch.setattr(settings, "MCP_HTTP_GET_TOOL", "http.get")

    def fake_post(url, headers=None, json=None, timeout=15):
        assert url == "http://127.0.0.1:8787/call"
        assert json["tool"] == "http.get"
        return _FakeResponse(
            status_code=200,
            text='{"ok": true}',
            json_data={
                "ok": True,
                "result": {
                    "status_code": 200,
                    "json": {"data": [{"id": "m2"}]},
                    "body": "{\"data\":[{\"id\":\"m2\"}]}",
                    "headers": {"content-type": "application/json"},
                },
            },
        )

    def fail_get(*args, **kwargs):
        raise AssertionError("Direct GET should not be used when MCP succeeds")

    monkeypatch.setattr(mcp_transport.requests, "post", fake_post)
    monkeypatch.setattr(mcp_transport.requests, "get", fail_get)

    result = mcp_transport.http_get_json("https://example.com/models", timeout_seconds=8)
    assert result.status_code == 200
    assert result.json_data["data"][0]["id"] == "m2"


def test_http_get_fallback_when_mcp_fail_open(monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_SERVER_URL", "http://127.0.0.1:8787")
    monkeypatch.setattr(settings, "MCP_FAIL_OPEN", True)

    def broken_post(*args, **kwargs):
        raise RuntimeError("mcp unavailable")

    def fake_get(url, headers=None, params=None, timeout=20):
        return _FakeResponse(status_code=200, text="ok", json_data=None, headers={})

    monkeypatch.setattr(mcp_transport.requests, "post", broken_post)
    monkeypatch.setattr(mcp_transport.requests, "get", fake_get)

    result = mcp_transport.http_get("https://example.com/health", timeout_seconds=5)
    assert result.status_code == 200
    assert result.text == "ok"


def test_http_get_raises_when_mcp_fail_open_disabled(monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_SERVER_URL", "http://127.0.0.1:8787")
    monkeypatch.setattr(settings, "MCP_FAIL_OPEN", False)

    def broken_post(*args, **kwargs):
        raise RuntimeError("mcp unavailable")

    monkeypatch.setattr(mcp_transport.requests, "post", broken_post)

    with pytest.raises(RuntimeError):
        mcp_transport.http_get("https://example.com/health", timeout_seconds=5)
