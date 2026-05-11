"""Run isolated admin endpoint smoke checks against a temporary local uvicorn process."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import requests


def load_admin_key(env_path: Path) -> str:
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("ADMIN_API_KEY="):
            return line.split("=", 1)[1].strip()
    return ""


def wait_for_server(base_url: str, timeout_seconds: int = 120) -> bool:
    started = time.time()
    while time.time() - started < timeout_seconds:
        try:
            r = requests.get(f"{base_url}/health", timeout=3)
            if r.status_code in (200, 503):
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    admin_key = load_admin_key(root / ".env")

    base_url = "http://127.0.0.1:5688"
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

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "5688",
        ],
        cwd=str(root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        if not wait_for_server(base_url):
            print("SERVER_START=FAILED")
            return 1

        print("SERVER_START=OK")

        for method, path, payload in checks:
            url = f"{base_url}{path}"
            started = time.perf_counter()
            try:
                if method == "GET":
                    response = requests.get(url, headers=headers, timeout=15)
                else:
                    response = requests.post(url, headers=headers, json=payload, timeout=15)
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                body_preview = response.text[:240].replace("\n", " ")
                print(f"{method} {path} -> {response.status_code} [{elapsed_ms}ms]")
                print(f"body: {body_preview}")
            except requests.RequestException as exc:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                print(f"{method} {path} -> ERROR [{elapsed_ms}ms]")
                print(f"error: {type(exc).__name__}: {exc}")

        return 0
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
