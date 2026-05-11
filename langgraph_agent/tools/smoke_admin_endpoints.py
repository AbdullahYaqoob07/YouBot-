"""Smoke-check admin retrieval + supervision endpoints without exposing secrets."""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests
from requests import RequestException


def load_admin_key(env_path: Path) -> str:
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("ADMIN_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("ADMIN_API_KEY not found in .env")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    admin_key = load_admin_key(root / ".env")

    base_url = "http://127.0.0.1:8000"
    headers = {
        "X-Admin-Key": admin_key,
        "X-Tenant-Id": "public",
        "X-Workspace-Id": "default",
        "Content-Type": "application/json",
    }

    checks: list[tuple[str, str, dict | None]] = [
        ("GET", "/admin/retrieval/profile", None),
        (
            "POST",
            "/admin/retrieval/profile",
            {
                "defaultMode": "rag",
                "allowedModes": ["rag", "page_index"],
                "pageWindowLimit": 4,
                "complianceCriticality": 0.5,
                "averageDocumentPages": 10,
                "queryComplexity": 0.5,
                "latencyBudgetMs": 2500,
                "costSensitivity": 0.5,
            },
        ),
        (
            "POST",
            "/admin/retrieval/recommend",
            {"query": "How do I renew residence permit?", "selectedModeOverride": None},
        ),
        ("GET", "/admin/supervision/conversations", None),
    ]

    for method, path, payload in checks:
        url = f"{base_url}{path}"
        started = time.perf_counter()
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=12)
            else:
                response = requests.post(url, headers=headers, json=payload, timeout=12)

            elapsed_ms = int((time.perf_counter() - started) * 1000)
            body_preview = response.text[:240].replace("\n", " ")
            print(f"{method} {path} -> {response.status_code} [{elapsed_ms}ms]")
            print(f"body: {body_preview}")
        except RequestException as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            print(f"{method} {path} -> ERROR [{elapsed_ms}ms]")
            print(f"error: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
