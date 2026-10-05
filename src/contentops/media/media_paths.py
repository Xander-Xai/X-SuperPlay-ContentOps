"""Logical media paths: a manifest must not contain a machine's directory layout.

The problem this solves
-----------------------
A committed manifest from the first M4.5 integration contained eight absolute
paths beginning ``D:\\Projects\\...``. That manifest is not reproducible: on Linux,
under a different checkout root, or on a drive letter that is not ``D:``, the
identical media and provenance would serialise to different bytes.

So "deterministic manifest" was true on exactly one workstation. A fingerprint over
a manifest is only useful if the same content fingerprints the same way for everyone,
and that fails the moment a drive letter is in the body.

The two logical forms
---------------------
``repo://<path>``
    relative to the repository root. Used for anything tracked or shared:
    project media, committed fixtures, the manifest's own location.
``project://<path>``
    relative to the one project directory. Used for media inside a project, because
    a project can move without invalidating its own internal references.

An absolute path is **never** produced by :func:`serialize_media_path`. That is
deliberate rather than a limitation: a machine root has no meaning in a committed
artifact, and inventing one would reintroduce the problem it solves.

Resolution happens at runtime, at the point of use. Composition and validation
receive a repo root and a project root and resolve; the manifest itself never needs
to know what drive it lives on.

Out of tree
-----------
A file outside both roots cannot be expressed logically. Rather than emit a
machine path and quietly break portability, :func:`serialize_media_path` returns
``None``, and the caller decides — usually by refusing to admit the asset, because
an asset that cannot be referenced portably does not belong in a shared manifest.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import List, Optional, Tuple, Union

__all__ = [
    "PROJECT_SCHEME",
    "REPO_SCHEME",
    "is_logical_path",
    "logical_prefix_map",
    "resolve_media_path",
    "sanitize_embedded_paths",
    "serialize_media_path",
]

REPO_SCHEME = "repo://"
PROJECT_SCHEME = "project://"

PathLike = Union[str, Path]


def is_logical_path(value: str) -> bool:
    """Whether ``value`` is already a logical reference rather than a path."""
    return value.startswith(REPO_SCHEME) or value.startswith(PROJECT_SCHEME)


def _posix(path: Path) -> str:
    """POSIX form of an absolute path, for comparison across separators."""
    return PurePosixPath(path.as_posix()).as_posix()


def _relative_to(path: Path, root: Path) -> Optional[str]:
    """POSIX relative path, or ``None`` when ``path`` is not under ``root``.

    Compared by resolved parts rather than by string prefix, so ``D:/Projects`` and
    ``D:/ProjectsOld`` are correctly treated as different roots instead of one
    being read as a prefix of the other.
    """
    try:
        relative = Path(os.path.normpath(str(path))).relative_to(
            Path(os.path.normpath(str(root)))
        )
    except ValueError:
        return None
    return PurePosixPath(relative.as_posix()).as_posix()


def _join(scheme: str, relative: str) -> str:
    """``scheme://rel``, collapsing the project/repo root itself to ``scheme://``.

    ``project://.`` would be technically resolvable but reads as a typo, and a
    reader skimming a receipt should not have to decide which it means.
    """
    normalised = PurePosixPath(relative.replace("\\", "/")).as_posix()
    if normalised in (".", ""):
        return scheme
    return f"{scheme}{normalised}"


def serialize_media_path(
    local_path: PathLike,
    *,
    repo_root: PathLike,
    project_root: Optional[PathLike] = None,
) -> Optional[str]:
    """Convert a local path into a portable logical reference.

    Project-relative wins over repo-relative, because a project may be checked out
    anywhere and its internal references must survive that.

    Returns:
        ``repo://...``, ``project://...``, or ``None`` when the path lies outside
        both roots. ``None`` is not a fallback signal to be worked around; it means
        the asset cannot be referenced portably and the caller should refuse it.
    """
    if not str(local_path):
        return None
    if is_logical_path(str(local_path)):
        return str(local_path)

    absolute = Path(local_path)
    if not absolute.is_absolute():
        # Already relative. Resolve against the project when one is known, so the
        # result is anchored rather than dependent on the process cwd.
        if project_root is not None:
            absolute = (Path(project_root) / absolute).resolve()
        else:
            return None
    else:
        absolute = absolute.resolve()

    if project_root is not None:
        relative = _relative_to(absolute, Path(project_root).resolve())
        if relative is not None:
            return _join(PROJECT_SCHEME, relative)

    repo = Path(repo_root).resolve()
    relative = _relative_to(absolute, repo)
    if relative is not None:
        return _join(REPO_SCHEME, relative)

    return None


def resolve_media_path(
    logical_ref: str,
    *,
    repo_root: PathLike,
    project_root: Optional[PathLike] = None,
) -> Path:
    """Turn a logical reference back into a local path.

    Raises:
        ValueError: the reference is absolute or malformed. Accepting one would
            silently reintroduce machine-dependent behaviour, so a manifest
            containing ``D:\\...`` fails loudly here rather than quietly working on
            one machine.
    """
    value = str(logical_ref)
    if value.startswith(PROJECT_SCHEME):
        if project_root is None:
            raise ValueError(
                f"{value!r} is project-relative but no project_root was supplied"
            )
        return (Path(project_root) / value[len(PROJECT_SCHEME):]).resolve()
    if value.startswith(REPO_SCHEME):
        return (Path(repo_root) / value[len(REPO_SCHEME):]).resolve()

    raise ValueError(
        f"{value!r} is not a logical media reference. A committed manifest must not "
        f"carry an absolute path; use {REPO_SCHEME}<path> or {PROJECT_SCHEME}<path>."
    )


def logical_prefix_map(
    *, repo_root: PathLike, project_root: Optional[PathLike] = None
) -> List[Tuple[str, str]]:
    """``(absolute prefix, logical scheme)`` pairs, **longest prefix first**.

    Longest-first is load-bearing, not cosmetic. A project path also sits under the
    repo root, so converting repo-relative first would turn
    ``<repo>/projects/demo/x.mp4`` into ``repo://projects/demo/x.mp4`` and hide the
    project-relative form that actually applies. Both native (``D:\\a\\b``) and
    POSIX spellings are listed, because a message that came from a tool may use
    either.
    """
    pairs: List[Tuple[str, str]] = []
    if project_root is not None:
        resolved = Path(project_root).resolve()
        pairs.append((str(resolved), PROJECT_SCHEME))
        pairs.append((PurePosixPath(resolved.as_posix()).as_posix(), PROJECT_SCHEME))
    resolved_repo = Path(repo_root).resolve()
    pairs.append((str(resolved_repo), REPO_SCHEME))
    pairs.append((PurePosixPath(resolved_repo.as_posix()).as_posix(), REPO_SCHEME))

    # De-duplicate while keeping the longest-first ordering.
    seen = set()
    unique: List[Tuple[str, str]] = []
    for prefix, scheme in pairs:
        if prefix and (prefix, scheme) not in seen:
            seen.add((prefix, scheme))
            unique.append((prefix, scheme))
    unique.sort(key=lambda item: len(item[0]), reverse=True)
    return unique


def sanitize_embedded_paths(
    text: str,
    *,
    repo_root: PathLike,
    project_root: Optional[PathLike] = None,
) -> str:
    """Rewrite absolute paths **inside** a longer string as logical references.

    :func:`serialize_media_path` only handles a string that is *entirely* a path. A
    QC message like ``final.mp4 not found at D:\\...\\final.mp4`` embeds one in prose,
    and those strings are exactly what ended up committed. So this scans for known
    root prefixes and rewrites the paths it finds around them.

    Only known roots are matched, never a bare ``/`` or drive letter. A generic
    "does this look like a path" regex would rewrite legitimate prose — a URL, a
    date, a POSIX-looking fragment — and a sanitizer that damages valid text is worse
    than the leak it removes. What it does not recognise, it leaves alone.
    """
    if not text or not isinstance(text, str):
        return text
    if is_logical_path(text):
        return text

    rewritten = text
    for prefix, scheme in logical_prefix_map(
        repo_root=repo_root, project_root=project_root
    ):
        search_from = 0
        while True:
            index = rewritten.find(prefix, search_from)
            if index < 0:
                break
            end = index + len(prefix)
            tail = rewritten[end:]
            # Require a separator or end-of-string, so ``D:\\a\\repoOld`` is not
            # read as living inside ``D:\\a\\repo``.
            if tail and tail[0] not in ("/", "\\"):
                search_from = end
                continue
            relative = PurePosixPath(tail.replace("\\", "/").lstrip("/")).as_posix()
            replacement = _join(scheme, relative)
            rewritten = rewritten[:index] + replacement
            search_from = index + len(replacement)
    return rewritten
