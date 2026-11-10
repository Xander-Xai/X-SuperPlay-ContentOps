"""Write a JianYing draft for a human to open, and stop there.

What this is
------------
A **handoff**, not a composer. Easel v0.2.1 already produces the finished film
(``final/<slug>.mp4``). This module exists for the one thing that pipeline cannot
do: give the Founder an editable timeline in 剪映 so a person can adjust a cut, a
caption or a shot order and then publish it themselves.

So the draft is built from what is already accepted -- the ``MediaManifest``
timeline and the subtitle cues -- and nothing else. It does not walk the asset
inventory, does not re-plan motion, does not re-time narration, and does not
render. The output of this module is a draft folder plus a receipt that says, in
plain fields, that nobody has approved or published it.

Why automatic export is forbidden here
--------------------------------------
The upstream README is explicit: batch export drives JianYing's visible controls
with ``uiautomation``, and that is documented as working **only on JianYing 6 and
below** ("剪映7+版本对控件进行了隐藏, 故本功能目前仅支持剪映6及以下版本"). It also
moves the cursor, forces the window to the foreground and is Windows-only.

A pipeline that clicked through the UI on a version the upstream project does not
support would produce either a hung process or a silently wrong file, and it would
do that with a human's mouse. So this module never imports ``JianyingController``,
never opens JianYing, and never exports. ``tests/test_jianying_handoff.py`` asserts
the absence structurally rather than trusting this paragraph.

Why the standard library cannot write this file
-----------------------------------------------
``draft_content.json`` is not "a JSON file with some tracks". Writing it by hand
means reimplementing, and keeping in sync with every JianYing release:

* a **material registry** -- every image/video/audio/text material gets a uuid, a
  local id and a path record, and every segment references those ids, so one
  wrong id is a draft that opens empty;
* a **time base** in microseconds, with ``target_timerange`` and
  ``source_timerange`` that must agree with the material duration and the speed,
  plus rounding rules that differ between adjacent clips;
* **canvas, track and segment defaults** -- version strings, ``canvas_config``,
  ``platform``, render indices, per-track attribute maps -- where a missing key is
  usually not an error but a silently ignored clip;
* **per-version drift**: the schema changed between 5.9, 6.x and 10.x, and the
  upstream project carries that mapping.

Any of that can be produced by ``json.dump`` if you already know the exact schema,
which is the same statement as "you have rewritten the library". The realistic
outcomes of hand-rolling it are (a) a draft JianYing refuses to open, or (b) a
draft it opens with the clips silently dropped -- and both are only discoverable by
launching JianYing, which is exactly the thing this pipeline cannot automate.
``pyJianYingDraft`` exists to own that schema; it is Apache-2.0, it is pinned, and
it is called as a library (no source vendored into this repository).

Licence and pinning
-------------------
``pyJianYingDraft`` 0.3.1, Apache-2.0 (Copyright 2024 Gary Guan),
https://github.com/GuanYixuan/pyJianYingDraft . The version is asserted at runtime:
a different installed version is refused, because the file format is the whole
contract. Upgrading is a deliberate change to ``PINNED_VERSION`` plus a fresh
fixture run, never an ambient environment change.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "HandoffError",
    "PINNED_PACKAGE",
    "PINNED_VERSION",
    "build_handoff",
    "parse_srt",
    "receipt_for",
    "write_receipt",
]

PINNED_PACKAGE = "pyJianYingDraft"
PINNED_VERSION = "0.3.1"
LICENSE = "Apache-2.0"
SOURCE_URL = "https://github.com/GuanYixuan/pyJianYingDraft"
RECEIPT_SCHEMA = "contentops.jianying-handoff/v1"
DRAFT_MANIFEST = Path("receipts") / "media-manifest.json"
DEFAULT_SUBTITLES = Path("assets") / "captions" / "default.srt"
DEFAULT_DRAFTS_DIR = Path("work") / "jianying" / "drafts"
DEFAULT_FPS = 30

_SRT_TIME = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi"}


class HandoffError(RuntimeError):
    """Refusal. Carries a machine-readable code; never a partial draft."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


# --------------------------------------------------------------------------- #
# inputs
# --------------------------------------------------------------------------- #

def parse_srt(text: str) -> List[Dict[str, Any]]:
    """Parse SRT into ``[{index, start, end, text}]`` with seconds as floats.

    Deliberately small: these files are produced by this repository's own caption
    step, and a parser that guesses around malformed input would hand the draft a
    cue whose timing nobody can defend. A cue without a readable time range is a
    refusal, not a skipped line.
    """
    cues: List[Dict[str, Any]] = []
    blocks = re.split(r"\r?\n\s*\r?\n", text.strip().lstrip("\ufeff"))
    for position, block in enumerate(blocks, start=1):
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        times = None
        for offset, line in enumerate(lines[:3]):
            match = _SRT_TIME.search(line)
            if match:
                times = (match, offset)
                break
        if times is None:
            raise HandoffError(
                "SUBTITLES_UNREADABLE",
                f"cue {position} has no start/end time: {lines[0][:60]!r}",
            )
        match, offset = times
        start = (int(match.group(1)) * 3600 + int(match.group(2)) * 60
                 + int(match.group(3)) + int(match.group(4).ljust(3, "0")) / 1000)
        end = (int(match.group(5)) * 3600 + int(match.group(6)) * 60
               + int(match.group(7)) + int(match.group(8).ljust(3, "0")) / 1000)
        body = " ".join(line.strip() for line in lines[offset + 1:]).strip()
        if not body:
            raise HandoffError("SUBTITLES_UNREADABLE",
                               f"cue {position} has a time range but no text")
        if end <= start:
            raise HandoffError("SUBTITLES_UNREADABLE",
                               f"cue {position} ends before it starts ({start}->{end})")
        cues.append({"index": position, "start": round(start, 3),
                     "end": round(end, 3), "text": body})
    if not cues:
        raise HandoffError("SUBTITLES_UNREADABLE", "the subtitle file has no cue")
    return cues


def _resolve_project_uri(value: str, project: Path) -> Path:
    """Map ``project://x`` to ``project/x``; refuse anything that escapes."""
    if value.startswith("project://"):
        relative = value[len("project://"):]
        candidate = (project / relative).resolve()
    else:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            raise HandoffError(
                "ASSET_PATH_UNRESOLVED",
                f"{value!r} is neither a project:// path nor absolute",
            )
        candidate = candidate.resolve()
    try:
        candidate.relative_to(project.resolve())
    except ValueError:
        raise HandoffError(
            "ASSET_PATH_OUTSIDE_PROJECT",
            f"{value!r} resolves outside {project}; a draft must not point at it",
        ) from None
    return candidate


def _subtitles_path(project: Path, override: Optional[Path]) -> Path:
    if override is not None:
        candidate = Path(override)
        return candidate if candidate.is_absolute() else (project / candidate)
    receipt = project / "receipts" / "subtitles.json"
    if receipt.is_file():
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        declared = payload.get("path")
        if isinstance(declared, str) and declared.strip():
            return project / declared
    return project / DEFAULT_SUBTITLES


def _read_manifest(project: Path) -> Dict[str, Any]:
    path = project / DRAFT_MANIFEST
    if not path.is_file():
        raise HandoffError(
            "MANIFEST_MISSING",
            f"{DRAFT_MANIFEST.as_posix()} not found under {project}; the draft is "
            "built from an accepted timeline, never from an inventory scan",
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("timeline"), list):
        raise HandoffError("MANIFEST_UNREADABLE",
                           f"{path} has no timeline list")
    return payload


def _placements(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Timeline order, each slot naming exactly one asset. No inventory walk."""
    assets = {item.get("asset_id"): item for item in manifest.get("assets") or []
              if isinstance(item, dict)}
    placements: List[Dict[str, Any]] = []
    for slot in manifest["timeline"]:
        if not isinstance(slot, dict):
            raise HandoffError("TIMELINE_UNREADABLE", "a timeline slot is not an object")
        asset_id = slot.get("active_asset_id")
        asset = assets.get(asset_id)
        if asset is None:
            raise HandoffError(
                "TIMELINE_ASSET_UNRESOLVED",
                f"slot {slot.get('placement_id')!r} names {asset_id!r}, which the "
                "manifest does not describe",
            )
        placements.append({
            "placement_id": slot.get("placement_id"),
            "asset_id": asset_id,
            "path": asset.get("path"),
            "modality": asset.get("modality"),
        })
    if not placements:
        raise HandoffError("TIMELINE_EMPTY", "the manifest timeline has no slot")
    return placements


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# the draft
# --------------------------------------------------------------------------- #

def _library():
    try:
        import pyJianYingDraft as draft
    except ImportError as exc:  # pragma: no cover - exercised by a fixture patch
        raise HandoffError(
            "LIBRARY_MISSING",
            f"{PINNED_PACKAGE}=={PINNED_VERSION} is not installed; install the "
            "pinned version (see the module docstring) instead of vendoring it",
        ) from exc
    try:
        installed = importlib.metadata.version(PINNED_PACKAGE)
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover
        installed = "unknown"
    if installed != PINNED_VERSION:
        raise HandoffError(
            "LIBRARY_VERSION_MISMATCH",
            f"installed {PINNED_PACKAGE} is {installed}, pinned is {PINNED_VERSION}; "
            "the draft format is the contract, so this is a deliberate upgrade",
        )
    return draft


def build_handoff(project: Path, *, drafts_dir: Optional[Path] = None,
                  draft_name: Optional[str] = None, fps: int = DEFAULT_FPS,
                  replace: bool = False,
                  subtitles: Optional[Path] = None) -> Dict[str, Any]:
    """Write one draft from the accepted timeline and return its receipt.

    Nothing is rendered, exported or opened. The caller gets a receipt whose
    ``production_ready`` and ``publish_authorized`` are always false.
    """
    from contentops.media.quality_gate import MediaManifest

    project = Path(project).resolve()
    if not project.is_dir():
        raise HandoffError("PROJECT_MISSING", f"{project} is not a directory")

    manifest_path = project / DRAFT_MANIFEST
    manifest = MediaManifest.load(manifest_path)          # validates the timeline
    placements = _placements(_read_manifest(project))
    # The library's own validation is the contract; if the manifest cannot be
    # composed as stated, fail here rather than in a draft nobody can open.
    manifest.timeline_assets()

    subtitle_file = _subtitles_path(project, subtitles)
    if not subtitle_file.is_file():
        raise HandoffError("SUBTITLES_MISSING", f"{subtitle_file} does not exist")
    cues = parse_srt(subtitle_file.read_text(encoding="utf-8"))
    if len(cues) != len(placements):
        raise HandoffError(
            "TIMELINE_CUE_MISMATCH",
            f"{len(placements)} timeline placement(s) but {len(cues)} subtitle cue(s); "
            "this handoff pairs one picture per cue and will not guess a mapping",
        )

    resolved: List[Path] = []
    for index, placement in enumerate(placements):
        path = _resolve_project_uri(str(placement["path"] or ""), project)
        if not path.is_file():
            raise HandoffError(
                "ASSET_MISSING",
                f"placement {placement['placement_id']!r} points at {path}, "
                "which does not exist",
            )
        suffix = path.suffix.lower()
        if suffix not in _IMAGE_SUFFIXES | _VIDEO_SUFFIXES:
            raise HandoffError(
                "ASSET_TYPE_UNSUPPORTED",
                f"placement {placement['placement_id']!r} is {suffix or 'extensionless'}; "
                "a draft gets a still or a clip",
            )
        resolved.append(path)

    draft = _library()
    name = draft_name or f"{project.name}-handoff"
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise HandoffError("DRAFT_NAME_INVALID",
                           f"{name!r} must be letters, digits, dot, dash or underscore")
    root = Path(drafts_dir) if drafts_dir is not None else project / DEFAULT_DRAFTS_DIR
    if not root.is_absolute():
        root = (project / root).resolve()
    try:
        root.relative_to(project)
    except ValueError:
        raise HandoffError(
            "DRAFTS_OUTSIDE_PROJECT",
            f"{root} is outside {project}; the draft stays with its project",
        ) from None
    if (root / name).exists() and not replace:
        raise HandoffError(
            "DRAFT_EXISTS",
            f"{root / name} already exists; pass replace=True to overwrite it",
        )
    root.mkdir(parents=True, exist_ok=True)

    folder = draft.DraftFolder(str(root))
    script = folder.create_draft(name, 1080, 1920, fps=fps, allow_replace=replace)

    script.append_track(draft.TrackSpec(draft.TrackType.video, "source"))
    script.append_track(draft.TrackSpec(draft.TrackType.text, "subtitles"))

    for index, (placement, path) in enumerate(zip(placements, resolved)):
        # Pictures tile the cue grid: a shot lasts until the next cue starts, and
        # the last one covers its own cue. Derived from the subtitle timing only,
        # so no shot length is invented.
        start = cues[index]["start"]
        end = cues[index + 1]["start"] if index + 1 < len(cues) else cues[index]["end"]
        if end <= start:
            raise HandoffError(
                "SUBTITLES_UNREADABLE",
                f"cue {index + 1} gives shot {placement['placement_id']!r} no duration",
            )
        segment = draft.VideoSegment(str(path), draft.trange_seconds(start, end=end))
        script.add_segment(segment, "source")

    for cue in cues:
        text = draft.TextSegment(
            cue["text"], draft.trange_seconds(cue["start"], end=cue["end"]))
        script.add_segment(text, "subtitles")

    script.save()

    draft_root = root / name
    files = {}
    for candidate in sorted(draft_root.rglob("*.json")):
        files[candidate.relative_to(draft_root).as_posix()] = _sha256(candidate)
    if not files:
        raise HandoffError("DRAFT_NOT_WRITTEN",
                           f"{draft_root} holds no JSON after save(); nothing to review")

    return receipt_for(project, draft_root, name, placements, cues, files,
                       manifest_path=manifest_path, subtitle_file=subtitle_file,
                       fps=fps, drafts_dir=root)


def receipt_for(project: Path, draft_root: Path, name: str,
                placements: Sequence[Dict[str, Any]], cues: Sequence[Dict[str, Any]],
                files: Dict[str, str], *, manifest_path: Path, subtitle_file: Path,
                fps: int, drafts_dir: Path) -> Dict[str, Any]:
    """The audit trail: what was written, from what, by which version."""
    def project_uri(path: Path) -> str:
        try:
            return "project://" + path.relative_to(project).as_posix()
        except ValueError:  # pragma: no cover - guarded by the caller
            return str(path)

    return {
        "schema": RECEIPT_SCHEMA,
        "state": "DRAFT_WRITTEN",
        "library": {
            "package": PINNED_PACKAGE,
            "version": PINNED_VERSION,
            "license": LICENSE,
            "source": SOURCE_URL,
            "vendored": False,
        },
        "draft": {
            "name": name,
            "path": project_uri(draft_root),
            "dir": project_uri(drafts_dir),
            "width": 1080,
            "height": 1920,
            "fps": fps,
            "files_sha256": files,
        },
        "inputs": {
            "media_manifest": project_uri(manifest_path),
            "subtitles": project_uri(subtitle_file),
            "placements": [
                {"placement_id": item["placement_id"], "asset_id": item["asset_id"],
                 "path": item["path"]} for item in placements
            ],
            "cues": len(cues),
            "duration_s": round(cues[-1]["end"], 3),
        },
        "export_performed": False,
        "manual_export_required": True,
        "timeline_editable_by_human": True,
        "production_ready": False,
        "publish_authorized": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
        "notes": [
            "Upstream documents batch export as JianYing 6 and below only; this run "
            "never exports, clicks the UI or opens JianYing.",
            "The Founder opens the draft, edits if needed, exports and publishes.",
            "No template is loaded, so the draft format is created new rather than "
            "read from an existing (possibly non-plaintext) draft_content.json.",
        ],
    }


def write_receipt(project: Path, receipt: Dict[str, Any]) -> Path:
    path = Path(project) / "receipts" / "jianying-handoff.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path
