#!/usr/bin/env python3
"""One entry point for the GZH and XHS graphic workflows: locate, verify, describe.

Usage:
    python scripts/graphic_workflow.py status --workflow gzh
    python scripts/graphic_workflow.py status --workflow xhs
    python scripts/graphic_workflow.py verify --workflow xhs --root D:/Software/XHS/xhs_未来智能
    python scripts/graphic_workflow.py plan --workflow gzh --json

Both workflows are installed by the operator outside this repository and are
never copied into it. This command reads a verified root, verifies every locked
byte, and prints the operator operations. It never executes a workflow step,
starts the Easel host, drafts, or publishes.

Exit codes: 0 = verified/plan printed, 4 = BLOCKED.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _module(workflow: str):
    if workflow == "gzh":
        from contentops.gzh import runtime as module
    elif workflow == "xhs":
        from contentops.xhs import runtime as module
    else:  # pragma: no cover - argparse restricts the value
        raise SystemExit(f"unknown workflow {workflow!r}")
    return module


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("status", "verify", "plan"))
    parser.add_argument("--workflow", choices=("gzh", "xhs"), required=True)
    parser.add_argument("--root", default=None,
                        help="workflow root (default: CONTENTOPS_GZH_ROOT / CONTENTOPS_XHS_ROOT)")
    parser.add_argument("--lock", default=None,
                        help="trusted lock (default: runtime/<workflow>-runtime.lock.json)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    module = _module(args.workflow)
    blocked = module.GzhBlocked if args.workflow == "gzh" else module.XhsBlocked
    lock_path = Path(args.lock) if args.lock else None
    root = Path(args.root) if args.root else None

    try:
        if args.command == "status":
            result = module.status(root, lock_path=lock_path, repo_root=ROOT)
        elif args.command == "verify":
            result = module.verify(module.locate_root(root, repo_root=ROOT),
                                   module.load_lock(lock_path), repo_root=ROOT)
        else:
            result = module.plan(root, lock_path=lock_path, repo_root=ROOT)
    except blocked as exc:
        result = {"state": "BLOCKED", "code": exc.code, "detail": exc.detail}

    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
    return 0 if result.get("state") != "BLOCKED" else 4


if __name__ == "__main__":
    raise SystemExit(main())
