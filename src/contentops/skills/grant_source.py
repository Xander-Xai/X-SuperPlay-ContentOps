"""Load an execution grant from a verified approval record.

Why this is separate from the decision
--------------------------------------
:mod:`contentops.skills.authorization` is a pure function: it can refuse a grant
with no provenance, but it cannot check where that provenance came from. This
module is the only code that reads a grant off disk, and it anchors every grant
to an existing human decision record.

The anchor, not a second ledger
-------------------------------
The repository already has one authoritative human record per project:
``receipts/human-review.json``. It ships with ``decision: null`` and a note that
it is not an approval until a person fills it. A skill grant does not replace or
duplicate that record; it *references* it by digest:

```
skill-grant.json  --approval-->  receipts/human-review.json (decision APPROVED)
```

If the review record changes after the grant was written, the digest no longer
matches and the grant is refused. If no review record exists, or its decision is
not ``APPROVED``, no grant can be loaded at all.

What this cannot prove
----------------------
A caller with write access to the repository can author both files. This is a
tamper-evident, Owner-gated workflow, not an operating-system security boundary.
The honest claim is: *no execution grant exists unless a recorded human decision
says APPROVED, and editing either record is detectable*. Signing keys are out of
scope for this increment; see ADR-010.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from contentops.skills.authorization import ExecutionGrant

__all__ = [
    "GRANT_SCHEMA",
    "REVIEW_SCHEMA_NOTE",
    "GrantSourceError",
    "consume",
    "load_grant",
    "record_digest",
    "review_digest",
]

GRANT_SCHEMA = "contentops.skill-execution-grant/v1"
REVIEW_SCHEMA_NOTE = "hand-written review record; decision must be APPROVED"
GRANT_RELPATH = Path("receipts") / "skill-grant.json"
REVIEW_RELPATH = Path("receipts") / "human-review.json"
CONSUMPTION_RELPATH = Path("receipts") / "grants"
REQUIRED_DECISION = "APPROVED"


class GrantSourceError(RuntimeError):
    """A grant could not be loaded from a trustworthy record."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def record_digest(payload: Mapping[str, Any]) -> str:
    """Digest of a review record, stable across key order and line endings."""
    return "sha256:" + hashlib.sha256(_canonical(payload)).hexdigest()


def review_digest(path: Path) -> str:
    """Digest of the review file as parsed JSON, not as raw bytes.

    Parsing first means a trailing newline or reordering keys does not look like
    tampering, while a changed value does.
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GrantSourceError("REVIEW_UNREADABLE",
                               f"the review record cannot be read: {exc}") from exc
    return record_digest(payload)


def _owner_allowed(issuer: str, owner_identities: Iterable[str]) -> bool:
    allowed = {str(item).strip() for item in owner_identities if str(item).strip()}
    return bool(allowed) and issuer in allowed


def load_grant(project_dir: Path, *, owner_identities: Iterable[str],
               grant_path: Optional[Path] = None,
               review_path: Optional[Path] = None) -> ExecutionGrant:
    """Read the project's grant, verifying it against the human record.

    Raises :class:`GrantSourceError` with a stable code on every refusal.
    """
    project = Path(project_dir)
    grant_file = Path(grant_path) if grant_path else project / GRANT_RELPATH
    review_file = Path(review_path) if review_path else project / REVIEW_RELPATH

    if not grant_file.is_file():
        raise GrantSourceError("NO_GRANT_RECORD",
                               "the project has no signed-off skill grant")
    try:
        payload = json.loads(grant_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GrantSourceError("GRANT_UNREADABLE",
                               f"the grant record cannot be read: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != GRANT_SCHEMA:
        raise GrantSourceError("GRANT_SCHEMA", f"schema is not {GRANT_SCHEMA}")

    issuer = str(payload.get("issuer") or "")
    if not _owner_allowed(issuer, owner_identities):
        raise GrantSourceError(
            "ISSUER_NOT_APPROVED",
            "the grant issuer is not in the configured Owner identity list")

    approval = payload.get("approval") or {}
    if not isinstance(approval, dict):
        raise GrantSourceError("APPROVAL_INVALID", "the approval block is not a mapping")
    if not review_file.is_file():
        raise GrantSourceError("APPROVAL_MISSING",
                               f"the referenced review record is absent: {review_file.name}")
    try:
        review = json.loads(review_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GrantSourceError("APPROVAL_UNREADABLE",
                               f"the review record cannot be read: {exc}") from exc

    if review.get("decision") != REQUIRED_DECISION:
        raise GrantSourceError(
            "APPROVAL_NOT_APPROVED",
            f"the review decision is {review.get('decision')!r}, not {REQUIRED_DECISION!r}")
    for field in ("reviewer", "reviewed_at"):
        if not str(review.get(field) or "").strip():
            raise GrantSourceError("APPROVAL_INVALID",
                                   f"the review record has no {field}")

    actual_digest = record_digest(review)
    declared_digest = str(approval.get("sha256") or "")
    if declared_digest != actual_digest:
        raise GrantSourceError(
            "APPROVAL_TAMPERED",
            "the review record no longer matches the digest the grant was approved against")

    def _text(field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise GrantSourceError("GRANT_INVALID", f"the grant has no {field}")
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

    return ExecutionGrant(
        grant_id=_text("grant_id"),
        issuer=issuer,
        subject=_text("subject"),
        skill_id=_text("skill_id"),
        skill_version=_text("skill_version"),
        account=_text("account"),
        pipeline=_text("pipeline"),
        stage=_text("stage"),
        operations=tuple(operations),
        issued_at=_text("issued_at"),
        expires_at=_text("expires_at"),
        max_units=_count("max_units", 1),
        max_uses=_count("max_uses", 1),
        uses_consumed=int(payload.get("uses_consumed", 0) or 0),
        revoked=bool(payload.get("revoked", False)),
        revoked_reason=str(payload.get("revoked_reason") or ""),
        provenance=actual_digest,
    )


def consume(project_dir: Path, *, grant: ExecutionGrant,
            request_id: str, now: str) -> Dict[str, Any]:
    """Atomically spend one use of a grant.

    The atomic step is ``O_CREAT|O_EXCL`` on ``use-NNNN.json``. Two processes
    racing for the last use both see the same directory; exactly one creation
    succeeds and the other gets ``FileExistsError`` and moves on. A plain
    read-then-write counter would let both win.
    """
    if not request_id or not str(request_id).strip():
        raise GrantSourceError("REQUEST_ID", "a request id is required")
    directory = Path(project_dir) / CONSUMPTION_RELPATH / grant.grant_id
    directory.mkdir(parents=True, exist_ok=True)
    for index in range(1, grant.max_uses + 1):
        marker = directory / f"use-{index:04d}.json"
        try:
            handle = os.open(str(marker), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump({"request_id": request_id, "grant_id": grant.grant_id,
                       "consumed_at": now}, stream, sort_keys=True, indent=2)
            stream.write("\n")
        return {"use": index, "marker": marker.name, "consumed_at": now}
    raise GrantSourceError(
        "USES_EXHAUSTED",
        f"{grant.max_uses}/{grant.max_uses} uses are already consumed")


def consumed_uses(project_dir: Path, grant_id: str) -> List[str]:
    """Marker files already spent. Read-only; used by receipts and tests."""
    directory = Path(project_dir) / CONSUMPTION_RELPATH / grant_id
    if not directory.is_dir():
        return []
    return sorted(item.name for item in directory.glob("use-*.json"))
