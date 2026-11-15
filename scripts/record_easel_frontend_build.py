#!/usr/bin/env python3
"""Run the pinned frontend build and record its receipt in the same breath.

Why this exists
---------------
The workbench host refuses to serve browser assets without a build receipt that
binds the exact source commit, the reviewed lockfile, the toolchain that ran and
the full `dist` inventory. Recording that receipt by hand — hashing a dist tree
that already existed — would be provenance laundering: it would make a stale or
foreign build look freshly reviewed. So this script runs the two reviewed
commands itself and writes the record only after both succeeded.

Order of operations
-------------------
    read policy -> check the lockfile digest -> check the toolchain range
        -> refuse an existing dist -> npm ci -> npm run build
        -> hash the fresh dist -> write the manifest

Every refusal happens before the build, so nothing here can turn a failed build
into a recorded one.

Usage
-----
    python scripts/record_easel_frontend_build.py --workbench .runtime/easel-v030
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from process_utils import hidden_run  # noqa: E402
from verify_easel_runtime import _version_in_range  # noqa: E402

POLICY_PATH = ROOT / "runtime" / "easel-workbench-build-policy.json"
MANIFEST_PATH = ROOT / "runtime" / "easel-workbench-frontend-build.json"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _fail(message: str) -> None:
    print(f"REFUSED: {message}", file=sys.stderr)
    raise SystemExit(4)


def _resolve(executable: str) -> str:
    """CreateProcess does not try PATHEXT: `npm` is a .cmd and must be spelled out."""
    found = shutil.which(executable)
    if not found:
        _fail(f"{executable} is not on PATH")
    return found


def _tool_version(command: list[str]) -> str:
    command = [_resolve(command[0]), *command[1:]]
    result = hidden_run(command, timeout=60)
    if result.returncode != 0:
        _fail(f"{' '.join(command)} failed: {result.stderr.strip()[:200]}")
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workbench", required=True,
                        help="absolute path of the workbench instance that owns this build")
    args = parser.parse_args()

    from contentops.easel import pins

    engine = pins.workbench()
    workbench = Path(args.workbench).resolve()
    if not workbench.is_dir():
        _fail(f"workbench instance {workbench} does not exist")
    frontend = workbench / "web" / "frontend"

    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if policy.get("schema") != "contentops.easel-frontend-build-policy/v1":
        _fail("build policy schema is not the reviewed one")

    lock_path = frontend / "package-lock.json"
    if not lock_path.is_file():
        _fail(f"no package-lock.json under {frontend}")
    lock_digest = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    if lock_digest != policy.get("package_lock_sha256"):
        _fail("lockfile digest does not match the reviewed policy")

    node_version = _tool_version(["node", "--version"])
    npm_version = _tool_version(["npm", "--version"])
    toolchain = {"node": node_version, "npm": npm_version}
    toolchain_range = policy.get("toolchain_range") or {}
    if toolchain_range and not all(
            _version_in_range(toolchain.get(name, ""), toolchain_range.get(name, ""))
            for name in ("node", "npm")):
        _fail(f"toolchain {toolchain} is outside the reviewed range {toolchain_range}; "
              f"the recorded observation is {policy.get('observed')}")

    dist = frontend / "dist"
    if dist.exists() and any(dist.iterdir()):
        _fail(f"{dist} already has content; a receipt must describe a fresh build — "
              f"remove it deliberately and run this again")

    build_command = policy.get("build_command") or []
    if not build_command:
        _fail("the policy declares no build command")
    build_command = [_resolve(build_command[0]), *build_command[1:]]

    npm_log = ROOT / "runtime" / "easel-frontend-build.log"
    npm_exe = _resolve("npm")
    for step, command in (("npm ci", [npm_exe, "ci"]), ("npm run build", list(build_command))):
        with open(npm_log, "ab") as fh:
            fh.write(f"\n===== {_now()} {step} =====\n".encode("utf-8"))
            result = hidden_run(command, cwd=str(frontend), timeout=1800,
                                stdout=fh, stderr=subprocess.STDOUT)
        if result.returncode != 0:
            _fail(f"{step} failed with exit {result.returncode}; "
                  f"see {npm_log.name} in runtime/")

    inventory: dict[str, str] = {}
    for path in sorted(dist.rglob("*")):
        if path.is_file():
            inventory[path.relative_to(dist).as_posix()] = hashlib.sha256(
                path.read_bytes()).hexdigest()
    if not inventory:
        _fail("the build produced no dist files")
    tree_digest = hashlib.sha256(json.dumps(
        inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    manifest = {
        "schema": "contentops.easel-frontend-build/v1",
        "source_commit": engine.commit,
        "package_lock_sha256": lock_digest,
        "toolchain": toolchain,
        "toolchain_rule": "range" if toolchain_range else "exact",
        "build_command": policy.get("build_command"),
        "build_executable": build_command[0],
        "destination": str(frontend.resolve()),
        "files": inventory,
        "tree_sha256": tree_digest,
        "built_at": _now(),
        "built_by": "scripts/record_easel_frontend_build.py",
        "note": "Written immediately after npm ci and npm run build completed in this "
                "instance. The dist inventory binds the receipt to the bytes the build "
                "produced; the host refuses to serve anything else.",
    }
    MANIFEST_PATH.write_bytes((json.dumps(manifest, indent=2, ensure_ascii=False)
                               + "\n").encode("utf-8"))

    print(f"recorded {MANIFEST_PATH.name}")
    print(f"  source_commit : {engine.commit[:12]}")
    print(f"  toolchain     : node {node_version} / npm {npm_version} "
          f"(rule: {manifest['toolchain_rule']})")
    print(f"  dist files    : {len(inventory)}")
    print(f"  tree_sha256   : {tree_digest[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
