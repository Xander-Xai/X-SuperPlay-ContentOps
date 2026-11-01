"""Lifecycle helpers for the pinned Easel host.

This module never edits upstream Easel and never starts the upstream entry point
directly. The upstream ``web/app.py`` binds ``0.0.0.0`` and allows ``CORS *``;
this module serves the same ASGI app through :class:`GuardMiddleware` on a
loopback address only.

Importing FastAPI/uvicorn or the upstream app is deferred to the moment a host
is actually served, so status checks and tests remain stdlib-only.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .guard import GuardMiddleware, HostPolicy

BIND_HOST = "127.0.0.1"
DEFAULT_PORT = 7861
HOST_APP = Path(".runtime") / "easel" / "web" / "app.py"
HOST_CLI = Path(".runtime") / "easel" / "easel" / "cli.py"
LOCK = Path("runtime") / "easel.lock.json"


class HostError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def _pin(root: Path) -> Dict[str, Any]:
    path = root / LOCK
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def host_status(root: Path) -> Dict[str, Any]:
    """Report whether the pinned host can be served, without starting it."""
    root = Path(root)
    blockers = []
    if not (root / HOST_APP).is_file():
        blockers.append("HOST_APP_MISSING")
    if not (root / HOST_CLI).is_file():
        blockers.append("HOST_CLI_MISSING")
    lock = _pin(root)
    if not lock.get("tag") or not lock.get("commit"):
        blockers.append("HOST_PIN_MISSING")
    for module in ("fastapi", "uvicorn"):
        if importlib.util.find_spec(module) is None:
            blockers.append(f"HOST_DEPENDENCY_MISSING:{module}")

    return {
        "schema": "contentops.easel-host/v1",
        "state": "HOST_BLOCKED" if blockers else "HOST_READY",
        "blockers": blockers,
        "pin": {"tag": lock.get("tag"), "commit": lock.get("commit")},
        "app": (root / HOST_APP).relative_to(root).as_posix() if (root / HOST_APP).is_file() else HOST_APP.as_posix(),
        "bind_host": BIND_HOST,
        "default_port": DEFAULT_PORT,
        "mutations": "DENIED",
        "allowed_methods": ["GET", "HEAD", "OPTIONS"],
        "note": "HOST_READY means this process may serve read-only pages. It is not "
                "publication authority, and it does not approve any content.",
    }


def load_upstream_app(root: Path):
    """Import the pinned upstream ASGI app. Never called by a status check."""
    root = Path(root).resolve()
    app_path = root / HOST_APP
    if not app_path.is_file():
        raise HostError("HOST_APP_MISSING", app_path.as_posix())
    easel_root = str(root / ".runtime" / "easel")
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


def serve(root: Path, port: int = DEFAULT_PORT, policy: Optional[HostPolicy] = None) -> None:
    """Serve the guarded host on loopback. This function blocks."""
    status = host_status(root)
    if status["state"] != "HOST_READY":
        raise HostError("HOST_BLOCKED", ", ".join(status["blockers"]))
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise HostError("HOST_PORT_INVALID", str(port))
    try:
        import uvicorn  # type: ignore
    except ImportError:
        raise HostError("HOST_DEPENDENCY_MISSING", "uvicorn") from None

    upstream = load_upstream_app(root)
    guarded = GuardMiddleware(upstream, policy or HostPolicy())
    uvicorn.run(
        guarded,
        host=BIND_HOST,
        port=port,
        log_level="warning",
        proxy_headers=False,
        server_header=False,
    )
