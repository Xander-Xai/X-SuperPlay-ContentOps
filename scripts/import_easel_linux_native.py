#!/usr/bin/env python3
"""Extract a separately supplied, digest-pinned fs-safe Linux npm archive.

This command makes no network request and installs no dependency into the
system. It copies regular files only to a new candidate directory. The archive
and SHA-256 must be supplied independently; a hash proves byte consistency,
not publisher identity. Run only after the archive source is authorized.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import tarfile
from pathlib import Path, PurePosixPath

PACKAGE = "@openclaw/fs-safe-linux-x64-gnu"
VERSION = "0.25.0"
MAX_BYTES = 128 * 1024 * 1024
MAX_FILES = 1000


def ordinary(path: Path) -> None:
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("absolute paths without parent traversal are required")
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError("linked paths are not permitted")


def import_archive(archive: Path, destination: Path, digest: str,
                   download_receipt_sha256: str | None = None) -> dict:
    if os.name != "posix":
        raise ValueError("candidate import must run in Linux")
    ordinary(archive)
    ordinary(destination)
    receipt = destination.with_name(destination.name + ".import.json")
    ordinary(receipt)
    if (not re.fullmatch(r"[0-9a-f]{64}", digest) or not archive.is_file()
            or destination.exists() or receipt.exists() or not destination.parent.is_dir()):
        raise ValueError("archive, digest or destination is invalid")
    if archive.stat().st_size > MAX_BYTES:
        raise ValueError("compressed archive exceeds size limit")
    sha = hashlib.sha256()
    with archive.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    if sha.hexdigest() != digest:
        raise ValueError("archive digest does not match")
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        if not members or len(members) > MAX_FILES:
            raise ValueError("archive entry count is invalid")
        selected = []
        paths = set()
        total = 0
        for member in members:
            if "\\" in member.name or "\x00" in member.name:
                raise ValueError("archive contains an invalid path")
            parts = PurePosixPath(member.name).parts
            if (not parts or parts[0] != "package" or member.name.startswith("/")
                    or any(part in (".", "..") for part in parts)
                    or not (member.isdir() or member.isfile())):
                raise ValueError("archive contains a link, special file or unsafe path")
            relative = PurePosixPath(*parts[1:])
            if not relative.parts:
                continue
            if member.isfile():
                if relative.as_posix() in paths or any(part.startswith(".") for part in relative.parts):
                    raise ValueError("archive contains a hidden or duplicate file")
                paths.add(relative.as_posix())
                total += member.size
                if total > MAX_BYTES:
                    raise ValueError("archive exceeds extraction limit")
                selected.append((member, relative))
        if "package.json" not in paths or not any(path.endswith(".node") for path in paths):
            raise ValueError("archive lacks the package manifest or native module")
        metadata_member = next(member for member, path in selected if path.as_posix() == "package.json")
        if metadata_member.size > 1024 * 1024:
            raise ValueError("package metadata exceeds size limit")
        metadata_file = bundle.extractfile(metadata_member)
        if metadata_file is None:
            raise ValueError("package metadata is unreadable")
        with metadata_file:
            metadata = json.loads(metadata_file.read().decode("utf-8"))
        if not isinstance(metadata, dict) or metadata.get("name") != PACKAGE or metadata.get("version") != VERSION:
            raise ValueError("archive package identity does not match the candidate")
        for member, relative in selected:
            if relative.as_posix().endswith(".node"):
                native = bundle.extractfile(member)
                if native is None:
                    raise ValueError("native module is unreadable")
                with native:
                    header = native.read(20)
                if (len(header) != 20 or header[:6] != b"\x7fELF\x02\x01"
                        or struct.unpack_from("<H", header, 18)[0] != 62):
                    raise ValueError("native module is not Linux x86-64 ELF")
        destination.mkdir()
        files = {}
        for member, relative in selected:
            output = destination.joinpath(*relative.parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                raise ValueError("archive member is unreadable")
            file_hash = hashlib.sha256()
            with source, output.open("xb") as stream:
                while chunk := source.read(1024 * 1024):
                    file_hash.update(chunk)
                    stream.write(chunk)
            files[relative.as_posix()] = file_hash.hexdigest()
    final_sha = hashlib.sha256()
    with archive.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            final_sha.update(block)
    if final_sha.hexdigest() != digest:
        raise ValueError("archive changed during import; partial output retained")
    record = {"schema": "contentops.easel-linux-native-import/v1", "package": PACKAGE,
              "version": VERSION, "archive_sha256": digest, "files": files,
              "download_receipt_sha256": download_receipt_sha256,
              "publisher_identity": "UNVERIFIED", "execution_authorized": False}
    with receipt.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return {"status": "IMPORTED_UNVERIFIED", "destination": str(destination),
            "receipt": str(receipt), "archive_sha256": digest, "file_count": len(files)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    parser.add_argument("destination")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--sha256", help="independently supplied archive digest")
    selector.add_argument("--download-receipt", help="adjacent candidate download receipt")
    args = parser.parse_args()
    try:
        archive = Path(args.archive)
        receipt_digest = None
        digest = args.sha256
        if args.download_receipt:
            download_receipt = Path(args.download_receipt)
            ordinary(archive)
            ordinary(download_receipt)
            if (download_receipt != archive.with_name(archive.name + ".download.json")
                    or not download_receipt.is_file() or download_receipt.stat().st_size > 32768):
                raise ValueError("download receipt must be the archive's adjacent receipt")
            receipt_bytes = download_receipt.read_bytes()
            receipt = json.loads(receipt_bytes.decode("utf-8"))
            if (not isinstance(receipt, dict)
                    or receipt.get("schema") != "contentops.easel-linux-native-download/v1"
                    or receipt.get("package") != PACKAGE or receipt.get("version") != VERSION
                    or receipt.get("registry") != "registry.npmjs.org"
                    or receipt.get("execution_authorized") is not False):
                raise ValueError("download receipt does not match the fixed package")
            digest = receipt.get("archive_sha256")
            if not isinstance(digest, str):
                raise ValueError("download receipt lacks an archive digest")
            receipt_digest = hashlib.sha256(receipt_bytes).hexdigest()
        result = import_archive(archive, Path(args.destination), digest, receipt_digest)
    except (OSError, ValueError, TypeError, tarfile.TarError, UnicodeDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 4
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
