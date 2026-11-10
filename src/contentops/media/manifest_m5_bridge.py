"""Fail-closed adapter from an M4.5 manifest timeline to M5/Easel inputs."""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence, Tuple

from contentops.media.media_envelope import MediaAssetEnvelope, MediaModality
from contentops.media.media_paths import is_logical_path
from contentops.media.quality_gate import (
    ADMISSIBLE_GATE_STATES,
    GATE_STATES,
    AssetQualityGate,
    MediaManifest,
    TimelineError,
    TimelinePlacement,
)
from contentops.media.transport import ffprobe_json


class ManifestBridgeError(ValueError):
    """An explicit M4.5 manifest cannot safely drive the M5 storyboard."""


def validate_manifest_structure(payload: Dict[str, Any]) -> None:
    """Validate the untrusted serialized boundary before ``MediaManifest.load``.

    The existing loader performs deserialization and bool coercion; this check
    deliberately validates raw JSON types and timeline consistency first.
    """
    if not isinstance(payload, dict) or payload.get("schema") != "contentops.media-manifest/v1":
        raise ManifestBridgeError("manifest schema must be contentops.media-manifest/v1")
    assets = payload.get("assets")
    timeline = payload.get("timeline")
    counts = payload.get("counts")
    if not isinstance(assets, list) or not isinstance(timeline, list) or not isinstance(counts, dict):
        raise ManifestBridgeError("manifest assets, timeline, and counts must have valid shapes")
    if not timeline:
        raise ManifestBridgeError("manifest timeline is empty")

    by_id: Dict[str, Dict[str, Any]] = {}
    for asset in assets:
        if not isinstance(asset, dict):
            raise ManifestBridgeError("manifest assets must be objects")
        asset_id = asset.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id.strip() or asset_id in by_id:
            raise ManifestBridgeError("manifest asset ids must be unique non-empty strings")
        if asset.get("modality") not in (MediaModality.IMAGE, MediaModality.VIDEO, MediaModality.SPEECH):
            raise ManifestBridgeError(f"{asset_id}: modality has no M5 bridge contract")
        for flag in ("generated", "evidence_capable", "production_ready"):
            if type(asset.get(flag)) is not bool:
                raise ManifestBridgeError(f"{asset_id}: {flag} must be a JSON boolean")
        for key in ("placement_id", "path", "sha256", "fingerprint"):
            value = asset.get(key)
            if key == "placement_id" and value is None and asset["modality"] in (MediaModality.SPEECH, MediaModality.AUDIO):
                continue
            if not isinstance(value, str) or not value.strip():
                raise ManifestBridgeError(f"{asset_id}: {key} must be a non-empty string")
        for key in ("receipt_ref", "transform_receipt_ref", "asset_kind", "audio_policy", "derived_from", "evidence_use"):
            value = asset.get(key)
            if value is not None and not isinstance(value, str):
                raise ManifestBridgeError(f"{asset_id}: {key} must be a string or null")
        if not isinstance(asset.get("claim_refs", []), list) or any(not isinstance(ref, str) for ref in asset.get("claim_refs", [])):
            raise ManifestBridgeError(f"{asset_id}: claim_refs must be a string list")
        if not isinstance(asset.get("fallback", {}), dict):
            raise ManifestBridgeError(f"{asset_id}: fallback must be an object")
        by_id[asset_id] = asset

    state_map = counts.get("by_gate_state")
    if not isinstance(state_map, dict) or set(state_map) != set(by_id):
        raise ManifestBridgeError("manifest gate-state map must name every asset exactly once")
    if any(state not in GATE_STATES for state in state_map.values()):
        raise ManifestBridgeError("manifest contains an unknown gate state")

    placement_ids: set[str] = set()
    active_ids: set[str] = set()
    placement_by_id: Dict[str, Dict[str, Any]] = {}
    for placement in timeline:
        if not isinstance(placement, dict):
            raise ManifestBridgeError("manifest timeline entries must be objects")
        placement_id = placement.get("placement_id")
        active_id = placement.get("active_asset_id")
        if not isinstance(placement_id, str) or not placement_id.strip() or placement_id in placement_ids:
            raise ManifestBridgeError("timeline placement ids must be unique non-empty strings")
        if not isinstance(active_id, str) or active_id not in by_id:
            raise ManifestBridgeError(f"{placement_id}: unknown active asset")
        if active_id in active_ids:
            raise ManifestBridgeError("one active asset cannot fill multiple placements")
        placement_ids.add(placement_id)
        active_ids.add(active_id)
        placement_by_id[placement_id] = placement
        active = by_id[active_id]
        if active.get("placement_id") != placement_id:
            raise ManifestBridgeError(f"{placement_id}: active envelope placement does not match")
        if active.get("modality") not in MediaModality.VISUAL:
            raise ManifestBridgeError(f"{placement_id}: nonvisual asset cannot be active")
        if state_map[active_id] not in ADMISSIBLE_GATE_STATES:
            raise ManifestBridgeError(f"{placement_id}: serialized gate state is not admissible")
        superseded = placement.get("superseded_asset_ids", [])
        if not isinstance(superseded, list) or any(not isinstance(item, str) for item in superseded):
            raise ManifestBridgeError(f"{placement_id}: superseded_asset_ids must be a string list")

    # A declared audio-removal transform is authoritative for that placement;
    # never resurrect its source even if a hand-edited timeline marks it usable.
    for placement_id in placement_ids:
        derived = [
            asset for asset in assets
            if asset.get("placement_id") == placement_id
            and asset.get("derived_from")
            and asset.get("audio_policy") in ("MUTE", "REPLACE")
        ]
        if len(derived) > 1:
            raise ManifestBridgeError(f"{placement_id}: multiple derived audio-policy assets are ambiguous")
        if derived:
            winner = derived[0]
            placement = placement_by_id[placement_id]
            if placement.get("active_asset_id") != winner["asset_id"]:
                raise ManifestBridgeError(f"{placement_id}: replaced source cannot be reactivated")
            if winner["derived_from"] not in placement.get("superseded_asset_ids", []):
                raise ManifestBridgeError(f"{placement_id}: transform source is not recorded as superseded")
            source = by_id.get(winner["derived_from"])
            if source is None or source.get("placement_id") != placement_id:
                raise ManifestBridgeError(f"{placement_id}: derived asset has invalid source lineage")


@dataclass(frozen=True)
class ValidatedManifest:
    manifest: MediaManifest
    manifest_path: Path
    manifest_sha256: str
    fingerprint: str
    asset_paths: Dict[str, Path]
    receipt_paths: Dict[str, Path]
    asset_sha256: Dict[str, str]
    receipt_sha256: Dict[str, str]
    active_audio_present: Dict[str, bool]
    fixture_assets: frozenset[str] = frozenset()


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _resolve_logical_asset(
    reference: str, *, repo_root: Path, project_root: Path
) -> Tuple[Path, Path]:
    if not isinstance(reference, str) or not is_logical_path(reference):
        raise ManifestBridgeError("manifest media paths must use project:// or repo://")
    if reference.startswith("project://"):
        root, suffix = project_root.resolve(), reference[len("project://"):]
    elif reference.startswith("repo://"):
        root, suffix = repo_root.resolve(), reference[len("repo://"):]
    else:
        raise ManifestBridgeError("unsupported media path scheme")
    if (not suffix or "\\" in suffix or ":" in suffix or suffix.startswith("/")
            or PurePosixPath(suffix).is_absolute()
            or any(part in ("", ".", "..") for part in suffix.split("/"))):
        raise ManifestBridgeError(f"unsafe logical media path {reference!r}")
    candidate = root.joinpath(*suffix.split("/")).resolve()
    if not _within(candidate, root) or not candidate.is_file():
        raise ManifestBridgeError(f"media path is missing or escapes its declared root: {reference}")
    return candidate, root


def _resolve_receipt(asset_path: Path, root: Path, reference: Optional[str]) -> Optional[Path]:
    if reference is None:
        return None
    if (not isinstance(reference, str) or not reference.strip() or "\\" in reference
            or ":" in reference or PurePosixPath(reference).is_absolute()
            or reference.startswith("/")
            or any(part in ("", ".", "..") for part in reference.split("/"))):
        raise ManifestBridgeError("receipt references must be safe project-relative paths")
    candidate = asset_path.parent.joinpath(*reference.split("/")).resolve()
    if not _within(candidate, root) or not candidate.is_file():
        raise ManifestBridgeError(f"receipt is missing or escapes its declared root: {reference}")
    return candidate


def validate_manifest_file(
    manifest_path: Path, *, repo_root: Path, project_root: Path
) -> ValidatedManifest:
    """Strictly load, revalidate, hash, and probe an explicit manifest.

    All paths are contained before `MediaManifest.load` or media receipt parsing;
    serialized gate states are compared with a fresh validation verdict.
    """
    manifest_path = Path(manifest_path).resolve()
    repo_root, project_root = Path(repo_root).resolve(), Path(project_root).resolve()
    if not (_within(manifest_path, project_root) or _within(manifest_path, repo_root)):
        raise ManifestBridgeError("manifest file must be inside the project or repository")
    if not manifest_path.is_file():
        raise ManifestBridgeError("manifest file does not exist")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestBridgeError(f"manifest is not valid UTF-8 JSON: {exc}") from exc
    validate_manifest_structure(payload)

    asset_paths: Dict[str, Path] = {}
    receipt_paths: Dict[str, Path] = {}
    asset_sha256: Dict[str, str] = {}
    receipt_sha256: Dict[str, str] = {}
    fixture_assets: set[str] = set()
    for raw in payload["assets"]:
        asset_path, declared_root = _resolve_logical_asset(
            raw["path"], repo_root=repo_root, project_root=project_root
        )
        asset_paths[raw["asset_id"]] = asset_path
        asset_sha256[raw["asset_id"]] = raw["sha256"]
        if hashlib.sha256(asset_path.read_bytes()).hexdigest() != raw["sha256"]:
            raise ManifestBridgeError(f"{raw['asset_id']}: file SHA-256 differs from manifest")
        if raw.get("derived_from") is None:
            receipt_path = _resolve_receipt(asset_path, declared_root, raw.get("receipt_ref"))
        else:
            receipt_path = _resolve_receipt(asset_path, declared_root, raw.get("transform_receipt_ref"))
        if receipt_path is not None:
            receipt_paths[raw["asset_id"]] = receipt_path
            receipt_sha256[raw["asset_id"]] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
            try:
                receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ManifestBridgeError(f"{raw['asset_id']}: receipt is not valid JSON") from exc
            if receipt_payload.get("fixture") is True or receipt_payload.get("fixture_kind"):
                fixture_assets.add(raw["asset_id"])

    for raw in payload["assets"]:
        if raw.get("derived_from") in fixture_assets:
            fixture_assets.add(raw["asset_id"])

    try:
        manifest = MediaManifest.load(manifest_path)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ManifestBridgeError(f"manifest deserialization failed: {exc}") from exc

    fresh_states: Dict[str, str] = {}
    gate = AssetQualityGate()
    for envelope in manifest.assets:
        try:
            envelope.validate_shape()
            decision = gate.evaluate(
                envelope, repo_root=repo_root, project_root=project_root
            )
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            raise ManifestBridgeError(f"{envelope.asset_id}: validation failed: {exc}") from exc
        result = decision.validation
        if result is None:
            raise ManifestBridgeError(f"{envelope.asset_id}: gate returned no validation evidence")
        if result.observed_sha256 and result.observed_sha256 != envelope.sha256:
            raise ManifestBridgeError(f"{envelope.asset_id}: observed digest differs from envelope")
        fresh = decision.state
        recorded = (payload["counts"]["by_gate_state"]).get(envelope.asset_id)
        if fresh != recorded:
            raise ManifestBridgeError(
                f"{envelope.asset_id}: serialized gate state {recorded!r} "
                f"does not match fresh state {fresh!r}"
            )
        fresh_states[envelope.asset_id] = fresh

    manifest.gate_states = fresh_states
    try:
        active = manifest.timeline_assets()
    except TimelineError as exc:
        raise ManifestBridgeError(str(exc)) from exc

    audio_present: Dict[str, bool] = {}
    for envelope in active:
        if envelope.modality != MediaModality.VIDEO:
            continue
        policy = envelope.audio_policy
        if policy not in ("KEEP", "MUTE", "REPLACE"):
            raise ManifestBridgeError(f"{envelope.asset_id}: video AudioPolicy must be explicit")
        try:
            probe = ffprobe_json(asset_paths[envelope.asset_id])
        except (RuntimeError, OSError, ValueError) as exc:
            raise ManifestBridgeError(f"{envelope.asset_id}: cannot probe video audio: {exc}") from exc
        has_audio = any(stream.get("codec_type") == "audio" for stream in probe.get("streams", []))
        audio_present[envelope.asset_id] = has_audio
        if policy == "KEEP":
            if envelope.is_derived or not has_audio:
                raise ManifestBridgeError(
                    f"{envelope.asset_id}: KEEP requires the original active clip with native audio"
                )
        elif not envelope.is_derived or has_audio:
            raise ManifestBridgeError(
                f"{envelope.asset_id}: {policy} requires an audio-free derived clip"
            )

    return ValidatedManifest(
        manifest=manifest,
        manifest_path=manifest_path,
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        fingerprint=manifest.fingerprint(),
        asset_paths=asset_paths,
        receipt_paths=receipt_paths,
        asset_sha256=asset_sha256,
        receipt_sha256=receipt_sha256,
        active_audio_present=audio_present,
        fixture_assets=frozenset(fixture_assets),
    )


def map_script_to_active_assets(
    manifest: MediaManifest, lines: Sequence[Dict[str, Any]]
) -> List[Tuple[Dict[str, Any], MediaAssetEnvelope]]:
    """Return the explicit one-to-one script-line → active placement mapping.

    Neither inventory order nor filenames participate in selection. Script order
    and declared Timeline order must agree, and a line's optional ``asset_id`` is
    a consistency assertion, never an alternate asset selector.
    """
    if not manifest.timeline:
        raise ManifestBridgeError("manifest timeline is empty")
    try:
        active = manifest.timeline_assets()
    except TimelineError as exc:
        raise ManifestBridgeError(str(exc)) from exc

    line_ids = [line.get("id") for line in lines]
    if any(not isinstance(line_id, str) or not line_id.strip() for line_id in line_ids):
        raise ManifestBridgeError("every script line needs a non-empty id")
    if len(line_ids) != len(set(line_ids)):
        raise ManifestBridgeError("script line ids must be unique")

    placement_to_envelope = {
        placement.placement_id: manifest.envelope_for(placement.active_asset_id)
        for placement in manifest.timeline
    }
    placements = [line.get("placement_id") for line in lines]
    if any(not isinstance(pid, str) or not pid.strip() for pid in placements):
        raise ManifestBridgeError("every manifest-mode script line needs placement_id")
    if len(placements) != len(set(placements)):
        raise ManifestBridgeError("script lines cannot map to one placement more than once")
    if set(placements) != set(placement_to_envelope):
        missing = sorted(set(placement_to_envelope) - set(placements))
        extra = sorted(set(placements) - set(placement_to_envelope))
        raise ManifestBridgeError(
            f"script/timeline mapping is not one-to-one; unmapped={missing}, unknown={extra}"
        )
    if placements != [placement.placement_id for placement in manifest.timeline]:
        raise ManifestBridgeError(
            "script placement order conflicts with manifest timeline order"
        )

    mapped: List[Tuple[Dict[str, Any], MediaAssetEnvelope]] = []
    for line in lines:
        placement_id = line["placement_id"]
        envelope = placement_to_envelope[placement_id]
        if envelope is None:
            raise ManifestBridgeError(f"{placement_id}: active asset is missing")
        if line.get("asset_id") and line["asset_id"] != envelope.asset_id:
            raise ManifestBridgeError(
                f"{line['id']}: asset_id conflicts with active timeline asset "
                f"{envelope.asset_id!r}"
            )
        mapped.append((line, envelope))
    if len(active) != len(mapped):
        raise ManifestBridgeError("not every active visual placement maps to one script line")
    return mapped


def _repo_relative(path: Path, repo_root: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError as exc:
        raise ManifestBridgeError("Easel inputs must resolve inside the repository") from exc


def _srt_stamp(value: str) -> float:
    match = re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
    if not match:
        raise ManifestBridgeError(f"invalid SRT timestamp {value!r}")
    hours, minutes, seconds, millis = (int(part) for part in match.groups())
    if minutes > 59 or seconds > 59:
        raise ManifestBridgeError(f"invalid SRT timestamp {value!r}")
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def _verify_subtitles(
    path: Path, lines: Sequence[Dict[str, Any]], timings: Sequence[Dict[str, Any]],
    total_duration: float,
) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ManifestBridgeError("subtitle file is missing or unreadable") from exc
    blocks = [block.strip() for block in re.split(r"\r?\n\s*\r?\n", content) if block.strip()]
    if len(blocks) != len(lines):
        raise ManifestBridgeError("subtitle cue count must match script line count")
    cue_re = re.compile(
        r"^\d+\s*\n(\d{2,}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*"
        r"(\d{2,}:\d{2}:\d{2}[,.]\d{3})\s*\n([\s\S]+)$"
    )
    previous_end = -1.0
    for index, (block, line, timing) in enumerate(zip(blocks, lines, timings)):
        match = cue_re.match(block)
        if not match:
            raise ManifestBridgeError(f"subtitle cue {index + 1} is malformed")
        start, end = _srt_stamp(match.group(1)), _srt_stamp(match.group(2))
        text = match.group(3).strip()
        expected_start = float(timing["start"])
        expected_end = expected_start + float(timing["duration"])
        if start < 0 or end <= start or end > total_duration + 0.02 or start < previous_end - 0.02:
            raise ManifestBridgeError(f"subtitle cue {index + 1} is outside the audio timeline")
        if abs(start - expected_start) > 0.02 or abs(end - expected_end) > 0.02:
            raise ManifestBridgeError(f"subtitle cue {index + 1} is not aligned to its narration line")
        if text != str(line.get("caption") or "").strip():
            raise ManifestBridgeError(f"subtitle cue {index + 1} does not match its script caption")
        previous_end = end


def build_m5_storyboard(
    validated: ValidatedManifest,
    lines: Sequence[Dict[str, Any]],
    narration_lines: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    narration_duration_s: Optional[float] = None,
    narration_path: Optional[Path] = None,
    subtitle_path: Optional[Path] = None,
    project_root: Path,
    repo_root: Path,
    size: str = "1080x1920",
    voice_provider: Optional[str] = None,
    technical_preview: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build an Easel storyboard from only validated active manifest placements."""
    if technical_preview:
        return build_technical_preview_storyboard(
            validated, project_root=project_root, repo_root=repo_root, size=size,
        )
    if (narration_lines is None or narration_duration_s is None
            or narration_path is None or subtitle_path is None):
        raise ManifestBridgeError(
            "formal M5 storyboards require narration timings, audio, and subtitles"
        )
    mapped = map_script_to_active_assets(validated.manifest, lines)
    if len(narration_lines) != len(lines):
        raise ManifestBridgeError("script, narration, and timeline line counts must match")
    try:
        total_duration = float(narration_duration_s)
    except (TypeError, ValueError) as exc:
        raise ManifestBridgeError("narration duration must be numeric") from exc
    if not math.isfinite(total_duration) or total_duration <= 0:
        raise ManifestBridgeError("narration duration must be finite and positive")

    voice_path, captions_path = Path(narration_path).resolve(), Path(subtitle_path).resolve()
    project_root = Path(project_root).resolve()
    if not _within(voice_path, project_root) or not voice_path.is_file():
        raise ManifestBridgeError("narration audio must exist inside the project")
    if not _within(captions_path, project_root) or not captions_path.is_file():
        raise ManifestBridgeError("subtitles must exist inside the project")

    starts: List[float] = []
    speech_ends: List[float] = []
    for index, (line, timing) in enumerate(zip(lines, narration_lines)):
        if not isinstance(timing, dict):
            raise ManifestBridgeError(f"narration timing {index + 1} must be an object")
        timing_id = timing.get("line_id", timing.get("id"))
        if timing_id is not None and timing_id != line.get("id"):
            raise ManifestBridgeError(f"narration timing {index + 1} names a different script line")
        try:
            start = float(timing["start"])
            duration = float(timing["duration"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ManifestBridgeError(f"narration timing {index + 1} needs start and duration") from exc
        if (not math.isfinite(start) or not math.isfinite(duration) or start < 0 or duration <= 0
                or start + duration > total_duration + 0.02):
            raise ManifestBridgeError(f"narration timing {index + 1} is outside the audio duration")
        if index == 0 and abs(start) > 0.02:
            raise ManifestBridgeError("first narration line must start at zero")
        if starts and start < speech_ends[-1] - 0.001:
            raise ManifestBridgeError("narration line timings overlap or move backwards")
        starts.append(start)
        speech_ends.append(start + duration)
    _verify_subtitles(captions_path, lines, narration_lines, total_duration)

    boundaries = [0.0] + starts[1:] + [total_duration]
    shots: List[Dict[str, Any]] = []
    placement_records: List[Dict[str, Any]] = []
    for index, ((line, envelope), start, end) in enumerate(zip(mapped, boundaries, boundaries[1:])):
        duration = round(end - start, 3)
        if not math.isfinite(duration) or duration <= 0:
            raise ManifestBridgeError(f"{line['id']}: timeline interval is not positive")
        asset_path = validated.asset_paths.get(envelope.asset_id)
        if asset_path is None:
            raise ManifestBridgeError(f"{envelope.asset_id}: validated path is missing")
        if hashlib.sha256(asset_path.read_bytes()).hexdigest() != validated.asset_sha256.get(envelope.asset_id):
            raise ManifestBridgeError(f"{envelope.asset_id}: media changed after manifest validation")
        receipt_path = validated.receipt_paths.get(envelope.asset_id)
        if receipt_path is None or hashlib.sha256(receipt_path.read_bytes()).hexdigest() != validated.receipt_sha256.get(envelope.asset_id):
            raise ManifestBridgeError(f"{envelope.asset_id}: receipt changed after manifest validation")
        reference = _repo_relative(asset_path, repo_root)
        is_video = envelope.modality == MediaModality.VIDEO
        if envelope.modality not in (MediaModality.IMAGE, MediaModality.VIDEO):
            raise ManifestBridgeError(f"{envelope.asset_id}: active asset is not visual")
        if envelope.asset_id in validated.fixture_assets:
            source_type = "fixture"
        elif is_video and envelope.generated:
            source_type = "generated"
        elif is_video:
            source_type = "real_recording" if str(envelope.asset_kind).upper() in (
                "REAL", "SCREEN_RECORDING"
            ) else "video"
        elif envelope.generated:
            source_type = "ai_generated"
        else:
            source_type = {
                "REAL": "real_screenshot", "SCREENSHOT": "real_screenshot",
                "SCREEN_RECORDING": "real_recording", "DIAGRAM": "diagram",
            }.get(str(envelope.asset_kind or "").upper(), "stock")
        shot: Dict[str, Any] = {
            "shot_id": envelope.placement_id,
            "image": reference,
            "motion": "static",
            "duration": duration,
            "duration_s": duration,
            "source": reference,
            "source_type": source_type,
            "caption": line.get("caption"),
            "narration": line.get("narration"),
            "claim": line.get("claim"),
            "media_provenance": {
                "asset_id": envelope.asset_id,
                "placement_id": envelope.placement_id,
                "sha256": envelope.sha256,
                "receipt_ref": envelope.receipt_ref,
                "transform_receipt_ref": envelope.transform_receipt_ref,
                "generated": envelope.generated,
                "evidence_capable": envelope.evidence_capable,
                "evidence_use": envelope.evidence_use,
                "fixture": envelope.asset_id in validated.fixture_assets,
            },
        }
        if is_video:
            shot["video"] = reference
            shot["audio_policy"] = envelope.audio_policy
            shot["audio_mode"] = "native" if envelope.audio_policy == "KEEP" else "dub"
        shots.append(shot)
        placement_records.append({
            "line_id": line["id"],
            "placement_id": envelope.placement_id,
            "active_asset_id": envelope.asset_id,
            "asset_sha256": envelope.sha256,
            "asset_path": reference,
            "start": round(start, 3),
            "duration": duration,
            "generated": envelope.generated,
            "evidence_capable": envelope.evidence_capable,
            "fixture": envelope.asset_id in validated.fixture_assets,
            "audio_policy": envelope.audio_policy,
            "audio_present": validated.active_audio_present.get(envelope.asset_id),
        })

    storyboard = {
        "size": size,
        "image_motion": "static",
        "pad_mode": "trim",
        "shots": shots,
        "narration": _repo_relative(voice_path, repo_root),
        "subtitle": _repo_relative(captions_path, repo_root),
        "engine": "easel",
        **({"voice_provider": voice_provider} if voice_provider else {}),
        "media_manifest_fingerprint": validated.fingerprint,
        "media_manifest_sha256": validated.manifest_sha256,
        "audio_postconditions": validated.manifest.audio_postconditions(),
        "generated_visuals": {
            "count": sum(1 for _, asset in mapped if asset.generated),
            "policy": "support_only_never_evidence",
        },
    }
    receipt = {
        "schema": "contentops.m5-manifest-bridge/v1",
        "status": "OK",
        "mode": "MANIFEST_DRIVEN",
        "manifest": _repo_relative(validated.manifest_path, repo_root),
        "manifest_sha256": validated.manifest_sha256,
        "manifest_fingerprint": validated.fingerprint,
        "provider_calls": 0,
        "placements": placement_records,
        "production_ready": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }
    return storyboard, receipt


def build_technical_preview_storyboard(
    validated: ValidatedManifest,
    *,
    project_root: Path,
    repo_root: Path,
    size: str = "1080x1920",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build a silent, claim-free storyboard from the active M4.5 timeline.

    This adapter is deliberately separate from ``build_m5_storyboard``: it
    accepts no script or narration and can only mark its output as a technical
    sample. The formal M5 narration and review gates remain untouched.
    """
    project_root, repo_root = Path(project_root).resolve(), Path(repo_root).resolve()
    lines = [
        {"id": f"technical-preview-{placement.placement_id}",
         "placement_id": placement.placement_id,
         "caption": "TECHNICAL_SAMPLE_ONLY"}
        for placement in validated.manifest.timeline
    ]
    mapped = map_script_to_active_assets(validated.manifest, lines)
    shots: List[Dict[str, Any]] = []
    placement_records: List[Dict[str, Any]] = []
    for line, envelope in mapped:
        asset_path = validated.asset_paths.get(envelope.asset_id)
        if asset_path is None or not _within(asset_path, project_root):
            raise ManifestBridgeError(f"{envelope.asset_id}: validated project asset path is missing")
        if hashlib.sha256(asset_path.read_bytes()).hexdigest() != validated.asset_sha256.get(envelope.asset_id):
            raise ManifestBridgeError(f"{envelope.asset_id}: media changed after manifest validation")
        receipt_path = validated.receipt_paths.get(envelope.asset_id)
        if receipt_path is None or hashlib.sha256(receipt_path.read_bytes()).hexdigest() != validated.receipt_sha256.get(envelope.asset_id):
            raise ManifestBridgeError(f"{envelope.asset_id}: receipt changed after manifest validation")
        info = ffprobe_json(str(asset_path))
        try:
            duration = float(info["format"]["duration"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ManifestBridgeError(f"{envelope.asset_id}: finite video duration is required") from exc
        if not math.isfinite(duration) or duration <= 0:
            raise ManifestBridgeError(f"{envelope.asset_id}: finite video duration is required")
        reference = _repo_relative(asset_path, repo_root)
        source_ref = envelope.path
        shot = {
            "shot_id": envelope.placement_id,
            "video": reference,
            "image": reference,
            "source": reference,
            "source_type": "generated" if envelope.generated else "video",
            "motion": "static",
            "duration": round(duration, 3),
            "duration_s": round(duration, 3),
            "audio_mode": "dub",
            "audio_policy": envelope.audio_policy,
            "caption": "TECHNICAL_SAMPLE_ONLY",
            "media_provenance": {
                "asset_id": envelope.asset_id,
                "placement_id": envelope.placement_id,
                "sha256": envelope.sha256,
                "receipt_ref": envelope.receipt_ref,
                "transform_receipt_ref": envelope.transform_receipt_ref,
                "source_asset_ref": source_ref,
                "generated": envelope.generated,
                "evidence_capable": envelope.evidence_capable,
                "evidence_use": envelope.evidence_use,
            },
        }
        shots.append(shot)
        placement_records.append({
            "line_id": line["id"], "placement_id": envelope.placement_id,
            "active_asset_id": envelope.asset_id, "asset_sha256": envelope.sha256,
            "asset_path": reference, "duration": round(duration, 3),
            "audio_policy": envelope.audio_policy,
            "generated": envelope.generated, "evidence_capable": envelope.evidence_capable,
        })
    storyboard = {
        "size": size, "image_motion": "static", "pad_mode": "trim",
        "shots": shots, "engine": "easel",
        "media_manifest_fingerprint": validated.fingerprint,
        "media_manifest_sha256": validated.manifest_sha256,
        "technical_sample_status": "TECHNICAL_SAMPLE_ONLY",
        "production_ready": False, "publish_authorized": False,
    }
    receipt = {
        "schema": "contentops.m5-technical-preview-bridge/v1",
        "status": "OK", "mode": "M4.5_MANIFEST_TECHNICAL_PREVIEW",
        "manifest": _repo_relative(validated.manifest_path, repo_root),
        "manifest_sha256": validated.manifest_sha256,
        "manifest_fingerprint": validated.fingerprint,
        "provider_calls": 0, "placements": placement_records,
        "technical_sample_status": "TECHNICAL_SAMPLE_ONLY",
        "production_ready": False, "publish_authorized": False,
    }
    return storyboard, receipt
