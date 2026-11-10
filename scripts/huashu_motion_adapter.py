#!/usr/bin/env python3
"""Describe and verify the pinned Huashu Motion adapter without executing it."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media import huashu_motion  # noqa: E402
from process_utils import hidden_run  # noqa: E402


def _git_probe(root: Path, *args: str) -> tuple[int, str]:
    result = hidden_run(["git", "-C", str(root), *args], timeout=30)
    return result.returncode, (result.stdout or "").strip()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="verify the pinned runtime identity without running om")
    status.add_argument("--root", type=Path, default=huashu_motion.DEFAULT_RUNTIME)
    plan = sub.add_parser("plan", help="describe one upstream operation without invoking it")
    plan.add_argument("operation", choices=sorted(huashu_motion.OPERATIONS))
    request = sub.add_parser("request", help="write a blocked/not-executed receipt without invoking om")
    request.add_argument("operation", choices=sorted(huashu_motion.OPERATIONS))
    request.add_argument("--project", type=Path, required=True)
    request.add_argument("--root", type=Path, default=huashu_motion.DEFAULT_RUNTIME)
    args = parser.parse_args(argv)

    if args.command == "status":
        result = huashu_motion.verify_runtime(args.root, git_probe=_git_probe)
    elif args.command == "plan":
        result = huashu_motion.describe_operation(args.operation)
    else:
        runtime = huashu_motion.verify_runtime(args.root, git_probe=_git_probe)
        result = huashu_motion.request_operation(args.operation, runtime=runtime)
        result["receipt_path"] = str(huashu_motion.write_operation_receipt(args.project, result))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("status") == "TRUSTED_RUNTIME" else 2


if __name__ == "__main__":
    raise SystemExit(main())
