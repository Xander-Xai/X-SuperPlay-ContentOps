#!/usr/bin/env python3
"""Locate and verify a locally installed GZH workflow. Never run or publish.

Usage:
    python scripts/gzh_runtime.py status
    python scripts/gzh_runtime.py verify --root D:/Software/GZH/gzh_未来智能
    python scripts/gzh_runtime.py plan --json

``status`` reports what it found; ``verify`` exits 4 unless every locked byte
matches and the identity contract is the expected one; ``plan`` prints the
operator operations and always reports ``execution_authorized: false`` and
``publish_authorized: false``.

The vendored workflow is not redistributed by this repository (Issue #56). This
command reads a root the operator installed elsewhere; it does not copy it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.gzh.runtime import (  # noqa: E402
    BLOCKED,
    GzhBlocked,
    locate_root,
    load_lock,
    plan,
    status,
    verify,
)

BLOCKED_EXIT = 4


def _print(payload, as_json: bool) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2) if as_json else payload)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("status", "verify", "plan"))
    parser.add_argument("--root", default=None,
                        help="workflow root (default: CONTENTOPS_GZH_ROOT)")
    parser.add_argument("--lock", default=None,
                        help="trusted lock (default: runtime/gzh-runtime.lock.json)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    lock_path = Path(args.lock) if args.lock else None
    root = Path(args.root) if args.root else None

    if args.command == "status":
        result = status(root, lock_path=lock_path, repo_root=ROOT)
        _print(result, args.json)
        return 0 if result["state"] != BLOCKED else BLOCKED_EXIT

    if args.command == "verify":
        try:
            result = verify(locate_root(root, repo_root=ROOT),
                            load_lock(lock_path), repo_root=ROOT)
        except GzhBlocked as blocked:
            _print({"state": BLOCKED, "code": blocked.code,
                    "detail": blocked.detail}, args.json)
            return BLOCKED_EXIT
        _print(result, args.json)
        return 0

    result = plan(root, lock_path=lock_path, repo_root=ROOT)
    _print(result, args.json)
    return 0 if result["state"] != BLOCKED else BLOCKED_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
