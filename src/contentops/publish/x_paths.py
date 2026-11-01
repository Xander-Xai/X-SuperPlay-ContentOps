"""One path contract for the X publish slice.

Every path in an X record is data a caller supplies. A gate that opens it must
answer three questions before it touches the filesystem:

1. Is this a single name or a relative path, not an absolute path, drive path,
   UNC path or a backslash spelling that means something different on Windows?
2. Does it stay inside the root it claims to belong to?
3. Does any component of it arrive through a symlink?

All three are answered here so the pipeline, the bridge and the post gate cannot
disagree about what "inside the project" means.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

#: A content id is one file-name component, not a path.
SINGLE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_DRIVE = re.compile(r"^[A-Za-z]:")


def is_single_component(value: object) -> bool:
    """True only for one safe file-name component (no separators, no dots)."""
    return isinstance(value, str) and bool(SINGLE_COMPONENT.fullmatch(value))


def safe_relative(value: object) -> Optional[Path]:
    """A relative path that cannot traverse, or ``None``.

    Backslashes are refused on every platform, because ``..\\x`` is a harmless
    file name on Linux and a traversal on Windows. The check must mean the same
    thing on both CI runners.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or "\x00" in text or "\\" in text:
        return None
    if text.startswith("/") or _DRIVE.match(text):
        return None
    path = Path(text)
    if path.is_absolute() or str(path) in ("", "."):
        return None
    if any(part in ("", ".", "..") for part in path.parts):
        return None
    return path


def _has_symlink_component(root: Path, relative: Path) -> bool:
    current = root
    for part in relative.parts:
        current = current / part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False


def resolve_inside(root: Path, value: object, *,
                   must_be_file: bool = False) -> Optional[Path]:
    """Resolve ``value`` under ``root``, or return ``None`` if it is not safe.

    Absolute inputs are refused: a record names a project-relative artifact.
    Symlinks are refused even when they point back inside the root, because a
    link is a second identity the review of the record never approved.
    """
    relative = safe_relative(value)
    if relative is None:
        return None
    root_resolved = Path(root).resolve()
    if _has_symlink_component(root_resolved, relative):
        return None
    try:
        resolved = (root_resolved / relative).resolve()
    except OSError:
        return None
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        return None
    if must_be_file and not resolved.is_file():
        return None
    return resolved


def ensure_inside(root: Path, path: Path) -> bool:
    """True when an already-built path resolves inside ``root`` without links."""
    root_resolved = Path(root).resolve()
    try:
        resolved = Path(path).resolve()
        relative = resolved.relative_to(root_resolved)
    except (OSError, ValueError):
        return False
    return not _has_symlink_component(root_resolved, relative)
