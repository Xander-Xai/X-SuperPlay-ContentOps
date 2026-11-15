"""Operator CLI for the guarded Easel host.

    python scripts/easel_host.py status
    python scripts/easel_host.py serve [--port 7861]
    python scripts/easel_host.py status --workbench
    python scripts/easel_host.py serve --workbench
    python scripts/easel_host.py status --offline-tasks-only
    python scripts/easel_host.py serve --offline-tasks-only [--port 7862]

`serve` binds loopback only. The production host refuses every mutation; the
workbench candidate enables project-bound offline scaffold and evidence-draft
routes. These routes make no Agent, model, gateway or provider call. It does
not install FastAPI, uvicorn, OpenClaw or
browser dependencies; a missing dependency is reported as HOST_BLOCKED, not
silently installed.

`--workbench` reports or serves the workbench instance named by
`runtime/easel-workbench-overlay.json` (or the path in CONTENTOPS_EASEL_WORKBENCH)
instead of `.runtime/easel`. The workbench is the same upstream code plus a
declared tuning layer, so its bytes are verified in overlay mode: the upstream
baseline must match the pinned commit, and the recorded tuning is reported
separately.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.easel.host import (  # noqa: E402
    DEFAULT_OFFLINE_TASK_PORT, DEFAULT_PORT, HostError, host_status,
    offline_task_host_status, serve, serve_offline_tasks,
)


def _workbench_tree() -> Optional[Path]:
    """The workbench instance named by the overlay record, if it exists.

    Keeping this in the CLI rather than in host.py means ``host.py`` stays a
    library: it receives a tree and reports on it, and never needs to know that
    an overlay record exists.
    """
    record_path = ROOT / "runtime" / "easel-workbench-overlay.json"
    if not record_path.is_file():
        return None
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or not isinstance(record.get("instance"), dict):
        return None
    instance = record["instance"]
    env_name = instance.get("path_env") or ""
    if not isinstance(env_name, str):
        return None
    raw = os.environ.get(env_name, "").strip() if env_name else ""
    raw = raw or instance.get("path")
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw.strip()).expanduser()
    return path if path.is_absolute() and path.is_dir() else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="report whether the pinned host can be served")
    status.add_argument("--json", action="store_true")
    status.add_argument("--verify-bytes", action="store_true",
                        help="also compare the runtime tree with the pinned upstream commit "
                             "(uses a pinned local index when available; serve always does this)")
    status.add_argument("--workbench", action="store_true",
                        help="report the workbench instance instead of .runtime/easel")
    status.add_argument("--offline-tasks-only", action="store_true",
                        help="report readiness for the isolated ContentOps offline panel")
    run = sub.add_parser("serve", help="serve the guarded host on 127.0.0.1")
    run.add_argument("--port", type=int)
    run.add_argument("--workbench", action="store_true",
                     help="serve the workbench instance instead of .runtime/easel")
    run.add_argument("--offline-tasks-only", action="store_true",
                     help="serve only the ContentOps offline panel/API, without importing Easel")
    args = parser.parse_args()

    if getattr(args, "offline_tasks_only", False) and getattr(args, "workbench", False):
        parser.error("--offline-tasks-only and --workbench are separate host modes")
    if args.command == "serve" and args.port is None:
        args.port = (DEFAULT_OFFLINE_TASK_PORT if getattr(args, "offline_tasks_only", False)
                     else DEFAULT_PORT)

    if getattr(args, "offline_tasks_only", False):
        if args.command == "status":
            payload = offline_task_host_status()
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0 if payload["state"] == "HOST_READY" else 4
        try:
            print(f"Starting offline panel at http://127.0.0.1:{args.port}/contentops/offline-task",
                  file=sys.stderr, flush=True)
            serve_offline_tasks(ROOT, port=args.port)
        except HostError as exc:
            print(json.dumps({"ok": False, "error": exc.code, "detail": exc.detail},
                             ensure_ascii=False, indent=2))
            return 4
        return 0

    tree = None
    if getattr(args, "workbench", False):
        tree = _workbench_tree()
        if tree is None:
            print(json.dumps({"ok": False, "error": "WORKBENCH_ABSENT",
                              "detail": "no workbench instance at the path the overlay "
                                        "record names (set CONTENTOPS_EASEL_WORKBENCH)"}),
                  ensure_ascii=False, indent=2)
            return 4

    if args.command == "status":
        payload = host_status(ROOT, verify_bytes=args.verify_bytes, tree=tree)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["state"] == "HOST_READY" else 4

    try:
        if tree is not None:
            print(f"Starting candidate host; offline panel: http://127.0.0.1:{args.port}/contentops/offline-task",
                  file=sys.stderr, flush=True)
        serve(ROOT, port=args.port, tree=tree)
    except HostError as exc:
        print(json.dumps({"ok": False, "error": exc.code, "detail": exc.detail},
                         ensure_ascii=False, indent=2))
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
