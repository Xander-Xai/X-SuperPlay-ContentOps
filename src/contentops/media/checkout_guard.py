"""Refuse production writes into a main checkout that is already dirty.

Why this module exists
----------------------
The main checkout had accumulated 24 modified tracked files when this rule was
added: QC receipts rewritten by later runs, a storyboard edited in place, a
sample spreadsheet row appended. None of that work was lost, but none of it was
reviewable either -- the receipts that are supposed to be the evidence trail had
been overwritten by the next experiment, so "what did the last accepted run
actually record" stopped being answerable from Git.

The receipts are not the disease; the disease is that a production entry point
will happily write into a checkout that already holds unreviewed work. Every run
after the first one buries the previous run's evidence a little deeper.

So the rule is narrow and it is a refusal, not a cleanup:

*   A production run that targets a project inside the **main checkout** is
    refused when that checkout has any uncommitted change -- tracked edits or
    untracked files. Refusing at the door means this run cannot be the reason a
    receipt gets overwritten.
*   ``projects/_local/`` is exempt. It is gitignored, it is where experiments
    belong, and a run there cannot dirty anything by definition.
*   A linked git worktree is not the main checkout. Writes there do not touch
    the main checkout's index or working tree, so the guard does not apply.
*   A project outside the repository cannot dirty the repository, so the guard
    does not apply. Neither does a directory that is not a git checkout at all
    (``NOT_A_CHECKOUT``): there is no index to pollute, and refusing would break
    every fixture that runs an entry point against a temporary project.

What it never does: ``git clean``, ``git restore``, ``git stash``, deleting
untracked files, or deciding which dirty file is "probably fine". The operator
resolves the tree; this module only reports it and stops.

The check runs once per process and is cached. That matters: ``produce_video``
writes its own receipt before delegating to ``m5_production.build()``, so a
second, uncached check would see the fresh receipt and block the very run that
just wrote it. The state that governs a run is the state it started in.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from process_utils import hidden_run  # noqa: E402

__all__ = [
    "DirtyCheckoutError",
    "checkout_state",
    "ensure_writable_checkout",
    "main_checkout_root",
    "reset_cache",
]

LOCAL_PROJECTS = ("projects", "_local")
MAX_LISTED_PATHS = 12
GIT_TIMEOUT_SECONDS = 60

_cache: Dict[tuple, Dict[str, Any]] = {}


class DirtyCheckoutError(RuntimeError):
    """The main checkout holds unreviewed work, so this run must not write."""

    def __init__(self, message: str, state: Dict[str, Any]) -> None:
        super().__init__(message)
        self.state = state


def reset_cache() -> None:
    """Forget every observed checkout state. Tests use this; production does not."""
    _cache.clear()


def _git(repo_root: Path, *args: str) -> Optional[subprocess.CompletedProcess]:
    """Run one git command through the shared no-console subprocess layer."""
    try:
        return hidden_run(["git", "-C", str(repo_root), *args],
                          timeout=GIT_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None


def main_checkout_root(repo_root: Path) -> Optional[Path]:
    """Return the main worktree root, or None when git cannot tell us.

    ``--git-common-dir`` points at the shared ``.git`` for every worktree of the
    repository, so its parent is the main checkout even when this call runs from
    a linked worktree. A normal checkout simply reports ``.git``.
    """
    repo_root = Path(repo_root).resolve()
    result = _git(repo_root, "rev-parse", "--git-common-dir")
    if result is None or result.returncode != 0:
        return None
    reported = result.stdout.strip().splitlines()
    if not reported:
        return None
    common = Path(reported[-1])
    if not common.is_absolute():
        common = (repo_root / common).resolve()
    else:
        common = common.resolve()
    return common.parent if common.name == ".git" else None


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _dirty_entries(repo_root: Path) -> Optional[List[str]]:
    """Return every uncommitted path, or None when git could not be read."""
    result = _git(
        repo_root,
        "status",
        "--porcelain",
        "-z",
        "--untracked-files=normal",
        "--ignore-submodules=none",
    )
    if result is None or result.returncode != 0:
        return None
    entries: List[str] = []
    for chunk in result.stdout.split("\0"):
        if not chunk.strip():
            continue
        # Porcelain -z puts the status in the first two columns; a rename adds a
        # second path in the following chunk, which is reported as its own entry.
        entries.append(chunk[3:] if len(chunk) > 3 else chunk.strip())
    return entries


def checkout_state(project: Path, *, repo_root: Path) -> Dict[str, Any]:
    """Describe whether this project's run may write, without writing anything."""
    repo_root = Path(repo_root).resolve()
    project = Path(project).resolve()

    if not _is_inside(project, repo_root):
        return {
            "allowed": True,
            "reason": "PROJECT_OUTSIDE_REPO",
            "checkout": None,
            "project": str(project),
            "local_sandbox": False,
            "dirty_count": 0,
            "dirty_paths": [],
        }

    relative = project.relative_to(repo_root)
    local_sandbox = relative.parts[:2] == LOCAL_PROJECTS

    # A directory that is not a checkout has no index to pollute. This is the
    # fixture case: every test that runs a production entry point against a temp
    # project would otherwise be refused for a checkout that does not exist.
    if not (repo_root / ".git").exists():
        return {
            "allowed": True,
            "reason": "NOT_A_CHECKOUT",
            "checkout": None,
            "project": relative.as_posix(),
            "local_sandbox": local_sandbox,
            "dirty_count": 0,
            "dirty_paths": [],
        }

    main_root = main_checkout_root(repo_root)
    if main_root is None:
        return {
            "allowed": False,
            "reason": "GIT_UNAVAILABLE",
            "checkout": None,
            "project": relative.as_posix(),
            "local_sandbox": local_sandbox,
            "dirty_count": 0,
            "dirty_paths": [],
        }

    if main_root != repo_root:
        return {
            "allowed": True,
            "reason": "NOT_MAIN_CHECKOUT",
            "checkout": "WORKTREE",
            "project": relative.as_posix(),
            "local_sandbox": local_sandbox,
            "dirty_count": 0,
            "dirty_paths": [],
        }

    if local_sandbox:
        return {
            "allowed": True,
            "reason": "LOCAL_SANDBOX",
            "checkout": "MAIN",
            "project": relative.as_posix(),
            "local_sandbox": True,
            "dirty_count": 0,
            "dirty_paths": [],
        }

    entries = _dirty_entries(repo_root)
    if entries is None:
        return {
            "allowed": False,
            "reason": "GIT_UNAVAILABLE",
            "checkout": "MAIN",
            "project": relative.as_posix(),
            "local_sandbox": False,
            "dirty_count": 0,
            "dirty_paths": [],
        }

    if entries:
        return {
            "allowed": False,
            "reason": "DIRTY_MAIN_CHECKOUT",
            "checkout": "MAIN",
            "project": relative.as_posix(),
            "local_sandbox": False,
            "dirty_count": len(entries),
            "dirty_paths": sorted(entries)[:MAX_LISTED_PATHS],
        }

    return {
        "allowed": True,
        "reason": "CLEAN",
        "checkout": "MAIN",
        "project": relative.as_posix(),
        "local_sandbox": False,
        "dirty_count": 0,
        "dirty_paths": [],
    }


def ensure_writable_checkout(project: Path, *, repo_root: Path) -> Dict[str, Any]:
    """Return the cached state, raising when this run must not write.

    Raises ``DirtyCheckoutError``. The message names the checkout, the count and
    up to twelve paths, because "the tree is dirty" is not actionable and a list
    of twelve is enough to recognise which experiment leaked.
    """
    repo_root = Path(repo_root).resolve()
    project = Path(project).resolve()
    key = (str(repo_root), str(project))
    state = _cache.get(key)
    if state is None:
        state = checkout_state(project, repo_root=repo_root)
        _cache[key] = state
    if state["allowed"]:
        return state
    if state["reason"] == "GIT_UNAVAILABLE":
        raise DirtyCheckoutError(
            "refusing to write: git could not report the checkout state for "
            f"{repo_root}, so this run cannot prove it is writing into a clean "
            "checkout",
            state,
        )
    listed = "\n".join(f"    {path}" for path in state["dirty_paths"])
    raise DirtyCheckoutError(
        "refusing to write into a dirty main checkout: "
        f"{state['dirty_count']} uncommitted path(s) under {repo_root}.\n"
        f"{listed}\n"
        "  Commit or set aside that work, or run the experiment under "
        "projects/_local/ (gitignored). This guard never reverts anything.",
        state,
    )
