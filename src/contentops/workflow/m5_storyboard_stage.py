"""M5 storyboard construction and narration alignment (Issue #140 slice)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def align_shots_to_narration(
    shots: List[Dict[str, Any]],
    narration_lines: List[Dict[str, Any]],
    *,
    blocked_error: type[Exception],
) -> List[Dict[str, Any]]:
    """Align visual placements to measured narration, retaining legacy behavior."""
    if not shots or not narration_lines:
        return shots
    segment_ids = [str(line.get("line_id") or line.get("segment_id") or "")
                   for line in narration_lines]
    has_segment_ids = any(shot.get("segment_id") for shot in shots)
    if has_segment_ids and any(not value for value in segment_ids):
        ordered_segments = list(dict.fromkeys(str(shot.get("segment_id") or "")
                                              for shot in shots))
        if (any(not value for value in segment_ids)
                and all(not value for value in segment_ids)
                and len(ordered_segments) == len(narration_lines)):
            segment_ids = ordered_segments
        else:
            raise blocked_error("measured narration lines need line_id to align multi-shot segments")
    if not has_segment_ids and len(shots) != len(narration_lines):
        raise blocked_error("storyboard shots do not match measured narration lines")

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    if has_segment_ids:
        for shot in shots:
            segment_id = str(shot.get("segment_id") or "")
            if segment_id not in segment_ids:
                raise blocked_error(f"storyboard references unknown narration segment {segment_id!r}")
            grouped.setdefault(segment_id, []).append(shot)
    for index, line in enumerate(narration_lines):
        segment_id = segment_ids[index]
        rows = grouped.get(segment_id, []) if has_segment_ids else [shots[index]]
        if not rows:
            raise blocked_error(f"narration segment {segment_id or index + 1!r} has no visual shot")
        start = float(line.get("start") or 0.0)
        if index + 1 < len(narration_lines):
            end = float(narration_lines[index + 1].get("start") or 0.0)
        else:
            end = start + float(line.get("duration") or 0.0)
        span = end - start
        if span <= 0:
            raise blocked_error(f"narration line {index + 1} has a non-positive timeline span")
        weights = []
        for shot in rows:
            try:
                weight = float(shot.get("duration_weight") or shot.get("duration") or 1.0)
            except (TypeError, ValueError):
                weight = 0.0
            if weight <= 0:
                raise blocked_error(f"shot {shot.get('shot_id')!r} has a non-positive timeline weight")
            weights.append(weight)
        cursor = start
        for row_index, (shot, weight) in enumerate(zip(rows, weights)):
            shot_end = end if row_index == len(rows) - 1 else cursor + span * weight / sum(weights)
            duration = shot_end - cursor
            shot["segment_id"] = segment_id or str(line.get("line_id") or index + 1)
            shot["start"] = round(cursor, 3)
            shot["end"] = round(shot_end, 3)
            shot["duration"] = round(duration, 3)
            shot["duration_s"] = round(duration, 3)
            cursor = shot_end
    return shots


def stage_storyboard(
    project: Path,
    config: Dict[str, Any],
    script: Dict[str, Any],
    narration: Dict[str, Any],
    subtitles: Dict[str, Any],
    assets: Dict[str, Any],
    media_audio: Optional[Dict[str, Any]] = None,
    *,
    repo_root: Path,
    blocked_error: type[Exception],
    payload_sha256: Callable[[Dict[str, Any]], str],
    relative_label: Callable[[Path], str],
    write_json: Callable[[Path, Dict[str, Any]], None],
    align: Callable[[List[Dict[str, Any]], List[Dict[str, Any]]], List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Build the M5 storyboard while preserving evidence, motion and audio gates."""
    from contentops.media.storyboard_adapter import StoryboardContractError, build_shots

    motion_assets = {}
    motion_receipt = project / "receipts" / "motion-stage.json"
    motion_configured = (config.get("motion") or {}).get("backend") in {
        "huashu-art-motion", "huashu-motion", "art-motion", "motion",
    }
    if motion_configured and not motion_receipt.is_file():
        raise blocked_error("motion backend was requested but no motion-stage receipt was written")
    if motion_receipt.is_file():
        try:
            motion_data = json.loads(motion_receipt.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise blocked_error(f"motion stage receipt is invalid: {exc}") from None
        if motion_data.get("state") == "OK":
            expected_script_sha = payload_sha256(script)
            if motion_data.get("script_sha256") != expected_script_sha:
                if motion_configured:
                    raise blocked_error("motion-stage receipt does not match the current M5 script")
            else:
                motion_assets = {
                    str(row.get("placement_id")): str(row.get("asset_id"))
                    for row in motion_data.get("shots", [])
                    if row.get("placement_id") and row.get("asset_id")
                }
    storyboard_lines = []
    for original in script["lines"]:
        line = dict(original)
        motion_id = str(motion_assets.get(str(line.get("id")))
                        or line.get("motion_asset_id") or "")
        if motion_id:
            motion_asset = assets.get(motion_id)
            if not motion_asset:
                raise blocked_error(f"{line.get('id')}: motion asset {motion_id!r} is not registered")
            if not (motion_asset.get("generated")
                    or str(motion_asset.get("type") or "").lower().startswith("generated_")):
                raise blocked_error(
                    f"{line.get('id')}: motion asset {motion_id!r} is not generated visual support")
            line["asset_id"] = motion_id
        storyboard_lines.append(line)
    storyboard_visuals = None
    if script.get("visual_shots") is not None:
        storyboard_visuals = []
        for original in script.get("visual_shots") or []:
            row = dict(original)
            placement_id = str(row.get("shot_id") or row.get("placement_id") or "")
            motion_id = str(motion_assets.get(placement_id)
                            or row.get("motion_asset_id") or row.get("asset_id") or "")
            if motion_id:
                motion_asset = assets.get(motion_id)
                if not motion_asset:
                    raise blocked_error(
                        f"{placement_id}: visual asset {motion_id!r} is not registered")
                if (motion_assets.get(placement_id)
                        and not (motion_asset.get("generated")
                                 or str(motion_asset.get("type") or "").lower().startswith("generated_"))):
                    raise blocked_error(
                        f"{placement_id}: motion asset {motion_id!r} is not generated visual support")
                row["asset_id"] = motion_id
            storyboard_visuals.append(row)
    try:
        shots = build_shots(lines=storyboard_lines,
                            narration_lines=narration["lines"],
                            assets=assets, repo_root=repo_root,
                            visual_shots=storyboard_visuals)
    except StoryboardContractError as exc:
        raise blocked_error(f"storyboard contract: {exc}")
    shots = align(shots, narration["lines"])
    target = (config.get("target") or {}).get("resolution", "1080x1920")
    generated_visual_ids = sorted({
        str(shot.get("asset_id")) for shot in shots
        if shot.get("asset_id") in assets
        and (bool(assets[shot["asset_id"]].get("generated"))
             or str(assets[shot["asset_id"]].get("type") or "").lower().startswith("generated_"))
    })
    storyboard = {
        "size": target,
        "image_motion": "static",
        "pad_mode": "trim",
        "shots": shots,
        "narration": f"{relative_label(project)}/assets/voice/narration.wav",
        "subtitle": f"{relative_label(project)}/assets/captions/default.srt",
        "engine": "easel",
        "voice_provider": (f"{narration.get('voice_provider', narration.get('engine', 'unknown'))}"
                           f"/{narration.get('voice') or 'unspecified'}"),
        "generated_visuals": {
            "count": len(generated_visual_ids),
            "asset_ids": generated_visual_ids,
            "policy": "visual_support_not_claim_evidence" if generated_visual_ids else "real_assets_only",
        },
    }

    # Supplied audio is a support track underneath narration, never a claim source.
    if media_audio:
        bgm = media_audio.get("bgm")
        if bgm:
            if not (repo_root / bgm["repo_path"]).is_file():
                raise blocked_error(f"bgm file missing: {bgm['repo_path']}")
            storyboard["bgm"] = bgm["repo_path"]
            storyboard["bgm_volume"] = bgm["volume"]
        total = float(narration.get("duration_s") or 0.0)
        placements = []
        for sfx in media_audio.get("sfx") or []:
            if not (repo_root / sfx["repo_path"]).is_file():
                raise blocked_error(f"sfx file missing: {sfx['repo_path']}")
            at = float(sfx["at"])
            if total and at >= total:
                raise blocked_error(
                    f"{sfx['id']}: sfx placement {at:.3f}s is at or beyond the "
                    f"{total:.3f}s narration timeline"
                )
            entry = {"file": sfx["repo_path"], "at": at, "volume": sfx["volume"]}
            if any(old["file"] == entry["file"] and old["at"] == entry["at"]
                   for old in placements):
                raise blocked_error(f"{sfx['id']}: duplicate sfx placement")
            placements.append(entry)
        if placements:
            storyboard["sfx"] = placements

    path = project / "script" / "storyboard.json"
    write_json(path, storyboard)
    return {"storyboard": storyboard, "shots": len(shots), "path": path}
