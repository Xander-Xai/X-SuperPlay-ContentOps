"""A human review of the copy is a precondition, not a report.

The failure this prevents: a film is composed, narrated and published from a
script nobody read. Every producer in this repository could reach the script by
filename, so "the copy exists" was silently standing in for "a person approved
the copy".

So the gate is one small, boring contract:

- the *copy* is fingerprinted from the files that carry meaning (the master, the
  caption file, and each shot's unit/narration/visual/duration) — build metadata
  such as ``narration``, ``subtitle`` or ``runtime`` is excluded, because the
  pipeline writes those itself and they must not invalidate a review;
- a review record binds a decision to that fingerprint, a named reviewer and a
  written opinion;
- anything other than ``APPROVED`` on the current fingerprint blocks.

Two states are deliberately distinct: ``CHANGES_REQUESTED`` is a decision (the
copy must change), while a missing or stale review means nobody has decided yet.
Both stop the pipeline, but they demand different actions.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "contentops.copy-review/v1"
GATE_SCHEMA = "contentops.copy-gate/v1"
RECORD = Path("receipts") / "script-review.json"
STATUSES = ("APPROVED", "CHANGES_REQUESTED")

#: Storyboard fields that carry meaning. Everything else is build metadata the
#: pipeline rewrites, and including it would invalidate a review on every build.
COPY_FIELDS = ("unit", "narration", "image", "source_type", "duration",
               "designed_card", "placement")


class CopyReviewRequired(Exception):
    """Raised by :func:`require_approved` when the pipeline must not continue."""

    def __init__(self, reason: str, remedy: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.remedy = remedy


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def copy_fingerprint(project: Path) -> str:
    """A digest of what the copy *says*, stable across builds."""
    script = project / "script"
    parts: List[bytes] = []
    master = script / "master.md"
    parts.append(b"master\0" + (master.read_bytes() if master.is_file() else b""))
    for caption in sorted(script.glob("*.srt")):
        parts.append(b"srt\0" + caption.name.encode("utf-8") + b"\0" + caption.read_bytes())
    board = script / "storyboard.json"
    shots: List[Dict[str, Any]] = []
    if board.is_file():
        try:
            document = json.loads(board.read_text(encoding="utf-8"))
        except ValueError:
            document = {}
        for shot in document.get("shots") or []:
            shots.append({key: shot.get(key) for key in COPY_FIELDS})
        parts.append(b"storyboard\0" + _canonical({"shots": shots,
                                                   "size": document.get("size")}))
    return _sha(b"\n".join(parts))


def load(project: Path) -> Optional[Dict[str, Any]]:
    path = project / RECORD
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {"schema": SCHEMA, "status": "UNREADABLE"}


def status(project: Path) -> Dict[str, Any]:
    """Everything a caller needs to explain the gate, without raising."""
    fingerprint = copy_fingerprint(project)
    record = load(project)
    if record is None:
        return {"schema": GATE_SCHEMA, "ok": False, "state": "NOT_REVIEWED",
                "copy_sha256": fingerprint, "remedy": _remedy(project),
                "detail": "no receipts/script-review.json"}
    if record.get("status") not in STATUSES:
        return {"schema": GATE_SCHEMA, "ok": False, "state": "NOT_REVIEWED",
                "copy_sha256": fingerprint, "remedy": _remedy(project),
                "detail": f"unrecognised status {record.get('status')!r}"}
    if record.get("copy_sha256") != fingerprint:
        return {"schema": GATE_SCHEMA, "ok": False, "state": "STALE",
                "copy_sha256": fingerprint, "reviewed_sha256": record.get("copy_sha256"),
                "remedy": _remedy(project),
                "detail": "the copy changed after it was reviewed"}
    if record["status"] != "APPROVED":
        return {"schema": GATE_SCHEMA, "ok": False, "state": "CHANGES_REQUESTED",
                "copy_sha256": fingerprint, "reviewer": record.get("reviewer"),
                "opinion": record.get("opinion"), "remedy": _remedy(project),
                "detail": "the reviewer asked for changes"}
    return {"schema": GATE_SCHEMA, "ok": True, "state": "APPROVED",
            "copy_sha256": fingerprint, "reviewer": record.get("reviewer"),
            "opinion": record.get("opinion"), "reviewed_at": record.get("reviewed_at")}


def require_approved(project: Path) -> Dict[str, Any]:
    """Return the gate when approved; raise :class:`CopyReviewRequired` otherwise."""
    gate = status(project)
    if gate["ok"]:
        return gate
    raise CopyReviewRequired(
        f"copy review gate: {gate['state']} — {gate.get('detail', '')}".strip(),
        gate.get("remedy", ""))


def decide(project: Path, *, status_value: str, reviewer: str, opinion: str,
           reviewed_at: str) -> Dict[str, Any]:
    """Write a review record bound to the current copy fingerprint."""
    if status_value not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    if not reviewer.strip():
        raise ValueError("a review needs a named reviewer")
    if not opinion.strip():
        raise ValueError("a review needs a written opinion; 'looks fine' is not a record")
    record = {
        "schema": SCHEMA,
        "status": status_value,
        "reviewer": reviewer.strip(),
        "opinion": opinion.strip(),
        "reviewed_at": reviewed_at,
        "copy_sha256": copy_fingerprint(project),
    }
    path = project / RECORD
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def _remedy(project: Path) -> str:
    return (f"python scripts/copy_review.py {project.as_posix()} "
            f"--approve --reviewer <name> --opinion \"<what you decided>\"")
