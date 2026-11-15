#!/usr/bin/env python3
"""Prepare a Windows sandbox specification for review; never launch a process.

The runtime must already exist at projects/<runtime-project>/work/
easel-windows-runtime/<package>/ and its sibling <package>.json must contain an
exhaustive SHA-256 map. The task remains bound to its own project and account.
No dependency is installed and no execution permission is granted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.easel.agent_workspace import read_agent_workspace  # noqa: E402
from contentops.easel.offline_task import OfflineTaskError, _ensure_child_dir, _linklike, _project_file, _safe_project  # noqa: E402
from contentops.easel.windows_sandbox import SandboxPlanError, build_windows_sandbox_spec  # noqa: E402
from contentops.easel.windows_process import WindowsProcessError, review_windows_candidate  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="existing project slug")
    parser.add_argument("--account", required=True, help="project-bound account slug")
    parser.add_argument("--run-id", required=True, help="prepared workspace UUID")
    parser.add_argument("--package", required=True, help="existing Windows runtime package slug")
    parser.add_argument("--runtime-project", help="project containing the read-only package (defaults to task project)")
    parser.add_argument("--write-receipt", action="store_true",
                        help="write a new project-local review receipt; never overwrite or execute")
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", args.package):
            raise ValueError("invalid package slug")
        project, _ = _safe_project(ROOT, args.project)
        runtime_project, _ = _safe_project(ROOT, args.runtime_project or args.project)
        state = read_agent_workspace(repo_root=ROOT, account=args.account,
                                     project_slug=args.project, run_id=args.run_id)
        if state.get("input_state") != "CURRENT" or state.get("preparation") != "PREPARED":
            raise ValueError("workspace is stale, unsafe, or cancelled")
        package_base = f"work/easel-windows-runtime/{args.package}"
        manifest_path = _project_file(runtime_project, package_base + ".json")
        raw = manifest_path.read_bytes()
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError("runtime manifest is too large")
        manifest = json.loads(raw.decode("utf-8"))
        if (not isinstance(manifest, dict)
                or manifest.get("schema") != "contentops.easel-windows-runtime-package/v1"
                or manifest.get("package") != package_base
                or not isinstance(manifest.get("files"), dict)):
            raise ValueError("runtime manifest is invalid")
        result = build_windows_sandbox_spec(
            workspace=project / "work" / "easel-agent-workspaces" / args.run_id,
            runtime=runtime_project / package_base, runtime_files=manifest["files"],
            runtime_base=runtime_project / "work" / "easel-windows-runtime")
        result["launch_fields"] = review_windows_candidate(result)["status"]
        current = read_agent_workspace(repo_root=ROOT, account=args.account,
                                       project_slug=args.project, run_id=args.run_id)
        if current.get("input_state") != "CURRENT" or current.get("preparation") != "PREPARED":
            raise ValueError("workspace changed or was cancelled during review")
        manifest_path = _project_file(runtime_project, package_base + ".json")
        with manifest_path.open("rb") as stream:
            if stream.read(16 * 1024 * 1024 + 1) != raw:
                raise ValueError("runtime manifest changed during review")
        result["runtime_provenance"] = "NOT_VERIFIED"
        result["runtime_project"] = args.runtime_project or args.project
        if args.write_receipt:
            receipts = _ensure_child_dir(project, "receipts")
            receipt_path = receipts / f"easel-windows-sandbox-plan-{args.run_id}.json"
            if _linklike(receipt_path):
                raise ValueError("sandbox plan receipt is linked")
            receipt = {"schema": "contentops.easel-windows-sandbox-plan-receipt/v1",
                       "run_id": args.run_id, "account": args.account, "project": args.project,
                       "runtime_project": result["runtime_project"], "package": args.package,
                       "runtime_manifest_sha256": hashlib.sha256(raw).hexdigest(),
                       "spec_sha256": result["spec_sha256"],
                       "candidate_argv_sha256": result["candidate_argv_sha256"],
                       "environment_block_sha256": result["environment_block_sha256"],
                       "launch_fields": result["launch_fields"],
                       "execution_route": result["execution_route"], "gateway_route": result["gateway_route"],
                       "sandbox_identity": result["sandbox_identity"],
                       "status": "REVIEW_ONLY", "isolation": "NOT_VERIFIED",
                       "execution": "NOT_AUTHORIZED", "production_ready": False,
                       "publish_authorized": False}
            with receipt_path.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(receipt, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            result["receipt"] = receipt_path.relative_to(project).as_posix()
    except (OfflineTaskError, SandboxPlanError, WindowsProcessError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)[:300],
                          "execution": "NOT_AUTHORIZED"}, ensure_ascii=False, indent=2))
        return 4
    print(json.dumps({"status": "REVIEW_ONLY", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
