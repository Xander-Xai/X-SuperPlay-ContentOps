"""Load an execution approval and spend it atomically.

Why this is separate from the decision
--------------------------------------
:mod:`contentops.skills.authorization` is a pure function: it can refuse a grant
with no provenance, but it cannot check where that provenance came from. This
module is the only code that reads a grant off disk.

One record, not two
-------------------
An earlier revision kept a ``skill-grant.json`` that *referenced* the video
review by digest. That was wrong twice over: a content review is not an
execution approval, and any field the grant did not inherit from the review
(account, operations, expiry) could be edited without touching the approval.

Now there is exactly one record,
``receipts/skill-execution-approval.json``, and it is the authorization itself:

* ``purpose`` must be ``skill_execution`` — a content review can never satisfy it;
* every scope field is read from this one record, so there is no derived copy to
  drift out of sync;
* ``evidence`` may point at ``receipts/human-review.json``; it is checked for
  integrity but never grants anything.

What this cannot prove
----------------------
A caller with write access to the project can author this file. That is a
tamper-evident, Owner-gated workflow on a local filesystem, not authentication
and not an operating-system security boundary. No signature is used, so
non-repudiation is not claimed. See ADR-010.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from contentops.skills.authorization import ExecutionGrant

__all__ = [
    "APPROVAL_RELPATH",
    "APPROVAL_SCHEMA",
    "CONSUMPTION_RELPATH",
    "REQUIRED_PURPOSE",
    "GrantSourceError",
    "consume",
    "consumed_uses",
    "load_grant",
    "record_digest",
]

APPROVAL_SCHEMA = "contentops.skill-execution-approval/v1"
REQUIRED_PURPOSE = "skill_execution"
APPROVAL_RELPATH = Path("receipts") / "skill-execution-approval.json"
EVIDENCE_RELPATH = Path("receipts") / "human-review.json"
CONSUMPTION_RELPATH = Path("receipts") / "grants"

#: A grant id becomes a directory name. Anything that is not a single, plain
#: path component is refused rather than sanitised: silently rewriting an id
#: would make two different approvals share one consumption ledger.
_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

#: Windows maps these to devices even inside a directory, so a grant id that
#: happens to be one of them cannot name a real ledger directory.
_RESERVED_NAMES = ({"con", "prn", "aux", "nul"}
                   | {f"com{index}" for index in range(1, 10)}
                   | {f"lpt{index}" for index in range(1, 10)})



class GrantSourceError(RuntimeError):
    """A grant could not be loaded or spent. ``code`` is stable for callers."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def record_digest(payload: Mapping[str, Any]) -> str:
    """Digest of a parsed record. Stable across key order and line endings."""
    return "sha256:" + hashlib.sha256(_canonical(payload)).hexdigest()


def _safe_component(value: Any, field: str) -> str:
    """Refuse anything that is not a single plain path component."""
    if not isinstance(value, str) or not _COMPONENT_RE.match(value):
        raise GrantSourceError(
            "UNSAFE_PATH",
            f"{field} is not a safe path component (letters, digits, '.', '_' and "
            f"'-' only; no separators, no '..', no drive letters)")
    # Windows silently drops a trailing dot or space, and treats a device name as
    # a device: either would make the id name a different path than it reads as.
    if value.rstrip(". ") != value or value.split(".")[0].lower() in _RESERVED_NAMES:
        raise GrantSourceError(
            "UNSAFE_PATH", f"{field} is a reserved or ambiguous name on this platform")
    return value


def _project_root(project_dir: Path) -> Path:
    root = Path(project_dir)
    try:
        if not root.is_dir():
            raise GrantSourceError("PROJECT_INVALID", f"project is not a directory: {root.name}")
        return root.resolve(strict=True)
    except OSError as exc:
        raise GrantSourceError("PROJECT_INVALID", f"the project cannot be resolved: {exc}") from exc


def _contained(root: Path, candidate: Path, *, label: str) -> Path:
    """Resolve ``candidate`` and refuse it if it leaves ``root``.

    ``resolve`` follows symlinks, so a symlinked ``receipts`` directory pointing
    outside the project is refused here rather than silently written through.
    """
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        raise GrantSourceError("UNSAFE_PATH", f"{label} cannot be resolved: {exc}") from exc
    if resolved != root and not resolved.is_relative_to(root):
        raise GrantSourceError("UNSAFE_PATH", f"{label} resolves outside the project")
    return resolved


def _owner_allowed(issuer: str, owner_identities: Iterable[str]) -> bool:
    allowed = {str(item).strip() for item in owner_identities if str(item).strip()}
    return bool(allowed) and issuer in allowed


def _read_json(path: Path, *, missing: str, unreadable: str) -> Dict[str, Any]:
    if not path.is_file():
        raise GrantSourceError(missing, f"{path.name} is absent")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GrantSourceError(unreadable, f"{path.name} cannot be read: {exc}") from exc
    if not isinstance(payload, dict):
        raise GrantSourceError(unreadable, f"{path.name} is not a JSON object")
    return payload


def load_grant(project_dir: Path, *, owner_identities: Iterable[str],
               approval_path: Optional[Path] = None,
               evidence_path: Optional[Path] = None) -> ExecutionGrant:
    """Read the project's execution approval. Raises on every refusal."""
    root = _project_root(project_dir)
    approval_file = _contained(root,
                               Path(approval_path) if approval_path
                               else root / APPROVAL_RELPATH,
                               label="approval record")
    payload = _read_json(approval_file, missing="NO_GRANT_RECORD",
                         unreadable="GRANT_UNREADABLE")
    if payload.get("schema") != APPROVAL_SCHEMA:
        raise GrantSourceError("GRANT_SCHEMA", f"schema is not {APPROVAL_SCHEMA}")
    if payload.get("purpose") != REQUIRED_PURPOSE:
        raise GrantSourceError(
            "WRONG_PURPOSE",
            f"purpose is {payload.get('purpose')!r}; only {REQUIRED_PURPOSE!r} can "
            f"authorize a skill execution")

    issuer = str(payload.get("issuer") or "")
    if not _owner_allowed(issuer, owner_identities):
        raise GrantSourceError(
            "ISSUER_NOT_APPROVED",
            "the issuer is not in the configured Owner identity list")

    evidence = payload.get("evidence")
    if evidence is not None:
        if not isinstance(evidence, dict):
            raise GrantSourceError("EVIDENCE_INVALID", "the evidence block is not a mapping")
        evidence_file = _contained(root,
                                   Path(evidence_path) if evidence_path
                                   else root / str(evidence.get("record") or EVIDENCE_RELPATH),
                                   label="evidence record")
        evidence_payload = _read_json(evidence_file, missing="EVIDENCE_MISSING",
                                      unreadable="EVIDENCE_UNREADABLE")
        if str(evidence.get("sha256") or "") != record_digest(evidence_payload):
            raise GrantSourceError(
                "EVIDENCE_TAMPERED",
                "the supporting evidence no longer matches the digest the approval "
                "was written against")

    def _text(field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise GrantSourceError("GRANT_INVALID", f"the approval has no {field}")
        return value

    operations = payload.get("operations")
    if not isinstance(operations, list) or not operations or \
            not all(isinstance(item, str) and item.strip() for item in operations):
        raise GrantSourceError("GRANT_INVALID",
                               "operations must be a non-empty list of strings")

    def _count(field: str, minimum: int) -> int:
        value = payload.get(field, minimum)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise GrantSourceError("GRANT_INVALID",
                                   f"{field} must be an integer of at least {minimum}")
        return value

    skill_id = _text("skill_id")
    account = _text("account")
    if account == "*":
        raise GrantSourceError(
            "GRANT_INVALID",
            "an approval must name one concrete account; a wildcard would widen "
            "it to accounts nobody approved")

    return ExecutionGrant(
        grant_id=_safe_component(payload.get("approval_id"), "approval_id"),
        issuer=issuer,
        subject=_text("subject"),
        skill_id=skill_id,
        skill_version=_text("skill_version"),
        account=account,
        pipeline=_text("pipeline"),
        stage=_text("stage"),
        operations=tuple(operations),
        issued_at=_text("issued_at"),
        expires_at=_text("expires_at"),
        max_units=_count("max_units", 1),
        max_uses=_count("max_uses", 1),
        uses_consumed=0,
        revoked=bool(payload.get("revoked", False)),
        revoked_reason=str(payload.get("revoked_reason") or ""),
        provenance=record_digest(payload),
    )


def _grant_directory(root: Path, grant_id: str) -> Path:
    safe = _safe_component(grant_id, "grant_id")
    base = root / CONSUMPTION_RELPATH
    _contained(root, base, label="consumption directory")
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise GrantSourceError("CONSUMPTION_UNAVAILABLE",
                               f"the consumption directory cannot be created: {exc}") from exc
    directory = base / safe
    _contained(root, directory, label="grant consumption directory")
    if directory.is_symlink():
        raise GrantSourceError("UNSAFE_PATH", "the grant directory is a symlink")
    try:
        directory.mkdir(exist_ok=True)
    except OSError as exc:
        raise GrantSourceError("CONSUMPTION_UNAVAILABLE",
                               f"the grant directory cannot be created: {exc}") from exc
    return _contained(root, directory, label="grant consumption directory")


def _create_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    try:
        handle = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise
    except OSError as exc:
        raise GrantSourceError("MARKER_WRITE",
                               f"a consumption marker cannot be created: {exc}") from exc
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(dict(payload), stream, sort_keys=True, indent=2)
            stream.write("\n")
    except OSError as exc:
        raise GrantSourceError("MARKER_WRITE",
                               f"a consumption marker cannot be written: {exc}") from exc


def consume(project_dir: Path, *, grant: ExecutionGrant,
            request_id: str, now: str) -> Dict[str, Any]:
    """Spend one use, exactly once, even under concurrent processes.

    Two exclusive creations carry the guarantees:

    * ``request-<hash>.json`` — one attempt per request id, so re-sending the
      same request cannot spend a second use;
    * ``use-NNNN.json`` — the use slots, so a grant with ``max_uses`` of 1 can be
      won by exactly one caller.
    """
    if not isinstance(request_id, str) or not request_id.strip():
        raise GrantSourceError("REQUEST_ID", "a request id is required")
    root = _project_root(project_dir)
    directory = _grant_directory(root, grant.grant_id)

    request_key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:16]
    request_marker = directory / f"request-{request_key}.json"
    _contained(root, request_marker, label="request marker")
    try:
        _create_exclusive(request_marker, {"request_id": request_id,
                                           "grant_id": grant.grant_id,
                                           "attempted_at": now})
    except FileExistsError:
        raise GrantSourceError(
            "DUPLICATE_REQUEST",
            "this request id already spent an attempt; a retry needs a new id")

    for index in range(1, grant.max_uses + 1):
        marker = directory / f"use-{index:04d}.json"
        _contained(root, marker, label="use marker")
        try:
            _create_exclusive(marker, {"request_id": request_id,
                                       "grant_id": grant.grant_id,
                                       "consumed_at": now})
        except FileExistsError:
            continue
        return {"use": index, "marker": marker.name, "consumed_at": now}
    raise GrantSourceError(
        "USES_EXHAUSTED",
        f"{grant.max_uses}/{grant.max_uses} uses are already consumed")


def consumed_uses(project_dir: Path, grant_id: str) -> List[str]:
    """Marker files already spent. Read-only; never creates anything."""
    root = _project_root(project_dir)
    directory = root / CONSUMPTION_RELPATH / _safe_component(grant_id, "grant_id")
    _contained(root, directory, label="grant consumption directory")
    if not directory.is_dir():
        return []
    return sorted(item.name for item in directory.glob("use-*.json"))
