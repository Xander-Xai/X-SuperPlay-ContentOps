"""Deny-by-default guard for the pinned Easel web host.

The upstream application is a full creator workbench. It can read provider
credentials, install tools, publish, delete outputs and write account state.
Those are legitimate upstream features; they are not features this repository
has authorised for an agent-driven host.

The guard sits in front of the upstream ASGI app and answers before the app is
called. It is deliberately a policy gate, not a second web framework: it does
not log in, publish, generate, or store anything.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import unquote, urlsplit

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
SAFE_EXACT = frozenset({
    "/",
    "/onepage",
    "/favicon.ico",
})
#: Workbench reads that may return *content* through this guard. Until every
#: upstream reader at each prefix has been audited for what it can serve, file
#: reads stay closed (see SYSTEM_DIR_SEGMENTS below); the safest workbench
#: surface kept open is the static UI shell.
SAFE_PREFIXES = (
    "/static/",
    "/assets/",
)
#: Prefixes that name upstream *resources* (files, persona bodies, skill
#: payloads). These stay disabled until a per-resource audit authorises them:
#: the upstream readers validate containment, not secrecy, and the outputs
#: tree holds system directories this repository must never expose.
SAFE_RESOURCE_PREFIXES_DISABLED = (
    # Both upstream routes call get_skills(), which reads the runtime .env.
    "/api/status",
    "/api/skills",
    "/api/skill/",
    "/api/persona/",
    "/api/output/",
    "/api/media/",
    "/api/outputs",
    "/api/personas",
)
#: Routes that must never be reachable through this guard, even if a future
#: release adds a read method or a prefix accidentally overlaps a safe one.
ALWAYS_DENIED_PREFIXES = (
    "/api/publish/",
    "/api/login/",
    "/api/logout/",
    "/api/accounts/",
    "/api/env/",
    "/api/settings/",
    "/api/upload",
    "/api/profile/",
    "/api/session/",
    "/api/chat",
)
PATH_ESCAPE = re.compile(r"(^|/)\.\.?(/|$)")
OFFLINE_TASK_STATUS_PATH = re.compile(
    r"^/api/contentops/draft-task/[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
OFFLINE_TASK_DRAFT_PATH = re.compile(
    r"^/api/contentops/draft-task/[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}/draft$"
)
OFFLINE_TASK_ARTIFACTS_PATH = re.compile(
    r"^/api/contentops/draft-task/[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}/artifacts$"
)
OFFLINE_PROFILE_DETAIL_PATH = re.compile(r"^/api/contentops/profiles/[a-z0-9][a-z0-9-]{0,79}$")
HOST_RE = re.compile(r"^(127\.0\.0\.1|localhost|\[::1\])(?::\d{1,5})?$", re.IGNORECASE)

#: Path segments that name Easel's own system directories under ``outputs/``.
#: The upstream reading endpoints (``_safe_output_path``) only verify
#: containment inside ``outputs/`` — they do not exclude these — so a decoded
#: path through any file read route must never carry one. Applied to every
#: segment, so traversal-spelled or redundantly encoded variants are caught
#: just the same; ``_normalise_path`` has already collapsed escape attempts.
SYSTEM_DIR_SEGMENTS = frozenset({
    "_login",
    "_sessions",
    "_debug",
    "_publish",
    "_profile_build",
    "analytics",
})


class HostGuardError(ValueError):
    """A request is refused with a stable code the caller can branch on."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class HostPolicy:
    """What the host may expose through this repository.

    ``allow_workbench_reads`` keeps audited read-only UI paths available.
    ``allow_offline_tasks`` opens only the exact ContentOps scaffold submit and
    receipt/draft read routes. It never opens an upstream Easel mutation.
    """

    allow_workbench_reads: bool = True
    allow_offline_tasks: bool = False

    def safe_route(self, method: str, path: str) -> Tuple[bool, str]:
        method = method.upper()
        if self.allow_offline_tasks and (
                (method == "OPTIONS" and (
                    path in {
                        "/api/contentops/draft-task",
                        "/api/contentops/evidence-draft",
                        "/api/contentops/agent-workspace",
                        "/api/contentops/agent-proposal",
                        "/api/contentops/agent-approval-inspection",
                        "/api/contentops/agent-cancel",
                        "/api/contentops/agent-collect",
                        "/api/contentops/windows-sandbox-review",
                        "/api/contentops/profiles",
                        "/api/contentops/projects",
                        "/api/contentops/draft-tasks",
                        "/api/contentops/status",
                        "/api/contentops/project-readiness",
                        "/api/contentops/skills/video-script",
                        "/contentops/offline-task",
                        "/contentops/offline-task.js",
                        "/contentops/offline-task.css",
                    }
                    or OFFLINE_TASK_STATUS_PATH.fullmatch(path)
                    or OFFLINE_TASK_DRAFT_PATH.fullmatch(path)
                    or OFFLINE_TASK_ARTIFACTS_PATH.fullmatch(path)
                    or OFFLINE_PROFILE_DETAIL_PATH.fullmatch(path)
                ))
                or
                (method == "POST" and path == "/api/contentops/draft-task")
                or (method == "POST" and path == "/api/contentops/evidence-draft")
                or (method == "POST" and path == "/api/contentops/agent-workspace")
                or (method == "POST" and path == "/api/contentops/agent-proposal")
                or (method == "POST" and path == "/api/contentops/agent-approval-inspection")
                or (method == "POST" and path == "/api/contentops/agent-cancel")
                or (method == "POST" and path == "/api/contentops/agent-collect")
                or (method == "POST" and path == "/api/contentops/windows-sandbox-review")
                or (method == "GET" and path == "/api/contentops/profiles")
                or (method == "GET" and path == "/api/contentops/projects")
                or (method == "GET" and path == "/api/contentops/draft-tasks")
                or (method == "GET" and path == "/api/contentops/status")
                or (method == "GET" and OFFLINE_PROFILE_DETAIL_PATH.fullmatch(path))
                or (method == "GET" and path == "/api/contentops/project-readiness")
                or (method == "GET" and path == "/api/contentops/skills/video-script")
                or (method == "GET" and path in {
                    "/contentops/offline-task",
                    "/contentops/offline-task.js",
                    "/contentops/offline-task.css",
                })
                or (method == "GET" and (OFFLINE_TASK_STATUS_PATH.fullmatch(path)
                                          or OFFLINE_TASK_DRAFT_PATH.fullmatch(path)
                                          or OFFLINE_TASK_ARTIFACTS_PATH.fullmatch(path)))):
            return True, ""
        if method not in SAFE_METHODS:
            return False, "HOST_ROUTE_DENIED"
        if not self.allow_workbench_reads:
            return False, "HOST_ROUTE_DENIED"
        for prefix in ALWAYS_DENIED_PREFIXES:
            if path.startswith(prefix):
                return False, "HOST_ROUTE_DENIED"
        for prefix in SAFE_RESOURCE_PREFIXES_DISABLED:
            # Exact paths ("/api/outputs", "/api/personas") and everything
            # under the slash-terminated ones. A denial here names the audit
            # gate, not a guess about what the reader would have done.
            if path == prefix or (prefix.endswith("/") and path.startswith(prefix)) \
                    or path.startswith(prefix + "/"):
                return False, "HOST_RESOURCE_AUDIT_REQUIRED"
        if any(segment.lower() in SYSTEM_DIR_SEGMENTS for segment in path.split("/")):
            return False, "HOST_SYSTEM_DIR_DENIED"
        if path in SAFE_EXACT:
            return True, ""
        if any(path.startswith(prefix) for prefix in SAFE_PREFIXES):
            return True, ""
        return False, "HOST_ROUTE_DENIED"


def _headers(scope: Dict[str, Any]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for key, value in scope.get("headers") or []:
        try:
            result[key.decode("latin-1").lower()] = value.decode("latin-1")
        except (AttributeError, UnicodeDecodeError):
            continue
    return result


def _host_allowed(value: str) -> bool:
    return bool(value) and bool(HOST_RE.match(value.strip()))


def _origin_allowed(value: str) -> bool:
    if not value:
        return True
    try:
        parsed = urlsplit(value.strip())
        if (parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.path
                or parsed.query or parsed.fragment):
            return False
        # Accessing port validates its syntax and range.
        _ = parsed.port
        return parsed.hostname.lower() in LOOPBACK_HOSTS
    except ValueError:
        return False


def _same_origin(host: str, origin: str) -> bool:
    """Require the browser's complete HTTP origin for state-changing routes."""
    if not host or not origin:
        return False
    try:
        parsed = urlsplit(origin)
        host_parts = urlsplit("//" + host)
        if (parsed.scheme.lower() != "http" or not parsed.hostname
                or parsed.username or parsed.password or parsed.path
                or parsed.query or parsed.fragment or not host_parts.hostname
                or host_parts.username or host_parts.password
                or host_parts.path or host_parts.query or host_parts.fragment):
            return False
        return (parsed.hostname.lower() == host_parts.hostname.lower()
                and (parsed.port or 80) == (host_parts.port or 80))
    except ValueError:
        return False


def _normalise_path(path: str) -> str:
    decoded = unquote(path or "")
    if not decoded.startswith("/"):
        raise HostGuardError("HOST_PATH_INVALID", "path must be absolute")
    if "\x00" in decoded or "\\" in decoded:
        raise HostGuardError("HOST_PATH_INVALID", "path contains a forbidden character")
    for segment in decoded.split("/"):
        if segment in (".", ".."):
            raise HostGuardError("HOST_PATH_INVALID", "path traversal is not allowed")
    if PATH_ESCAPE.search(decoded):
        raise HostGuardError("HOST_PATH_INVALID", "path traversal is not allowed")
    return decoded


def _deny_headers() -> List[Tuple[bytes, bytes]]:
    return [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"cache-control", b"no-store"),
        (b"x-contentops-host-guard", b"deny-by-default"),
    ]


async def _deny(send, code: str, detail: str) -> None:
    body = json.dumps({"error": code, "detail": detail}, ensure_ascii=False).encode("utf-8")
    await send({"type": "http.response.start", "status": 403, "headers": _deny_headers()})
    await send({"type": "http.response.body", "body": body})


class GuardMiddleware:
    """ASGI middleware that refuses unsafe host requests before upstream."""

    def __init__(self, app, policy: Optional[HostPolicy] = None) -> None:
        self.app = app
        self.policy = policy or HostPolicy()

    async def __call__(self, scope, receive, send):
        scope_type = scope.get("type")
        if scope_type == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope_type == "websocket":
            # No websocket route is authorised, now or after an upstream change.
            # Closing here keeps the guard the single policy point instead of
            # forwarding a scope it never inspected.
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope_type != "http":
            return

        method = str(scope.get("method") or "").upper()
        sensitive_headers = [key.lower() for key, _ in scope.get("headers") or []
                             if key.lower() in (b"host", b"origin")]
        if sensitive_headers.count(b"host") != 1 or sensitive_headers.count(b"origin") > 1:
            await _deny(send, "HOST_HEADERS_AMBIGUOUS", "Host and Origin headers must not be duplicated")
            return
        headers = _headers(scope)

        try:
            path = _normalise_path(str(scope.get("path") or ""))
        except HostGuardError as exc:
            await _deny(send, exc.code, exc.detail)
            return

        if not _host_allowed(headers.get("host", "")):
            await _deny(send, "HOST_HEADER_INVALID", "Host must be a loopback name")
            return
        if not _origin_allowed(headers.get("origin", "")):
            await _deny(send, "HOST_ORIGIN_INVALID", "Origin must be loopback or absent")
            return

        if (method == "POST" and self.policy.allow_offline_tasks
                and path in {"/api/contentops/draft-task", "/api/contentops/evidence-draft", "/api/contentops/agent-workspace", "/api/contentops/agent-proposal", "/api/contentops/agent-approval-inspection", "/api/contentops/agent-cancel", "/api/contentops/agent-collect", "/api/contentops/windows-sandbox-review"}
                and not _same_origin(headers.get("host", ""), headers.get("origin", ""))):
            await _deny(send, "HOST_CSRF_DENIED", "task submission requires the same loopback origin")
            return

        ok, code = self.policy.safe_route(method, path)
        if not ok:
            await _deny(send, code, f"{method} {path} is not in the host read allowlist")
            return

        if method == "OPTIONS":
            allow = b"GET, HEAD, OPTIONS"
            if self.policy.allow_offline_tasks:
                if path in {"/api/contentops/draft-task", "/api/contentops/evidence-draft", "/api/contentops/agent-workspace", "/api/contentops/agent-proposal", "/api/contentops/agent-approval-inspection", "/api/contentops/agent-cancel", "/api/contentops/agent-collect", "/api/contentops/windows-sandbox-review"}:
                    allow = b"POST, OPTIONS"
                elif (path in {"/api/contentops/profiles", "/api/contentops/projects", "/api/contentops/draft-tasks", "/api/contentops/status", "/api/contentops/project-readiness", "/api/contentops/skills/video-script"}
                      or path in {"/contentops/offline-task",
                                  "/contentops/offline-task.js",
                                  "/contentops/offline-task.css"}
                      or OFFLINE_TASK_STATUS_PATH.fullmatch(path)
                      or OFFLINE_TASK_DRAFT_PATH.fullmatch(path)):
                    allow = b"GET, OPTIONS"
                elif OFFLINE_TASK_ARTIFACTS_PATH.fullmatch(path):
                    allow = b"GET, OPTIONS"
                elif OFFLINE_PROFILE_DETAIL_PATH.fullmatch(path):
                    allow = b"GET, OPTIONS"
            await send({
                "type": "http.response.start",
                "status": 204,
                "headers": [
                    (b"allow", allow),
                    (b"cache-control", b"no-store"),
                    (b"x-contentops-host-guard", b"deny-by-default"),
                ],
            })
            await send({"type": "http.response.body", "body": b""})
            return

        async def guarded_send(message):
            if message.get("type") == "http.response.start":
                headers_out = list(message.get("headers") or [])
                headers_out = [
                    (key, value) for key, value in headers_out
                    if key.lower() not in (b"access-control-allow-origin",)
                ]
                headers_out.extend([
                    (b"cache-control", b"no-store"),
                    (b"x-contentops-host-guard", b"deny-by-default"),
                ])
                message = {**message, "headers": headers_out}
            await send(message)

        await self.app(scope, receive, guarded_send)
