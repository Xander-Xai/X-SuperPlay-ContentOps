#!/usr/bin/env python3
"""Inventory an existing project-local Windows Agent package without installing it.

Reads only the explicit package directory; rejects credential/session paths and
links before hashing. Writes an adjacent, new-only manifest. This inventory is
not an isolation, software provenance, or execution approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.easel.offline_task import OfflineTaskError, _safe_project  # noqa: E402
from contentops.easel.agent_sandbox import SandboxPlanError, _ordinary  # noqa: E402
from contentops.easel.windows_sandbox import _extended_windows_path  # noqa: E402
from contentops.easel.path_safety import is_linklike  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--package", required=True)
    args = parser.parse_args()
    try:
        if os.name != "nt" or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", args.package):
            raise ValueError("Windows and a valid package slug are required")
        project, _ = _safe_project(ROOT, args.project)
        relative = f"work/easel-windows-runtime/{args.package}"
        package = _ordinary(project / relative, directory=True)
        manifest_path = package.parent / (args.package + ".json")
        if manifest_path.exists() or is_linklike(manifest_path):
            raise ValueError("runtime manifest already exists or is linked")
        files: dict[str, str] = {}
        total = 0
        walk_root = _extended_windows_path(package)
        def fail_walk(error: OSError) -> None:
            raise error
        for directory, directories, names in os.walk(walk_root, followlinks=False, onerror=fail_walk):
            directories.sort()
            names.sort()
            parent = Path(directory)
            for name in directories + names:
                path = parent / name
                lowered = name.casefold()
                if (is_linklike(path)
                        or lowered in {".git", ".ssh", ".aws", ".openclaw", ".easel-browser-profiles",
                                       "credentials.json", "auth-profiles.json",
                                       "cookies.sqlite", "token.json", "browser-profiles"}
                        or lowered.startswith(".env")):
                    raise ValueError("package contains a prohibited or linked path")
            for name in names:
                path = parent / name
                if not path.is_file():
                    raise ValueError("package contains a non-regular file")
                if ({"sessions", "credentials", "cookies"} & {part.casefold() for part in path.relative_to(walk_root).parts}
                        and path.suffix.casefold() not in {".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".map"}):
                    raise ValueError("package contains credential or session data")
                total += path.stat().st_size
                if total > 2 * 1024 * 1024 * 1024 or len(files) >= 100_000:
                    raise ValueError("package exceeds the inventory limit")
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                files[path.relative_to(walk_root).as_posix()] = digest.hexdigest()
        if not {"node.exe", "openclaw/openclaw.mjs"}.issubset(files):
            raise ValueError("package must include node.exe and openclaw/openclaw.mjs")
        record = {"schema": "contentops.easel-windows-runtime-package/v1", "package": relative,
                  "files": files, "bytes": total, "provenance": "NOT_VERIFIED",
                  "execution_authorized": False, "production_ready": False,
                  "publish_authorized": False}
        with manifest_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(record, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
    except (OfflineTaskError, SandboxPlanError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)[:300]}, ensure_ascii=False))
        return 4
    print(json.dumps({"status": "INVENTORIED_UNVERIFIED", "manifest": str(manifest_path),
                      "file_count": len(files), "execution_authorized": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
