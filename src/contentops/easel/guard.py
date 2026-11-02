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
from urllib.parse import unquote

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
SAFE_EXACT = frozenset({
    "/",
    "/onepage",
    "/favicon.ico",
    "/api/status",
    "/api/skills",
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

    ``allow_workbench_reads`` keeps the read-only UI useful. Mutations are not a
    flag: this release has no authorised mutation path, so a policy cannot turn
    one on by accident.
    """

    allow_workbench_reads: bool = True

    def safe_route(self, method: str, path: str) -> Tuple[bool, str]:
        method = method.upper()
        if method not in SAFE_METHODS:
            return False, "HOST_ROUTE_DENIED"
        if not self.allow_workbench_reads and path != "/api/status":
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
    if value.strip() == "null":
        return False
    match = re.match(r"^https?://([^/:]+)(?::\d{1,5})?$", value.strip(), re.IGNORECASE)
    if not match:
        return False
    return match.group(1).lower() in LOOPBACK_HOSTS


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

        ok, code = self.policy.safe_route(method, path)
        if not ok:
            await _deny(send, code, f"{method} {path} is not in the host read allowlist")
            return

        if method == "OPTIONS":
            await send({
                "type": "http.response.start",
                "status": 204,
                "headers": [
                    (b"allow", b"GET, HEAD, OPTIONS"),
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
