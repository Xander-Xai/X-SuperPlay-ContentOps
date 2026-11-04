"""The GZH (WeChat official account) workflow as a locally installed runtime.

Why an adapter and not a copy
-----------------------------
The ten-stage GZH workflow lives in a vendored tree that Issue #56 has not
cleared for public redistribution. Copying it into this repository would
republish code whose rights are unresolved. So ContentOps carries the *seam*
instead of the code:

- the operator installs the workflow somewhere outside this repository and
  records a trusted lock: which root, which identity, which files, which
  rights status, which operations;
- the adapter locates that root, verifies every recorded byte, and reads the
  identity contract;
- it describes the operations. It does not run them, draft, or publish.

A missing root or lock is ``MISSING_RUNTIME`` / ``LOCK_MISSING`` — not a pass.
An unresolved rights status does not block verification of the files, but it
does block production: the plan always reports ``production_ready: false`` and
``publish_authorized: false``.

Parsing note
------------
The contract files are YAML, and CI does not install PyYAML. Only four
top-level scalars are needed, so the reader accepts a single ``key: value``
line and refuses when a key is missing or appears twice. The lock's hashes, not
the parser, are what prove the reviewed contract has not changed.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "contentops.gzh-runtime-lock/v1"
STATUS_SCHEMA = "contentops.gzh-status/v1"
PLAN_SCHEMA = "contentops.gzh-plan/v1"

ROOT_ENV = "CONTENTOPS_GZH_ROOT"
LOCK_PATH = Path("runtime") / "gzh-runtime.lock.json"

VERIFIED = "VERIFIED"
BLOCKED = "BLOCKED"

#: The identity the lock must state. A lock that names another account or
#: another medium is not this workflow.
REQUIRED_IDENTITY = {
    "workflow_id": "gzh-thinktank",
    "account_id": "thinktank",
    "content_medium": "wechat_article",
}

#: Operations the operator may run against a verified root. None of them is
#: executed by this adapter, and none of them publishes.
OPERATIONS = (
    {"name": "initialize", "authority": "OPERATOR",
     "command": "python scripts/matrix_init.py --route <external-route> --title <title>"},
    {"name": "audit", "authority": "READ_ONLY",
     "command": "python scripts/workspace_audit.py --check"},
    {"name": "lifecycle", "authority": "OPERATOR",
     "command": "python scripts/workspace_lifecycle.py --workspace <workspace> "
                "--to delivered|archive|quarantine"},
)


class GzhBlocked(Exception):
    """The GZH runtime cannot be used, and this is the named reason."""

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
        raise GzhBlocked("LOCK_MISSING", f"{target.as_posix()} is missing")
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GzhBlocked("LOCK_MALFORMED", f"{target.as_posix()}: {exc}") from None
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise GzhBlocked("LOCK_MALFORMED",
                         f"{target.as_posix()} must declare schema {SCHEMA!r}")

    identity = document.get("identity")
    if not isinstance(identity, dict):
        raise GzhBlocked("LOCK_MALFORMED", "lock.identity must be an object")
    for key, expected in REQUIRED_IDENTITY.items():
        if str(identity.get(key) or "") != expected:
            raise GzhBlocked(
                "IDENTITY_UNEXPECTED",
                f"lock.identity.{key} must be {expected!r}, got "
                f"{identity.get(key)!r}")

    files = document.get("files")
    if not isinstance(files, list) or not files:
        raise GzhBlocked("LOCK_MALFORMED", "lock.files must be a non-empty list")
    for entry in files:
        if not isinstance(entry, dict) or not entry.get("path") or not entry.get("sha256"):
            raise GzhBlocked("LOCK_MALFORMED",
                             "each lock.files entry needs path and sha256")

    rights = document.get("rights")
    if not isinstance(rights, dict) or not rights.get("status"):
        raise GzhBlocked("LOCK_MALFORMED",
                         "lock.rights must state a status; an unstated rights "
                         "status is not 'cleared'")
    return document


def locate_root(root: Optional[Path] = None, *, repo_root: Optional[Path] = None) -> Path:
    """The installed workflow root, or a named refusal."""
    candidate = root or os.environ.get(ROOT_ENV)
    if not candidate:
        raise GzhBlocked(
            "MISSING_RUNTIME",
            f"no workflow root: pass a path or set {ROOT_ENV}")
    resolved = Path(candidate).expanduser().resolve()
    if not resolved.is_dir():
        raise GzhBlocked("MISSING_RUNTIME", f"{resolved.as_posix()} is not a directory")
    boundary = (Path(repo_root) if repo_root else _repo_root()).resolve()
    try:
        relative = resolved.relative_to(boundary)
    except ValueError:
        return resolved
    # The project-local .runtime/ tree is gitignored and is the approved
    # operator install location. Any other in-repo path would put the workflow
    # into the public repository, so it stays refused.
    if relative.parts and relative.parts[0] == ".runtime":
        return resolved
    raise GzhBlocked(
        "ROOT_INSIDE_REPO",
        f"{resolved.as_posix()} is inside the public repository; the vendored "
        f"workflow must stay outside it (Issue #56)")


def _scalars(path: Path, keys: List[str]) -> Dict[str, str]:
    """Read top-level ``key: value`` lines; refuse a missing or doubled key."""
    found: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line[0].isspace():
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key not in keys:
            continue
        value = value.strip().strip('"').strip("'")
        if key in found:
            raise GzhBlocked("CONTRACT_AMBIGUOUS",
                             f"{path.name}: {key!r} appears more than once")
        found[key] = value
    missing = [key for key in keys if key not in found]
    if missing:
        raise GzhBlocked("CONTRACT_INCOMPLETE",
                         f"{path.name} is missing {missing}")
    return found


def verify(root: Path, lock: Dict[str, Any], *, repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Verify every recorded byte and the identity the lock states."""
    boundary = (Path(repo_root) if repo_root else _repo_root()).resolve()
    identity_file = root / "workflow-identity.yaml"
    contract_file = root / "workspace-contract.yaml"

    problems: List[str] = []
    for entry in lock["files"]:
        relative = str(entry["path"]).replace("\\", "/")
        if relative.startswith("/") or ".." in Path(relative).parts:
            raise GzhBlocked("LOCK_PATH_ILLEGAL",
                             f"lock path {relative!r} escapes the workflow root")
        target = (root / relative).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            raise GzhBlocked("LOCK_PATH_ILLEGAL",
                             f"lock path {relative!r} resolves outside the root") from None
        if not target.is_file():
            problems.append(f"{relative}: file missing")
            continue
        actual = _sha256(target)
        if actual != str(entry["sha256"]):
            problems.append(f"{relative}: sha256 {actual[:12]} != recorded "
                            f"{str(entry['sha256'])[:12]}")
    if problems:
        raise GzhBlocked("HASH_DRIFT", "; ".join(problems))

    if not identity_file.is_file():
        raise GzhBlocked("CONTRACT_INCOMPLETE",
                         f"{identity_file.as_posix()} is missing")
    if not contract_file.is_file():
        raise GzhBlocked("CONTRACT_INCOMPLETE",
                         f"{contract_file.as_posix()} is missing")

    live = _scalars(identity_file, list(REQUIRED_IDENTITY))
    for key, expected in REQUIRED_IDENTITY.items():
        if live.get(key) != expected:
            raise GzhBlocked(
                "IDENTITY_MISMATCH",
                f"{identity_file.name}: {key} is {live.get(key)!r}, expected {expected!r}")

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
    except GzhBlocked as blocked:
        return {"schema": STATUS_SCHEMA, "state": BLOCKED,
                "code": blocked.code, "detail": blocked.detail}


def plan(
    root: Optional[Path] = None,
    *,
    lock_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Describe the operations; grant nothing.

    ``execution_authorized`` and ``publish_authorized`` are always false. The
    rights status is carried through so a caller cannot mistake a file check
    for a rights decision.
    """
    result = status(root, lock_path=lock_path, repo_root=repo_root)
    rights = str(result.get("rights_status") or "UNRESOLVED")
    ready = result["state"] == VERIFIED and rights == "CLEARED"
    return {
        "schema": PLAN_SCHEMA,
        "state": result["state"],
        "code": result.get("code"),
        "detail": result.get("detail"),
        "workflow_id": result.get("workflow_id"),
        "account_id": result.get("account_id"),
        "content_medium": result.get("content_medium"),
        "rights_status": rights,
        "operations": [
            {**operation, "execution_authorized": False, "publish_authorized": False}
            for operation in OPERATIONS
        ],
        "execution_authorized": False,
        "publish_authorized": False,
        "production_ready": ready,
        "note": "this adapter verifies and describes; it never runs a stage, "
                "drafts an article or publishes. A CLEARED rights status is a "
                "record, not this tool's decision.",
    }
