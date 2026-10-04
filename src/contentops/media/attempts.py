"""Durable generation attempt records: retry evidence that survives a process.

Why a file and not an attribute
-------------------------------
The retry rule is "attempt 2 must change a real generation input". That check used
to compare against ``provider._last_attempt_fingerprint``, which only lives inside
one Python process. The real operator workflow is two separate commands:

```
python scripts/synthesize_narration.py ...          # process 1
python scripts/synthesize_narration.py --retry-from <record> ...   # process 2
```

In process 2 the attribute is ``None``, so an **identical** attempt 2 sailed
through and the rule silently did nothing. The evidence therefore has to be on
disk, next to the generated assets, where the next process can find it.

What a record is, and is not
-----------------------------
It is **retry evidence**, not an asset receipt. The receipt describes a successful
generation and is immutable (see ``minimax_speech``); the attempt record describes
what was tried and how it ended.

What a record never contains
----------------------------
No credential, no credential fragment, no ``Authorization`` header, no account id,
and no raw provider response. ``failure_reason`` is a sanitised class-level string,
never a pasted API body.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = [
    "ATTEMPT_SCHEMA_VERSION",
    "STATUS_STARTED",
    "STATUS_FAILED",
    "STATUS_SUCCEEDED",
    "AttemptRecordError",
    "GenerationAttemptRecord",
    "attempts_dir",
    "sanitise_failure",
]

ATTEMPT_SCHEMA_VERSION = "contentops.generation-attempt/v1"

STATUS_STARTED = "STARTED"
STATUS_FAILED = "FAILED"
STATUS_SUCCEEDED = "SUCCEEDED"

VALID_STATUSES = (STATUS_STARTED, STATUS_FAILED, STATUS_SUCCEEDED)


class AttemptRecordError(ValueError):
    """The supplied retry reference is missing, malformed or not usable."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sanitise_failure(text: Optional[str], limit: int = 200) -> str:
    """Reduce a failure to a short, key-free description.

    Anything that looks like a credential is replaced outright, and the result is
    truncated, because this string is written to a file that gets committed
    alongside receipts.
    """
    import re

    if not text:
        return ""
    cleaned = re.sub(r"sk-[A-Za-z0-9\-_]{4,}", "sk-***", str(text))
    cleaned = re.sub(r"(?i)(bearer)\s+\S+", r"\1 ***", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned[:limit]


@dataclass
class GenerationAttemptRecord:
    """One generation attempt. Sanitised, durable, and cheap to inspect."""

    provider: str
    modality: str
    fingerprint: str
    attempt_number: int
    status: str = STATUS_STARTED
    attempt_id: str = ""
    schema_version: str = ATTEMPT_SCHEMA_VERSION
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    failure_class: Optional[str] = None
    failure_reason: Optional[str] = None
    asset_sha256: Optional[str] = None
    receipt_ref: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise AttemptRecordError(
                f"status must be one of {VALID_STATUSES}, got {self.status!r}"
            )
        if not self.attempt_id:
            self.attempt_id = self._make_id()

    def _make_id(self) -> str:
        seed = "|".join(
            [
                self.schema_version,
                self.provider,
                self.modality,
                self.fingerprint,
                str(self.attempt_number),
                self.created_at,
            ]
        )
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    # -- serialisation ----------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "attempt_id": self.attempt_id,
            "provider": self.provider,
            "modality": self.modality,
            "fingerprint": self.fingerprint,
            "attempt_number": self.attempt_number,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "failure_class": self.failure_class,
            "failure_reason": self.failure_reason,
            "asset_sha256": self.asset_sha256,
            "receipt_ref": self.receipt_ref,
            "contains_secrets": False,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "GenerationAttemptRecord":
        if not isinstance(payload, dict):
            raise AttemptRecordError("attempt record is not a JSON object")
        version = payload.get("schema_version")
        if version != ATTEMPT_SCHEMA_VERSION:
            raise AttemptRecordError(
                f"attempt record schema {version!r} is not "
                f"{ATTEMPT_SCHEMA_VERSION!r}"
            )
        for field_name in ("provider", "modality", "fingerprint"):
            if not payload.get(field_name):
                raise AttemptRecordError(
                    f"attempt record field {field_name!r} is missing"
                )
        try:
            attempt_number = int(payload.get("attempt_number"))
        except (TypeError, ValueError):
            raise AttemptRecordError("attempt_number is missing or not an integer")
        status = payload.get("status")
        if status not in VALID_STATUSES:
            raise AttemptRecordError(f"attempt record status {status!r} is invalid")
        return cls(
            provider=str(payload["provider"]),
            modality=str(payload["modality"]),
            fingerprint=str(payload["fingerprint"]),
            attempt_number=attempt_number,
            status=status,
            attempt_id=str(payload.get("attempt_id") or ""),
            schema_version=ATTEMPT_SCHEMA_VERSION,
            created_at=str(payload.get("created_at") or _now()),
            updated_at=str(payload.get("updated_at") or _now()),
            failure_class=payload.get("failure_class"),
            failure_reason=payload.get("failure_reason"),
            asset_sha256=payload.get("asset_sha256"),
            receipt_ref=payload.get("receipt_ref"),
        )

    # -- persistence ------------------------------------------------------

    def path_in(self, work_dir: Path) -> Path:
        return attempts_dir(work_dir) / f"{self.attempt_id}.json"

    def write(self, work_dir: Path) -> Path:
        target = self.path_in(work_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return target

    def mark_failed(self, failure_class: str, reason: Optional[str]) -> "GenerationAttemptRecord":
        self.status = STATUS_FAILED
        self.failure_class = failure_class
        self.failure_reason = sanitise_failure(reason)
        self.updated_at = _now()
        return self

    def mark_succeeded(self, asset_sha256: str, receipt_ref: Optional[str]) -> "GenerationAttemptRecord":
        self.status = STATUS_SUCCEEDED
        self.asset_sha256 = asset_sha256
        self.receipt_ref = receipt_ref
        self.updated_at = _now()
        return self


def attempts_dir(work_dir: Path) -> Path:
    return Path(work_dir) / "attempts"


def load_attempt_record(path: Path) -> GenerationAttemptRecord:
    """Load and structurally validate a retry reference.

    Raises:
        AttemptRecordError: the file is missing, unparsable, the wrong schema,
            or missing a required field.
    """
    path = Path(path)
    if not path.is_file():
        raise AttemptRecordError(f"retry record not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise AttemptRecordError(f"retry record is unreadable: {exc}") from exc
    return GenerationAttemptRecord.from_dict(payload)


def find_attempt_records(work_dir: Path, *, status: Optional[str] = None) -> List[GenerationAttemptRecord]:
    """All parseable attempt records in a work directory, newest last."""
    directory = attempts_dir(work_dir)
    if not directory.is_dir():
        return []
    found: List[GenerationAttemptRecord] = []
    for candidate in sorted(directory.glob("*.json")):
        try:
            record = load_attempt_record(candidate)
        except AttemptRecordError:
            continue
        if status is None or record.status == status:
            found.append(record)
    return found


def latest_failed_attempt(work_dir: Path, modality: str) -> Optional[GenerationAttemptRecord]:
    """Most recent FAILED record for a modality, or ``None``."""
    candidates = [
        record
        for record in find_attempt_records(work_dir, status=STATUS_FAILED)
        if record.modality == modality
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda r: (r.created_at, r.attempt_id))[-1]


def append_reuse_event(work_dir: Path, event: Dict[str, Any]) -> Path:
    """Append-only audit trail for cache reuse.

    The generation receipt is immutable, so reuse activity cannot be recorded by
    rewriting it. A JSONL event log keeps the history without touching provenance.
    """
    directory = Path(work_dir) / "reuse-events.jsonl"
    directory.parent.mkdir(parents=True, exist_ok=True)
    with directory.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return directory


def read_reuse_events(work_dir: Path) -> List[Dict[str, Any]]:
    path = Path(work_dir) / "reuse-events.jsonl"
    if not path.is_file():
        return []
    events: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events