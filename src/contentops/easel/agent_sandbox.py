"""Construct, but never execute, the candidate Linux Agent isolation command.

This module does not establish a security boundary. A sandbox must first be
independently verified, including nested tools and process escape, and a real
task must receive its own grant before any caller may execute a command.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
from pathlib import Path
from typing import Any

from .agent_workspace import AGENT_POLICY
from .path_safety import is_linklike


class SandboxPlanError(ValueError):
    pass


def _ordinary(path: Path, *, directory: bool) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise SandboxPlanError("sandbox paths must be absolute without parent traversal")
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        if is_linklike(current):
            raise SandboxPlanError("sandbox paths cannot contain links")
    if not (path.is_dir() if directory else path.is_file()):
        raise SandboxPlanError("required sandbox path is unavailable")
    return path.resolve(strict=True)


def build_linux_sandbox_plan(*, workspace: Path, runtime: Path,
                             runtime_files: dict[str, str],
                             filter_build_receipt: dict[str, Any]) -> dict[str, Any]:
    """Build a reviewable bwrap argv for a separately packaged Linux runtime.

    Runtime must be a dedicated package with an exhaustive file SHA-256 map;
    it must contain bin/node, openclaw/openclaw.mjs, and packaged Linux shared
    libraries under system/lib, system/lib64 or system/usr/lib. Only declared
    files are made visible. No host home, environment or network
    namespace is inherited. This alone does not prohibit subprocesses or prove
    OpenClaw's tool policy, and the returned argv is NOT authorized to run.
    """
    if os.name != "posix":
        raise SandboxPlanError("the candidate launcher must be prepared on Linux")
    work = _ordinary(Path(workspace), directory=True)
    cancellation = work / "cancel.json"
    if cancellation.exists() or is_linklike(cancellation):
        raise SandboxPlanError("prepared task was cancelled or cancellation state is unsafe")
    package = _ordinary(Path(runtime), directory=True)
    input_dir = _ordinary(work / "input", directory=True)
    output_dir = _ordinary(work / "output", directory=True)
    manifest_path = _ordinary(work / "workspace.json", directory=False)
    try:
        record = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise SandboxPlanError("workspace manifest is unreadable") from None
    if not isinstance(record, dict) or record.get("schema") != "contentops.easel-agent-workspace/v1":
        raise SandboxPlanError("workspace manifest is invalid")
    inputs = record.get("input_sha256")
    if not isinstance(inputs, dict) or not inputs or not isinstance(runtime_files, dict) or not runtime_files:
        raise SandboxPlanError("input or runtime manifest is missing")

    def verify_tree(base: Path, expected: dict[str, str]) -> None:
        seen = set()
        for path in base.rglob("*"):
            if is_linklike(path):
                raise SandboxPlanError("linked files are forbidden in sandbox inputs")
            if path.is_dir():
                continue
            if not path.is_file():
                raise SandboxPlanError("special files are forbidden in sandbox inputs")
            rel = path.relative_to(base).as_posix()
            digest = expected.get(rel)
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise SandboxPlanError("undeclared or invalid sandbox file")
            sha = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    sha.update(chunk)
            if sha.hexdigest() != digest:
                raise SandboxPlanError("sandbox file digest mismatch")
            seen.add(rel)
        if seen != set(expected):
            raise SandboxPlanError("sandbox files are missing")

    verify_tree(input_dir, inputs)
    verify_tree(package, runtime_files)
    if (not {"bin/node", "openclaw/openclaw.mjs", "lib/no_subprocess.so", "lib/sandbox-bootstrap.cjs"}.issubset(runtime_files)
            or not {"prompt.txt", "openclaw.json"}.issubset(inputs)):
        raise SandboxPlanError("runtime does not contain its declared entry points")
    with (package / "bin" / "node").open("rb") as stream:
        header = stream.read(20)
    if (len(header) != 20 or header[:6] != b"\x7fELF\x02\x01"
            or struct.unpack_from("<H", header, 18)[0] != 62):
        raise SandboxPlanError("candidate Node is not a Linux x86-64 ELF binary")
    bootstrap_source = Path(__file__).resolve().parents[3] / "extensions" / "easel-workbench" / "sandbox" / "sandbox-bootstrap.cjs"
    if (_ordinary(bootstrap_source, directory=False).read_bytes()
            != (package / "lib" / "sandbox-bootstrap.cjs").read_bytes()):
        raise SandboxPlanError("sandbox bootstrap differs from repository source")
    filter_source = bootstrap_source.with_name("no_subprocess.c")
    filter_source_sha = hashlib.sha256(_ordinary(filter_source, directory=False).read_bytes()).hexdigest()
    if (not isinstance(filter_build_receipt, dict)
            or filter_build_receipt.get("schema") != "contentops.easel-sandbox-filter-build/v1"
            or filter_build_receipt.get("status") != "BUILT_UNVERIFIED"
            or filter_build_receipt.get("execution_authorized") is not False
            or filter_build_receipt.get("source_sha256") != filter_source_sha
            or filter_build_receipt.get("binary_sha256") != runtime_files["lib/no_subprocess.so"]):
        raise SandboxPlanError("filter build receipt does not match the source and package bytes")
    try:
        policy = json.loads((input_dir / "openclaw.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise SandboxPlanError("agent policy is unreadable") from None
    if policy != AGENT_POLICY:
        raise SandboxPlanError("agent policy does not match the required deny-all policy")
    library_mounts = []
    for source, target in (("system/lib", "/lib"), ("system/lib64", "/lib64"),
                           ("system/usr/lib", "/usr/lib")):
        directory = package / source
        if directory.is_dir():
            library_mounts.extend(["--ro-bind", str(directory), target])
    if not library_mounts:
        raise SandboxPlanError("a packaged Linux shared-library directory is required")
    argv = ["bwrap", "--die-with-parent", "--new-session", "--unshare-all",
            "--clearenv", "--proc", "/proc", "--dev", "/dev",
            "--tmpfs", "/tmp", "--dir", "/home", "--dir", "/home/agent",
            "--dir", "/usr", *library_mounts,
            "--ro-bind", str(input_dir), "/input",
            "--bind", str(output_dir), "/output",
            "--ro-bind", str(package), "/runtime",
            "--setenv", "HOME", "/home/agent", "--setenv", "TMPDIR", "/tmp",
            "--setenv", "OPENCLAW_STATE_DIR", "/tmp/openclaw",
            "--setenv", "OPENCLAW_CONFIG_PATH", "/input/openclaw.json",
            "--setenv", "LD_PRELOAD", "/runtime/lib/no_subprocess.so",
            "--chdir", "/output", "--", "/runtime/bin/node", "--require", "/runtime/lib/sandbox-bootstrap.cjs",
            "/runtime/openclaw/openclaw.mjs",
            "agent", "exec", "--message-file", "/input/prompt.txt", "--cwd", "/output",
            "--config", "/input/openclaw.json", "--code-mode", "direct",
            "--timeout", "120", "--json"]
    return {"schema": "contentops.easel-agent-sandbox-plan/v1", "argv": argv,
            "run_id": record.get("run_id"), "network": "NAMESPACE_REQUESTED",
            "execution": "NOT_AUTHORIZED", "isolation": "NOT_VERIFIED",
            "openclaw_policy": "INPUT_BOUND_NOT_VERIFIED",
            "filter_build_binding": "CONSISTENT_UNSIGNED",
            "missing": ["runtime_package_provenance", "linux_runtime_compatibility", "tool_policy_verification",
                        "preload_activation_and_process_restriction_verification", "isolation_verification", "task_grant"],
            "production_ready": False, "publish_authorized": False}
