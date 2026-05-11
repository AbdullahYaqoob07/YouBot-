"""Business readiness audit for YouBot SaaS integration.

Runs endpoint checks against the live backend and writes a JSON report.
Use this to validate actual implementation before production integration.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests


@dataclass
class CheckResult:
    name: str
    method: str
    endpoint: str
    required: bool
    status_code: int
    ok: bool
    duration_ms: int
    summary: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run YouBot business readiness checks")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--tenant-id", default="public", help="Tenant ID header")
    parser.add_argument("--workspace-id", default="default", help="Workspace ID header")
    parser.add_argument("--admin-key", default="", help="Admin key for /admin and /tenant-analytics")
    parser.add_argument("--api-key", default="", help="Platform API key for /webhook/ai-agent")
    parser.add_argument("--client-key", default="", help="Client API key for /v1/chat")
    parser.add_argument("--timeout-ms", type=int, default=12000, help="Request timeout per check")
    parser.add_argument(
        "--output",
        default="tools/business_readiness_report.json",
        help="Path to write JSON report",
    )
    return parser.parse_args()


def build_headers(tenant_id: str, workspace_id: str, key_name: str | None = None, key_value: str = "") -> dict[str, str]:
    headers = {
        "X-Tenant-Id": tenant_id,
        "X-Workspace-Id": workspace_id,
    }
    if key_name and key_value:
        headers[key_name] = key_value
    return headers


def summarize_payload(payload: Any) -> str:
    if isinstance(payload, dict):
        if "detail" in payload:
            return str(payload["detail"])[:140]
        if "status" in payload:
            return f"status={payload.get('status')}"
        keys = list(payload.keys())
        return f"keys={keys[:5]}"
    text = str(payload)
    return text[:140] if len(text) > 140 else text


def run_request(
    base_url: str,
    method: str,
    endpoint: str,
    headers: dict[str, str],
    timeout_ms: int,
    payload: dict[str, Any] | None = None,
) -> tuple[int, bool, int, str]:
    url = f"{base_url.rstrip('/')}{endpoint}"
    started = time.perf_counter()
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=timeout_ms / 1000)
        else:
            send_headers = dict(headers)
            send_headers["Content-Type"] = "application/json"
            response = requests.post(url, headers=send_headers, json=payload, timeout=timeout_ms / 1000)

        elapsed_ms = int((time.perf_counter() - started) * 1000)

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            body = response.json()
        else:
            body = {"raw": response.text[:500]}

        return response.status_code, response.ok, elapsed_ms, summarize_payload(body)
    except Exception as exc:  # pragma: no cover - runtime utility
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return 0, False, elapsed_ms, f"error={type(exc).__name__}: {exc}"


def main() -> int:
    args = parse_args()

    base_url = args.base_url.rstrip("/")
    timeout_ms = max(1000, args.timeout_ms)

    checks: list[tuple[str, str, str, bool, dict[str, str], dict[str, Any] | None]] = []

    checks.append((
        "health",
        "GET",
        "/health",
        True,
        {},
        None,
    ))

    if args.admin_key:
        admin_headers = build_headers(args.tenant_id, args.workspace_id, "X-Admin-Key", args.admin_key)
        checks.extend(
            [
                (
                    "retrieval_profile",
                    "GET",
                    "/admin/retrieval/profile",
                    True,
                    admin_headers,
                    None,
                ),
                (
                    "supervision_conversations",
                    "GET",
                    "/admin/supervision/conversations",
                    True,
                    admin_headers,
                    None,
                ),
                (
                    "analytics_overview",
                    "GET",
                    "/tenant-analytics/overview?days=30",
                    True,
                    admin_headers,
                    None,
                ),
                (
                    "governance_usage",
                    "GET",
                    "/tenant-analytics/governance/usage?days=30",
                    True,
                    admin_headers,
                    None,
                ),
            ]
        )

    if args.api_key:
        webhook_headers = build_headers(args.tenant_id, args.workspace_id, "X-API-Key", args.api_key)
        checks.append((
            "webhook_chat",
            "POST",
            "/webhook/ai-agent",
            True,
            webhook_headers,
            {
                "message": "Business readiness check: test webhook path",
                "userId": "biz_check_user",
                "channel": "web",
                "tenantId": args.tenant_id,
                "workspaceId": args.workspace_id,
            },
        ))

    if args.client_key:
        client_headers = build_headers(args.tenant_id, args.workspace_id, "X-API-Key", args.client_key)
        checks.append((
            "client_chat",
            "POST",
            "/v1/chat",
            True,
            client_headers,
            {
                "message": "Business readiness check: test client path",
                "userId": "biz_check_user",
                "channel": "web",
            },
        ))

    results: list[CheckResult] = []

    for name, method, endpoint, required, headers, payload in checks:
        status_code, ok, duration_ms, summary = run_request(
            base_url=base_url,
            method=method,
            endpoint=endpoint,
            headers=headers,
            timeout_ms=timeout_ms,
            payload=payload,
        )
        results.append(
            CheckResult(
                name=name,
                method=method,
                endpoint=endpoint,
                required=required,
                status_code=status_code,
                ok=ok,
                duration_ms=duration_ms,
                summary=summary,
            )
        )

    required_checks = [r for r in results if r.required]
    passed_required = [r for r in required_checks if r.ok]
    failed_required = [r for r in required_checks if not r.ok]

    overall_status = "ready" if not failed_required else "not_ready"

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url": base_url,
        "tenant_id": args.tenant_id,
        "workspace_id": args.workspace_id,
        "overall_status": overall_status,
        "counts": {
            "total": len(results),
            "passed": len([r for r in results if r.ok]),
            "failed": len([r for r in results if not r.ok]),
            "required_total": len(required_checks),
            "required_passed": len(passed_required),
            "required_failed": len(failed_required),
        },
        "checks": [asdict(r) for r in results],
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== YouBot Business Readiness Audit ===")
    print(f"Base URL: {base_url}")
    print(f"Tenant/Workspace: {args.tenant_id}/{args.workspace_id}")
    print(f"Overall status: {overall_status}")
    print(
        "Required checks: "
        f"{len(passed_required)}/{len(required_checks)} passed"
    )
    print(f"Report written to: {output_path}")

    for row in results:
        state = "PASS" if row.ok else "FAIL"
        print(
            f"[{state}] {row.method} {row.endpoint} "
            f"({row.duration_ms}ms, {row.status_code}) -> {row.summary}"
        )

    return 0 if overall_status == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
