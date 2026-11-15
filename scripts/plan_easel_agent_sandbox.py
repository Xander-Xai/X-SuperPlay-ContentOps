#!/usr/bin/env python3
"""Build an unapproved Linux sandbox plan from an existing workspace/package.

Read a JSON object from stdin with absolute Linux paths `workspace`, `runtime`,
`runtime_manifest`, and `filter_build_receipt`. This command does not start the plan or a model.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.easel.agent_sandbox import (SandboxPlanError, _ordinary,  # noqa: E402
                                           build_linux_sandbox_plan)
from contentops.easel.agent_workspace import read_agent_workspace  # noqa: E402
from resolve_easel import resolve_easel_workbench  # noqa: E402


def main() -> int:
    try:
        request_bytes = sys.stdin.buffer.read(32769)
        if len(request_bytes) > 32768:
            raise ValueError("request exceeds 32 KiB")
        request = json.loads(request_bytes.decode("utf-8"))
        if not isinstance(request, dict) or set(request) != {"workspace", "runtime", "runtime_manifest", "filter_build_receipt"}:
            raise ValueError("request requires workspace, runtime, runtime_manifest and filter_build_receipt")
        workspace = _ordinary(Path(request["workspace"]), directory=True)
        try:
            parts = workspace.relative_to(ROOT.resolve(strict=True)).parts
        except ValueError:
            raise ValueError("workspace must be inside this repository") from None
        if len(parts) != 5 or parts[0] != "projects" or parts[2:4] != ("work", "easel-agent-workspaces"):
            raise ValueError("workspace must be a direct project Agent run")
        workspace_record_path = _ordinary(workspace / "workspace.json", directory=False)
        workspace_bytes = workspace_record_path.read_bytes()
        if len(workspace_bytes) > 1024 * 1024:
            raise ValueError("workspace record exceeds size limit")
        workspace_record = json.loads(workspace_bytes.decode("utf-8"))
        if not isinstance(workspace_record, dict) or not isinstance(workspace_record.get("account"), str):
            raise ValueError("workspace record is invalid")
        def current_workspace():
            state = read_agent_workspace(repo_root=ROOT, account=workspace_record["account"],
                                         project_slug=parts[1], run_id=parts[4])
            if state["input_state"] != "CURRENT" or state["preparation"] != "PREPARED":
                raise ValueError("workspace is stale or cancelled")
            if state["frontend_state"] != "CURRENT_VERIFIED":
                raise ValueError("candidate frontend build is not currently verified")
            if workspace_record_path.read_bytes() != workspace_bytes:
                raise ValueError("workspace record changed during planning")
            return state
        state = current_workspace()
        resolved_easel = resolve_easel_workbench(ROOT)
        if (resolved_easel.get("status") != "OK"
                or resolved_easel.get("commit") != workspace_record.get("easel_commit")):
            raise ValueError("candidate Easel upstream, overlay or profile verification failed")
        manifest = _ordinary(Path(request["runtime_manifest"]), directory=False)
        manifest_bytes = manifest.read_bytes()
        if len(manifest_bytes) > 16 * 1024 * 1024:
            raise ValueError("runtime manifest exceeds size limit")
        record = json.loads(manifest_bytes.decode("utf-8"))
        if (not isinstance(record, dict)
                or record.get("schema") != "contentops.easel-agent-runtime-package/v1"
                or record.get("provenance") != "UNVERIFIED"
                or record.get("execution_authorized") is not False
                or record.get("node_binary_format") != "ELF64-x86-64"
                or not isinstance(record.get("openclaw_version"), str)
                or not isinstance(record.get("fs_safe_version"), str)
                or not isinstance(record.get("native_import_receipt_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", record["native_import_receipt_sha256"])
                or not isinstance(record.get("native_archive_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", record["native_archive_sha256"])
                or not isinstance(record.get("files"), dict)):
            raise ValueError("invalid candidate runtime manifest")
        filter_path = _ordinary(Path(request["filter_build_receipt"]), directory=False)
        filter_bytes = filter_path.read_bytes()
        if len(filter_bytes) > 32768:
            raise ValueError("filter build receipt exceeds size limit")
        filter_record = json.loads(filter_bytes.decode("utf-8"))
        plan = build_linux_sandbox_plan(workspace=workspace,
                                        runtime=Path(request["runtime"]),
                                        runtime_files=record["files"], filter_build_receipt=filter_record)
        metadata_path = _ordinary(Path(request["runtime"]) / "openclaw" / "package.json", directory=False)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (not isinstance(metadata, dict) or metadata.get("name") != "openclaw"
                or metadata.get("version") != record["openclaw_version"]):
            raise ValueError("OpenClaw package version differs from its manifest")
        base = Path(request["runtime"]) / "openclaw" / "node_modules" / "@openclaw"
        fs_path = _ordinary(base / "fs-safe" / "package.json", directory=False)
        native_path = _ordinary(base / "fs-safe-linux-x64-gnu" / "package.json", directory=False)
        fs_metadata = json.loads(fs_path.read_text(encoding="utf-8"))
        native_metadata = json.loads(native_path.read_text(encoding="utf-8"))
        native_prefix = "openclaw/node_modules/@openclaw/fs-safe-linux-x64-gnu/"
        if (not isinstance(fs_metadata, dict) or not isinstance(native_metadata, dict)
                or fs_metadata.get("name") != "@openclaw/fs-safe"
                or native_metadata.get("name") != "@openclaw/fs-safe-linux-x64-gnu"
                or fs_metadata.get("version") != record["fs_safe_version"]
                or native_metadata.get("version") != record["fs_safe_version"]
                or not any(key.startswith(native_prefix) and key.endswith(".node") for key in record["files"])):
            raise ValueError("Linux fs-safe native package is missing or mismatched")
        plan["runtime_manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        plan["runtime_provenance"] = "UNVERIFIED"
        plan["openclaw_version"] = record["openclaw_version"]
        plan["fs_safe_version"] = record["fs_safe_version"]
        plan["native_import_receipt_sha256"] = record.get("native_import_receipt_sha256")
        plan["native_archive_sha256"] = record.get("native_archive_sha256")
        plan["filter_build_receipt_sha256"] = hashlib.sha256(filter_bytes).hexdigest()
        current_workspace()
        plan["account"] = state["account"]
        plan["project"] = state["project"]
        plan["workspace_record_sha256"] = hashlib.sha256(workspace_bytes).hexdigest()
        plan["easel_commit"] = resolved_easel["commit"]
        plan["easel_verification"] = resolved_easel["verification"]
    except (OSError, UnicodeDecodeError, ValueError, TypeError, KeyError, SandboxPlanError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 4
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
