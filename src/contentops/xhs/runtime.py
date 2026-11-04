"""XHS (Xiaohongshu) workflow as a locally installed runtime.

Why an adapter and not a copy
-----------------------------
The XHS pre-publication workflow is a 47-skill tree. Its root is Apache-2.0 but
one bundled skill is AGPL-3.0, and the tree also carries account-specific
working data. Copying it into this public repository would redistribute both.
So ContentOps carries the *seam*:

- the operator installs the workflow outside this repository and records a
  trusted lock (root identity, contract files, rights status, operations);
- the adapter locates that root, verifies every recorded byte, and reads the
  identity the lock states;
- it describes the operations. It does not run them, draft, or publish.

A missing root or lock is ``MISSING_RUNTIME`` / ``LOCK_MISSING`` — not a pass.
The rights status does not block file verification, but it always keeps the plan
at ``production_ready: false`` and ``publish_authorized: false``.

Easel boundary
--------------
The adapter is the GRAPHIC_TEXT seam. Easel remains the base for visual assets
and composition; this adapter only produces the manual package plan. It never
starts the Easel host, installs a dependency or authorizes publication.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "contentops.xhs-runtime-lock/v1"
STATUS_SCHEMA = "contentops.xhs-status/v1"
PLAN_SCHEMA = "contentops.xhs-plan/v1"

ROOT_ENV = "CONTENTOPS_XHS_ROOT"
LOCK_PATH = Path("runtime") / "xhs-runtime.lock.json"

VERIFIED = "VERIFIED"
BLOCKED = "BLOCKED"

#: The identity the lock must state. A lock naming another workflow or medium
#: is not this adapter.
REQUIRED_IDENTITY = {
    "workflow_id": "xhs-fa",
    "account_id": "future-intelligence",
    "content_medium": "xiaohongshu_image",
}

#: Operations the operator may run against a verified root. None is executed
#: here, and the last one produces a package only; it never publishes.
OPERATIONS = (
    {"name": "workspace_new", "authority": "OPERATOR",
     "command": "python scripts/workspace.py new --title <title>"},
    {"name": "gate", "authority": "READ_ONLY",
     "command": "python scripts/pipeline_gate.py --check"},
    {"name": "finalize", "authority": "OPERATOR",
     "command": "python scripts/workspace.py finalize --workspace <workspace>"},
    {"name": "publication_package", "authority": "OPERATOR",
     "command": "python scripts/publication_package.py --workspace <workspace>"},
)


class XhsBlocked(Exception):
    """The XHS runtime cannot be used, and this is the named reason."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_lock(path: Optional[Path] = None) -> Dict[str, Any]:
    """Read and structurally validate the trusted lock."""
    target = Path(path) if path else _repo_root() / LOCK_PATH
    if not target.is_file():
        raise XhsBlocked("LOCK_MISSING", f"{target.as_posix()} is missing")
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise XhsBlocked("LOCK_MALFORMED", f"{target.as_posix()}: {exc}") from None
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise XhsBlocked("LOCK_MALFORMED",
                         f"{target.as_posix()} must declare schema {SCHEMA!r}")

    identity = document.get("identity")
    if not isinstance(identity, dict):
        raise XhsBlocked("LOCK_MALFORMED", "lock.identity must be an object")
    for key, expected in REQUIRED_IDENTITY.items():
        if str(identity.get(key) or "") != expected:
            raise XhsBlocked(
                "IDENTITY_UNEXPECTED",
                f"lock.identity.{key} must be {expected!r}, got {identity.get(key)!r}")

    files = document.get("files")
    if not isinstance(files, list) or not files:
        raise XhsBlocked("LOCK_MALFORMED", "lock.files must be a non-empty list")
    for entry in files:
        if not isinstance(entry, dict) or not entry.get("path") or not entry.get("sha256"):
            raise XhsBlocked("LOCK_MALFORMED",
                             "each lock.files entry needs path and sha256")
    return document


def locate_root(root: Optional[Path] = None, *, repo_root: Optional[Path] = None) -> Path:
    """The installed workflow root, or a named refusal."""
    candidate = root or os.environ.get(ROOT_ENV)
    if not candidate:
        raise XhsBlocked("MISSING_RUNTIME",
                         f"no workflow root: pass a path or set {ROOT_ENV}")
    resolved = Path(candidate).expanduser().resolve()
    if not resolved.is_dir():
        raise XhsBlocked("MISSING_RUNTIME", f"{resolved.as_posix()} is not a directory")
    boundary = (Path(repo_root) if repo_root else _repo_root()).resolve()
    try:
        resolved.relative_to(boundary)
    except ValueError:
        return resolved
    raise XhsBlocked(
        "ROOT_INSIDE_REPO",
        f"{resolved.as_posix()} is inside the public repository; the installed "
        f"workflow must stay outside it (Issue #51)")


def verify(root: Path, lock: Dict[str, Any], *, repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Verify every recorded byte and the identity the lock states."""
    identity = lock.get("identity") if isinstance(lock.get("identity"), dict) else {}
    for key, expected in REQUIRED_IDENTITY.items():
        if str(identity.get(key) or "") != expected:
            raise XhsBlocked(
                "IDENTITY_UNEXPECTED",
                f"lock.identity.{key} must be {expected!r}, got {identity.get(key)!r}")
    boundary = (Path(repo_root) if repo_root else _repo_root()).resolve()
    problems: List[str] = []
    for entry in lock["files"]:
        relative = str(entry["path"]).replace("\\", "/")
        if relative.startswith("/") or ".." in Path(relative).parts:
            raise XhsBlocked("LOCK_PATH_ILLEGAL",
                             f"lock path {relative!r} escapes the workflow root")
        target = (root / relative).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            raise XhsBlocked("LOCK_PATH_ILLEGAL",
                             f"lock path {relative!r} resolves outside the root") from None
        if not target.is_file():
            problems.append(f"{relative}: file missing")
            continue
        actual = _sha256(target)
        if actual != str(entry["sha256"]):
            problems.append(f"{relative}: sha256 {actual[:12]} != recorded {str(entry['sha256'])[:12]}")
    if problems:
        raise XhsBlocked("HASH_DRIFT", "; ".join(problems))

    rights = lock.get("rights") or {}
    return {
        "schema": STATUS_SCHEMA,
        "state": VERIFIED,
        "root": str(root.resolve()),
        "workflow_id": REQUIRED_IDENTITY["workflow_id"],
        "account_id": REQUIRED_IDENTITY["account_id"],
        "content_medium": REQUIRED_IDENTITY["content_medium"],
        "rights_status": str(rights.get("status") or "UNRESOLVED"),
        "rights_note": str(rights.get("note") or ""),
        "files_verified": len(lock["files"]),
        "repo_boundary": str(boundary),
        "production_ready": False,
        "publish_authorized": False,
    }


def status(
    root: Optional[Path] = None,
    *,
    lock_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Locate, load and verify; never raise for a missing runtime."""
    try:
        lock = load_lock(lock_path)
        located = locate_root(root, repo_root=repo_root)
        return verify(located, lock, repo_root=repo_root)
    except XhsBlocked as blocked:
        return {"schema": STATUS_SCHEMA, "state": BLOCKED,
                "code": blocked.code, "detail": blocked.detail}


def plan(
    root: Optional[Path] = None,
    *,
    lock_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Describe the operations; grant nothing."""
    result = status(root, lock_path=lock_path, repo_root=repo_root)
    rights = str(result.get("rights_status") or "UNRESOLVED")
    return {
        "schema": PLAN_SCHEMA,
        "state": result["state"],
        "root": result.get("root"),
        "workflow_id": result.get("workflow_id"),
        "account_id": result.get("account_id"),
        "content_medium": result.get("content_medium"),
        "rights_status": rights,
        "rights_note": result.get("rights_note", ""),
        "easel_surface": "graphic_text_manual_package",
        "operations": [dict(item) for item in OPERATIONS],
        "execution_authorized": False,
        "publish_authorized": False,
        "production_ready": False,
        "detail": result.get("detail"),
        "code": result.get("code"),
    }
