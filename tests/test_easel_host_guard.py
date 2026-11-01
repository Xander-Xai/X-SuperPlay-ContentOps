"""Tests for the Easel host guard.

The host is the most dangerous surface in this repository: the upstream web
application can read credentials, install tools, publish and delete. These tests
pin the guard's default-deny behaviour before any upstream app can run.

Run: python tests/test_easel_host_guard.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.easel.guard import GuardMiddleware, HostPolicy  # noqa: E402
from contentops.easel.host import host_status  # noqa: E402


class FakeApp:
    def __init__(self) -> None:
        self.calls = []

    async def __call__(self, scope, receive, send):
        self.calls.append((scope["method"], scope["path"]))
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        })
        await send({"type": "http.response.body", "body": b"upstream"})


def _run(method: str, path: str, headers: dict[str, str] | None = None) -> tuple[int, bytes, list, FakeApp]:
    app = FakeApp()
    guard = GuardMiddleware(app, HostPolicy())
    sent: list = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode("ascii"),
        "headers": [
            (key.lower().encode("latin-1"), value.encode("latin-1"))
            for key, value in (headers or {"host": "127.0.0.1:7861"}).items()
        ],
        "scheme": "http",
        "server": ("127.0.0.1", 7861),
        "client": ("127.0.0.1", 50000),
    }
    asyncio.run(guard(scope, receive, send))
    status = next(item["status"] for item in sent if item["type"] == "http.response.start")
    body = b"".join(item.get("body", b"") for item in sent if item["type"] == "http.response.body")
    return status, body, sent, app


def test_loopback_read_is_forwarded():
    status, body, _, app = _run("GET", "/api/status")
    assert status == 200
    assert body == b"upstream"
    assert app.calls == [("GET", "/api/status")]


def test_publish_is_denied_before_upstream():
    status, body, _, app = _run("POST", "/api/publish/douyin")
    assert status == 403
    assert app.calls == [], "a denied request must never reach the upstream app"
    assert json.loads(body)["error"] == "HOST_ROUTE_DENIED"


def test_credentials_and_settings_writes_are_denied():
    for method, path in (
        ("POST", "/api/login/douyin"),
        ("POST", "/api/accounts/douyin/credentials"),
        ("POST", "/api/env/install"),
        ("PUT", "/api/settings/models/save"),
        ("DELETE", "/api/output/anything"),
        ("POST", "/api/chat"),
    ):
        status, body, _, app = _run(method, path)
        assert status == 403, f"{method} {path} should be denied"
        assert app.calls == [], f"{method} {path} reached upstream"
        assert json.loads(body)["error"] == "HOST_ROUTE_DENIED"


def test_unknown_read_route_is_denied():
    status, body, _, app = _run("GET", "/api/unknown-secret")
    assert status == 403
    assert app.calls == []
    assert json.loads(body)["error"] == "HOST_ROUTE_DENIED"


def test_path_traversal_is_denied():
    for path in ("/static/../.env", "/assets/%2e%2e/%2e%2e/secret", "/static/a%00b"):
        status, body, _, app = _run("GET", path)
        assert status == 403, path
        assert app.calls == [], path
        assert json.loads(body)["error"] == "HOST_PATH_INVALID"


def test_non_loopback_host_is_denied():
    status, body, _, app = _run("GET", "/api/status", {"host": "0.0.0.0:7861"})
    assert status == 403
    assert app.calls == []
    assert json.loads(body)["error"] == "HOST_HEADER_INVALID"


def test_non_loopback_origin_is_denied():
    status, body, _, app = _run(
        "GET", "/api/status", {"host": "127.0.0.1:7861", "origin": "https://evil.example"}
    )
    assert status == 403
    assert app.calls == []
    assert json.loads(body)["error"] == "HOST_ORIGIN_INVALID"


def test_guard_marks_response_as_host_guarded():
    _, _, sent, _ = _run("GET", "/api/status")
    start = next(item for item in sent if item["type"] == "http.response.start")
    headers = {key.decode(): value.decode() for key, value in start["headers"]}
    assert headers["x-contentops-host-guard"] == "deny-by-default"
    assert headers["cache-control"] == "no-store"


def test_host_status_blocks_a_missing_runtime():
    with tempfile.TemporaryDirectory() as tmp:
        status = host_status(Path(tmp))
    assert status["state"] == "HOST_BLOCKED"
    assert "HOST_APP_MISSING" in status["blockers"]
    assert status["bind_host"] == "127.0.0.1"
    assert status["mutations"] == "DENIED"


TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - a test runner reports, it does not raise
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok   {test.__name__}")
    print(f"{len(TESTS) - failures}/{len(TESTS)} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
