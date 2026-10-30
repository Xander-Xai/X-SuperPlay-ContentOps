"""Byte-stable primitives shared by the routing and hotspot layers.

Why this is its own module
--------------------------
The hotspot layer sits *below* routing: a plan is built before any route
exists, and the router reads the plan. If the plan builder imported the
router's module for a timestamp helper, the two layers would import each
other. These three functions are the only things that crossed that boundary,
so they live here, where neither layer owns the other.

Everything here is deterministic on purpose. A receipt that cannot be
re-computed byte-for-byte is not evidence, so the digest fixes key order and
separators and the timestamp is UTC to the second.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def utcnow() -> str:
    """The current time as ``2026-10-30T09:15:00Z``."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    """Stable bytes for hashing. Key order and separators are fixed."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    """The SHA-256 of a value's canonical bytes, as lowercase hex."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


__all__ = ["canonical_bytes", "digest", "utcnow"]
