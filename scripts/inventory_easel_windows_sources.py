#!/usr/bin/env python3
"""Create a copy specification from explicit local Windows runtime sources.

Reads only an explicitly named Node executable and OpenClaw package directory;
does not copy, install, execute, inspect settings, or contact a provider. Output
is suitable for package_easel_windows_runtime.py but is not provenance proof.
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

from contentops.easel.agent_sandbox import SandboxPlanError, _ordinary  # noqa: E402
from contentops.easel.offline_task import OfflineTaskError, _ensure_child_dir, _linklike, _safe_project  # noqa: E402
from package_easel_windows_runtime import PROHIBITED, SOURCE_EXTENSIONS, SOURCE_ONLY_COMPONENTS  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--node", required=True, help="absolute path to an existing node.exe")
    parser.add_argument("--openclaw", required=True, help="absolute path to an existing OpenClaw package directory")
    parser.add_argument("--write", action="store_true", help="write a new project-local UTF-8 specification file")
    args = parser.parse_args()
    try:
        if os.name != "nt" or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", args.package):
            raise ValueError("Windows and a valid package slug are required")
        project, _ = _safe_project(ROOT, args.project)
        node = _ordinary(Path(args.node), directory=False)
        package = _ordinary(Path(args.openclaw), directory=True)
        if package.name.casefold() != "openclaw" or package.parent.name.casefold() != "node_modules":
            raise ValueError("OpenClaw source must be an explicit node_modules/openclaw package directory")
        if node.name.casefold() != "node.exe":
            raise ValueError("explicit Node source must be named node.exe")
        for path in (node, package):
            if any(part.casefold() in PROHIBITED or part.casefold().startswith(".env") for part in path.parts):
                raise ValueError("protected source path is forbidden")
        rows = []
        exclusions = []
        total = 0

        def add(path: Path, target: str) -> None:
            nonlocal total
            total += path.stat().st_size
            if total > 2 * 1024 * 1024 * 1024 or len(rows) >= 100_000:
                raise ValueError("source inventory exceeds size limit")
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            rows.append({"source": str(path), "target": target, "sha256": digest.hexdigest()})

        add(node, "node.exe")
        for directory, directories, names in os.walk(package, followlinks=False):
            directories.sort()
            names.sort()
            parent = Path(directory)
            # Record and omit dotenv files/directories without opening them.
            for name in list(directories):
                if name.casefold().startswith(".env"):
                    exclusions.append((parent / name).relative_to(package).as_posix())
                    directories.remove(name)
            for name in list(names):
                if name.casefold().startswith(".env"):
                    exclusions.append((parent / name).relative_to(package).as_posix())
                    names.remove(name)
            for name in directories + names:
                path = parent / name
                if (_linklike(path)
                        or name.casefold() in PROHIBITED
                        or (name.casefold().startswith(("credentials", "auth-profiles", "cookie"))
                            and path.is_file() and path.suffix.casefold() not in (SOURCE_EXTENSIONS | {".md"}))
                        or path.suffix.casefold() in {".pem", ".key", ".pfx", ".sqlite", ".db"}):
                    raise ValueError("OpenClaw source contains a linked or protected path: "
                                     + path.relative_to(package).as_posix())
            for name in names:
                path = parent / name
                if not path.is_file():
                    raise ValueError("OpenClaw source contains a non-regular file")
                if (SOURCE_ONLY_COMPONENTS & {part.casefold() for part in path.relative_to(package).parts}
                        and path.suffix.casefold() not in SOURCE_EXTENSIONS):
                    raise ValueError("OpenClaw package contains credential or session data")
                add(path, "openclaw/" + path.relative_to(package).as_posix())
        targets = {row["target"] for row in rows}
        if not {"openclaw/openclaw.mjs", "openclaw/package.json"}.issubset(targets):
            raise ValueError("OpenClaw package entry points are missing")
        spec = {"project": args.project, "package": args.package, "files": rows,
                "source_exclusions": exclusions}
        if args.write:
            work = _ensure_child_dir(project, "work")
            parent = work / "easel-windows-runtime"
            if _linklike(parent):
                raise ValueError("runtime directory is linked")
            parent.mkdir(exist_ok=True)
            if not parent.is_dir() or parent.resolve(strict=True).parent != work:
                raise ValueError("runtime directory is unsafe")
            destination = parent / (args.package + ".source-spec.json")
            with destination.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(spec, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
    except (OfflineTaskError, SandboxPlanError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)[:300]}, ensure_ascii=False), file=sys.stderr)
        return 4
    if args.write:
        print(json.dumps({"status": "INVENTORIED_UNVERIFIED", "spec": str(destination),
                          "file_count": len(rows), "execution_authorized": False}, ensure_ascii=False))
    else:
        print(json.dumps(spec, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
