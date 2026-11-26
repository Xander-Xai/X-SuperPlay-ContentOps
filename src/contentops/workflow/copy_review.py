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
#: what it claims. The claim ledger is deliberately excluded: its quotes and
#: artifact pointers are independently checked by the M5 claims stage and do not
#: change the creator's copy. The line-level claim binding in ``script.json`` and
#: storyboard fields remains in this fingerprint. Generated narration text is
#: also excluded because the pipeline writes it from the approved copy.
SOURCE_FILES = ("master.md", "lines.json", "script.json",
                "claim-map.json", "assets.json", "cut-plan.json")

#: Committed inputs outside ``script/``. ``motion/timeline.json`` carries shot
#: order and segment durations, so a hand edit to it changes the film without
#: touching a word. It is written by ``build_motion_film`` from measured
#: narration durations, so on a project that runs that driver the regenerated
#: content is a function of the narration already bound above — the hash does not
#: move. If it ever gains a timestamp, this entry is the thing to revisit.
SOURCE_PATHS = (Path("motion") / "timeline.json",)

#: The GRAPHIC_TEXT line has no ``script/`` tree. The copy fingerprint binds
#: the selected draft bytes and its editorial identity, not mutable image-plan
#: details such as generated asset paths or layout metadata.
GRAPHIC_INPUT_FILE = Path("graphic-input.json")

#: The topic-level copy precedes both production contracts and must participate
#: in their review freshness calculation whenever the project carries it.
CANONICAL_COPY_FILE = Path("00_brief") / "canonical-copy.json"
COPY_DERIVATIVE_FILE = Path("00_brief") / "copy-derivative.json"

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


def _m5_script_projects_derivative(project: Path) -> bool:
    """Whether ``script.json`` is a faithful machine projection of reviewed copy.

    A generated M5 representation must not trigger a duplicate copy review, but
    a changed narration, caption, segment order or claim binding must not inherit
    the old approval. Invalid or incomplete projections stay fingerprinted.
    """
    script_path = project / "script" / "script.json"
    derivative_path = project / COPY_DERIVATIVE_FILE
    if not script_path.is_file() or not derivative_path.is_file():
        return False
    try:
        script = json.loads(script_path.read_text(encoding="utf-8"))
        derivative = json.loads(derivative_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if (script.get("schema") != "contentops.m5-script/v1"
            or derivative.get("format") != "VIDEO"):
        return False
    lines = script.get("lines")
    segments = derivative.get("segments")
    if not isinstance(lines, list) or not lines or not isinstance(segments, list) or not segments:
        return False
    index = 0
    for segment in segments:
        if not isinstance(segment, dict):
            return False
        segment_id = str(segment.get("source_segment_id") or "")
        text = segment.get("text")
        claim_refs = {str(value) for value in segment.get("claim_refs") or []}
        if not segment_id or not isinstance(text, str):
            return False
        pieces = []
        segment_claims = set()
        while index < len(lines):
            line = lines[index]
            if not isinstance(line, dict) or line.get("source_segment_id") != segment_id:
                break
            narration = line.get("narration")
            caption = line.get("caption")
            if (not isinstance(narration, str) or not narration
                    or caption != narration):
                return False
            primary = str(line.get("claim") or "")
            raw_claims = line.get("claims")
            if raw_claims is None:
                line_claims = {primary} if primary else set()
            elif (not isinstance(raw_claims, list)
                  or any(not isinstance(value, str) or not value for value in raw_claims)):
                return False
            else:
                line_claims = set(raw_claims)
                if len(line_claims) != len(raw_claims):
                    return False
                if primary and primary not in line_claims:
                    return False
            if not line_claims.issubset(claim_refs):
                return False
            segment_claims.update(line_claims)
            pieces.append(narration)
            index += 1
        if not pieces or "".join(pieces) != text or segment_claims != claim_refs:
            return False
    return index == len(lines)


def _graphic_copy_parts(project: Path, graphic_input_path: Optional[Path] = None) -> List[bytes]:
    project = Path(project).resolve()
    if (project / "script" / "script.json").is_file():
        parts = []
        for relative in (Path("draft.md"), GRAPHIC_INPUT_FILE):
            source = project / relative
            if source.is_file():
                parts.append(b"graphic\\0" + relative.as_posix().encode("utf-8")
                             + b"\\0" + source.read_bytes())
        return parts
    default_input = project / GRAPHIC_INPUT_FILE
    if graphic_input_path is None and not default_input.is_file():
        legacy_draft = project / "draft.md"
        return ([b"graphic-draft\\0draft.md\\0" + legacy_draft.read_bytes()]
                if legacy_draft.is_file() else [])
    raw_input = Path(graphic_input_path or default_input)
    if not raw_input.is_absolute():
        raw_input = project / raw_input
    try:
        raw_relative = raw_input.absolute().relative_to(project).as_posix()
    except ValueError:
        raise ValueError("GRAPHIC_INPUT_PATH_INVALID: input must be inside the project") from None
    current = project
    for segment in Path(raw_relative).parts:
        current = current / segment
        if current.is_symlink():
            raise ValueError("GRAPHIC_INPUT_PATH_INVALID: input must not use symlinks")
    input_path = raw_input.resolve()
    input_relative = raw_relative
    if not input_path.is_file():
        raise ValueError("GRAPHIC_INPUT_PATH_INVALID: input must be an existing project file")
    parts: List[bytes] = []
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"GRAPHIC_INPUT_INVALID: {exc}") from None
    if not isinstance(data, dict):
        raise ValueError("GRAPHIC_INPUT_INVALID: input must be a JSON object")
    reference = data.get("draft")
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError("GRAPHIC_DRAFT_REQUIRED: graphic input must select a draft")
    reference = reference.strip().replace("\\", "/")
    repo_scope = reference.startswith("repo://")
    if repo_scope:
        if project.parent.name != "projects":
            raise ValueError("GRAPHIC_DRAFT_PATH_INVALID: repo:// requires projects/<slug>")
        base = project.parent.parent.resolve()
        logical = reference[len("repo://"):]
    else:
        base = project
        logical = reference
    if not logical or logical.startswith("/") or ".." in logical.split("/"):
        raise ValueError("GRAPHIC_DRAFT_PATH_INVALID: expected a safe relative draft path")
    candidate = base / logical
    current = base
    for segment in Path(logical).parts:
        current = current / segment
        if current.is_symlink():
            raise ValueError("GRAPHIC_DRAFT_PATH_INVALID: draft must not use symlinks")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise ValueError("GRAPHIC_DRAFT_PATH_INVALID: draft escapes its allowed root") from None
    if not resolved.is_file():
        raise ValueError("GRAPHIC_DRAFT_MISSING: selected draft does not exist")
    logical_path = ("repo://" if repo_scope else "project://") + logical
    parts.append(b"graphic-identity\\0" + _canonical({
        "input": input_relative,
        "title": data.get("title"),
        "platform_id": data.get("platform_id"),
        "account": data.get("account"),
        "draft": logical_path,
    }))
    parts.append(b"graphic-draft\\0" + logical_path.encode("utf-8")
                 + b"\\0" + resolved.read_bytes())
    return parts


def copy_fingerprint(project: Path, graphic_input_path: Optional[Path] = None) -> str:
    """A digest of what the copy says, with verified M5 projections normalized."""
    script = project / "script"
    parts: List[bytes] = []
    m5_projection = _m5_script_projects_derivative(project)
    for name in SOURCE_FILES:
        if name == "script.json" and m5_projection:
            continue
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
    parts.extend(_graphic_copy_parts(project, graphic_input_path))
    for relative in (CANONICAL_COPY_FILE, COPY_DERIVATIVE_FILE,
                     Path("receipts") / "topic-package-ref.json",
                     Path("receipts") / "topic-package-handoff.json"):
        source = project / relative
        if source.is_file():
            parts.append(b"topic-copy\0" + relative.as_posix().encode("utf-8") + b"\0"
                         + source.read_bytes())
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


def _graphic_input_identity(project: Path, graphic_input_path: Optional[Path] = None) -> Optional[str]:
    project = Path(project).resolve()
    if graphic_input_path is None and not (project / GRAPHIC_INPUT_FILE).is_file():
        return None
    path = Path(graphic_input_path or (project / GRAPHIC_INPUT_FILE)).resolve()
    try:
        return path.relative_to(project).as_posix()
    except ValueError:
        raise ValueError("GRAPHIC_INPUT_PATH_INVALID: input must be inside the project") from None


def status(project: Path, *, projects_root: Optional[Path] = None,
           graphic_input_path: Optional[Path] = None) -> Dict[str, Any]:
    """Everything a caller needs to explain the gate, without raising."""
    fingerprint = copy_fingerprint(project, graphic_input_path)
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
    selected_input = _graphic_input_identity(project, graphic_input_path)
    if (selected_input is not None
            and record.get("graphic_input_path", "graphic-input.json") != selected_input):
        return {"schema": GATE_SCHEMA, "ok": False, "state": "STALE",
                "copy_sha256": fingerprint, "reviewed_sha256": record.get("copy_sha256"),
                "asset_drift": drift, "remedy": _remedy(project),
                "detail": "the selected graphic input changed after review"}
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
    from . import topic_package
    if topic_package.is_declared_consumer(project):
        lineage = topic_package.status_child(project, projects_root=projects_root)
        if lineage.get("applicable") and not lineage.get("ok"):
            return {"schema": GATE_SCHEMA, "ok": False, "state": "TOPIC_PACKAGE_STALE",
                    "copy_sha256": fingerprint, "reviewer": record.get("reviewer"),
                    "asset_drift": [], "remedy": _remedy(project),
                    "detail": str(lineage.get("detail") or lineage.get("state"))}
    return {"schema": GATE_SCHEMA, "ok": True, "state": "APPROVED",
            "copy_sha256": fingerprint, "asset_drift": [],
            "reviewer": record.get("reviewer"),
            "opinion": record.get("opinion"), "reviewed_at": record.get("reviewed_at")}


def require_approved(project: Path, *, projects_root: Optional[Path] = None,
                     graphic_input_path: Optional[Path] = None) -> Dict[str, Any]:
    """Return the gate when approved; raise :class:`CopyReviewRequired` otherwise."""
    gate = status(project, projects_root=projects_root,
                  graphic_input_path=graphic_input_path)
    if gate["ok"]:
        return gate
    raise CopyReviewRequired(
        f"copy review gate: {gate['state']} — {gate.get('detail', '')}".strip(),
        gate.get("remedy", ""))


def is_brief_driven(project: Path) -> bool:
    """Whether the project entered through the content router.

    A router project carries ``00_brief/brief.json``. The flag exists because
    the router chain has a copy that only exists after the brief bridge has
    written ``script/script.json`` and ``script/claims.json``: the review must
    cover those files, so the gate belongs after the conversion and before
    narration, not at the draft.
    """
    return (Path(project) / "00_brief" / "brief.json").is_file()


def require_if_brief_driven(project: Path) -> Optional[Dict[str, Any]]:
    """Enforce copy review for router projects; leave legacy projects alone.

    Historical M5 samples were produced before this gate existed and carry no
    router brief. Silently exempting them forever would be a hole, so the
    exemption is keyed to the absence of the brief, which a router project
    always has.
    """
    if not is_brief_driven(project):
        return None
    return require_approved(project)


def decide(project: Path, *, status_value: str, reviewer: str, opinion: str,
           reviewed_at: str, graphic_input_path: Optional[Path] = None) -> Dict[str, Any]:
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
        "copy_sha256": copy_fingerprint(project, graphic_input_path),
    }
    input_identity = _graphic_input_identity(project, graphic_input_path)
    if input_identity is not None:
        record["graphic_input_path"] = input_identity
    path = project / RECORD
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def _remedy(project: Path) -> str:
    return (f"python scripts/copy_review.py {project.as_posix()} "
            "--approve --reviewer <name> --opinion \"<what you decided>\" --confirm")
