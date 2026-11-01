"""Operator CLI for the guarded Easel host.

    python scripts/easel_host.py status
    python scripts/easel_host.py serve [--port 7861]

`serve` binds loopback only and refuses every mutation. It does not install
FastAPI, uvicorn, OpenClaw or browser dependencies; a missing dependency is
reported as HOST_BLOCKED, not silently installed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.easel.host import DEFAULT_PORT, HostError, host_status, serve  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="report whether the pinned host can be served")
    status.add_argument("--json", action="store_true")
    run = sub.add_parser("serve", help="serve the guarded host on 127.0.0.1")
    run.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    if args.command == "status":
        payload = host_status(ROOT)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["state"] == "HOST_READY" else 4

    try:
        serve(ROOT, port=args.port)
    except HostError as exc:
        print(json.dumps({"ok": False, "error": exc.code, "detail": exc.detail},
                         ensure_ascii=False, indent=2))
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
