"""How much of the finished cut is actual material, measured in seconds.

Why shot count was the wrong measurement
----------------------------------------
``qc_video`` counted shots whose ``source_type`` looked real and called the
fraction a ratio. A 95-second cut of 20 shots could be 19 one-second real
screenshots and one 76-second diagram and still pass. The number measured the
inventory, not what a viewer actually sees.

This module measures the visible timeline instead:

- every shot contributes an interval of its own measured duration;
- an interval counts as real only when its source is a capture of something
  real — a recording, a screenshot, a document, a log. Cards, diagrams,
  generated visuals and motion renders do not count, and neither does a shot
  whose source cannot be classified;
- overlapping intervals are unioned, so one second is counted once;
- the denominator is the **measured output file**, not the sum of the shots.
  Padding or trimming at composition time changes what is visible, and a
  denominator that ignores that would be a different video's ratio.

The gate is ``real_source_duration_ratio >= 0.70`` for the two accounts. A
missing interval, a missing source permission or a missing active-asset mapping
is ``BLOCKED`` — never silently excluded from the denominator. An unknown kind
is counted as non-real, because "unknown" is not evidence.

What this cannot do
-------------------
It verifies the record and the arithmetic. It cannot see whether the subject is
actually recognisable in a frame; that stays a human review. Neither this module
nor a PASS here grants production readiness or publication.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from contentops.media.claim_coverage import CAPTURE_SPELLINGS

SCHEMA = "contentops.real-source-duration/v1"

#: The floor both accounts must reach. A declared mix is checked before
#: production by ``claim_coverage.composition_policy_errors``; this is the
#: measurement of the cut that was actually made.
MIN_REAL_DURATION_RATIO = 0.70

PASS = "PASS"
FAIL = "FAIL"
BLOCKED = "BLOCKED"

#: Spoken as one list with claim_coverage so a synonym cannot pass one gate and
#: fail the other.
REAL_SOURCE_KINDS = frozenset(name.lower() for name in CAPTURE_SPELLINGS)

#: Kinds that are deliberately not evidence. Listing them is documentation: the
#: rule is "real iff in REAL_SOURCE_KINDS", so anything else — including a kind
#: nobody has seen before — is non-real by default.
NON_REAL_SOURCE_KINDS = frozenset({
    "diagram",
    "generated",
    "generated_image",
    "generated_video",
    "ai_generated",
    "stock",
    "title_card",
    "vector_animation",
    "card",
    "motion",
    "motion_clone",
})

#: Permissions that may back a visible real-source interval. A real shot whose
#: rights were never recorded cannot be counted as material a film may rely on.
USABLE_PERMISSIONS = frozenset({"OWNED", "CREATED_BY_OWNER", "LICENSED"})

EPSILON = 0.0005


@dataclass
class Interval:
    """One visible stretch of the finished cut."""

    shot_id: str
    start: float
    end: float
    kind: str
    real: bool
    source: str = ""
    reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.end - self.start, 3),
            "kind": self.kind,
            "real": self.real,
            "source": self.source,
            "reason": self.reason,
        }


def _normalise(kind: Any) -> str:
    return str(kind or "").strip().lower().replace("-", "_").replace(" ", "_")


def _union_seconds(intervals: Iterable[Tuple[float, float]]) -> float:
    """Total covered seconds, counting an overlap once."""
    ordered = sorted((max(0.0, start), max(0.0, end)) for start, end in intervals)
    total = 0.0
    cursor_start = None
    cursor_end = None
    for start, end in ordered:
        if end <= start:
            continue
        if cursor_start is None:
            cursor_start, cursor_end = start, end
            continue
        if start <= cursor_end + EPSILON:
            cursor_end = max(cursor_end, end)
        else:
            total += cursor_end - cursor_start
            cursor_start, cursor_end = start, end
    if cursor_start is not None:
        total += cursor_end - cursor_start
    return round(total, 3)


def _assets_by_path(assets: Any) -> Dict[str, Dict[str, Any]]:
    """Index ``sources/assets.json`` entries by repository path."""
    index: Dict[str, Dict[str, Any]] = {}
    entries = assets.get("assets") if isinstance(assets, dict) else assets
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        for key in ("repo_path", "origin", "path"):
            value = str(entry.get(key) or "").strip()
            if value:
                index.setdefault(value, entry)
    return index


def measure(
    storyboard: Dict[str, Any],
    *,
    output_duration_s: float,
    assets: Optional[Dict[str, Any]] = None,
    require_permission: bool = True,
) -> Dict[str, Any]:
    """Measure the real-source share of a cut described by a storyboard.

    ``output_duration_s`` is the measured duration of the rendered file. Without
    it the gate is ``BLOCKED``: a storyboard is a plan, and a plan cannot prove
    what the file contains.
    """
    if not isinstance(output_duration_s, (int, float)) or isinstance(output_duration_s, bool) \
            or output_duration_s <= EPSILON:
        return _blocked("OUTPUT_DURATION_MISSING",
                        "the rendered file's duration was not measured, so there is "
                        "no denominator")

    shots = storyboard.get("shots") if isinstance(storyboard, dict) else None
    if not isinstance(shots, list) or not shots:
        return _blocked("TIMELINE_MISSING", "the storyboard declares no shots")

    by_path = _assets_by_path(assets or {})
    intervals: List[Interval] = []
    missing_permission: List[str] = []
    missing_source: List[str] = []
    cursor = 0.0
    for index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            return _blocked("SHOT_INVALID", f"shot {index} is not an object")
        shot_id = str(shot.get("shot_id") or shot.get("placement") or f"shot-{index}")
        try:
            duration = float(shot.get("duration", shot.get("duration_s")))
        except (TypeError, ValueError):
            return _blocked("SHOT_DURATION_MISSING",
                            f"{shot_id} has no measured duration")
        if duration <= EPSILON:
            return _blocked("SHOT_DURATION_INVALID",
                            f"{shot_id} has a non-positive duration ({duration})")
        start = float(shot.get("start", cursor))
        end = start + duration
        cursor = end

        source = str(shot.get("source") or ship_source(shot))
        kind = _normalise(shot.get("source_type") or shot.get("kind"))
        if not kind:
            entry = by_path.get(source)
            if entry is not None:
                kind = _normalise(entry.get("type") or entry.get("kind"))
        if not source:
            missing_source.append(shot_id)
        real = kind in REAL_SOURCE_KINDS
        reason = "real capture" if real else (
            "declared non-real" if kind in NON_REAL_SOURCE_KINDS
            else "unclassified source is not evidence")
        if real and require_permission:
            entry = by_path.get(source)
            permission = str((entry or {}).get("permission") or "")
            if permission not in USABLE_PERMISSIONS:
                missing_permission.append(f"{shot_id}: {source or '(no source)'}")
        intervals.append(Interval(shot_id=shot_id, start=start, end=end, kind=kind,
                                  real=real, source=source, reason=reason))

    if missing_source:
        return _blocked("SOURCE_MISSING",
                        "shots with no source: " + ", ".join(missing_source[:8]))
    if missing_permission:
        return _blocked(
            "SOURCE_PERMISSION_MISSING",
            "real-source shots without a usable rights record: "
            + "; ".join(missing_permission[:8]))

    # Clip to the file: a shot that was trimmed away is not visible, and the
    # tail the composer added is visible but was never declared as material.
    for interval in intervals:
        interval.start = max(0.0, min(interval.start, output_duration_s))
        interval.end = max(interval.start, min(interval.end, output_duration_s))

    real_seconds = _union_seconds((iv.start, iv.end) for iv in intervals if iv.real)
    declared_seconds = _union_seconds((iv.start, iv.end) for iv in intervals)
    ratio = round(real_seconds / output_duration_s, 4)
    undeclared_tail = round(max(0.0, output_duration_s - declared_seconds), 3)
    ratio_ok = ratio + EPSILON >= MIN_REAL_DURATION_RATIO

    return {
        "schema": SCHEMA,
        "state": PASS if ratio_ok else FAIL,
        "ok": ratio_ok,
        "real_source_duration_ratio": ratio,
        "min": MIN_REAL_DURATION_RATIO,
        "real_seconds": real_seconds,
        "declared_seconds": declared_seconds,
        "output_duration_s": round(float(output_duration_s), 3),
        "undeclared_tail_s": undeclared_tail,
        "required_seconds": round(MIN_REAL_DURATION_RATIO * float(output_duration_s), 3),
        "intervals": [interval.as_dict() for interval in intervals],
        "note": "unknown kinds and undeclared time count as non-real; overlapping "
                "intervals are counted once; the denominator is the rendered file",
    }


def ship_source(shot: Dict[str, Any]) -> str:
    """The path a shot actually shows, whichever key the storyboard used."""
    for key in ("video", "image", "source"):
        value = shot.get(key)
        if value:
            return str(value)
    return ""


def _blocked(code: str, detail: str) -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "state": BLOCKED,
        "ok": False,
        "code": code,
        "detail": detail,
    }


def check(
    project: Path,
    *,
    output_duration_s: float,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read the project's storyboard and assets, then measure."""
    project = Path(project)
    storyboard_path = project / "script" / "storyboard.json"
    if not storyboard_path.is_file():
        return _blocked("STORYBOARD_MISSING",
                        f"{storyboard_path.as_posix()} is missing")
    try:
        storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _blocked("STORYBOARD_INVALID", f"{storyboard_path.as_posix()}: {exc}")

    assets: Dict[str, Any] = {}
    manifest_path = project / "sources" / "assets.json"
    if manifest_path.is_file():
        try:
            assets = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return _blocked("ASSETS_INVALID", f"{manifest_path.as_posix()}: {exc}")
    return measure(storyboard, output_duration_s=output_duration_s, assets=assets)
