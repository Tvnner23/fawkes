#!/usr/bin/env python3
"""Read-only smoke checks for a running Fawkes client boundary.

This intentionally sends no Chat messages and creates no Archive evidence.
Use the manual Rider Acceptance Suite for conversational capability checks.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
BASE_URL = os.getenv("FAWKES_APP_URL", "http://127.0.0.1:8787").rstrip("/")


def request_json(path, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = urlopen(Request(BASE_URL + path, headers=headers), timeout=10)
    return response.status, json.load(response)


def main():
    token = os.getenv("FAWKES_APP_TOKEN")
    if not token:
        print("FAIL FAWKES_APP_TOKEN is required in the environment.")
        return 2
    results = []
    try:
        request_json("/api/chat")
        results.append(("authentication_boundary", False, "unauthenticated request succeeded"))
    except HTTPError as exc:
        results.append(("authentication_boundary", exc.code == 401, f"HTTP {exc.code}"))
    except Exception as exc:
        results.append(("authentication_boundary", False, type(exc).__name__))

    for name, path, keys in (
        ("chat_continuity", "/api/chat", {"phoenix", "conversation", "messages"}),
        ("capability_discovery", "/api/capabilities", {"instance_id", "capabilities", "presentation"}),
        ("development_dashboard", "/api/development/dashboard", {"observations", "human_review_items", "memory_triage"}),
    ):
        try:
            status, payload = request_json(path, token)
            results.append((name, status == 200 and keys <= set(payload), f"HTTP {status}"))
        except Exception as exc:
            results.append((name, False, type(exc).__name__))

    try:
        _, manifest = request_json("/api/capabilities", token)
        visual = next(item for item in manifest["capabilities"] if item["name"] == "presentation.visualize")
        required = {"bar", "line", "pie", "donut", "scatter", "timeline", "flow"}
        results.append(("visualization_manifest", required <= set(visual.get("features", ())), ", ".join(visual.get("features", ()))))
    except Exception as exc:
        results.append(("visualization_manifest", False, type(exc).__name__))

    client = subprocess.run(
        ["node", "tests/js/app_login_harness.js"], cwd=ROOT,
        capture_output=True, text=True, timeout=15,
    )
    results.append((
        "client_rendering", client.returncode == 0 and "client-login-flow-ok" in client.stdout,
        (client.stdout + client.stderr).strip()[-240:],
    ))

    for name, passed, detail in results:
        print(f"{'PASS' if passed else 'FAIL'} {name}: {detail}")
    print("NOTE Conversational tests are manual because this smoke command never writes synthetic rider messages.")
    return 0 if all(item[1] for item in results) else 1


if __name__ == "__main__":
    sys.exit(main())
