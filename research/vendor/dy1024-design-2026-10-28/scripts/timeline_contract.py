"""Compile an applied OpenChatCut snapshot into the only Remotion timeline contract."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path

from media_jobs import bounded, file_hash
from media_providers import read, write

try:
    from canonical_workflow import CONTRACT_ID, LEGACY_CONTRACT_ID, SUPPORTED_CONTRACT_IDS
except ImportError:  # imported as scripts.timeline_contract
    from scripts.canonical_workflow import CONTRACT_ID, LEGACY_CONTRACT_ID, SUPPORTED_CONTRACT_IDS

ROOT = Path(__file__).resolve().parents[1]
UNSUPPORTED = ("effects", "zoom", "filters", "keyframes")
CANONICAL_CONTRACT = CONTRACT_ID


def _srt_frames(path: Path, fps: int) -> list[dict]:
    pattern = re.compile(
        r"(?:^|\n)\s*\d+\s*\n"
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*\n(.*?)(?=\n\s*\n|\Z)",
        re.DOTALL,
    )

    def frame(groups: tuple[str, ...]) -> int:
        hours, minutes, seconds, millis = (int(value) for value in groups)
        return round((hours * 3600 + minutes * 60 + seconds + millis / 1000) * fps)

    entries = []
    raw = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    for match in pattern.finditer(raw):
        start = frame(match.groups()[0:4])
        end = frame(match.groups()[4:8])
        text = "\n".join(line.strip() for line in match.group(9).splitlines() if line.strip())
        if text and end > start:
            entries.append({"from": start, "duration": end - start, "text": text})
    if not entries:
        raise ValueError("approved captions contain no valid SRT cues")
    return entries


def _canonical_paths(manifest: dict) -> dict[str, str]:
    paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
    defaults = {
        "audio": "03_audio/audio-handoff.json",
        "visual_plan": "04_visual/visual-plan.json",
        "asset_ledger": "05_assets/asset-ledger.json",
        "master_timeline": "06_edit/master-timeline.json",
    }
    return {key: str(paths.get(f"canonical_{key}") or defaults[key]) for key in defaults}


def _h3_timeline_source_errors(project: Path, manifest: dict, source: Path) -> list[str]:
    """Reject stale/silent H3 visuals before they enter the canonical timeline."""

    if source.name.casefold() in {"h3-staged-silent.mp4", "h3-staged-fixed.mp4"}:
        return ["digital-human timeline cannot consume the rejected H3 concat/remux source"]
    paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
    h3_value = str(paths.get("canonical_h3_manifest") or "05_avatar/h3-manifest.json")
    h3_path = bounded(project, h3_value)
    if not h3_path.is_file():
        return ["digital-human timeline requires a canonical H3 manifest"]
    try:
        h3 = read(h3_path)
    except Exception:
        return ["digital-human timeline H3 manifest is unreadable"]
    errors: list[str] = []
    if h3.get("generation_mode") != "continuous-audio-conditioned" or h3.get("generation_units") != 1:
        errors.append("digital-human timeline requires one continuous-audio-conditioned H3 generation")
    conditioning = h3.get("audio_conditioning")
    if not isinstance(conditioning, dict) or conditioning.get("frame_grid") != "17k+5" or int(conditioning.get("fps") or 0) != 24:
        errors.append("digital-human timeline H3 manifest must retain the 24fps 17k+5 conditioning card")
    native = h3.get("native_audio_conditioning")
    if not isinstance(native, dict) or native.get("coverage_sufficient") is not True:
        errors.append("digital-human timeline H3 manifest must prove native AV coverage")
    accepted_hashes = {
        str(h3.get("sha256") or "").lower(),
        str(h3.get("output_sha256") or "").lower(),
    }
    for item in h3.get("segments", []) if isinstance(h3.get("segments"), list) else []:
        if isinstance(item, dict):
            accepted_hashes.add(str(item.get("video_sha256") or "").lower())
    try:
        source_sha = file_hash(source)
    except OSError:
        source_sha = ""
    if source_sha not in accepted_hashes or len(source_sha) != 64:
        errors.append("digital-human timeline source SHA-256 is not registered by the canonical H3 manifest")
    return errors


def _canonical_compile_timeline(project: Path, snapshot_path: Path) -> dict:
    """Compile the applied editor snapshot into the canonical Edit & Render contract."""

    manifest = read(project / "content.json")
    contract_id = str(manifest.get("workflow_contract") or LEGACY_CONTRACT_ID)
    if contract_id not in SUPPORTED_CONTRACT_IDS:
        raise ValueError(f"canonical timeline compilation requires a supported workflow contract: {sorted(SUPPORTED_CONTRACT_IDS)}")
    paths = _canonical_paths(manifest)
    audio = read(project / paths["audio"])
    plan = read(project / paths["visual_plan"])
    ledger = read(project / paths["asset_ledger"])
    content_id = str(manifest.get("content_id") or "").strip()
    if snapshot_path.resolve().is_relative_to(project.resolve()) is False:
        raise ValueError("OpenChatCut snapshot must stay inside the content package")
    snapshot = read(snapshot_path)
    if snapshot.get("content_id") != content_id:
        raise ValueError("timeline snapshot belongs to another episode")
    timeline = snapshot.get("result", {}).get("timeline", {})
    if (timeline.get("width"), timeline.get("height"), timeline.get("fps")) != (1080, 1920, 30):
        raise ValueError("applied timeline must be 1080x1920 at 30 fps")
    if timeline.get("fit", "contain") not in {"contain", "cover"}:
        raise ValueError("unsupported OpenChatCut fit mode")
    if timeline.get("transitions"):
        raise ValueError("OpenChatCut transitions are not part of the canonical timeline contract")
    records = ledger.get("assets") if isinstance(ledger.get("assets"), list) else []
    by_id = {str(item.get("asset_id")): item for item in records if isinstance(item, dict) and item.get("asset_id")}
    by_name: dict[str, dict] = {}
    for asset in records:
        if not isinstance(asset, dict):
            continue
        name = Path(str(asset.get("source") or "")).name
        if name:
            if name in by_name:
                raise ValueError(f"ambiguous canonical asset filename: {name}")
            by_name[name] = asset
    tracks = timeline.get("tracks", []) if isinstance(timeline.get("tracks"), list) else []
    track_order = {str(track.get("id")): index for index, track in enumerate(tracks) if isinstance(track, dict)}
    hidden_tracks = {str(track.get("id")) for track in tracks if isinstance(track, dict) and track.get("hidden") is True}
    clips: list[dict] = []
    digital_human_segments: list[dict] = []
    for item in timeline.get("items", []) if isinstance(timeline.get("items"), list) else []:
        if not isinstance(item, dict) or item.get("kind") not in {"video", "image"}:
            raise ValueError("canonical OpenChatCut timeline accepts only video and image visual clips")
        if any(item.get(field) not in (None, {}, [], False) for field in UNSUPPORTED):
            raise ValueError(f"unsupported OpenChatCut edit on {item.get('id')}")
        asset = by_id.get(str(item.get("asset_id") or "")) or by_name.get(Path(str(item.get("name") or "")).name)
        if not asset:
            raise ValueError(f"timeline item is not bound to the approved asset ledger: {item.get('name')}")
        source = bounded(project, asset.get("source", ""))
        declared_sha = str(asset.get("sha256") or asset.get("approved_sha256") or "").strip().lower()
        if not source.is_file() or not declared_sha or file_hash(source) != declared_sha:
            raise ValueError("timeline source changed after asset clearance")
        if asset.get("asset_type") == "digital_human":
            h3_errors = _h3_timeline_source_errors(project, manifest, source)
            if h3_errors:
                raise ValueError("; ".join(h3_errors))
        track_id = str(item.get("trackId") or "")
        if track_id and track_id not in track_order:
            raise ValueError(f"timeline item uses an unknown track: {track_id}")
        if track_id in hidden_tracks:
            raise ValueError("hidden OpenChatCut tracks cannot enter the canonical timeline")
        if item.get("kind") == "video" and item.get("volume") not in (None, 0):
            raise ValueError("visual clips must be muted; final narration has one owner")
        if item.get("kind") == "image" and (int(item.get("srcInFrame") or 0) or float(item.get("playbackRate") or 1) != 1):
            raise ValueError("image clips cannot use source trim or playback rate")
        transform = item.get("transform") or {}
        if set(transform) - {"scale", "x", "y", "rotation", "crop"}:
            raise ValueError("unsupported transform")
        crop = transform.get("crop") or {}
        if set(crop) - {"left", "top", "right", "bottom"} or any(not 0 <= float(v) < 1 for v in crop.values()):
            raise ValueError("invalid crop")
        clip = {
            "id": str(item.get("id") or asset.get("asset_id")),
            "asset_id": str(asset.get("asset_id")),
            "kind": item["kind"],
            "file": source.relative_to(project).as_posix(),
            "sha256": declared_sha,
            "start_frame": int(item.get("startFrame") or 0),
            "duration_frames": int(item.get("durationInFrames") or 0),
            "trim_before": int(item.get("srcInFrame") or 0),
            "playback_rate": float(item.get("playbackRate") or 1),
            "muted": True,
            "track_id": track_id or None,
            "layer_index": track_order.get(track_id, 0),
            "transform": transform,
        }
        if clip["duration_frames"] <= 0:
            raise ValueError("visual clips must have positive durationInFrames")
        clips.append(clip)
        if asset.get("asset_type") == "digital_human":
            digital_human_segments.append({
                "asset_id": str(asset.get("asset_id")),
                "start_frame": clip["start_frame"],
                "duration_frames": clip["duration_frames"],
            })
    if not clips:
        raise ValueError("OpenChatCut timeline contains no approved visual clips")
    narration = bounded(project, audio.get("narration_wav", ""))
    captions = bounded(project, audio.get("srt", ""))
    if audio.get("status") not in {"ready_for_review", "approved"} or not narration.is_file() or file_hash(narration) != audio.get("audio_sha256"):
        raise ValueError("approved canonical narration handoff is stale")
    if not captions.is_file():
        raise ValueError("canonical audio handoff must provide an SRT caption file")
    clips.sort(key=lambda item: (item["start_frame"], item["id"]))
    duration_frames = max(item["start_frame"] + item["duration_frames"] for item in clips)
    audio_duration = float(audio.get("duration_seconds") or 0)
    if audio_duration > 0 and abs(duration_frames / 30 - audio_duration) > 0.25:
        raise ValueError("applied timeline duration no longer matches the locked narration")
    caption_cues = _srt_frames(captions, 30)
    target = project / "06_edit" / "remotion-native"
    receipt_path = project / "06_edit" / "render-receipt.json"
    contract = {
        "schema_version": 1,
        "contract": contract_id,
        "content_id": content_id,
        "status": "ready_for_review",
        "audio_source": paths["audio"],
        "audio_sha256": str(audio.get("audio_sha256") or ""),
        "openchatcut_owner": "timeline-editor",
        "hyperframes_owner": "transparent-overlay",
        "remotion_owner": "final-compositor",
        "openchatcut_project": snapshot_path.relative_to(project).as_posix(),
        "remotion_project": target.relative_to(project).as_posix(),
        "render_receipt": receipt_path.relative_to(project).as_posix(),
        "candidate_mp4": "",
        "candidate_sha256": "",
        "digital_human_segments": digital_human_segments,
        "fit": timeline.get("fit", "contain"),
        "tracks": [
            {"role": "narration", "source": paths["audio"], "sha256": str(audio.get("audio_sha256") or ""), "muted": False, "cues": caption_cues},
            *[
                {"role": str(by_id.get(clip["asset_id"], {}).get("asset_type") or "visual"), "asset_id": clip["asset_id"], "clip_id": clip["id"], "kind": clip["kind"], "source": clip["file"], "sha256": clip["sha256"], "muted": True, "start_frame": clip["start_frame"], "duration_frames": clip["duration_frames"], "trim_before": clip["trim_before"], "playback_rate": clip["playback_rate"], "track_id": clip["track_id"], "layer_index": clip["layer_index"], "transform": clip["transform"]}
                for clip in clips
            ],
        ],
    }
    write(project / paths["master_timeline"], contract)
    author_remotion(project, contract, canonical=True, captions=caption_cues, narration=narration)
    write(receipt_path, {"schema_version": 1, "source": paths["master_timeline"], "master_timeline_sha256": file_hash(project / paths["master_timeline"]), "status": "ready_for_review"})
    return contract


def compile_timeline(project: Path, snapshot_path: Path) -> dict:
    try:
        manifest = read(project / "content.json")
    except Exception:
        manifest = {}
    if manifest.get("workflow_contract") in SUPPORTED_CONTRACT_IDS:
        return _canonical_compile_timeline(project, snapshot_path)
    manifest = read(project / "content.json")
    snapshot = read(snapshot_path)
    consumption = read(project / manifest.get("paths", {}).get("openchatcut_consumption_plan", "04_video/openchatcut-consumption-plan.json"))
    audio = read(project / manifest.get("paths", {}).get("audio_handoff", "04_video/audio-handoff.json"))
    if snapshot.get("content_id") != manifest.get("content_id") or consumption.get("content_id") != manifest.get("content_id"):
        raise ValueError("timeline sources belong to another episode")
    expected_project = consumption.get("openchatcut", {}).get("project_id")
    if expected_project and snapshot.get("editor_project_id") != expected_project:
        raise ValueError("OpenChatCut project mismatch")
    timeline = snapshot.get("result", {}).get("timeline", {})
    if (timeline.get("width"), timeline.get("height"), timeline.get("fps")) != (1080, 1920, 30):
        raise ValueError("applied timeline must be 1080x1920 at 30 fps")
    if timeline.get("fit", "contain") not in {"contain", "cover"}:
        raise ValueError("unsupported OpenChatCut fit mode")
    if timeline.get("transitions"):
        raise ValueError("OpenChatCut transitions are not round-trippable yet; do not silently ignore them")
    tracks = timeline.get("tracks", [])
    track_order = {str(track.get("id")): index for index, track in enumerate(tracks)}
    hidden_tracks = {str(track.get("id")) for track in tracks if track.get("hidden") is True}
    beats = consumption.get("beats", [])
    by_name = {}
    for beat in beats:
        visual = beat.get("visual", {})
        names = {Path(str(visual.get(k, ""))).name for k in ("expected_filename", "local_path") if visual.get(k)}
        for name in names:
            if name in by_name:
                raise ValueError(f"ambiguous OpenChatCut asset filename: {name}")
            by_name[name] = beat
    clips = []
    for item in timeline.get("items", []):
        if item.get("kind") not in {"video", "image", "audio"}:
            raise ValueError(f"unsupported applied timeline item: {item.get('kind')}")
        if any(item.get(field) not in (None, {}, [], False) for field in UNSUPPORTED):
            raise ValueError(f"unsupported OpenChatCut edit on {item.get('id')}; do not silently ignore it")
        beat = by_name.get(Path(str(item.get("name", ""))).name)
        if item.get("kind") != "audio" and not beat:
            raise ValueError(f"timeline asset is not bound to the approved consumption plan: {item.get('name')}")
        if item.get("kind") == "audio":
            raise ValueError("OpenChatCut must not own narration; Remotion binds the approved audio handoff")
        track_id = str(item.get("trackId") or "")
        if track_id and track_id not in track_order:
            raise ValueError(f"timeline item uses an unknown track: {track_id}")
        if track_id in hidden_tracks:
            raise ValueError("hidden OpenChatCut tracks are not round-trippable; remove the item or show the track")
        if int(item.get("fadeInFrames") or 0) or int(item.get("fadeOutFrames") or 0):
            raise ValueError("OpenChatCut fades are not round-trippable yet; do not silently ignore them")
        visual = beat["visual"]
        source = bounded(project, visual["local_path"])
        if not source.is_file() or file_hash(source) != visual["sha256"]:
            raise ValueError("timeline source changed after asset clearance")
        volume = item.get("volume")
        if item["kind"] == "video" and volume not in (None, 0):
            raise ValueError("visual clips must be muted; final narration has one owner")
        if item["kind"] == "image" and (int(item.get("srcInFrame") or 0) or float(item.get("playbackRate") or 1) != 1):
            raise ValueError("image clips cannot use source trim or playback rate")
        transform = item.get("transform") or {}
        if set(transform) - {"scale", "x", "y", "rotation", "crop"}:
            raise ValueError("unsupported transform")
        crop = transform.get("crop") or {}
        if set(crop) - {"left", "top", "right", "bottom"} or any(not 0 <= float(v) < 1 for v in crop.values()):
            raise ValueError("invalid crop")
        clips.append(dict(id=item["id"], asset_id=beat["asset_id"], scene_id=beat["scene_id"],
                          kind=item["kind"], file=source.relative_to(project).as_posix(),
                          sha256=visual["sha256"], start_frame=int(item["startFrame"]),
                          duration_frames=int(item["durationInFrames"]), trim_before=int(item.get("srcInFrame") or 0),
                          playback_rate=float(item.get("playbackRate") or 1), muted=True,
                          track_id=track_id or None, track=str(item.get("track") or ""),
                          layer_index=track_order.get(track_id, 0), transform=transform))
    clips.sort(key=lambda item: (item["start_frame"], item["id"]))
    if not clips:
        raise ValueError("OpenChatCut timeline contains no approved visual clips")
    narration = bounded(project, audio["narration"])
    captions = bounded(project, audio["captions"])
    if audio.get("status") != "ready" or file_hash(narration) != audio.get("audio_sha256") or not captions.is_file():
        raise ValueError("approved narration/captions handoff is stale")
    duration_frames = max(c["start_frame"] + c["duration_frames"] for c in clips)
    audio_duration = float(audio.get("duration_seconds") or 0)
    if audio_duration > 0 and abs(duration_frames / 30 - audio_duration) > 0.25:
        raise ValueError("applied timeline duration no longer matches the locked narration")
    caption_cues = _srt_frames(captions, 30)
    contract = dict(schema_version=1, content_id=manifest["content_id"], status="ready",
                    source="openchatcut-applied-timeline", source_snapshot=snapshot_path.relative_to(project).as_posix(),
                    source_snapshot_sha256=file_hash(snapshot_path), editor_project_id=snapshot["editor_project_id"],
                    width=1080, height=1920, fps=30, fit=timeline.get("fit", "contain"), clips=clips,
                    narration=dict(file=narration.relative_to(project).as_posix(), sha256=file_hash(narration)),
                    captions=dict(file=captions.relative_to(project).as_posix(), sha256=file_hash(captions), cues=caption_cues),
                    duration_frames=duration_frames,
                    supported_edits=["order", "placement", "trim", "duration", "playback_rate", "crop", "position", "scale", "rotation", "gain=muted"])
    write(project / "04_video/master-timeline.json", contract)
    author_remotion(project, contract)
    return contract


def number(value):
    value = float(value)
    return int(value) if value.is_integer() else value


def author_remotion(project: Path, contract: dict, *, canonical: bool = False, captions: list[dict] | None = None, narration: Path | None = None):
    target = project / ("06_edit/remotion-native" if canonical else "06_motion/remotion-native")
    public = target / "public/media"
    public.mkdir(parents=True, exist_ok=True)
    nodes = []
    if canonical:
        render_clips = [dict(track, id=track.get("clip_id", track.get("asset_id", f"clip-{index}")), file=track.get("source", "")) for index, track in enumerate(contract.get("tracks", [])[1:], 1)]
        render_clips.sort(key=lambda clip: (-int(clip.get("layer_index", 0)), clip["start_frame"], clip["id"]))
        fit = contract.get("fit", "contain")
    else:
        render_clips = sorted(contract["clips"], key=lambda clip: (-clip["layer_index"], clip["start_frame"], clip["id"]))
        fit = contract["fit"]
    for index, clip in enumerate(render_clips, 1):
        source = bounded(project, clip["file"])
        staged = public / f"{index:03d}-{source.name}"
        if not staged.exists():
            try:
                os.link(source, staged)
            except OSError:
                shutil.copy2(source, staged)
        transform, crop = clip["transform"], clip["transform"].get("crop", {})
        props = [f'src={{staticFile("media/{staged.name}")}}']
        if clip["kind"] == "video":
            props += ["muted", f'trimBefore={{{clip["trim_before"]}}}', f'playbackRate={{{number(clip["playback_rate"])}}}']
            component = "Video"
        else:
            component = "Img"
        clip_path = "inset(%s%% %s%% %s%% %s%%)" % tuple(
            number(float(crop.get(side, 0)) * 100) for side in ("top", "right", "bottom", "left")
        )
        style = {"width": "100%", "height": "100%", "objectFit": fit,
                 "transform": f'translate({transform.get("x", 0)}%, {transform.get("y", 0)}%) rotate({transform.get("rotation", 0)}deg) scale({transform.get("scale", 1)})',
                 "clipPath": clip_path}
        props.append("style={{" + ",".join(f'{k}:{json.dumps(v)}' for k, v in style.items()) + "}}")
        media = f"        <{component}\n          " + "\n          ".join(props) + "\n        />"
        nodes.append(f'      <Sequence name={{{json.dumps(clip["asset_id"])}}} from={{{clip["start_frame"]}}} durationInFrames={{{clip["duration_frames"]}}}>\n{media}\n      </Sequence>')
    narration = narration or bounded(project, contract["narration"]["file"])
    staged_audio = public / narration.name
    if not staged_audio.exists():
        try:
            os.link(narration, staged_audio)
        except OSError:
            shutil.copy2(narration, staged_audio)
    caption_cues = captions if captions is not None else contract["captions"]["cues"]
    caption_nodes = [
        f'      <Sequence from={{{cue["from"]}}} durationInFrames={{{cue["duration"]}}}><div style={{{{position:"absolute",left:80,right:80,bottom:150,color:"white",fontSize:54,fontWeight:700,textAlign:"center",whiteSpace:"pre-wrap",textShadow:"0 3px 14px black"}}}}>{{{json.dumps(cue["text"], ensure_ascii=False)}}}</div></Sequence>'
        for cue in caption_cues
    ]
    source = """import React from 'react';
import {AbsoluteFill, Img, Sequence, staticFile} from 'remotion';
import {Audio, Video} from '@remotion/media';
export const OpenChatCutMaster: React.FC = () => (\n  <AbsoluteFill style={{backgroundColor: 'black'}}>\n%s\n%s\n    <Audio src={staticFile(%s)} />\n  </AbsoluteFill>\n);\n""" % ("\n".join(nodes), "\n".join(caption_nodes), json.dumps("media/" + staged_audio.name))
    (target / "src").mkdir(parents=True, exist_ok=True)
    (target / "src/OpenChatCutMaster.tsx").write_text(source, encoding="utf-8")
    if not canonical:
        write(target / "timeline-receipt.json", dict(master_timeline_sha256=file_hash(project / "04_video/master-timeline.json"),
                                                      source="04_video/master-timeline.json"))


def _canonical_contract_errors(project: Path) -> list[str]:
    try:
        manifest = read(project / "content.json")
        paths = _canonical_paths(manifest)
        path = project / paths["master_timeline"]
        if not path.is_file():
            return ["canonical master timeline is missing"]
        value = read(path)
        required = ("schema_version", "contract", "content_id", "status", "audio_source", "audio_sha256", "openchatcut_owner", "hyperframes_owner", "remotion_owner", "openchatcut_project", "remotion_project", "render_receipt", "candidate_mp4", "candidate_sha256", "digital_human_segments", "tracks")
        expected_contract = str(manifest.get("workflow_contract") or LEGACY_CONTRACT_ID)
        if any(field not in value for field in required) or value.get("contract") != expected_contract:
            raise ValueError("canonical master timeline shape is invalid")
        if value.get("status") not in {"ready_for_review", "approved"}:
            raise ValueError("canonical master timeline is not ready")
        audio = read(project / paths["audio"])
        if value.get("audio_sha256") != audio.get("audio_sha256"):
            raise ValueError("canonical master timeline audio hash is stale")
        narration = [track for track in value.get("tracks", []) if isinstance(track, dict) and track.get("role") == "narration"]
        if len(narration) != 1 or narration[0].get("source") != value.get("audio_source"):
            raise ValueError("canonical master timeline must contain one narration track")
        for track in value.get("tracks", []):
            if not isinstance(track, dict) or track.get("role") == "narration":
                continue
            source = bounded(project, track.get("source", ""))
            if not source.is_file() or file_hash(source) != track.get("sha256"):
                raise ValueError("canonical visual track hash is stale")
            if track.get("role") == "digital_human":
                h3_errors = _h3_timeline_source_errors(project, manifest, source)
                if h3_errors:
                    raise ValueError("; ".join(h3_errors))
        receipt = read(project / value["render_receipt"])
        if receipt.get("source") != paths["master_timeline"] or receipt.get("master_timeline_sha256") != file_hash(path):
            raise ValueError("canonical timeline render receipt is stale")
    except (OSError, ValueError, KeyError, TypeError):
        return ["canonical master timeline is missing or stale"]
    return []


def contract_errors(project: Path):
    try:
        manifest = read(project / "content.json")
    except Exception:
        manifest = {}
    if manifest.get("workflow_contract") in SUPPORTED_CONTRACT_IDS:
        return _canonical_contract_errors(project)
    path = project / "04_video/master-timeline.json"
    if not path.is_file():
        return ["applied OpenChatCut master timeline is missing"]
    try:
        value = read(path)
        snapshot = bounded(project, value["source_snapshot"])
        if value.get("status") != "ready" or file_hash(snapshot) != value["source_snapshot_sha256"]:
            raise ValueError
        for clip in value["clips"]:
            if file_hash(bounded(project, clip["file"])) != clip["sha256"]:
                raise ValueError
        if file_hash(bounded(project, value["narration"]["file"])) != value["narration"]["sha256"]:
            raise ValueError
        if file_hash(bounded(project, value["captions"]["file"])) != value["captions"]["sha256"]:
            raise ValueError
        receipt = read(project / "06_motion/remotion-native/timeline-receipt.json")
        if (receipt.get("source") != "04_video/master-timeline.json"
                or receipt.get("master_timeline_sha256") != file_hash(path)):
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError):
        return ["applied timeline contract is missing or stale"]
    return []


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("compile", choices=["compile"])
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compile_timeline(args.project.resolve(), args.snapshot.resolve()), ensure_ascii=True))
