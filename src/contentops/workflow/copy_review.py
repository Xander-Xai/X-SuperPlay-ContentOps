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
#: ``function`` and ``dna_role`` are here because the replication and composition
#: gates read them: without them, a shot could be relabelled from a recording to
#: an abstraction after approval and no review would be stale.
#:
#: ``video``, ``caption``, ``claim`` and ``source`` were added on 2026-11-01. They
#: were absent while the repository already supported video shots, which meant a
#: reviewed storyboard could have its clip, its caption, its claim binding or its
#: provenance swapped and still carry the old ``APPROVED``. The fingerprint covers
#: what the copy *claims and shows*, not only what it narrates.
COPY_FIELDS = ("unit", "narration", "caption", "claim", "image", "video",
               "source", "source_type", "duration", "designed_card",
               "placement", "function", "dna_role")

#: Declared asset digests live here. They are part of the fingerprint because a
#: path alone does not identify a file: replacing the bytes behind an unchanged
#: ``project://`` reference would otherwise leave a review looking current.
ASSET_MAP = Path("script") / "assets.json"

#: Files under ``script/`` that decide what the film says, in what order, and
#: what it claims. Notes, briefs and generated text (``narration.txt``,
#: ``*-output.txt``) are deliberately absent: they do not change the copy, and
#: hashing them would expire a review over an unrelated edit.
SOURCE_FILES = ("master.md", "lines.json", "script.json", "claims.json",
                "claim-map.json", "assets.json", "cut-plan.json")

#: Committed inputs outside ``script/``. ``motion/timeline.json`` carries shot
#: order and segment durations, so a hand edit to it changes the film without
#: touching a word. It is written by ``build_motion_film`` from measured
#: narration durations, so on a project that runs that driver the regenerated
#: content is a function of the narration already bound above — the hash does not
#: move. If it ever gains a timestamp, this entry is the thing to revisit.
SOURCE_PATHS = (Path("motion") / "timeline.json",)

#: Build products. Never hashed: they derive from the sources above, and hashing
#: them would expire a review on every rebuild.
GENERATED_PATHS = (Path("receipts") / "voice-lines.json",)


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
    for name in SOURCE_FILES:
        source = script / name
        if source.is_file():
            parts.append(b"script\0" + name.encode("utf-8") + b"\0" + source.read_bytes())
    for caption in sorted(script.glob("*.srt")):
        parts.append(b"srt\0" + caption.name.encode("utf-8") + b"\0" + caption.read_bytes())
    for relative in SOURCE_PATHS:
        source = project / relative
        if source.is_file():
            parts.append(b"source\0" + relative.as_posix().encode("utf-8") + b"\0"
                         + source.read_bytes())
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


def _declared_assets(project: Path) -> Dict[str, Any]:
    path = project / ASSET_MAP
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    assets = document.get("assets")
    return assets if isinstance(assets, dict) else {}


def _resolve(project: Path, reference: Any) -> Optional[Path]:
    if not isinstance(reference, str) or not reference.startswith("project://"):
        return None
    return (project / reference[len("project://"):]).resolve()


def asset_integrity(project: Path) -> List[Dict[str, str]]:
    """Declared asset digests against the bytes on disk.

    Only files that exist are compared. A clean checkout intentionally carries no
    media, and a missing file is a composition problem rather than a review
    problem, so the two are reported separately instead of being folded together.
    """
    drift: List[Dict[str, str]] = []
    for asset_id, record in sorted(_declared_assets(project).items()):
        if not isinstance(record, dict):
            continue
        declared = record.get("sha256")
        path = _resolve(project, record.get("path"))
        if not declared or path is None or not path.is_file():
            continue
        actual = _sha(path.read_bytes())
        if actual != declared:
            drift.append({"asset_id": asset_id, "path": str(record.get("path")),
                          "declared_sha256": declared, "actual_sha256": actual})
    return drift


def missing_assets(project: Path) -> List[Dict[str, str]]:
    """Declared assets whose file is absent. Composition must refuse these."""
    absent: List[Dict[str, str]] = []
    for asset_id, record in sorted(_declared_assets(project).items()):
        if not isinstance(record, dict):
            continue
        path = _resolve(project, record.get("path"))
        if path is None:
            continue
        if not path.is_file():
            absent.append({"asset_id": asset_id, "path": str(record.get("path"))})
    return absent


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
    drift = asset_integrity(project)
    if record is None:
        return {"schema": GATE_SCHEMA, "ok": False, "state": "NOT_REVIEWED",
                "copy_sha256": fingerprint, "asset_drift": drift,
                "remedy": _remedy(project),
                "detail": "no receipts/script-review.json"}
    if record.get("status") not in STATUSES:
        return {"schema": GATE_SCHEMA, "ok": False, "state": "NOT_REVIEWED",
                "copy_sha256": fingerprint, "asset_drift": drift,
                "remedy": _remedy(project),
                "detail": f"unrecognised status {record.get('status')!r}"}
    if record.get("copy_sha256") != fingerprint:
        return {"schema": GATE_SCHEMA, "ok": False, "state": "STALE",
                "copy_sha256": fingerprint, "reviewed_sha256": record.get("copy_sha256"),
                "asset_drift": drift, "remedy": _remedy(project),
                "detail": "the copy changed after it was reviewed"}
    if record["status"] != "APPROVED":
        return {"schema": GATE_SCHEMA, "ok": False, "state": "CHANGES_REQUESTED",
                "copy_sha256": fingerprint, "reviewer": record.get("reviewer"),
                "opinion": record.get("opinion"), "asset_drift": drift,
                "remedy": _remedy(project),
                "detail": "the reviewer asked for changes"}
    if drift:
        return {"schema": GATE_SCHEMA, "ok": False, "state": "ASSET_DRIFT",
                "copy_sha256": fingerprint, "reviewer": record.get("reviewer"),
                "asset_drift": drift, "remedy": _remedy(project),
                "detail": "declared asset digests no longer match the files on disk"}
    return {"schema": GATE_SCHEMA, "ok": True, "state": "APPROVED",
            "copy_sha256": fingerprint, "asset_drift": [],
            "reviewer": record.get("reviewer"),
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
