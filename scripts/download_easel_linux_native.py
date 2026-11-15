#!/usr/bin/env python3
"""Download one fixed public npm archive after separate user authorization.

This command contacts registry.npmjs.org. Do not invoke it until that network
action is expressly approved. It does not read npm config, send credentials,
install packages, run code from the archive, or overwrite an existing file.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import os
import re
import ssl
from pathlib import Path
from urllib.parse import urlsplit

HOST = "registry.npmjs.org"
PACKAGE = "@openclaw/fs-safe-linux-x64-gnu"
VERSION = "0.25.0"
METADATA_PATH = "/@openclaw%2ffs-safe-linux-x64-gnu/0.25.0"
MAX_METADATA = 2 * 1024 * 1024
MAX_ARCHIVE = 128 * 1024 * 1024


def _ordinary(path: Path) -> None:
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("destination must be absolute without parent traversal")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise ValueError("destination contains a linked path")


def _connection() -> http.client.HTTPSConnection:
    return http.client.HTTPSConnection(HOST, timeout=60, context=ssl.create_default_context())


def download(destination: Path) -> dict:
    _ordinary(destination)
    receipt = destination.with_name(destination.name + ".download.json")
    _ordinary(receipt)
    if destination.exists() or receipt.exists() or not destination.parent.is_dir():
        raise ValueError("destination and receipt must not exist; parent must exist")
    metadata_conn = _connection()
    try:
        metadata_conn.request("GET", METADATA_PATH, headers={"Accept": "application/json", "User-Agent": "ContentOps-candidate/1"})
        response = metadata_conn.getresponse()
        if response.status != 200:
            raise ValueError("registry metadata request failed")
        metadata_bytes = response.read(MAX_METADATA + 1)
        if len(metadata_bytes) > MAX_METADATA:
            raise ValueError("registry metadata exceeds limit")
    finally:
        metadata_conn.close()
    metadata = json.loads(metadata_bytes.decode("utf-8"))
    if not isinstance(metadata, dict) or metadata.get("name") != PACKAGE or metadata.get("version") != VERSION:
        raise ValueError("registry metadata does not match the requested package")
    dist = metadata.get("dist")
    if not isinstance(dist, dict) or not isinstance(dist.get("tarball"), str) or not isinstance(dist.get("integrity"), str):
        raise ValueError("registry metadata lacks archive or integrity")
    url = urlsplit(dist["tarball"])
    if (url.scheme != "https" or url.hostname != HOST or url.port not in (None, 443)
            or url.username is not None or url.password is not None or url.query or url.fragment
            or not re.fullmatch(r"/@openclaw/fs-safe-linux-x64-gnu/-/fs-safe-linux-x64-gnu-0\.25\.0\.tgz", url.path)):
        raise ValueError("registry archive address is not the fixed expected package")
    match = re.fullmatch(r"sha512-([A-Za-z0-9+/]+={0,2})", dist["integrity"])
    if not match:
        raise ValueError("registry integrity is not a single SHA-512 value")
    expected = base64.b64decode(match.group(1), validate=True)
    if len(expected) != 64:
        raise ValueError("registry SHA-512 length is invalid")
    archive_conn = _connection()
    sha512 = hashlib.sha512()
    sha256 = hashlib.sha256()
    size = 0
    try:
        archive_conn.request("GET", url.path, headers={"Accept": "application/octet-stream", "User-Agent": "ContentOps-candidate/1"})
        response = archive_conn.getresponse()
        if response.status != 200:
            raise ValueError("registry archive request failed")
        with destination.open("xb") as stream:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_ARCHIVE:
                    raise ValueError("archive exceeds size limit")
                sha512.update(chunk)
                sha256.update(chunk)
                stream.write(chunk)
    finally:
        archive_conn.close()
    if not size or sha512.digest() != expected:
        raise ValueError("archive integrity mismatch; partial file retained")
    result = {"schema": "contentops.easel-linux-native-download/v1", "package": PACKAGE,
              "version": VERSION, "registry": HOST, "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
              "archive_sha256": sha256.hexdigest(), "archive_sha512": sha512.hexdigest(),
              "archive_bytes": size, "publisher_identity": "NOT_INDEPENDENTLY_VERIFIED",
              "execution_authorized": False}
    with receipt.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", help="new absolute path for the archive")
    args = parser.parse_args()
    try:
        result = download(Path(args.destination))
    except (OSError, ValueError, TypeError, UnicodeDecodeError, http.client.HTTPException) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": type(exc).__name__}, ensure_ascii=False))
        return 4
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
