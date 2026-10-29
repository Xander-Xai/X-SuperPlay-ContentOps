"""Cross-platform hashes for workflow integrity manifests.

Text files are hashed with canonical LF line endings so Windows checkout
settings cannot make an otherwise unchanged manifest appear stale. Binary
files retain their exact bytes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def canonical_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    if "\x00" in text:
        return data
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(canonical_bytes(path)).hexdigest()
