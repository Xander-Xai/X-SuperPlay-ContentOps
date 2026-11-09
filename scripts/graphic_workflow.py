#!/usr/bin/env python3
"""One entry point for the GZH and X editorial workflows: verify and describe.

Usage:
    python scripts/graphic_workflow.py status --workflow gzh
    python scripts/graphic_workflow.py plan --workflow x --json

GZH is installed by the operator outside this repository and is never
copied into it; X is this repository's own manual-only editorial gate. The
command verifies the workspace and prints the operator operations. It never
executes a workflow step, calls a platform API, starts the Easel host, drafts,
or publishes.

The XHS (Xiaohongshu) graphic workflow was removed on 2026-11-09 by operator
instruction: the whole Xiaohongshu platform belongs to the VIDEO line, so no
graphic workflow, adapter or lock remains in the repository.

For ``x``, ``--root`` means the repository root (default: this checkout) and
``--account`` / ``--project`` override the default account and project paths.

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
    elif workflow == "x":
        from contentops.x import runtime as module
    else:  # pragma: no cover - argparse restricts the value
        raise SystemExit(f"unknown workflow {workflow!r}")
    return module


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("status", "verify", "plan"))
    parser.add_argument("--workflow", choices=("gzh", "x"), required=True)
    parser.add_argument("--root", default=None,
                        help="workflow root for gzh, or the repository root for x")
    parser.add_argument("--lock", default=None,
                        help="trusted lock (default: runtime/<workflow>-runtime.lock.json)")
    parser.add_argument("--account", default=None, help="x only: account JSON path")
    parser.add_argument("--project", default=None, help="x only: project directory")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    module = _module(args.workflow)
    if args.workflow == "gzh":
        blocked = module.GzhBlocked
    else:
        blocked = module.XBlocked

    lock_path = Path(args.lock) if args.lock else None
    root = Path(args.root) if args.root else None

    try:
        if args.workflow == "x":
            repo_root = root or ROOT
            account = Path(args.account) if args.account else None
            project = Path(args.project) if args.project else None
            if args.command == "status":
                result = module.status(repo_root=repo_root, account=account, project=project)
            elif args.command == "verify":
                result = module.verify(repo_root=repo_root, account=account, project=project)
            else:
                result = module.plan(repo_root=repo_root, account=account, project=project)
        elif args.command == "status":
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
