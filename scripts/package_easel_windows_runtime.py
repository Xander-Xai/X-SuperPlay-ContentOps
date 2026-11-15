#!/usr/bin/env python3
"""Copy explicitly listed local Windows runtime files to a new project package.

Reads UTF-8 JSON from stdin with project, package and files. Each file entry has
absolute source, relative target and expected sha256. This command does not
download, install dependencies, run code or grant execution. A failed copy is
left in place for inspection. A retry only reuses files whose bytes still match
the source specification; it never overwrites them.
"""
from __future__ import annotations

import hashlib
import argparse
import json
import os
import re
import struct
import sys
import uuid
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.easel.agent_sandbox import SandboxPlanError, _ordinary  # noqa: E402
from contentops.easel.offline_task import OfflineTaskError, _ensure_child_dir, _linklike, _safe_project  # noqa: E402

PROHIBITED = {".git", ".ssh", ".aws", ".openclaw", ".easel-browser-profiles",
              "credentials.json", "auth-profiles.json", "cookies.sqlite", "token.json",
              "browser-profiles"}
SOURCE_EXTENSIONS = {".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".map"}
SOURCE_ONLY_COMPONENTS = {"sessions", "credentials", "cookies"}


def _reserved_windows_name(part: str) -> bool:
    checker = getattr(os.path, "isreserved", None)
    return checker(part) if checker else Path(part).is_reserved()


def package(request: dict) -> dict:
    if os.name != "nt" or not isinstance(request, dict) or set(request) != {"project", "package", "files", "source_exclusions"}:
        raise ValueError("Windows and project, package, files are required")
    exclusions = request["source_exclusions"]
    if (not isinstance(exclusions, list) or len(exclusions) > 10_000
            or any(not isinstance(item, str) or not item or "\\" in item or ":" in item
                   or any(part in {"", ".", ".."} for part in item.split("/"))
                   or not any(part.casefold().startswith(".env") for part in item.split("/"))
                   for item in exclusions)):
        raise ValueError("source exclusions are invalid")
    name = request["package"]
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", name):
        raise ValueError("invalid package slug")
    project, _ = _safe_project(ROOT, request["project"])
    rows = request["files"]
    if not isinstance(rows, list) or not rows or len(rows) > 100_000:
        raise ValueError("invalid file list")
    selected = []
    targets = set()
    openclaw_root = None
    total = 0
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"source", "target", "sha256"}:
            raise ValueError("invalid file entry")
        source = _ordinary(Path(row["source"]), directory=False)
        target, digest = row["target"], row["sha256"]
        if not isinstance(target, str) or "\\" in target or ":" in target:
            raise ValueError("invalid package target")
        parts = PurePosixPath(target).parts
        if (not parts or target.startswith("/") or any(part in {"", ".", ".."} or part.endswith((" ", "."))
                or part.casefold() in PROHIBITED or part.casefold().startswith(".env")
                or _reserved_windows_name(part) for part in parts)):
            raise ValueError("unsafe package target")
        if any(part.casefold() in PROHIBITED or part.casefold().startswith(".env") for part in source.parts):
            raise ValueError("protected source path cannot be packaged")
        if target.casefold() in targets or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("duplicate package target or invalid digest")
        if target != "node.exe" and not target.startswith("openclaw/"):
            raise ValueError("only node.exe and openclaw package files are permitted")
        if target == "node.exe":
            if source.name.casefold() != "node.exe":
                raise ValueError("Node source must be named node.exe")
        else:
            source_root = source
            for _ in parts[1:]:
                source_root = source_root.parent
            if (source_root.name.casefold() != "openclaw" or source_root.parent.name.casefold() != "node_modules"
                    or source.relative_to(source_root).as_posix() != "/".join(parts[1:])):
                raise ValueError("OpenClaw files must come from their matching installed package paths")
            if openclaw_root is not None and source_root != openclaw_root:
                raise ValueError("OpenClaw files must come from one package")
            openclaw_root = source_root
            if (SOURCE_ONLY_COMPONENTS & {part.casefold() for part in parts}
                    and source.suffix.casefold() not in SOURCE_EXTENSIONS):
                raise ValueError("credential or session data cannot be packaged")
        total += source.stat().st_size
        if total > 2 * 1024 * 1024 * 1024:
            raise ValueError("runtime package exceeds size limit")
        targets.add(target.casefold())
        selected.append((source, parts, target, digest))
    native_prefix = "openclaw/node_modules/@openclaw/fs-safe-win32-x64-msvc/"
    required = {"node.exe", "openclaw/openclaw.mjs", "openclaw/package.json",
                "openclaw/node_modules/@openclaw/fs-safe/package.json", native_prefix + "package.json"}
    native_modules = sorted(target for target in targets if target.startswith(native_prefix) and target.endswith(".node"))
    if not required.issubset(targets) or len(native_modules) != 1:
        raise ValueError("Node, OpenClaw and exactly one Windows x64 fs-safe native module are required")
    work = _ensure_child_dir(project, "work")
    parent = work / "easel-windows-runtime"
    if _linklike(parent):
        raise ValueError("runtime directory is linked")
    parent.mkdir(exist_ok=True)
    if not parent.is_dir() or parent.resolve(strict=True).parent != work:
        raise ValueError("runtime directory is unsafe")
    destination = parent / name
    manifest = parent / (name + ".json")
    receipts = _ensure_child_dir(project, "receipts")
    receipt_path = receipts / f"windows-runtime-package-{name}-{uuid.uuid4()}.json"
    if receipt_path.exists() or _linklike(receipt_path):
        raise ValueError("package receipt already exists or is linked; refusing overwrite")
    if manifest.exists() or _linklike(destination) or _linklike(manifest):
        raise ValueError("package manifest exists or target is linked; refusing overwrite")
    if destination.exists() and not destination.is_dir():
        raise ValueError("existing package is not a directory")
    destination.mkdir(exist_ok=True)
    # Use the Win32 extended-length namespace for deep npm paths. Resolve and
    # check the normal project parent before adding the prefix.
    long_destination = Path("\\\\?\\" + str(destination.resolve(strict=True)))
    declared = {target.casefold(): expected for _, _, target, expected in selected}
    def fail_walk(error: OSError) -> None:
        raise error

    for base, dirs, names in os.walk(long_destination, followlinks=False, onerror=fail_walk):
        base_path = Path(base)
        if any(_linklike(base_path / name) for name in dirs):
            raise ValueError("existing package contains a linked directory")
        for existing_name in names:
            existing = base_path / existing_name
            relative_name = existing.relative_to(long_destination).as_posix().casefold()
            if _linklike(existing) or relative_name not in declared:
                raise ValueError("existing package contains an undeclared or linked file")
    files = {}
    for source, parts, target, expected in selected:
        output = long_destination.joinpath(*parts)
        output.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        if output.exists():
            if _linklike(output) or not output.is_file():
                raise ValueError("existing package file is unsafe")
            with output.open("rb") as current:
                for block in iter(lambda: current.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != expected:
                raise ValueError("existing package file differs; refusing overwrite")
            digest = hashlib.sha256()
            with source.open("rb") as incoming:
                for block in iter(lambda: incoming.read(1024 * 1024), b""):
                    digest.update(block)
        else:
            with source.open("rb") as incoming, output.open("xb") as outgoing:
                for block in iter(lambda: incoming.read(1024 * 1024), b""):
                    digest.update(block)
                    outgoing.write(block)
        if digest.hexdigest() != expected:
            raise ValueError("source digest changed; incomplete package retained")
        files[target] = expected
    def require_x64_pe(path: Path, label: str) -> None:
        with path.open("rb") as binary:
            dos = binary.read(64)
            if len(dos) != 64 or dos[:2] != b"MZ":
                raise ValueError(f"{label} is not a Windows executable; package retained")
            offset = struct.unpack_from("<I", dos, 0x3C)[0]
            if offset > 16 * 1024 * 1024:
                raise ValueError(f"{label} header is invalid; package retained")
            binary.seek(offset)
            header = binary.read(6)
            if len(header) != 6 or header[:4] != b"PE\0\0" or struct.unpack_from("<H", header, 4)[0] != 0x8664:
                raise ValueError(f"{label} is not Windows x86-64; package retained")

    require_x64_pe(destination / "node.exe", "node.exe")
    require_x64_pe(destination.joinpath(*PurePosixPath(native_modules[0]).parts), "fs-safe native module")
    metadata_path = destination / "openclaw" / "package.json"
    if metadata_path.stat().st_size > 1024 * 1024:
        raise ValueError("OpenClaw metadata is too large; package retained")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if (not isinstance(metadata, dict) or metadata.get("name") != "openclaw"
            or not isinstance(metadata.get("version"), str)
            or not re.fullmatch(r"[0-9A-Za-z.+-]{1,80}", metadata["version"])):
        raise ValueError("OpenClaw package metadata is invalid; package retained")
    fs_metadata = []
    for rel in ("openclaw/node_modules/@openclaw/fs-safe/package.json", native_prefix + "package.json"):
        path = destination.joinpath(*PurePosixPath(rel).parts)
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("fs-safe metadata is too large; package retained")
        fs_metadata.append(json.loads(path.read_text(encoding="utf-8")))
    if (not all(isinstance(item, dict) for item in fs_metadata)
            or fs_metadata[0].get("name") != "@openclaw/fs-safe"
            or fs_metadata[1].get("name") != "@openclaw/fs-safe-win32-x64-msvc"
            or not isinstance(fs_metadata[0].get("version"), str)
            or fs_metadata[0].get("version") != fs_metadata[1].get("version")):
        raise ValueError("Windows fs-safe versions do not match; package retained")
    relative = f"work/easel-windows-runtime/{name}"
    record = {"schema": "contentops.easel-windows-runtime-package/v1", "package": relative,
              "files": files, "bytes": total, "node_binary_format": "PE-x86-64",
              "source_exclusions": exclusions,
              "openclaw_version": metadata["version"], "provenance": "NOT_VERIFIED",
              "fs_safe_version": fs_metadata[0]["version"],
              "execution_authorized": False, "production_ready": False, "publish_authorized": False}
    with manifest.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(record, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    receipt = {"schema": "contentops.easel-windows-runtime-copy-receipt/v1",
               "project": request["project"], "package": relative,
               "manifest": manifest.relative_to(project).as_posix(),
               "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
               "file_count": len(files), "status": "PACKAGED_UNVERIFIED",
               "provenance": "NOT_VERIFIED", "isolation": "NOT_VERIFIED",
               "execution_authorized": False, "production_ready": False,
               "publish_authorized": False}
    with receipt_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return {"status": "PACKAGED_UNVERIFIED", "package": relative,
            "manifest": manifest.relative_to(project).as_posix(), "files": len(files),
            "receipt": receipt_path.relative_to(project).as_posix(),
            "execution_authorized": False}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", help="absolute path to an existing project-local UTF-8 source specification")
    args = parser.parse_args()
    try:
        if args.spec:
            source_spec = _ordinary(Path(args.spec), directory=False)
            parts = source_spec.relative_to((ROOT / "projects").resolve()).parts
            direct = len(parts) == 4 and parts[1:3] == ("work", "easel-windows-runtime")
            local = (len(parts) == 5 and parts[0] == "_local"
                     and parts[2:4] == ("work", "easel-windows-runtime"))
            if not (direct or local) or not parts[-1].endswith(".source-spec.json"):
                raise ValueError("source specification must be in the project runtime directory")
            with source_spec.open("rb") as stream:
                raw = stream.read(16 * 1024 * 1024 + 1)
        else:
            raw = sys.stdin.buffer.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError("package specification exceeds size limit")
        request = json.loads(raw.decode("utf-8"))
        if args.spec and isinstance(request, dict):
            project, _ = _safe_project(ROOT, request.get("project"))
            if source_spec.parent != project / "work" / "easel-windows-runtime":
                raise ValueError("source specification must belong to the selected project")
        result = package(request)
    except (OfflineTaskError, SandboxPlanError, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)[:300]}, ensure_ascii=False))
        return 4
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
