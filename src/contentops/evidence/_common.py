"""Shared validation for evidence contracts.

Every contract in this package is a JSON document that a receipt or a build
reads, so the failure mode is not an exception in a type checker but a document
that *looks* valid and asserts something unsupported. The helpers here keep the
four contracts agreeing on the two things that are easy to get subtly wrong:

- a SHA-256 is exactly 64 lowercase hex characters, never a prefix or a filename;
- a time range is resolved to integer milliseconds with an end strictly after
  its start, so ``00:05.000-00:05.000`` cannot pass as evidence of anything.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Tuple

SCHEMA_PREFIX = "contentops."

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_RANGE_RE = re.compile(
    r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\.(\d{3})\s*-\s*"
    r"(\d{1,2}):(\d{2})(?::(\d{2}))?\.(\d{3})\s*$"
)


class ContractError(ValueError):
    """A contract document is structurally valid JSON but semantically invalid.

    ``code`` is stable so a receipt can say ``EVIDENCE_SHA_MISMATCH`` instead of
    matching on prose.
    """

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise ContractError(code, detail)


def require_schema(document: Dict[str, Any], expected: str) -> None:
    require(isinstance(document, dict), "MALFORMED_DOCUMENT",
            f"expected a JSON object, got {type(document).__name__}")
    actual = document.get("schema")
    require(actual == expected, "UNSUPPORTED_SCHEMA",
            f"expected schema {expected!r}, got {actual!r}")


def require_text(value: Any, field: str) -> str:
    require(isinstance(value, str) and value.strip() != "", "MISSING_FIELD",
            f"{field} must be a non-empty string")
    return value


def require_sha256(value: Any, field: str) -> str:
    require(isinstance(value, str), "INVALID_SHA256",
            f"{field} must be a SHA-256 hex string")
    require(bool(_SHA_RE.match(value)), "INVALID_SHA256",
            f"{field} is not 64 lowercase hex characters: {value!r}")
    return value


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iso_utc(value: Any, field: str) -> datetime:
    """Parse an ISO-8601 timestamp and require an explicit UTC designator."""
    require(isinstance(value, str) and value.strip() != "", "MISSING_FIELD",
            f"{field} must be an ISO-8601 UTC timestamp")
    text = value.strip()
    require(text.endswith("Z") or text.endswith("+00:00"), "NON_UTC_TIMESTAMP",
            f"{field} must be UTC (ending in Z or +00:00): {value!r}")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("INVALID_TIMESTAMP", f"{field}: {exc}") from None
    return parsed.astimezone(timezone.utc)


def _group_ms(hours: Optional[str], minutes: str, seconds: Optional[str],
              millis: str) -> int:
    h = int(hours or 0)
    m = int(minutes)
    s = int(seconds or 0)
    require(m < 60 and s < 60, "INVALID_TIME_RANGE",
            f"minutes/seconds out of range: {hours}:{minutes}:{seconds}.{millis}")
    return ((h * 60 + m) * 60 + s) * 1000 + int(millis)


def parse_time_range(value: Any, field: str) -> Tuple[int, int]:
    """``MM:SS.mmm-MM:SS.mmm`` or ``HH:MM:SS.mmm-HH:MM:SS.mmm`` -> milliseconds."""
    require(isinstance(value, str), "INVALID_TIME_RANGE",
            f"{field} must be a time range string")
    match = _RANGE_RE.match(value)
    require(match is not None, "INVALID_TIME_RANGE",
            f"{field} is not a time range: {value!r}")
    start = _group_ms(match.group(1), match.group(2), match.group(3), match.group(4))
    end = _group_ms(match.group(5), match.group(6), match.group(7), match.group(8))
    require(end > start, "INVALID_TIME_RANGE",
            f"{field} ends at or before it starts: {value!r}")
    return start, end


def parse_ms_range(start_ms: Any, end_ms: Any, field: str) -> Tuple[int, int]:
    for name, value in (("start_ms", start_ms), ("end_ms", end_ms)):
        require(isinstance(value, int) and not isinstance(value, bool),
                "INVALID_TIME_RANGE", f"{field}.{name} must be an integer")
        require(value >= 0, "INVALID_TIME_RANGE", f"{field}.{name} must be >= 0")
    require(end_ms > start_ms, "INVALID_TIME_RANGE",
            f"{field} end_ms ({end_ms}) must exceed start_ms ({start_ms})")
    return start_ms, end_ms


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def fingerprint(document: Dict[str, Any], exclude: Iterable[str] = ()) -> str:
    """SHA-256 over a canonical form, omitting named volatile keys."""
    skipped = set(exclude)

    def scrub(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: scrub(v) for k, v in node.items() if k not in skipped}
        if isinstance(node, list):
            return [scrub(item) for item in node]
        return node

    return sha256_bytes(canonical_json(scrub(document)).encode("utf-8"))
