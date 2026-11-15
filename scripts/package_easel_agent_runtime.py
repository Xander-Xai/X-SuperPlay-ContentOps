#!/usr/bin/env python3
"""Copy an explicitly listed Linux Agent runtime into a new candidate directory.

Reads a JSON specification from stdin: {"destination": absolute path,
"manifest": absolute path, "native_import": receipt binding, "files": [{"source": absolute path, "target":
relative POSIX path, "sha256": lowercase digest}, ...]}. The manifest is
written outside the package and contains an exhaustive target-to-digest map.
This does not install software, fetch files, start processes or prove provenance.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import sys
from pathlib import Path, PurePosixPath


def ordinary_path(path: Path, *, exists: bool) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("paths must be absolute and contain no parent traversal")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ValueError("linked paths are not permitted")
    if exists and not path.is_file():
        raise ValueError("source file is unavailable")
    return path


def package(spec: dict) -> dict:
    if os.name != "posix":
        raise ValueError("packaging must run in Linux")
    if not isinstance(spec, dict) or set(spec) != {"destination", "manifest", "files", "native_import"}:
        raise ValueError("invalid package specification")
    binding = spec["native_import"]
    if (not isinstance(binding, dict) or set(binding) != {"receipt", "receipt_sha256"}
            or not isinstance(binding["receipt_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", binding["receipt_sha256"])):
        raise ValueError("native import binding is invalid")
    native_receipt_path = ordinary_path(Path(binding["receipt"]), exists=True)
    if native_receipt_path.stat().st_size > 1024 * 1024:
        raise ValueError("native import receipt exceeds size limit")
    native_receipt_bytes = native_receipt_path.read_bytes()
    if hashlib.sha256(native_receipt_bytes).hexdigest() != binding["receipt_sha256"]:
        raise ValueError("native import receipt changed")
    native_receipt = json.loads(native_receipt_bytes.decode("utf-8"))
    if (not isinstance(native_receipt, dict)
            or native_receipt.get("schema") != "contentops.easel-linux-native-import/v1"
            or native_receipt.get("package") != "@openclaw/fs-safe-linux-x64-gnu"
            or native_receipt.get("version") != "0.25.0"
            or native_receipt.get("publisher_identity") != "UNVERIFIED"
            or native_receipt.get("execution_authorized") is not False
            or not isinstance(native_receipt.get("archive_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", native_receipt["archive_sha256"])
            or not isinstance(native_receipt.get("files"), dict)):
        raise ValueError("native import receipt is invalid")
    destination = ordinary_path(Path(spec["destination"]), exists=False)
    manifest = ordinary_path(Path(spec["manifest"]), exists=False)
    if (destination.exists() or manifest.exists() or not destination.parent.is_dir()
            or not manifest.parent.is_dir() or destination == manifest
            or destination in manifest.parents):
        raise ValueError("destination and manifest must be absent, separate paths with existing parents")
    rows = spec["files"]
    if not isinstance(rows, list) or not rows or len(rows) > 50000:
        raise ValueError("invalid file list")
    selected = []
    targets = set()
    size = 0
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"source", "target", "sha256"}:
            raise ValueError("invalid file entry")
        source = ordinary_path(Path(row["source"]), exists=True)
        target = row["target"]
        lowered = {part.lower() for part in source.parts}
        browser_code = (isinstance(target, str)
                        and str(source).startswith("/mnt/d/Toolchains/npm-global/node_modules/openclaw/dist/extensions/browser/")
                        and target.startswith("openclaw/dist/extensions/browser/"))
        secret_proxy_code = (str(source) == "/mnt/d/Toolchains/npm-global/node_modules/openclaw/dist/secrets/egress-proxy/proxy.worker.js"
                             and target == "openclaw/dist/secrets/egress-proxy/proxy.worker.js")
        forbidden = {".ssh", ".aws", ".openclaw", "credentials"}
        if not secret_proxy_code:
            forbidden.add("secrets")
        if (lowered & forbidden or ("browser" in lowered and not browser_code)
                or source.name.lower().startswith(".env")):
            raise ValueError("credential or session paths cannot be packaged")
        digest = row["sha256"]
        if not isinstance(target, str) or "\\" in target:
            raise ValueError("invalid target path")
        parts = PurePosixPath(target).parts
        if (not parts or target.startswith("/") or any(p in (".", "..") or (p.startswith(".") and p not in {".bundle.hash", ".setup"}) for p in parts)
                or parts[0] not in {"bin", "lib", "openclaw", "system"} or target in targets):
            raise ValueError("unsafe or duplicate target")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid source digest")
        size += source.stat().st_size
        if size > 2 * 1024 * 1024 * 1024:
            raise ValueError("package exceeds size limit")
        selected.append((source, parts, target, digest))
        targets.add(target)
    if not {"bin/node", "openclaw/openclaw.mjs"}.issubset(targets):
        raise ValueError("missing runtime entry points")
    linux_native_prefix = "openclaw/node_modules/@openclaw/fs-safe-linux-x64-gnu/"
    if (linux_native_prefix + "package.json" not in targets
            or not any(target.startswith(linux_native_prefix) and target.endswith(".node") for target in targets)):
        raise ValueError("Linux x64 glibc fs-safe native package is missing; no fallback is accepted")
    native_files = {target[len(linux_native_prefix):]: digest for _, _, target, digest in selected
                    if target.startswith(linux_native_prefix)}
    if native_files != native_receipt["files"]:
        raise ValueError("native package files differ from their import receipt")
    source_map = {target: source for source, _, target, _ in selected}
    try:
        fs_safe = json.loads(source_map["openclaw/node_modules/@openclaw/fs-safe/package.json"].read_text(encoding="utf-8"))
        fs_native = json.loads(source_map[linux_native_prefix + "package.json"].read_text(encoding="utf-8"))
    except (KeyError, OSError, UnicodeDecodeError, ValueError):
        raise ValueError("fs-safe package metadata is missing or unreadable") from None
    if (not isinstance(fs_safe, dict) or not isinstance(fs_native, dict)
            or fs_safe.get("name") != "@openclaw/fs-safe"
            or fs_native.get("name") != "@openclaw/fs-safe-linux-x64-gnu"
            or not isinstance(fs_safe.get("version"), str)
            or fs_safe.get("version") != fs_native.get("version")):
        raise ValueError("fs-safe Linux native package version does not match")
    node = source_map["bin/node"]
    with node.open("rb") as stream:
        header = stream.read(20)
    if (len(header) != 20 or header[:6] != b"\x7fELF\x02\x01"
            or struct.unpack_from("<H", header, 18)[0] != 62):
        raise ValueError("Node entry point is not a Linux x86-64 ELF binary")
    package_json = source_map.get("openclaw/package.json")
    if package_json is None or package_json.stat().st_size > 1024 * 1024:
        raise ValueError("OpenClaw package metadata is missing or too large")
    try:
        metadata = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise ValueError("OpenClaw package metadata is unreadable") from None
    if (not isinstance(metadata, dict) or metadata.get("name") != "openclaw"
            or not isinstance(metadata.get("version"), str)
            or not re.fullmatch(r"[0-9A-Za-z.+-]{1,80}", metadata["version"])):
        raise ValueError("OpenClaw package metadata is invalid")
    destination.mkdir()
    hashes = {}
    for source, parts, target, expected in selected:
        output = destination.joinpath(*parts)
        output.parent.mkdir(parents=True, exist_ok=True)
        sha = hashlib.sha256()
        with source.open("rb") as incoming, output.open("xb") as outgoing:
            while chunk := incoming.read(1024 * 1024):
                sha.update(chunk)
                outgoing.write(chunk)
        if sha.hexdigest() != expected:
            raise ValueError("source digest changed or did not match; partial package retained")
        output.chmod(0o555 if source.stat().st_mode & 0o111 else 0o444)
        hashes[target] = expected
    with manifest.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump({"schema": "contentops.easel-agent-runtime-package/v1", "files": hashes,
                   "node_binary_format": "ELF64-x86-64", "openclaw_version": metadata["version"],
                   "fs_safe_version": fs_safe["version"],
                   "native_import_receipt_sha256": binding["receipt_sha256"],
                   "native_archive_sha256": native_receipt.get("archive_sha256"),
                   "provenance": "UNVERIFIED", "execution_authorized": False},
                  stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return {"status": "PACKAGED_UNVERIFIED", "file_count": len(hashes),
            "node_binary_format": "ELF64-x86-64", "openclaw_version": metadata["version"],
            "destination": str(destination), "manifest": str(manifest)}


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError("specification exceeds size limit")
        result = package(json.loads(raw.decode("utf-8")))
    except (OSError, TypeError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 4
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
