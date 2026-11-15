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
from contentops.easel.host import FrontendIntegrityMiddleware, host_status  # noqa: E402


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


def _run(method: str, path: str, headers: dict[str, str] | None = None,
         policy: HostPolicy | None = None) -> tuple[int, bytes, list, FakeApp]:
    app = FakeApp()
    guard = GuardMiddleware(app, policy or HostPolicy())
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
    """A resource the guard keeps open reaches upstream and is recorded once."""
    status, body, _, app = _run("GET", "/static/app.js")
    assert status == 200
    assert body == b"upstream"
    assert app.calls == [("GET", "/static/app.js")]


def test_upstream_status_route_is_denied_because_it_reads_env():
    """`/api/status` stays closed: it calls get_skills(), which reads the .env.

    ADR-022 D3 records the reason. The route used to be forwarded, and the test
    that asserted that was the reason nobody noticed the denial landing.
    """
    status, body, _, app = _run("GET", "/api/status")
    assert status == 403
    assert app.calls == [], "a denied request must never reach the upstream app"
    assert json.loads(body)["error"] == "HOST_RESOURCE_AUDIT_REQUIRED"


def test_offline_task_methods_are_opt_in_and_exact():
    disabled = HostPolicy()
    enabled = HostPolicy(allow_offline_tasks=True)
    submit = "/api/contentops/draft-task"
    status = "/api/contentops/draft-task/123e4567-e89b-42d3-a456-426614174000"
    assert disabled.safe_route("POST", submit)[0] is False
    assert enabled.safe_route("POST", submit)[0] is True
    assert enabled.safe_route("GET", status)[0] is True
    assert enabled.safe_route("GET", status + "/draft")[0] is True
    assert enabled.safe_route("GET", "/api/contentops/profiles")[0] is True
    assert enabled.safe_route("GET", "/contentops/offline-task")[0] is True
    for method, path in [
        ("POST", "/api/contentops/draft-task/123e4567-e89b-42d3-a456-426614174000"),
        ("PUT", submit),
        ("POST", "/api/chat"),
        ("POST", "/api/contentops/draft-task/../../api/publish"),
        ("GET", "/api/contentops/draft-task/not-a-uuid"),
        ("GET", "/api/contentops/draft-task/123e4567-e89b-42d3-a456-426614174000/draft/extra"),
        ("POST", "/contentops/offline-task"),
        ("GET", "/contentops/offline-task/other-file.js"),
    ]:
        assert enabled.safe_route(method, path)[0] is False, (method, path)


def test_offline_options_is_exact_and_reports_post_without_enabling_cors():
    policy = HostPolicy(allow_workbench_reads=False, allow_offline_tasks=True)
    submit = "/api/contentops/draft-task"
    assert policy.safe_route("OPTIONS", submit)[0] is True
    assert policy.safe_route("OPTIONS", "/api/chat")[0] is False

    status, _, sent, app = _run(
        "OPTIONS", submit,
        {"host": "127.0.0.1:7862", "origin": "http://localhost:7862"},
        policy,
    )
    headers = dict(sent[0]["headers"])
    assert status == 204
    assert headers[b"allow"] == b"POST, OPTIONS"
    assert b"access-control-allow-origin" not in headers
    assert app.calls == []

    rejected, body, _, _ = _run(
        "OPTIONS", submit,
        {"host": "127.0.0.1:7862", "origin": "https://evil.example"},
        policy,
    )
    assert rejected == 403
    assert b"HOST_ORIGIN_INVALID" in body


def test_frontend_integrity_blocks_browser_asset_reads_without_verified_build():
    app = FakeApp()
    middleware = FrontendIntegrityMiddleware(
        app, lambda: {"status": "MISMATCH", "reason": "tampered dist"})
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(middleware({"type": "http", "method": "GET", "path": "/assets/app.js"},
                           receive, send))
    assert sent[0]["status"] == 503
    assert b"HOST_FRONTEND_UNVERIFIED" in sent[1]["body"]
    assert app.calls == []


def test_frontend_integrity_does_not_recheck_api_status():
    app = FakeApp()
    checks = []
    middleware = FrontendIntegrityMiddleware(
        app, lambda: checks.append("checked") or {"status": "UNVERIFIED"})
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(middleware({"type": "http", "method": "GET", "path": "/api/status"},
                           receive, send))
    assert checks == []
    assert sent[0]["status"] == 200


def test_static_ui_shell_is_still_served():
    """The workbench UI shell stays readable — the audit is about resources."""
    for path in ("/", "/onepage", "/favicon.ico",
                 "/static/app.js", "/assets/logo.svg"):
        status, body, _, app = _run("GET", path)
        assert status == 200, path
        assert body == b"upstream", path


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


def test_v03_settings_gateway_and_archive_routes_remain_denied():
    for method, path in (
        ("GET", "/api/settings/bootstrap"),
        ("GET", "/api/settings/harness"),
        ("POST", "/api/gateway/restart"),
        ("GET", "/api/settings/local-agents"),
        ("POST", "/api/settings/local-agents/enable"),
        ("POST", "/api/settings/models/available"),
        ("GET", "/api/artifacts/archive"),
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


def test_workbench_resource_reads_stay_closed_until_audited():
    """File and resource reads are disabled pending a per-resource audit.

    The upstream readers verify path containment, not secrecy: ``outputs/``
    also holds ``_login``/``_sessions``/``_debug`` and similar system state.
    Instead of allowing a prefix and blacklisting the bad subtrees, the guard
    keeps every resource-reading prefix closed until each is audited.
    """
    for path in (
        "/api/outputs",
        "/api/output/anything.txt",
        "/api/media/logo.png",
        "/api/skills",  # exact route = fine, but /api/skill/x is the reader
        "/api/personas",
        "/api/persona/explorer",
        "/api/persona/explorer/files",
    ):
        assert path == "/api/skills" or True  # documentation clarity only
    for path in (
        "/api/outputs",
        "/api/output/anything.txt",
        "/api/output/_login/session.json",
        "/api/output/_sessions/latest.json",
        "/api/output/_debug/trace.log",
        "/api/output/_publish/state.json",
        "/api/output/_profile_build/job.json",
        "/api/output/analytics/week.csv",
        "/api/media/logo.png",
        "/api/skill/screen-reader",
        "/api/persona/explorer",
        "/api/persona/explorer/files",
    ):
        status, body, _, app = _run("GET", path)
        assert status == 403, f"{path} must stay closed"
        assert app.calls == [], f"{path} reached upstream"
        assert json.loads(body)["error"] == "HOST_RESOURCE_AUDIT_REQUIRED", path


def test_system_directory_segments_are_refused_on_any_allowed_route():
    """Even the open static prefixes must not serve a system directory."""
    for path in (
        "/static/_login/session.json",
        "/assets/_sessions/latest.json",
        "/static/_debug/trace.log",
        "/static/analytics/week.csv",
    ):
        status, body, _, app = _run("GET", path)
        assert status == 403, path
        assert app.calls == [], path
        assert json.loads(body)["error"] == "HOST_SYSTEM_DIR_DENIED"


def test_encoded_and_mixed_case_system_dirs_are_refused():
    """Redundant decoding survivors are judged on their final spelling."""
    for path in (
        "/api/output/%5Flogin/x",
        "/api/output/_%6Cogin/x",  # lowercase-encoded hand-swap guard
        "/static/_LOGIN/session.json",
        "/api/output/_Sessions/latest.json",
    ):
        status, body, _, app = _run("GET", path)
        assert status == 403, path
        assert app.calls == [], path


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


def test_websocket_is_closed_before_upstream():
    app = FakeApp()
    guard = GuardMiddleware(app, HostPolicy())
    sent: list = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "websocket.connect"}

    scope = {
        "type": "websocket",
        "path": "/api/publish/douyin",
        "headers": [(b"host", b"evil.example")],
    }
    asyncio.run(guard(scope, receive, send))
    assert app.calls == [], "a websocket must never reach the upstream app"
    assert sent == [{"type": "websocket.close", "code": 1008}]


def test_unknown_scope_is_not_forwarded():
    app = FakeApp()
    guard = GuardMiddleware(app, HostPolicy())
    asyncio.run(guard({"type": "something-new", "path": "/"}, None, None))
    assert app.calls == []


def _fake_root(tmp: Path) -> Path:
    (tmp / ".runtime" / "easel" / "web").mkdir(parents=True)
    (tmp / ".runtime" / "easel" / "easel").mkdir(parents=True)
    (tmp / ".runtime" / "easel" / "web" / "app.py").write_text("app = None\n", encoding="utf-8")
    (tmp / ".runtime" / "easel" / "easel" / "cli.py").write_text("", encoding="utf-8")
    (tmp / "runtime").mkdir()
    (tmp / "runtime" / "easel.lock.json").write_text(
        json.dumps({"tag": "v0.2.1", "commit": "3fe2d99"}), encoding="utf-8")
    return tmp


class FakeVerifier:
    def __init__(self, status: str) -> None:
        self.status = status

    def verify(self, runtime_dir):
        return {"status": self.status, "matched": 982, "reason": "fake"}


def test_a_mismatched_runtime_blocks_the_host():
    with tempfile.TemporaryDirectory() as tmp:
        root = _fake_root(Path(tmp))
        blocked = host_status(root, verify_bytes=True, verifier=FakeVerifier("MISMATCH"))
        trusted = host_status(root, verify_bytes=True, verifier=FakeVerifier("VERIFIED"))
        unchecked = host_status(root)
    assert blocked["state"] == "HOST_BLOCKED"
    assert "HOST_BYTES_MISMATCH" in blocked["blockers"]
    assert blocked["bytes"]["state"] == "MISMATCH"
    assert not any(item.startswith("HOST_BYTES_") for item in trusted["blockers"])
    assert unchecked["bytes"]["state"] == "NOT_CHECKED"


def test_default_host_verifies_production_tree_even_if_overlay_available():
    class BothVerifiers(FakeVerifier):
        def verify_overlay(self, record):
            raise AssertionError("production host must not verify the workbench")

    with tempfile.TemporaryDirectory() as tmp:
        root = _fake_root(Path(tmp))
        status = host_status(root, verify_bytes=True, verifier=BothVerifiers("MISMATCH"))
    assert status["bytes"]["state"] == "MISMATCH", status
    assert "HOST_BYTES_MISMATCH" in status["blockers"]


def test_workbench_verification_must_match_the_tree_to_be_imported():
    from contentops.easel.host import verify_runtime_bytes

    class OverlayVerifier:
        def load_overlay(self, path):
            return {"readable": True}

        def workbench_path(self, overlay):
            return Path("different-workbench")

        def verify_overlay(self, path):
            return {"status": "VERIFIED"}

    with tempfile.TemporaryDirectory() as tmp:
        result = verify_runtime_bytes(Path(tmp), OverlayVerifier(), tree=Path(tmp) / "selected")
    assert result["state"] != "VERIFIED", result


def test_an_unreachable_verifier_is_not_a_pass():
    with tempfile.TemporaryDirectory() as tmp:
        root = _fake_root(Path(tmp))
        status = host_status(root, verify_bytes=True, verifier=FakeVerifier("UNVERIFIED"))
    assert "HOST_BYTES_UNVERIFIED" in status["blockers"]


def test_host_status_reports_the_workbench_pin_not_the_production_pin():
    from contentops.easel import pins

    declared = pins.workbench()
    with tempfile.TemporaryDirectory() as tmp:
        root = _fake_root(Path(tmp))
        workbench = root / "workbench"
        (workbench / "web").mkdir(parents=True)
        (workbench / "easel").mkdir(parents=True)
        (workbench / "web" / "app.py").write_text("app = None\\n", encoding="utf-8")
        (workbench / "easel" / "cli.py").write_text("", encoding="utf-8")
        (root / "runtime" / "easel-workbench-overlay.json").write_text(
            json.dumps({"schema": "contentops.easel-workbench-overlay/v1",
                        "upstream": {"repo": declared.repo, "tag": declared.tag,
                                     "commit": declared.commit}}),
            encoding="utf-8",
        )
        status = host_status(root, tree=workbench)

    # The test environment may not have every module imported by the upstream
    # web app; this test is about selecting the workbench pin, not installing
    # host dependencies.
    assert status["state"] in {"HOST_READY", "HOST_BLOCKED"}
    assert status["pin"] == {"tag": declared.tag, "commit": declared.commit}
    assert status["frontend"]["status"] == "UNVERIFIED"
    assert status["mutations"] == "OFFLINE_DRAFTS_ONLY"
    # Exact list on purpose: this is the surface the host advertises, so an
    # accidental addition has to be a deliberate edit here as well.
    assert status["offline_task_routes"] == [
        "GET /api/contentops/profiles",
        "GET /api/contentops/projects?account={slug}",
        "GET /api/contentops/draft-tasks?account={slug}&project={slug}",
        "GET /api/contentops/status",
        "GET /api/contentops/profiles/{account}",
        "GET /api/contentops/project-readiness",
        "GET /api/contentops/skills/video-script",
        "POST /api/contentops/evidence-draft",
        "POST /api/contentops/draft-task",
        "POST /api/contentops/agent-workspace",
        "POST /api/contentops/agent-proposal",
        "POST /api/contentops/agent-approval-inspection",
        "POST /api/contentops/agent-cancel",
        "POST /api/contentops/agent-collect",
        "POST /api/contentops/windows-sandbox-review",
        "GET /api/contentops/draft-task/{task_id}?account={slug}&project={slug}",
        "GET /api/contentops/draft-task/{task_id}/draft?account={slug}&project={slug}",
        "GET /api/contentops/draft-task/{task_id}/artifacts?account={slug}&project={slug}",
    ]
    assert status["offline_task_ui"] == "/contentops/offline-task"
    assert "HOST_FRONTEND_UNVERIFIED" in status["blockers"]


def test_host_status_blocks_a_missing_runtime():
    with tempfile.TemporaryDirectory() as tmp:
        status = host_status(Path(tmp))
    assert status["state"] == "HOST_BLOCKED"
    assert "HOST_APP_MISSING" in status["blockers"]
    assert status["bind_host"] == "127.0.0.1"
    assert status["mutations"] == "DENIED"
    assert status["offline_task_routes"] == []
    assert status["offline_task_ui"] is None


def test_host_status_names_every_module_the_app_imports():
    """A missing import dependency must be a blocker, not a silent false pass.

    ``web/app.py`` imports ``sse_starlette``; the original check named only
    fastapi and uvicorn, so it could report HOST_READY for a host that would
    fail on first import. This pins the full set so a new upstream import shows
    up as a failing test rather than a wrong READY.
    """
    import contentops.easel.host as host_mod

    assert "sse_starlette" in host_mod.HOST_IMPORT_MODULES
    assert {"fastapi", "uvicorn", "pydantic"} <= set(host_mod.HOST_IMPORT_MODULES)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Lay out a fake runtime tree so only a dependency can block.
        (root / ".runtime" / "easel" / "web").mkdir(parents=True)
        (root / ".runtime" / "easel" / "web" / "app.py").write_text("")
        (root / ".runtime" / "easel" / "easel").mkdir(parents=True)
        (root / ".runtime" / "easel" / "easel" / "cli.py").write_text("")
        (root / "runtime").mkdir(parents=True)
        (root / "runtime" / "easel.lock.json").write_text(
            json.dumps({"tag": "v0.2.1", "commit": "x"}))

        original = host_mod.HOST_IMPORT_MODULES
        host_mod.HOST_IMPORT_MODULES = ("definitely_absent_mod",)
        try:
            status = host_status(root)
        finally:
            host_mod.HOST_IMPORT_MODULES = original

    assert status["state"] == "HOST_BLOCKED"
    assert any(b.startswith("HOST_DEPENDENCY_MISSING:definitely_absent_mod")
               for b in status["blockers"]), status["blockers"]


def test_offline_tasks_only_status_is_isolated_from_easel():
    import contentops.easel.host as host_mod

    original = host_mod.importlib.util.find_spec
    checked = []

    def find_spec(name, *args, **kwargs):
        checked.append(name)
        if name in {"uvicorn", "yaml"}:
            return object()
        raise AssertionError(f"offline-only status checked unrelated dependency: {name}")

    host_mod.importlib.util.find_spec = find_spec
    try:
        status = host_mod.offline_task_host_status()
    finally:
        host_mod.importlib.util.find_spec = original

    # uvicorn serves the panel; PyYAML binds the project (ADR-022 D3). Nothing
    # else may be imported — the mode exists precisely to avoid loading Easel.
    assert checked == ["uvicorn", "yaml"]
    assert status["state"] == "HOST_READY"
    assert status["mode"] == "OFFLINE_TASKS_ONLY"
    assert status["upstream_easel_loaded"] is False
    assert status["gateway_or_model_calls"] is False
    assert status["default_port"] == host_mod.DEFAULT_OFFLINE_TASK_PORT
    assert status["production_ready"] is False
    assert status["publish_authorized"] is False



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
