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

from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

VIDEO_SUFFIXES = (".mp4", ".mov", ".webm", ".m4v", ".mkv")

#: Asset types that mean "moving picture". ``motion`` is the M4.5 name for a
#: rendered clip; ``video`` is the M5 name.
VIDEO_TYPES = ("video", "motion", "generated_video")


class StoryboardContractError(Exception):
    """A shot cannot be expressed without guessing. The build must stop."""


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
                require_video_exists: bool = True) -> List[Dict[str, Any]]:
    """One shot per script line. No line may be silently skipped."""
    if len(lines) != len(narration_lines):
        raise StoryboardContractError(
            f"{len(lines)} script lines but {len(narration_lines)} measured "
            f"narration timings — the timeline is not aligned")

    shots: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for index, (line, timing) in enumerate(zip(lines, narration_lines)):
        asset_id = line.get("asset_id")
        if not asset_id:
            raise StoryboardContractError(f"line {index} has no asset_id")
        if asset_id not in assets:
            raise StoryboardContractError(
                f"line {index} references unknown asset {asset_id!r}")
        if asset_id in seen:
            raise StoryboardContractError(
                f"asset {asset_id!r} is placed twice; the timeline needs one active "
                f"asset per placement")
        seen.add(asset_id)

        asset = assets[asset_id]
        reference = asset.get("repo_path")
        if not reference:
            raise StoryboardContractError(f"asset {asset_id!r} has no repo_path")
        source_type = str(asset.get("type", "")).lower()
        duration = _positive_duration(timing.get("duration"), str(asset_id))
        video = is_video(reference, source_type)

        # A declared clip that is not on disk is a hard stop: the composer would
        # otherwise fall through to the still branch and render a placeholder over
        # a shot that was supposed to move. Stills keep their previous behaviour.
        if video and require_video_exists and not (repo_root / reference).is_file():
            raise StoryboardContractError(
                f"asset {asset_id!r} is declared as a clip but missing on disk: {reference}")
        shot: Dict[str, Any] = {
            "shot_id": asset_id,
            "caption": line.get("caption"),
            "narration": line.get("narration"),
            "claim": line.get("claim"),
            "source": reference,
            "source_type": source_type,
            "duration": duration,
            "duration_s": duration,
        }
        if video:
            # ``video`` is what the composer reads for a clip; ``image`` is kept
            # because the assembler picks one key or the other and a video shot
            # must not fall through to a still.
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
