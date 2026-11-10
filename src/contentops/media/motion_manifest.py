"""Register a checked Huashu motion clip as an M4.5 manifest asset.

Why this module exists
-----------------------
Both Huashu engines produce a *clip*. The M4.5 manifest consumes *assets*, and
the difference is provenance, not pixels: a clip that was rendered by an engine
has bytes that nobody captured, so it is generated media, it carries no source
evidence, and it must not become the active shot on its own — the active shot is
the audio-free transform of it, exactly like a provider shot whose native track
was replaced by narration.

This module performs that one step and stops:

    checked clip  ->  source receipt + source envelope
                  ->  deterministic audio-free transform
                  ->  derived envelope (the one the timeline activates)

It does not compose, does not publish, and does not approve anything. The
existing :mod:`contentops.media.manifest_m5_bridge` then reads the manifest and
hands the active timeline to M5.

What it refuses
---------------
- a clip whose bytes do not match the digest in its record
- a clip outside the project root
- a record that does not come from a pinned engine
- a generated clip that claims evidence capability
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from contentops.media.media_envelope import MediaAssetEnvelope
from contentops.media.huashu_motion import RECORD_SCHEMA, engine_identity

NATIVE_PREVIEW_SCHEMA = "contentops.native-motion-preview/v1"
_SHA256 = set("0123456789abcdef")

#: The provider-shaped receipt schema the shared video validator already accepts.
#: A locally rendered clip is generated media produced by a named local engine, so
#: it is recorded in the same shape as any other generated video rather than
#: inventing a second validation path.
VIDEO_RECEIPT_SCHEMA = "contentops.video-receipt/v1"

#: The suffix of the deterministic audio transform's receipt.
TRANSFORM_SUFFIX = ".transform.json"


class MotionAssetError(ValueError):
    """A motion clip cannot enter the M4.5 manifest as described."""


@dataclass(frozen=True)
class RegisteredMotionAsset:
    """The envelopes and receipt paths one motion clip produced."""

    source: MediaAssetEnvelope
    derived: MediaAssetEnvelope
    source_receipt_path: Path
    transform_receipt_path: Path
    clip_sha256: str
    spec_sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_receipt(path: Path, payload: Dict[str, Any]) -> Path:
    if path.exists():
        raise MotionAssetError(f"refusing to overwrite an existing receipt: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not path.is_file():
        raise MotionAssetError(f"the receipt could not be written: {path}")
    return path


def _native_preview_facts(record: Dict[str, Any], clip: Path, root: Path) -> Dict[str, Any]:
    """Validate the Native Motion receipt without translating it into Huashu."""
    renderer = record.get("renderer")
    output = record.get("output")
    rights = record.get("rights")
    if not isinstance(renderer, dict) or not isinstance(output, dict) or not isinstance(rights, dict):
        raise MotionAssetError("native preview renderer, output, and rights must be objects")
    digest = renderer.get("source_sha256")
    spec_digest = record.get("spec_sha256")
    output_digest = output.get("sha256")
    if any(not isinstance(value, str) or len(value) != 64 or set(value) - _SHA256
           for value in (digest, spec_digest, output_digest)):
        raise MotionAssetError("native preview renderer, spec, and output digests must be lowercase SHA-256")
    if (not isinstance(record.get("project"), str) or not record["project"].strip()
            or not isinstance(record.get("account"), str) or not record["account"].strip()
            or not isinstance(record.get("version"), str) or not record["version"].strip()
            or not isinstance(renderer.get("source"), str) or not renderer["source"].strip()):
        raise MotionAssetError("native preview project, account, version, and renderer source are required")
    dependencies = renderer.get("dependencies")
    if not isinstance(dependencies, dict) or not dependencies:
        raise MotionAssetError("native preview runtime dependencies are required")
    if output.get("technical_state") != "TECHNICALLY_CHECKED":
        raise MotionAssetError("only a technically checked native preview can be registered")
    if output.get("generated") is not True or output.get("evidence_capable") is not False:
        raise MotionAssetError("native motion must remain generated support, never evidence")
    if record.get("production_ready") is not False or record.get("publish_authorized") is not False:
        raise MotionAssetError("native preview cannot assert production or publication approval")
    if rights.get("public_use_cleared") is not False:
        raise MotionAssetError("native preview rights must not imply public-use clearance")
    relative = clip.relative_to(root).as_posix()
    if output.get("path") != "project://" + relative:
        raise MotionAssetError("native preview output path does not match the contained clip")
    if output_digest != _sha256(clip):
        raise MotionAssetError("native preview output digest differs from the checked clip")
    try:
        width_text, height_text = str(output["resolution"]).split("x", 1)
        width, height = int(width_text), int(height_text)
        duration = float(output["duration_s"])
        fps = float(output["fps"])
        frames = int(output["frames"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise MotionAssetError("native preview dimensions, frame rate, duration, and frame count are required") from exc
    if (width <= 0 or height <= 0 or duration <= 0 or fps <= 0 or frames <= 0
            or abs(frames - duration * fps) > 1.0):
        raise MotionAssetError("native preview technical media facts are invalid")
    return {
        "engine": "native-motion-preview",
        "version": record["version"],
        "commit": None,
        "spec_sha256": spec_digest,
        "asset_hashes": {},
        "resolution": output["resolution"],
        "width": width,
        "height": height,
        "duration": duration,
        "fps": fps,
        "frames": frames,
        "motion_origin": {
            "schema": NATIVE_PREVIEW_SCHEMA,
            "project": record["project"],
            "account": record["account"],
            "version": record["version"],
            "renderer": renderer,
            "rights": rights,
        },
    }


def register_motion_clip(
    record: Dict[str, Any],
    *,
    clip_path: Path,
    project_root: Path,
    asset_id: str,
    placement_id: str,
    audio_policy: str = "REPLACE",
    narration_source: Optional[str] = None,
    output_dir: Optional[Path] = None,
) -> RegisteredMotionAsset:
    """Register one checked clip and return the source and derived envelopes.

    ``audio_policy`` is ``REPLACE`` (the usual case: the clip's own soundtrack is
    dropped and narration replaces it) or ``MUTE`` (the clip is used silent and
    nothing is muxed over it). ``KEEP`` is refused here: keeping a clip's own
    soundtrack would put an unrequested audio track under the narration, which
    is the exact defect the audio policy exists to prevent.
    """
    if not isinstance(record, dict):
        raise MotionAssetError("the motion record must be an object")
    native = record.get("schema") == NATIVE_PREVIEW_SCHEMA
    if native:
        facts = _native_preview_facts(record, Path(clip_path).resolve(), Path(project_root).resolve())
    else:
        if record.get("schema") != RECORD_SCHEMA:
            raise MotionAssetError(
                f"the record must be a {RECORD_SCHEMA} or {NATIVE_PREVIEW_SCHEMA} record"
            )
        identity = engine_identity(str(record.get("engine") or ""))
        if (record.get("version") != identity["version"]
                or record.get("commit") != identity["commit"]):
            raise MotionAssetError("the record does not match the pinned engine runtime")
        facts = {
            "engine": str(record.get("engine")), "version": identity["version"],
            "commit": identity["commit"], "spec_sha256": record.get("spec_sha256"),
            "asset_hashes": dict(record.get("asset_hashes") or {}),
            "resolution": record["resolution"],
            "width": int(str(record["resolution"]).split("x")[0]),
            "height": int(str(record["resolution"]).split("x")[1]),
            "duration": float(record["duration"]), "fps": float(record["fps"]),
            "frames": None, "motion_origin": {
                "schema": RECORD_SCHEMA, "engine": record.get("engine"),
                "version": identity["version"], "commit": identity["commit"],
                "rights": record.get("rights"),
            },
        }
    if record.get("technical_status", "TECHNICALLY_CHECKED") != "TECHNICALLY_CHECKED":
        raise MotionAssetError("only a technically checked clip can be registered")
    provenance = record.get("output", {}) if native else record
    if (provenance.get("generated") is not True
            or provenance.get("evidence_capable") is not False):
        raise MotionAssetError("a generated clip must stay support-only and evidence-incapable")
    policy = str(audio_policy or "").upper()
    if policy not in {"MUTE", "REPLACE"}:
        raise MotionAssetError("audio_policy must be MUTE or REPLACE for a motion clip")

    root = Path(project_root).resolve()
    clip = Path(clip_path).resolve()
    if not clip.is_relative_to(root) or not clip.is_file():
        raise MotionAssetError("the clip is missing or escapes the project root")
    observed = _sha256(clip)
    expected_digest = record["output"]["sha256"] if native else record.get("clip_sha256")
    if observed != expected_digest:
        raise MotionAssetError(
            "the clip digest differs from the record; the bytes are not the ones that were checked"
        )
    if native:
        native_rights = record.get("rights")
        if (not isinstance(native_rights, dict)
                or native_rights.get("scope") != "P6-requested internal review only"
                or native_rights.get("public_use_cleared") is not False):
            raise MotionAssetError("native preview rights must remain explicitly internal-only")
    elif record.get("rights") not in (None, "", "UNRESOLVED"):
        raise MotionAssetError("a motion clip's rights must be recorded, not asserted")

    from contentops.media.media_transform import apply_audio_policy

    assets_dir = root / "assets"
    receipt_path = _write_receipt(
        clip.with_name(clip.name + ".receipt.json"),
        {
            "schema": VIDEO_RECEIPT_SCHEMA,
            "provider": facts["engine"],
            "product": facts["engine"],
            "plan": "local_engine",
            "transport": "local_engine",
            "model": facts["version"],
            "mode": "RENDER",
            "fingerprint": facts["spec_sha256"],
            "output_sha256": observed,
            "technical_qc": {
                "approved": True,
                "reasons": [],
                "width": facts["width"],
                "height": facts["height"],
                "duration_s": facts["duration"],
                "fps": facts["fps"],
                "frames": facts["frames"],
                "engine": facts["engine"],
                "engine_version": facts["version"],
                "engine_commit": facts["commit"],
                "spec_sha256": facts["spec_sha256"],
                "input_asset_hashes": facts["asset_hashes"],
            },
            "motion_origin": facts["motion_origin"],
            "billing_mode": "subscription",
            "payg_allowed": False,
            "credit_pack_allowed": False,
            "quota_consumed": False,
            "attempt": 1,
            "production_ready": False,
            "human_review": "PENDING_FOUNDER_REVIEW",
            "generated": True,
            "evidence_capable": False,
            "rights": "UNRESOLVED",
            "audio_policy": policy,
        },
    )

    source = MediaAssetEnvelope(
        asset_id=asset_id,
        modality="VIDEO",
        placement_id=placement_id,
        path="project://" + clip.relative_to(root).as_posix(),
        sha256=observed,
        receipt_ref=receipt_path.name,
        fingerprint=facts["spec_sha256"],
        asset_kind="GENERATED_VIDEO",
        generated=True,
        evidence_capable=False,
        evidence_use="VISUAL_SUPPORT",
        technical_status="PASS_TECHNICAL",
        human_review="PENDING_FOUNDER_REVIEW",
        production_ready=False,
    )
    source.validate_shape()

    application = apply_audio_policy(
        source_video=clip,
        policy=policy,
        output_dir=Path(output_dir) if output_dir else assets_dir / "processed",
        source_receipt_ref=receipt_path.name,
        source_fingerprint=str(facts["spec_sha256"]),
        narration_source=narration_source,
        source_generated=True,
    )
    derived_path = Path(application.output_path)
    if not derived_path.is_file():
        raise MotionAssetError("the audio-free transform did not produce a file")
    transform_receipt_path = Path(str(application.receipt_path))
    if not transform_receipt_path.is_file():
        raise MotionAssetError("the audio-free transform did not produce a receipt")
    derived_relative = derived_path.resolve().relative_to(root)
    derived = MediaAssetEnvelope(
        asset_id=f"{asset_id}-{policy.lower()}",
        modality="VIDEO",
        placement_id=placement_id,
        path="project://" + derived_relative.as_posix(),
        sha256=application.transform_receipt.output_sha256,
        receipt_ref=receipt_path.name,
        fingerprint=facts["spec_sha256"],
        asset_kind="GENERATED_VIDEO",
        generated=True,
        evidence_capable=False,
        evidence_use="VISUAL_SUPPORT",
        technical_status="PASS_TECHNICAL",
        human_review="PENDING_FOUNDER_REVIEW",
        production_ready=False,
        audio_policy=policy,
        derived_from=asset_id,
        transform_receipt_ref=derived_path.name + TRANSFORM_SUFFIX,
    )
    derived.validate_shape()
    return RegisteredMotionAsset(
        source=source,
        derived=derived,
        source_receipt_path=receipt_path,
        transform_receipt_path=transform_receipt_path,
        clip_sha256=observed,
        spec_sha256=str(facts["spec_sha256"]),
    )


def build_motion_manifest_entries(
    registered: List[RegisteredMotionAsset],
    *,
    decisions: Optional[Dict[str, Any]] = None,
) -> List[MediaAssetEnvelope]:
    """Return the manifest entries for registered clips, source before derived.

    The source stays in the inventory so the derived clip's lineage remains
    traversable; only the derived clip is eligible to be activated.
    """
    entries: List[MediaAssetEnvelope] = []
    for item in registered:
        entries.append(item.source)
        entries.append(item.derived)
    identifiers = [entry.asset_id for entry in entries]
    if len(identifiers) != len(set(identifiers)):
        raise MotionAssetError("two motion assets share an identifier")
    return entries
