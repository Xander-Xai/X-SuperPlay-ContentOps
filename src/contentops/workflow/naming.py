"""Deterministic package identity: one content id, one directory.

A package id is the join key for the video, its receipts, its delivery bundle
and its feedback record. If it can be written two ways, those records stop
joining, and a later audit reads two half-packages instead of one.

The id is `douyin-YYYYMMDD-NNN-topic-slug`: a calendar day, a three-digit
sequence within that day, and a portable ASCII slug. A Chinese-only title gets
a short hash slug rather than an unstable transliteration.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

CONTENT_ID_RE = re.compile(
    r"^douyin-(?P<date>\d{8})-(?P<sequence>\d{3})-(?P<slug>[a-z0-9][a-z0-9-]{2,47})$"
)


def slugify(value: str) -> str:
    """Stable lowercase ASCII slug; a hash fallback for CJK-only titles."""
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    if len(slug) < 3:
        digest = hashlib.sha256(str(value or "topic").encode("utf-8")).hexdigest()[:10]
        slug = f"topic-{digest}"
    return slug[:48].rstrip("-")


def validate_content_id(content_id: Any) -> Dict[str, str]:
    value = str(content_id or "").strip()
    match = CONTENT_ID_RE.fullmatch(value)
    if not match:
        raise ValueError(
            "content_id must match douyin-YYYYMMDD-NNN-topic-slug "
            "(lowercase ASCII, e.g. douyin-20261028-001-topic-a1b2c3)")
    try:
        datetime.strptime(match.group("date"), "%Y%m%d")
    except ValueError:
        raise ValueError("content_id contains an invalid calendar date") from None
    return match.groupdict()


def next_content_id(topic: str, root: Path, date: str = "") -> str:
    """Allocate the next free sequence for a day under ``root``."""
    root = Path(root).expanduser()
    day = date or datetime.now().astimezone().strftime("%Y%m%d")
    try:
        datetime.strptime(day, "%Y%m%d")
    except ValueError:
        raise ValueError("date must use YYYYMMDD and be a valid calendar date") from None
    used = set()
    if root.is_dir():
        for child in root.iterdir():
            if not child.is_dir():
                continue
            match = CONTENT_ID_RE.fullmatch(child.name)
            if match and match.group("date") == day:
                used.add(int(match.group("sequence")))
    sequence = 1
    while sequence in used:
        sequence += 1
    if sequence > 999:
        raise ValueError(f"no free sequence remains for {day}")
    return f"douyin-{day}-{sequence:03d}-{slugify(topic)}"


def package_path(root: Path, content_id: str) -> Path:
    """The one directory a content id owns; it must not escape the root."""
    validate_content_id(content_id)
    root = Path(root).resolve()
    path = (root / content_id).resolve()
    if root not in path.parents:
        raise ValueError("content_id resolves outside the production root")
    return path


def validate_package_name(name: str) -> Optional[str]:
    try:
        validate_content_id(name)
    except ValueError as exc:
        return str(exc)
    return None
