"""
MCP-first transport wrappers for external HTTP tool calls.

When MCP is enabled, outbound HTTP requests are routed through the configured
MCP server tool endpoints. If MCP is unavailable and MCP_FAIL_OPEN is true,
calls fall back to direct HTTP requests.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import requests
from loguru import logger

from config import settings


@dataclass
class HTTPResult:
    status_code: int
    text: str
    json_data: Any = None
    headers: Optional[dict[str, str]] = None

    @property
    def ok(self) -> bool:
        return 200 <= int(self.status_code) < 300


def _safe_json_from_response(response: requests.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return None


def _is_mcp_enabled() -> bool:
    return bool(settings.MCP_ENABLED and settings.MCP_SERVER_URL)


def _fallback_enabled(allow_fallback: Optional[bool]) -> bool:
    if allow_fallback is None:
        return bool(settings.MCP_FAIL_OPEN)
    return bool(allow_fallback)


def _mcp_endpoint() -> str:
    base = (settings.MCP_SERVER_URL or "").rstrip("/")
    return f"{base}/call"


def _mcp_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.MCP_API_KEY:
        headers["Authorization"] = f"Bearer {settings.MCP_API_KEY}"
    return headers


def _normalize_mcp_http_result(raw: Any) -> HTTPResult:
    """
    Normalize MCP response variants into HTTPResult.

    Accepted shapes:
    - {"status_code": 200, "body": "...", "json": {...}, "headers": {...}}
    - {"status": 200, "text": "...", "data": {...}}
    - {"response": {...same as above...}}
    """
    payload = raw
    if isinstance(payload, dict) and isinstance(payload.get("response"), dict):
        payload = payload["response"]

    if not isinstance(payload, dict):
        return HTTPResult(status_code=200, text=str(payload), json_data=None, headers={})

    status_code = int(payload.get("status_code", payload.get("status", 200)))
    raw_headers = payload.get("headers")
    headers: dict[str, str] = {}
    if isinstance(raw_headers, dict):
        headers = {str(k): str(v) for k, v in raw_headers.items()}
    text = payload.get("body", payload.get("text", ""))

    json_data = payload.get("json")
    if json_data is None:
        json_data = payload.get("data")

    if not isinstance(text, str):
        text = str(text)

    return HTTPResult(
        status_code=status_code,
        text=text,
        json_data=json_data,
        headers=headers,
    )


def mcp_call_tool(tool_name: str, arguments: dict[str, Any], timeout_seconds: Optional[int] = None) -> Any:
    """Call an MCP tool using a generic HTTP MCP gateway contract."""
    if not _is_mcp_enabled():
        raise RuntimeError("MCP is not enabled or MCP_SERVER_URL is missing")

    timeout = int(timeout_seconds or settings.MCP_TIMEOUT_SECONDS)
    payload = {
        "tool": tool_name,
        "arguments": arguments,
    }

    response = requests.post(
        _mcp_endpoint(),
        headers=_mcp_headers(),
        json=payload,
        timeout=timeout,
    )

    if not response.ok:
        raise RuntimeError(
            f"MCP tool call failed ({response.status_code}): {(response.text or '')[:400]}"
        )

    body = _safe_json_from_response(response)
    if isinstance(body, dict):
        if body.get("ok") is False:
            raise RuntimeError(str(body.get("error", "MCP tool call returned ok=false")))
        if "result" in body:
            return body["result"]
    return body if body is not None else response.text


def _handle_mcp_error(
    exc: Exception,
    op_name: str,
    allow_fallback: Optional[bool] = None,
    require_mcp: bool = False,
) -> None:
    if require_mcp:
        raise RuntimeError(f"MCP {op_name} failed while MCP is required: {exc}") from exc

    if _fallback_enabled(allow_fallback):
        logger.warning(f"MCP {op_name} failed, falling back to direct HTTP: {exc}")
        return
    raise RuntimeError(f"MCP {op_name} failed and fail-open is disabled: {exc}") from exc


def http_get(
    url: str,
    headers: Optional[dict[str, str]] = None,
    params: Optional[dict[str, Any]] = None,
    timeout_seconds: int = 20,
    allow_fallback: Optional[bool] = None,
    require_mcp: bool = False,
) -> HTTPResult:
    if _is_mcp_enabled():
        try:
            raw = mcp_call_tool(
                settings.MCP_HTTP_GET_TOOL,
                {
                    "url": url,
                    "headers": headers or {},
                    "params": params or {},
                    "timeoutSeconds": int(timeout_seconds),
                },
                timeout_seconds=timeout_seconds,
            )
            return _normalize_mcp_http_result(raw)
        except Exception as exc:
            _handle_mcp_error(exc, "http_get", allow_fallback=allow_fallback, require_mcp=require_mcp)
    elif require_mcp:
        raise RuntimeError("MCP http_get is required but MCP is not enabled")

    response = requests.get(url, headers=headers, params=params, timeout=timeout_seconds)
    return HTTPResult(
        status_code=response.status_code,
        text=response.text,
        json_data=_safe_json_from_response(response),
        headers={str(k): str(v) for k, v in response.headers.items()},
    )


def http_get_json(
    url: str,
    headers: Optional[dict[str, str]] = None,
    params: Optional[dict[str, Any]] = None,
    timeout_seconds: int = 20,
    allow_fallback: Optional[bool] = None,
    require_mcp: bool = False,
) -> HTTPResult:
    result = http_get(
        url,
        headers=headers,
        params=params,
        timeout_seconds=timeout_seconds,
        allow_fallback=allow_fallback,
        require_mcp=require_mcp,
    )
    if result.json_data is None and result.text:
        try:
            import json

            result.json_data = json.loads(result.text)
        except Exception:
            pass
    return result


def http_post_json(
    url: str,
    payload: dict[str, Any],
    headers: Optional[dict[str, str]] = None,
    timeout_seconds: int = 20,
    allow_fallback: Optional[bool] = None,
    require_mcp: bool = False,
) -> HTTPResult:
    merged_headers = {"Content-Type": "application/json"}
    if headers:
        merged_headers.update(headers)

    if _is_mcp_enabled():
        try:
            raw = mcp_call_tool(
                settings.MCP_HTTP_POST_TOOL,
                {
                    "url": url,
                    "headers": merged_headers,
                    "json": payload,
                    "timeoutSeconds": int(timeout_seconds),
                },
                timeout_seconds=timeout_seconds,
            )
            return _normalize_mcp_http_result(raw)
        except Exception as exc:
            _handle_mcp_error(
                exc,
                "http_post_json",
                allow_fallback=allow_fallback,
                require_mcp=require_mcp,
            )
    elif require_mcp:
        raise RuntimeError("MCP http_post_json is required but MCP is not enabled")

    response = requests.post(
        url,
        headers=merged_headers,
        json=payload,
        timeout=timeout_seconds,
    )
    return HTTPResult(
        status_code=response.status_code,
        text=response.text,
        json_data=_safe_json_from_response(response),
        headers={str(k): str(v) for k, v in response.headers.items()},
    )
