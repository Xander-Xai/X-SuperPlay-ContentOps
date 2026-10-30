#!/usr/bin/env python3
"""Shared fail-closed security primitives for the workflow control plane.

The article directory is untrusted input.  This module centralises three
properties that used to be implemented inconsistently across scripts:

* duplicate-key rejecting JSON/YAML parsing;
* repository-root boundary checks (with an explicit, test-only fixture escape);
* a small cross-process lock and compare-and-swap helper for matrix state.

These helpers do not authenticate a human or a repository.  They only make
the local control plane deterministic and fail closed when its inputs are
ambiguous or concurrently changed.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]


class DuplicateKeyError(ValueError):
    """Raised when a JSON/YAML object repeats a key."""


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_json_text(text: str) -> Any:
    """Parse JSON while rejecting duplicate object keys."""

    return json.loads(text, object_pairs_hook=_unique_pairs)


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return load_json_text(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, DuplicateKeyError):
        return default


def load_yaml_text(text: str) -> Any:
    """Parse YAML with a duplicate-key rejecting SafeLoader."""

    try:
        import yaml  # type: ignore
    except ImportError:
        # The workflow already treats PyYAML as an optional dependency in a
        # few low-level helpers.  Returning a failure sentinel is safer than
        # silently using the permissive loader when it is absent.
        raise RuntimeError("PyYAML is required for strict YAML parsing")

    class StrictLoader(yaml.SafeLoader):
        pass

    def construct_mapping(loader: Any, node: Any, deep: bool = False) -> dict[Any, Any]:
        loader.flatten_mapping(node)
        result: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in result:
                raise DuplicateKeyError(f"duplicate key: {key}")
            result[key] = loader.construct_object(value_node, deep=deep)
        return result

    StrictLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping,
    )
    return yaml.load(text, Loader=StrictLoader)


def load_yaml(path: Path, default: Any = None) -> Any:
    try:
        return load_yaml_text(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, DuplicateKeyError, RuntimeError):
        return default


def resolve_inside(candidate: Path | str, *, root: Path = ROOT, label: str = "path") -> Path:
    """Resolve *candidate* and require it to be inside *root*."""

    path = Path(candidate).expanduser()
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside repository root: {candidate}") from exc
    return resolved


def is_test_mode() -> bool:
    return os.environ.get("WORKFLOW_TEST_MODE") == "1"


def ensure_article_path(
    candidate: Path | str,
    *,
    allow_test_fixture: bool = True,
    label: str = "article path",
) -> Path:
    """Resolve an article path and fail closed outside the repository.

    Network-free unit/e2e fixtures may live in a temporary directory, but
    only while the explicit test mode is active.  External-action callers
    should pass ``allow_test_fixture=False`` so setting the test flag cannot
    turn into a publish/upload bypass.
    """

    # Article workspaces are deliberately external to the workflow source
    # tree.  Keep this import local so the low-level security module remains
    # usable while workspace_paths imports only standard-library primitives.
    try:
        from workspace_paths import resolve_article_workspace
        return resolve_article_workspace(candidate, allow_test_fixture=allow_test_fixture)
    except ValueError as exc:
        raise ValueError(f"{label}: {exc}") from exc


def content_snapshot(article_dir: Path) -> str:
    """Digest the mutable reader-facing files for a last-moment TOCTOU check."""

    payload: list[tuple[str, str]] = []
    for name in ("article.md", "article.html", "article.yaml"):
        path = article_dir / name
        digest = sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
        payload.append((name, digest))
    return sha256(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


@contextmanager
def state_lock(article_dir: Path, *, timeout: float = 10.0) -> Iterator[None]:
    """Acquire a cross-process lock for matrix-state transitions.

    ``msvcrt.locking`` is available on Windows and ``fcntl`` on POSIX.  The
    lock file is intentionally retained as a harmless workspace control file;
    its byte range is what provides mutual exclusion.
    """

    lock_path = article_dir / ".matrix-state.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    handle.seek(0)
    handle.write(b"0")
    handle.flush()
    deadline = time.monotonic() + timeout
    locked = False
    try:
        while not locked:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise TimeoutError("matrix-state lock timeout")
                time.sleep(0.05)
        yield
    finally:
        if locked:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


class StateConflict(RuntimeError):
    """Raised when a state/input digest changed during a gate transition."""
