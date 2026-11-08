"""Translate M5's evidence chain into the storyboard the pinned composer reads.

M5 and the M4.5 integration sample each built a storyboard, and they did not
agree. M5 emits ``duration_s``, ``caption``, ``narration``, ``claim`` and a
``source_type`` derived from its own asset map; ``manifest_to_storyboard`` emits
``duration``, ``shot_id`` and ``source``, and only it emits ``video``. The
composer reads ``duration`` and ``video``, so M5's own builder could not express
a clip at all and its per-shot timing was ignored.

This module is the single mapping. It is deliberately not a second asset list:
every shot comes from a line that already has an asset and a measured duration,
and it refuses rather than substituting a still or a default.

Rules enforced here, all raising :class:`StoryboardContractError`:

- a shot needs a positive measured duration;
- a video shot needs both the ``video`` key and an existing file;
- a declared asset that does not exist stops the build;
- ``duration`` and ``duration_s`` always carry the same value, so a receipt
  reader and the composer cannot disagree about a shot's length.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

VIDEO_SUFFIXES = (".mp4", ".mov", ".webm", ".m4v", ".mkv")

#: Asset types that mean "moving picture". ``motion`` is the M4.5 name for a
#: rendered clip; ``video`` is the M5 name.
VIDEO_TYPES = ("video", "motion", "generated_video")


class StoryboardContractError(Exception):
    """A shot cannot be expressed without guessing. The build must stop."""


@dataclass(frozen=True)
class NarrationSegment:
    """A semantic script unit timed by the measured narration audio."""

    segment_id: str
    text: str
    start: float
    end: float
    claim: Any = None
    evidence_ref: Any = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VisualShot:
    """One visual placement; several placements may explain one segment."""

    shot_id: str
    segment_id: str
    asset_id: str
    visual_role: str
    evidence_ref: Any
    duration_weight: float = 1.0
    variation: str = ""
    caption: str = ""
    visual_focus: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


VISUAL_ROLES = {"proof", "demo", "explain", "context", "transition"}


def is_video(asset_path: str, source_type: str) -> bool:
    if (source_type or "").lower() in VIDEO_TYPES:
        return True
    return Path(asset_path).suffix.lower() in VIDEO_SUFFIXES


def _positive_duration(value: Any, shot_id: str) -> float:
    try:
        duration = float(value)
    except (TypeError, ValueError):
        raise StoryboardContractError(
            f"shot {shot_id!r} has no numeric duration ({value!r})")
    if duration <= 0:
        raise StoryboardContractError(
            f"shot {shot_id!r} has a non-positive duration ({duration})")
    return round(duration, 3)


def build_shots(*,
                lines: Sequence[Dict[str, Any]],
                narration_lines: Sequence[Dict[str, Any]],
                assets: Dict[str, Any],
                repo_root: Path,
                require_video_exists: bool = True,
                visual_shots: Sequence[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
    """Map semantic narration to one or more visual placements.

    ``visual_shots`` is an explicit shot plan. Its rows point back to a
    semantic script line through ``segment_id``. Historical M5 projects omit
    that plan; they are converted to one placement per line without changing
    their existing asset, narration, caption, or measured timing contract.
    """
    if len(lines) != len(narration_lines):
        raise StoryboardContractError(
            f"{len(lines)} script lines but {len(narration_lines)} measured "
            f"narration timings — the timeline is not aligned")

    planned_by_segment: Dict[str, List[Dict[str, Any]]] = {}
    for index, row in enumerate(visual_shots or ()):
        if not isinstance(row, dict):
            raise StoryboardContractError(f"visual_shots[{index}] must be an object")
        segment_id = str(row.get("segment_id") or "").strip()
        if not segment_id:
            raise StoryboardContractError(f"visual_shots[{index}] has no segment_id")
        planned_by_segment.setdefault(segment_id, []).append(row)

    for segment_id, rows in planned_by_segment.items():
        by_asset: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            by_asset.setdefault(str(row.get("asset_id") or ""), []).append(row)
        for asset_id, repeated in by_asset.items():
            if asset_id and len(repeated) > 1:
                reasons = [str(row.get("variation") or "").strip() for row in repeated]
                if any(not reason for reason in reasons) or len(set(reasons)) != len(reasons):
                    raise StoryboardContractError(
                        f"segment {segment_id!r} repeats asset {asset_id!r} without distinct variation reasons")

    line_ids = {str(line.get("id") or f"segment-{index + 1:03d}")
                for index, line in enumerate(lines)}
    unknown_segments = sorted(set(planned_by_segment) - line_ids)
    if unknown_segments:
        raise StoryboardContractError(
            "visual_shots reference unknown narration segment(s): "
            + ", ".join(unknown_segments))

    shots: List[Dict[str, Any]] = []
    used_shot_ids: set[str] = set()
    for index, (line, timing) in enumerate(zip(lines, narration_lines)):
        segment_id = str(line.get("id") or f"segment-{index + 1:03d}")
        segment_start = float(timing.get("start") or 0.0)
        if index + 1 < len(narration_lines) and narration_lines[index + 1].get("start") is not None:
            segment_end = float(narration_lines[index + 1].get("start") or 0.0)
        else:
            segment_end = segment_start + float(timing.get("duration") or 0.0)
        narration_segment = NarrationSegment(
            segment_id=segment_id,
            text=str(line.get("narration") or ""),
            start=segment_start,
            end=segment_end,
            claim=line.get("claim"),
            evidence_ref=line.get("evidence_ref") or line.get("claim"),
        )
        if narration_segment.end <= narration_segment.start:
            raise StoryboardContractError(
                f"narration segment {segment_id!r} has a non-positive measured span")
        segment_rows = planned_by_segment.get(segment_id)
        if visual_shots is not None and not segment_rows:
            raise StoryboardContractError(
                f"narration segment {segment_id!r} has no visual shot plan")
        if segment_rows:
            weights = []
            for row in segment_rows:
                try:
                    weight = float(row.get("duration_weight", 1.0))
                except (TypeError, ValueError):
                    weight = 0.0
                if weight <= 0:
                    raise StoryboardContractError(
                        f"visual shot {row.get('shot_id')!r} has a non-positive duration_weight")
                weights.append(weight)
        else:
            segment_rows = [{
                "shot_id": f"{line.get('asset_id') or 'shot'}__{index + 1:03d}",
                "segment_id": segment_id,
                "asset_id": line.get("asset_id"),
                "visual_role": str(line.get("visual_role") or "explain"),
                "evidence_ref": line.get("evidence_ref") or line.get("claim"),
                "duration_weight": 1.0,
                "caption": line.get("caption") or "",
            }]
            weights = [1.0]

        for sub_index, (row, weight) in enumerate(zip(segment_rows, weights)):
            asset_id = str(row.get("asset_id") or "").strip()
            if not asset_id:
                raise StoryboardContractError(
                    f"visual shot {row.get('shot_id')!r} has no asset_id")
            if asset_id not in assets:
                raise StoryboardContractError(
                    f"visual shot references unknown asset {asset_id!r}")
            role = str(row.get("visual_role") or "").strip().lower()
            if role not in VISUAL_ROLES:
                raise StoryboardContractError(
                    f"visual shot {row.get('shot_id')!r} has invalid visual_role {role!r}")
            evidence_ref = row.get("evidence_ref")
            if role == "proof" and not evidence_ref:
                raise StoryboardContractError(
                    f"proof shot {row.get('shot_id')!r} needs evidence_ref")
            asset = assets[asset_id]
            reference = asset.get("repo_path")
            if not reference:
                raise StoryboardContractError(f"asset {asset_id!r} has no repo_path")
            source_type = str(asset.get("type", "")).lower()
            duration = _positive_duration(timing.get("duration"), segment_id)
            video = is_video(reference, source_type)
            if video and require_video_exists and not (repo_root / reference).is_file():
                raise StoryboardContractError(
                    f"asset {asset_id!r} is declared as a clip but missing on disk: {reference}")
            shot_id = str(row.get("shot_id") or f"{asset_id}__{index + 1:03d}-{sub_index + 1:02d}")
            if shot_id in used_shot_ids:
                raise StoryboardContractError(f"duplicate shot_id {shot_id!r}")
            used_shot_ids.add(shot_id)
            visual_shot = VisualShot(
                shot_id=shot_id, segment_id=narration_segment.segment_id,
                asset_id=asset_id, visual_role=role, evidence_ref=evidence_ref,
                duration_weight=weight, variation=str(row.get("variation") or ""),
                caption=str(row.get("caption") or ""),
                visual_focus=str(row.get("visual_focus") or ""),
            )
            shot: Dict[str, Any] = {
                **visual_shot.as_dict(),
                "caption": row.get("caption") or (line.get("caption") if len(segment_rows) == 1 else ""),
                "narration": line.get("narration") if sub_index == 0 else "",
                "claim": line.get("claim"),
                "source": reference,
                "source_type": source_type,
                "duration_weight": weight,
                "duration": round(duration * weight / sum(weights), 3),
                "duration_s": round(duration * weight / sum(weights), 3),
            }
            if video:
                shot["video"] = reference
                shot["image"] = reference
                shot["motion"] = "static"
            else:
                shot["image"] = reference
                shot["motion"] = "static"
            shots.append(shot)
    return shots


def shot_is_video(shot: Dict[str, Any]) -> bool:
    return bool(shot.get("video"))


def timeline_duration(shots: Iterable[Dict[str, Any]]) -> float:
    return round(sum(float(shot.get("duration") or 0.0) for shot in shots), 3)
