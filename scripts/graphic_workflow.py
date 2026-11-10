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

from contentops.platforms.registry import workflow_routes  # noqa: E402

_ROUTE = {"gzh": "wechat_article", "x": "x"}


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
    parser.add_argument("--workflow", choices=("gzh", "x", "video"), required=True)
    parser.add_argument("--root", default=None,
                        help="workflow root for gzh, or the repository root for x")
    parser.add_argument("--lock", default=None,
                        help="trusted lock (default: runtime/<workflow>-runtime.lock.json)")
    parser.add_argument("--account", default=None, help="x only: account JSON path")
    parser.add_argument("--project", default=None, help="project directory for x, or the finished film for video handoff")
    parser.add_argument("--handoff", action="store_true",
                        help="video only: pack the finished film and build the Xiaohongshu argv. Does not run the uploader.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.workflow == "video":
        routes = [
            item for item in workflow_routes(ROOT)
            if item["platform_id"] in {
                "douyin", "bilibili", "xiaohongshu_video", "shipinhao", "youtube",
            }
        ]
        result = {
            "schema": "contentops.video-workflow-status/v1",
            "state": "DESCRIBE_ONLY",
            "routes": routes,
            "publish_authorized": False,
            "production_ready": False,
            "skill_declared": False,
        }
        if args.handoff:
            if not args.project:
                result["state"] = "BLOCKED"
                result["code"] = "PROJECT_REQUIRED"
                result["detail"] = "小红书投递需要已完成的项目目录"
                print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
                return 4
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "video_deliver", ROOT / "scripts" / "video_deliver.py")
            deliver = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(deliver)
            video_ids = [
                item["platform_id"] for item in routes
                if any(command["script"] == "scripts/video_deliver.py" for command in item["commands"])
            ]
            joined = ",".join(video_ids)
            pack_code = deliver.main(["pack", "--project", args.project, "--platforms", joined])
            dispatch_code = deliver.main([
                "dispatch", "--project", args.project, "--platforms", joined,
            ])
            result["handoff"] = {
                "platform_ids": video_ids,
                "pack_exit": pack_code,
                "dispatch_exit": dispatch_code,
                "execute": False,
                "publish_authorized": False,
                "production_ready": False,
            }
            result["state"] = "HANDOFF_READY" if pack_code == 0 else "BLOCKED"
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
        return 0 if result["state"] != "BLOCKED" else 4

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

    route = workflow_routes(ROOT, _ROUTE[args.workflow])[0]
    result = dict(result)
    result["transport_route"] = route
    result["publish_authorized"] = False
    result["production_ready"] = False

    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
    return 0 if result.get("state") != "BLOCKED" else 4


if __name__ == "__main__":
    raise SystemExit(main())
