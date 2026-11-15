#!/usr/bin/env python3
"""Generate a candidate packaging specification from explicit local inputs.

Linux only. Reads JSON from stdin with `node`, `openclaw`, `filter`, `bootstrap`,
`libraries` (source-to-target map), `destination` and `manifest`. Outputs a
file list with hashes for review; it does not copy, install, or run the runtime.
Source links and hidden entries are rejected; npm's `.bin` command directory,
`.package-lock.json` metadata and the top-level `docs` tree are excluded.
The explicit `linux_fs_safe` and `linux_fs_safe_receipt` paths supply the
separate Linux native package and its unsigned offline-import receipt.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path, PurePosixPath


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if os.name != "posix" or len(raw) > 1024 * 1024:
            raise ValueError("Linux and a request under 1 MiB are required")
        request = json.loads(raw.decode("utf-8"))
        required = {"node", "openclaw", "filter", "bootstrap", "libraries", "destination", "manifest", "linux_fs_safe", "linux_fs_safe_receipt"}
        if not isinstance(request, dict) or set(request) != required or not isinstance(request["libraries"], dict):
            raise ValueError("invalid inventory request")
        native_package = Path(request["linux_fs_safe"])
        if not native_package.is_absolute() or native_package.is_symlink() or not native_package.is_dir():
            raise ValueError("a separate Linux fs-safe native package directory is required")
        import_receipt = Path(request["linux_fs_safe_receipt"])
        if (not import_receipt.is_absolute() or import_receipt.is_symlink()
                or not import_receipt.is_file() or import_receipt.stat().st_size > 1024 * 1024):
            raise ValueError("Linux fs-safe import receipt is required")
        for candidate in (native_package, import_receipt):
            current = Path(candidate.anchor)
            if ".." in candidate.parts:
                raise ValueError("parent traversal is forbidden")
            for part in candidate.parts[1:]:
                current /= part
                if current.is_symlink():
                    raise ValueError("linked native package paths are forbidden")
        import_receipt_bytes = import_receipt.read_bytes()
        imported = json.loads(import_receipt_bytes.decode("utf-8"))
        if (not isinstance(imported, dict)
                or imported.get("schema") != "contentops.easel-linux-native-import/v1"
                or imported.get("package") != "@openclaw/fs-safe-linux-x64-gnu"
                or imported.get("version") != "0.25.0"
                or imported.get("publisher_identity") != "UNVERIFIED"
                or imported.get("execution_authorized") is not False
                or not isinstance(imported.get("files"), dict)):
            raise ValueError("Linux fs-safe import receipt is invalid")
        pending = []
        targets = set()

        def add(source_value: str | Path, target: str) -> None:
            source = Path(source_value)
            if not source.is_absolute() or ".." in source.parts:
                raise ValueError("source must be an absolute path without parent traversal")
            current = Path(source.anchor)
            for part in source.parts[1:]:
                current /= part
                if current.is_symlink():
                    raise ValueError("linked source is not allowed: " + str(source))
            lowered = {part.lower() for part in source.parts}
            browser_code = (str(source).startswith("/mnt/d/Toolchains/npm-global/node_modules/openclaw/dist/extensions/browser/")
                            and target.startswith("openclaw/dist/extensions/browser/"))
            secret_proxy_code = (str(source) == "/mnt/d/Toolchains/npm-global/node_modules/openclaw/dist/secrets/egress-proxy/proxy.worker.js"
                                 and target == "openclaw/dist/secrets/egress-proxy/proxy.worker.js")
            forbidden = {".ssh", ".aws", ".openclaw", "credentials"}
            if not secret_proxy_code:
                forbidden.add("secrets")
            if (lowered & forbidden or ("browser" in lowered and not browser_code)
                    or source.name.lower().startswith(".env")):
                category = sorted(lowered & forbidden) or (["browser"] if "browser" in lowered else ["dotenv"])
                raise ValueError("protected path class cannot be inventoried: " + category[0])
            parts = PurePosixPath(target).parts
            if (not source.is_file() or not parts or target.startswith("/") or "\\" in target
                    or any(part.startswith(".") and part not in {".bundle.hash", ".setup"} for part in parts) or target in targets):
                raise ValueError("invalid source or target: " + target)
            pending.append((source, target))
            targets.add(target)
            if len(pending) > 50000:
                raise ValueError("runtime contains too many files")

        add(request["node"], "bin/node")
        add(request["filter"], "lib/no_subprocess.so")
        add(request["bootstrap"], "lib/sandbox-bootstrap.cjs")
        package = Path(request["openclaw"])
        if not package.is_absolute() or not package.is_dir() or package.is_symlink():
            raise ValueError("OpenClaw source must be an absolute ordinary directory")
        for directory, dirs, files in os.walk(package, topdown=True, followlinks=False):
            dirs.sort()
            files.sort()
            dirs[:] = [name for name in dirs if name != ".bin"]
            if Path(directory) == package:
                dirs[:] = [name for name in dirs if name != "docs"]
            for name in dirs:
                path = Path(directory) / name
                if (name.startswith(".") and name != ".setup") or path.is_symlink():
                    raise ValueError("hidden or linked OpenClaw directory: " + str(path))
            for name in files:
                if name == ".package-lock.json":
                    continue
                path = Path(directory) / name
                if path.is_symlink():
                    raise ValueError("linked OpenClaw file must be resolved explicitly: " + str(path))
                add(path, "openclaw/" + path.relative_to(package).as_posix())
        for directory, dirs, files in os.walk(native_package, topdown=True, followlinks=False):
            dirs.sort()
            files.sort()
            if any(name.startswith(".") or (Path(directory) / name).is_symlink() for name in dirs):
                raise ValueError("hidden or linked native package directory")
            for name in files:
                path = Path(directory) / name
                add(path, "openclaw/node_modules/@openclaw/fs-safe-linux-x64-gnu/" + path.relative_to(native_package).as_posix())
        for source, target in request["libraries"].items():
            if not isinstance(target, str) or not target.startswith(("system/lib/", "system/lib64/", "system/usr/lib/")):
                raise ValueError("invalid Linux library target")
            add(source, target)
        if "openclaw/openclaw.mjs" not in targets:
            raise ValueError("OpenClaw entry point is missing")
        entries = []
        for source, target in pending:
            sha = hashlib.sha256()
            with source.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    sha.update(block)
            entries.append({"source": str(source), "target": target, "sha256": sha.hexdigest()})
        native_prefix = "openclaw/node_modules/@openclaw/fs-safe-linux-x64-gnu/"
        native_digests = {entry["target"][len(native_prefix):]: entry["sha256"] for entry in entries
                          if entry["target"].startswith(native_prefix)}
        if native_digests != imported["files"]:
            raise ValueError("Linux fs-safe files differ from their import receipt")
        if import_receipt.read_bytes() != import_receipt_bytes:
            raise ValueError("Linux fs-safe import receipt changed during inventory")
        result = {"destination": request["destination"], "manifest": request["manifest"], "files": entries,
                  "native_import": {"receipt": str(import_receipt),
                                    "receipt_sha256": hashlib.sha256(import_receipt_bytes).hexdigest()}}
    except (OSError, TypeError, ValueError, KeyError, UnicodeDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 4
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
