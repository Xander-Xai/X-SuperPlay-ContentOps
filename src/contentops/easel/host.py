"""Lifecycle helpers for the pinned Easel host.

This module never edits upstream Easel and never starts the upstream entry point
directly. The upstream ``web/app.py`` binds ``0.0.0.0`` and allows ``CORS *``;
this module serves it through :class:`GuardMiddleware` on loopback only. The
workbench candidate adds one ContentOps-owned offline scaffold API; production
Easel mutations remain denied.

Importing FastAPI/uvicorn or the upstream app is deferred to the moment a host
is actually served, so status checks and tests remain stdlib-only.
"""

from __future__ import annotations

import importlib.util
import hashlib
import json
import mimetypes
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .guard import GuardMiddleware, HostPolicy
from .offline_api import OfflineTaskAPI
from .path_safety import is_linklike

BIND_HOST = "127.0.0.1"
DEFAULT_PORT = 7861
DEFAULT_OFFLINE_TASK_PORT = 7862
HOST_APP = Path(".runtime") / "easel" / "web" / "app.py"
HOST_CLI = Path(".runtime") / "easel" / "easel" / "cli.py"
LOCK = Path("runtime") / "easel.lock.json"
WORKBENCH_BUILD_MANIFEST = Path("runtime") / "easel-workbench-frontend-build.json"

#: Every module ``web/app.py`` imports at module level. A missing one means the
#: app cannot be imported, so the host cannot be served even though the files
#: are present. Keep this in step with the upstream import block; a new import
#: that is not listed here would let ``host_status`` report a false HOST_READY.
HOST_IMPORT_MODULES = ("fastapi", "uvicorn", "pydantic", "sse_starlette")


class HostError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


class FrontendIntegrityMiddleware:
    """Recheck build bytes before each browser page or static asset read."""

    def __init__(self, app, check_build, read_asset=None) -> None:
        self.app = app
        self.check_build = check_build
        self.read_asset = read_asset

    async def __call__(self, scope, receive, send):
        if (scope.get("type") == "http"
                and scope.get("method", "GET").upper() in {"GET", "HEAD"}
                and not str(scope.get("path", "")).startswith("/api/")):
            path = str(scope.get("path") or "")
            if (path != "/" and not (path.startswith("/assets/")
                    and "%" not in path and "\\" not in path
                    and all(part not in ("", ".", "..") for part in path[1:].split("/")))):
                body = b'{"error":"HOST_FRONTEND_ROUTE_DENIED"}'
                await send({"type": "http.response.start", "status": 403,
                            "headers": [(b"content-type", b"application/json; charset=utf-8"),
                                        (b"cache-control", b"no-store")]})
                await send({"type": "http.response.body", "body": body})
                return
            try:
                result = self.check_build()
            except Exception as exc:  # noqa: BLE001 - fail closed on verifier errors
                result = {"status": "UNVERIFIED", "reason": type(exc).__name__}
            if result.get("status") != "VERIFIED":
                body = json.dumps({
                    "error": "HOST_FRONTEND_UNVERIFIED",
                    "detail": result.get("reason", "frontend build is not verified"),
                }, ensure_ascii=False).encode("utf-8")
                await send({"type": "http.response.start", "status": 503,
                            "headers": [(b"content-type", b"application/json; charset=utf-8"),
                                        (b"cache-control", b"no-store")]})
                await send({"type": "http.response.body", "body": body})
                return

            async def verified_send(message):
                if message.get("type") == "http.response.start":
                    headers = [(key, value) for key, value in (message.get("headers") or [])
                               if key.lower() not in (b"content-security-policy",)]
                    headers.append((b"content-security-policy",
                                    b"default-src 'self'; script-src 'self' 'unsafe-inline'; "
                                    b"style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                                    b"font-src 'self' data:; connect-src 'self'; object-src 'none'; "
                                    b"frame-src 'none'; base-uri 'none'"))
                    message = {**message, "headers": headers}
                await send(message)

            if self.read_asset is not None:
                try:
                    body, content_type = self.read_asset(path, result)
                except (OSError, ValueError, KeyError, TypeError):
                    body = b'{"error":"HOST_FRONTEND_UNVERIFIED"}'
                    await send({"type": "http.response.start", "status": 503,
                                "headers": [(b"content-type", b"application/json; charset=utf-8"),
                                            (b"cache-control", b"no-store")]})
                    await send({"type": "http.response.body", "body": body})
                    return
                await verified_send({"type": "http.response.start", "status": 200,
                                     "headers": [(b"content-type", content_type.encode("ascii")),
                                                 (b"content-length", str(len(body)).encode("ascii")),
                                                 (b"cache-control", b"no-store")]})
                await verified_send({"type": "http.response.body",
                                     "body": b"" if scope.get("method", "GET").upper() == "HEAD" else body})
                return
            await self.app(scope, receive, verified_send)
            return
        await self.app(scope, receive, send)


def _pin(root: Path) -> Dict[str, Any]:
    path = root / LOCK
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _workbench_pin(root: Path) -> Dict[str, Any]:
    """Read workbench provenance without conflating it with the production pin."""
    from .agent_workspace import WORKBENCH_COMMIT, WORKBENCH_REPO

    path = root / "runtime" / "easel-workbench-overlay.json"
    try:
        if is_linklike(path) or is_linklike(path.parent):
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    upstream = payload.get("upstream") if isinstance(payload, dict) else None
    if (not isinstance(upstream, dict) or payload.get("schema") != "contentops.easel-workbench-overlay/v1"
            or upstream.get("repo") != WORKBENCH_REPO or upstream.get("commit") != WORKBENCH_COMMIT):
        return {}
    return upstream


def _load_verifier(root: Path):
    """Import the pinned-runtime verifier without making it a package dependency."""
    root = Path(root).resolve()
    script = root / "scripts" / "verify_easel_runtime.py"
    if not script.is_file():
        raise HostError("HOST_VERIFIER_MISSING", script.as_posix())
    scripts_dir = str(script.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("contentops_pinned_runtime_verifier", script)
    if spec is None or spec.loader is None:
        raise HostError("HOST_VERIFIER_UNLOADABLE", script.as_posix())
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_runtime_bytes(root: Path, verifier: Any = None,
                         tree: Optional[Path] = None) -> Dict[str, Any]:
    """Compare the local runtime tree with upstream at the pinned commit.

    A presence check is not identity: only a byte comparison says the code about
    to be imported is the code the lock names. ``UNVERIFIABLE`` (offline, no
    ``gh``) is not a pass.

    ``tree`` selects the runtime tree; it defaults to ``.runtime/easel``. A
    workbench instance has a tuning overlay on top of the same upstream code, so
    it is verified through the verifier's overlay mode instead of the strict
    baseline comparison — that is what lets a *declared* tuning pass while an
    undeclared edit still fails.
    """
    root = Path(root)
    runtime_tree = Path(tree) if tree is not None else root / ".runtime" / "easel"
    try:
        module = verifier or _load_verifier(root)
    except Exception as exc:  # noqa: BLE001 - a missing verifier blocks the host
        return {"state": "UNVERIFIABLE", "detail": f"{type(exc).__name__}: {exc}"}
    try:
        if tree is not None:
            pin = _workbench_pin(root)
            if not pin:
                return {"state": "MISMATCH", "detail": "workbench identity does not match the planned v0.3.0 commit"}
            record_path = root / "runtime" / "easel-workbench-overlay.json"
            overlay = module.load_overlay(record_path)
            if not overlay.get("readable"):
                return {"state": "UNVERIFIABLE", "detail": "workbench record unreadable"}
            recorded_tree = module.workbench_path(overlay).resolve()
            if recorded_tree != runtime_tree.resolve():
                return {"state": "MISMATCH", "detail": "verified workbench path differs from selected runtime"}
            result = module.verify_overlay(record_path, profile_mode="generated")
            if result.get("expected_commit") != pin["commit"]:
                return {"state": "MISMATCH", "detail": "workbench identity changed during verification"}
            if Path(result.get("workbench_path") or "").resolve() != runtime_tree.resolve():
                return {"state": "MISMATCH", "detail": "verifier returned a different runtime path"}
        else:
            result = module.verify(runtime_tree)
    except Exception as exc:  # noqa: BLE001 - never turn a crash into a pass
        return {"state": "UNVERIFIABLE", "detail": f"{type(exc).__name__}: {exc}"}
    state = str(result.get("status") or "UNVERIFIED")
    payload = {
        "state": state,
        "matched": result.get("matched"),
        "expected_commit": result.get("expected_commit"),
        "detail": result.get("reason") or "",
    }
    if state == "VERIFIED":
        payload["detail"] = ""
    return payload


def host_status(root: Path, *, verify_bytes: bool = False,
                verifier: Any = None, tree: Optional[Path] = None) -> Dict[str, Any]:
    """Report whether the pinned host can be served, without starting it.

    ``tree`` names the runtime tree to inspect; it defaults to
    ``.runtime/easel``. A workbench instance passes its own path so the status
    describes what ``serve`` would actually load.
    """
    root = Path(root)
    runtime_tree = Path(tree) if tree is not None else root / HOST_APP.parent.parent
    app_path = runtime_tree / "web" / "app.py"
    cli_path = runtime_tree / "easel" / "cli.py"
    blockers = []
    if not app_path.is_file():
        blockers.append("HOST_APP_MISSING")
    if not cli_path.is_file():
        blockers.append("HOST_CLI_MISSING")
    lock = _workbench_pin(root) if tree is not None else _pin(root)
    if not lock.get("tag") or not lock.get("commit"):
        blockers.append("HOST_PIN_MISSING")
    # Check every module the upstream app imports at module level, not just the
    # two the original check named. `host_status` reporting HOST_READY while
    # `web/app.py` cannot import (sse_starlette absent) was a false pass: the
    # host would have failed on first import. The list is kept in
    # HOST_IMPORT_MODULES so a new upstream import shows up as a diff here.
    for module in HOST_IMPORT_MODULES:
        if importlib.util.find_spec(module) is None:
            blockers.append(f"HOST_DEPENDENCY_MISSING:{module}")

    bytes_result: Dict[str, Any] = {"state": "NOT_CHECKED"}
    frontend_result: Dict[str, Any] = {"status": "NOT_CHECKED"}
    if tree is not None:
        try:
            module = verifier or _load_verifier(root)
            frontend_result = module.verify_frontend_build(
                runtime_tree / "web" / "frontend",
                root / WORKBENCH_BUILD_MANIFEST,
                str(lock.get("commit") or ""),
            )
        except Exception as exc:  # noqa: BLE001 - provenance errors block serving
            frontend_result = {"status": "UNVERIFIED",
                               "reason": f"{type(exc).__name__}: {exc}"}
        if frontend_result.get("status") != "VERIFIED":
            blockers.append(f"HOST_FRONTEND_{frontend_result.get('status', 'UNVERIFIED')}")
    if verify_bytes and app_path.is_file():
        bytes_result = verify_runtime_bytes(root, verifier, tree=tree)
        if bytes_result["state"] != "VERIFIED":
            blockers.append(f"HOST_BYTES_{bytes_result['state']}")

    return {
        "schema": "contentops.easel-host/v1",
        "state": "HOST_BLOCKED" if blockers else "HOST_READY",
        "blockers": blockers,
        "pin": {"tag": lock.get("tag"), "commit": lock.get("commit")},
        "bytes": bytes_result,
        "frontend": frontend_result,
        "runtime_tree": _display_path(runtime_tree, root),
        "app": _display_path(app_path, root),
        "bind_host": BIND_HOST,
        "default_port": DEFAULT_PORT,
        "mutations": "OFFLINE_DRAFTS_ONLY" if tree is not None else "DENIED",
        "allowed_methods": (["GET", "HEAD", "OPTIONS", "POST"]
                            if tree is not None else ["GET", "HEAD", "OPTIONS"]),
        "offline_task_routes": (["GET /api/contentops/profiles",
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
                                 "GET /api/contentops/draft-task/{task_id}/artifacts?account={slug}&project={slug}"]
                                if tree is not None else []),
        "offline_task_ui": "/contentops/offline-task" if tree is not None else None,
        "note": "HOST_READY means this process may serve the audited UI and, for the "
                "workbench candidate, the offline draft APIs. "
                "It is not real Agent execution, publication authority, or content approval.",
    }


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def load_upstream_app(root: Path, tree: Optional[Path] = None):
    """Import the upstream ASGI app. Never called by a status check.

    ``tree`` selects the runtime tree; it defaults to ``.runtime/easel``.
    """
    root = Path(root).resolve()
    runtime_tree = Path(tree).resolve() if tree is not None else root / ".runtime" / "easel"
    app_path = runtime_tree / "web" / "app.py"
    if not app_path.is_file():
        raise HostError("HOST_APP_MISSING", app_path.as_posix())
    easel_root = str(runtime_tree)
    if easel_root not in sys.path:
        sys.path.insert(0, easel_root)
    spec = importlib.util.spec_from_file_location("contentops_easel_web_app", app_path)
    if spec is None or spec.loader is None:
        raise HostError("HOST_APP_UNLOADABLE", app_path.as_posix())
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - missing upstream deps are a host blocker
        raise HostError("HOST_APP_UNLOADABLE", f"{type(exc).__name__}: {exc}") from None
    app = getattr(module, "app", None)
    if app is None:
        raise HostError("HOST_APP_UNLOADABLE", "upstream module exposes no ASGI app")
    return app


def serve(root: Path, port: int = DEFAULT_PORT, policy: Optional[HostPolicy] = None,
          verifier: Any = None, tree: Optional[Path] = None) -> None:
    """Serve the guarded host on loopback. This function blocks.

    ``tree`` selects the runtime tree; it defaults to ``.runtime/easel``. A
    workbench instance passes its path, and its bytes are verified in overlay
    mode (upstream baseline proven, declared tuning reported) before serving.
    """
    status = host_status(root, verify_bytes=True, verifier=verifier, tree=tree)
    if status["state"] != "HOST_READY":
        raise HostError("HOST_BLOCKED", ", ".join(status["blockers"]))
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise HostError("HOST_PORT_INVALID", str(port))
    try:
        import uvicorn  # type: ignore
    except ImportError:
        raise HostError("HOST_DEPENDENCY_MISSING", "uvicorn") from None

    upstream = load_upstream_app(root, tree=tree)
    if tree is not None:
        module = verifier or _load_verifier(Path(root))
        lock = _workbench_pin(Path(root))

        def check_build():
            return module.verify_frontend_build(
                Path(tree) / "web" / "frontend",
                Path(root) / WORKBENCH_BUILD_MANIFEST,
                str(lock.get("commit") or ""),
            )

        def read_verified_asset(path, verification):
            manifest_path = Path(root) / WORKBENCH_BUILD_MANIFEST
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            relative = "index.html" if path == "/" else path[1:]
            if manifest.get("tree_sha256") != verification.get("tree_sha256"):
                raise ValueError("frontend manifest changed")
            expected = manifest["files"][relative]
            dist = Path(tree) / "web" / "frontend" / "dist"
            current = dist
            for part in relative.split("/"):
                current = current / part
                if is_linklike(current):
                    raise ValueError("linked frontend asset")
            if not current.is_file() or not current.resolve(strict=True).is_relative_to(dist.resolve(strict=True)):
                raise ValueError("frontend asset outside build")
            data = current.read_bytes()
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError("frontend asset digest changed")
            # Windows MIME registrations vary between machines. Module scripts
            # must use a JavaScript MIME type or browsers refuse to execute them.
            suffix = Path(relative).suffix.lower()
            content_type = {".html": "text/html; charset=utf-8",
                            ".js": "text/javascript; charset=utf-8",
                            ".mjs": "text/javascript; charset=utf-8",
                            ".css": "text/css; charset=utf-8",
                            ".svg": "image/svg+xml"}.get(suffix)
            if content_type is None:
                content_type = mimetypes.guess_type(relative)[0] or "application/octet-stream"
            return data, content_type

        upstream = FrontendIntegrityMiddleware(upstream, check_build, read_verified_asset)
        upstream = OfflineTaskAPI(upstream, Path(root))
    selected_policy = policy or HostPolicy(allow_offline_tasks=tree is not None)
    guarded = GuardMiddleware(upstream, selected_policy)
    uvicorn.run(
        guarded,
        host=BIND_HOST,
        port=port,
        log_level="warning",
        proxy_headers=False,
        server_header=False,
    )


class _OfflineNotFoundApp:
    async def __call__(self, scope, receive, send):
        body = b'{"error":"NOT_FOUND"}'
        await send({"type": "http.response.start", "status": 404,
                    "headers": [(b"content-type", b"application/json; charset=utf-8"),
                                (b"content-length", str(len(body)).encode("ascii")),
                                (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": body})


def offline_task_host_status() -> Dict[str, Any]:
    """Report readiness for the project-owned offline panel, without Easel imports."""
    blockers = []
    if importlib.util.find_spec("uvicorn") is None:
        blockers.append("HOST_DEPENDENCY_MISSING:uvicorn")
    if importlib.util.find_spec("yaml") is None:
        blockers.append("HOST_DEPENDENCY_MISSING:PyYAML")
    return {
        "schema": "contentops.easel-offline-task-host/v1",
        "state": "HOST_BLOCKED" if blockers else "HOST_READY",
        "mode": "OFFLINE_TASKS_ONLY",
        "blockers": blockers,
        "bind_host": BIND_HOST,
        "default_port": DEFAULT_OFFLINE_TASK_PORT,
        "panel_url": f"http://{BIND_HOST}:{DEFAULT_OFFLINE_TASK_PORT}/contentops/offline-task",
        "upstream_easel_loaded": False,
        "gateway_or_model_calls": False,
        "network_tools": "NOT_EXPOSED",
        "system_network_isolation": "NOT_ESTABLISHED",
        "agent_execution": "NOT_AUTHORIZED",
        "allowed_methods": ["GET", "POST", "OPTIONS"],
        "routes": ["GET /contentops/offline-task",
                   "GET /api/contentops/status",
                   "GET /api/contentops/project-readiness",
                   "GET /api/contentops/skills/video-script",
                   "GET /api/contentops/profiles",
                   "GET /api/contentops/projects?account={slug}",
                   "GET /api/contentops/draft-tasks?account={slug}&project={slug}",
                   "GET /api/contentops/profiles/{account}",
                   "POST /api/contentops/evidence-draft",
                   "POST /api/contentops/draft-task",
                   "POST /api/contentops/agent-workspace",
                   "POST /api/contentops/agent-cancel",
                   "POST /api/contentops/agent-collect",
                   "GET /api/contentops/draft-task/{task_id}",
                   "GET /api/contentops/draft-task/{task_id}/draft",
                   "GET /api/contentops/draft-task/{task_id}/artifacts"],
        "production_ready": False,
        "publish_authorized": False,
    }


def serve_offline_tasks(root: Path, port: int = DEFAULT_OFFLINE_TASK_PORT) -> None:
    """Serve only the ContentOps-owned offline panel/API on loopback.

    This mode does not import Easel, FastAPI routes, gateway clients or provider
    settings. It requires the already-installed uvicorn package and writes only
    task scaffolds and receipts inside an existing ContentOps project.
    """
    status = offline_task_host_status()
    if status["state"] != "HOST_READY":
        raise HostError("HOST_BLOCKED", ", ".join(status["blockers"]))
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise HostError("HOST_PORT_INVALID", str(port))
    try:
        import uvicorn  # type: ignore
    except ImportError:
        raise HostError("HOST_DEPENDENCY_MISSING", "uvicorn") from None
    app = OfflineTaskAPI(_OfflineNotFoundApp(), Path(root))
    guarded = GuardMiddleware(app, HostPolicy(allow_workbench_reads=False,
                                               allow_offline_tasks=True))
    uvicorn.run(guarded, host=BIND_HOST, port=port, log_level="warning",
                proxy_headers=False, server_header=False)
