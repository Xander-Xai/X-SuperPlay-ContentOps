"""Deterministic transforms, recorded separately from provider generations.

Provider assets are immutable
-----------------------------
Once a generation receipt is written, its canonical bytes are evidence. M2, M3 and
M4 each enforce that: a speech WAV, an image and an H3 shot are never rewritten in
place.

Applying an audio policy therefore **cannot** edit the original. H3 returned an
unrequested AAC track in both M2.0 and M4, so every generated shot carries audio
nobody asked for, and the KEEP/MUTE/REPLACE decision has to happen somewhere. This
module does it by producing a **derived asset** and a **transform receipt**, and
leaves the provider generation exactly as it was.

Why a separate receipt rather than editing the original
------------------------------------------------------
Reusing the generation receipt for transformed bytes would make one receipt claim
two things: that the provider produced these bytes, and that something local then
changed them. Downstream, "is this shot straight from the provider?" becomes
unanswerable, and a re-run would appear to change a receipt it must not change.

So provenance stays a chain instead of being flattened:

``shot.mp4`` (provider) → ``shot-mute.mp4`` (derived) → transform receipt
→ ``shot.mp4.receipt.json`` (the untouched original)

AudioPolicy, applied
--------------------
``KEEP``
    the original is reused unchanged. **No transform runs and no derived asset is
    produced** — copying a file to "transform" it would invent provenance for
    bytes that did not move.
``MUTE``
    a derived asset with no audio stream.
``REPLACE``
    a derived asset with no native H3 audio, plus an explicit
    ``replacement_narration_required`` flag. The narration is **not** written in
    here: it is muxed during composition from a deterministic track, so a silent
    mix can never result from this step.

The postcondition that matters
------------------------------
After this runs, the H3 native track and the narration track must not both be
present unless a later, explicit mix policy says so. That is checked here rather
than trusted: :func:`apply_audio_policy` verifies the output's actual stream
layout, and the manifest carries the requirement forward so composition can
enforce it.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from contentops.media.fingerprint import sha256_file
from contentops.media.media_envelope import MediaModality
from contentops.media.transport import ffprobe_json
from contentops.media.video_contract import AudioPolicy

__all__ = [
    "TRANSFORM_SCHEMA",
    "AudioPolicyError",
    "TransformReceipt",
    "apply_audio_policy",
    "transform_receipt_to_dict",
]

TRANSFORM_SCHEMA = "contentops.media-transform/v1"

#: Written next to a derived asset, matching the provider sidecar convention so
#: both kinds of provenance file are found by the same rule.
TRANSFORM_SUFFIX = ".transform.json"


class AudioPolicyError(RuntimeError):
    """A deterministic transform could not be completed or verified.

    Never raised to mean "the policy was refused" — an invalid policy is a
    planning error and is refused before this module runs.
    """


@dataclass
class TransformReceipt:
    """Provenance for bytes produced by a deterministic local transform.

    Distinct from a generation receipt in the only way that matters: nothing here
    was produced by a provider. ``generated`` is therefore ``false`` and
    ``derived`` is ``true``.
    """

    transform_type: str
    source_asset_sha256: str
    source_receipt_ref: Optional[str]
    source_fingerprint: Optional[str]
    output_path: str
    output_sha256: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    tool: str = "ffmpeg"
    tool_version: Optional[str] = None
    #: Digest of the exact argv used, so two runs with the same inputs are
    #: recognisably the same operation without re-running it.
    command_fingerprint: str = ""
    created_at: Optional[str] = None
    generated: bool = False
    derived: bool = True
    production_ready: bool = False
    human_review: str = "PENDING_FOUNDER_REVIEW"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": TRANSFORM_SCHEMA,
            "transform_type": self.transform_type,
            "source_asset_sha256": self.source_asset_sha256,
            "source_receipt_ref": self.source_receipt_ref,
            "source_fingerprint": self.source_fingerprint,
            "output_path": self.output_path,
            "output_sha256": self.output_sha256,
            "parameters": dict(self.parameters),
            "tool": self.tool,
            "tool_version": self.tool_version,
            "command_fingerprint": self.command_fingerprint,
            "created_at": self.created_at,
            "generated": self.generated,
            "derived": self.derived,
            "production_ready": self.production_ready,
            "human_review": self.human_review,
        }


def transform_receipt_to_dict(receipt: TransformReceipt) -> Dict[str, Any]:
    return receipt.as_dict()


def _ffmpeg_version() -> Optional[str]:
    """Best-effort tool version, so a receipt says what produced the bytes."""
    try:
        from process_utils import hidden_run
    except ImportError:  # pragma: no cover - process_utils is always on the path
        return None
    result = hidden_run(["ffmpeg", "-version"], timeout=60)
    if result.returncode != 0 or not result.stdout:
        return None
    first = str(result.stdout).splitlines()[0]
    return first.split(" ")[2] if len(first.split(" ")) > 2 else first.strip() or None


def _command_fingerprint(command: List[str]) -> str:
    canonical = json.dumps(command, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _has_audio_stream(path: Path) -> Optional[bool]:
    payload = ffprobe_json(path)
    streams = payload.get("streams") or []
    return any(s.get("codec_type") == "audio" for s in streams)


def _strip_audio(source: Path, destination: Path) -> List[str]:
    """Remove every audio stream, copying video streams without re-encoding.

    ``-c:v copy`` matters: re-encoding a generated shot to drop a track would
    change the picture, so a "MUTE" would silently degrade the visuals. Copying
    the video stream and dropping only audio keeps the derived asset faithful to
    the provider's render.
    """
    from process_utils import hidden_run

    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-y", "-v", "error", "-nostdin",
        "-i", str(source),
        "-map", "0:v:0",
        "-c:v", "copy",
        "-an",
        str(destination),
    ]
    result = hidden_run(command, timeout=600)
    if result.returncode != 0 or not destination.is_file():
        raise AudioPolicyError(
            "removing the audio stream failed: "
            f"{(result.stderr or '').strip()[-300:] or 'ffmpeg reported errors'}"
        )
    return command


@dataclass
class AudioPolicyApplication:
    """What applying a policy produced, and what composition must do next."""

    policy: str
    #: The asset composition should use. The original for ``KEEP``; the derived
    #: file for ``MUTE`` and ``REPLACE``.
    output_path: str
    #: True when bytes changed. ``False`` for ``KEEP``.
    derived: bool
    #: Set when composition must mux a deterministic narration track. The
    #: narration is deliberately *not* written here.
    replacement_narration_required: bool = False
    narration_source: Optional[str] = None
    #: What was actually verified about the output's streams.
    observed_audio_stream: Optional[bool] = None
    receipt_path: Optional[str] = None
    transform_receipt: Optional[TransformReceipt] = None
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "policy": self.policy,
            "output_path": self.output_path,
            "derived": self.derived,
            "replacement_narration_required": self.replacement_narration_required,
            "narration_source": self.narration_source,
            "observed_audio_stream": self.observed_audio_stream,
            "receipt_path": self.receipt_path,
            "notes": list(self.notes),
        }


def apply_audio_policy(
    *,
    source_video: Path,
    policy: str,
    output_dir: Path,
    source_receipt_ref: Optional[str] = None,
    source_fingerprint: Optional[str] = None,
    narration_source: Optional[str] = None,
    created_at: Optional[str] = None,
) -> AudioPolicyApplication:
    """Apply one audio policy, producing a derived asset when bytes must change.

    Args:
        source_video: the immutable provider-generated shot.
        policy: ``KEEP``, ``MUTE`` or ``REPLACE``.
        output_dir: where a derived asset is written. The source is never
            written to.
        source_receipt_ref: the provider generation receipt, recorded so
            provenance stays traversable.
        source_fingerprint: the provider request fingerprint, same reason.
        narration_source: the deterministic narration track composition will mux.
            Recorded on the application when ``REPLACE`` asks for it; never muxed
            here, so this step cannot produce a silent mix.
        created_at: caller-supplied timestamp, so a test can produce a
            byte-stable receipt.

    Returns:
        An :class:`AudioPolicyApplication`. The original file is never modified.

    Raises:
        ValueError: the policy is not one of the three.
        AudioPolicyError: the transform could not be completed, or its result did
            not satisfy the policy's postcondition.
    """
    if policy not in AudioPolicy.ALL:
        raise ValueError(
            f"unknown audio policy {policy!r}; expected one of "
            f"{', '.join(AudioPolicy.ALL)}"
        )
    source = Path(source_video)
    if not source.is_file():
        raise AudioPolicyError(f"source video does not exist: {source}")

    source_sha = sha256_file(source)

    if policy == AudioPolicy.KEEP:
        # Reused unchanged. No copy, no derived asset, no transform receipt --
        # bytes that did not move must not acquire provenance implying they did.
        observed = _has_audio_stream(source)
        application = AudioPolicyApplication(
            policy=policy,
            output_path=str(source),
            derived=False,
            observed_audio_stream=observed,
        )
        if observed is False:
            application.notes.append(
                "KEEP was requested but the source carries no audio stream, so "
                "nothing was kept. Recorded rather than assumed."
            )
        return application

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / f"{source.stem}-{policy.lower()}{source.suffix or '.mp4'}"

    command = _strip_audio(source, destination)

    # Verify the postcondition instead of trusting the command.
    observed = _has_audio_stream(destination)
    if observed is not False:
        raise AudioPolicyError(
            f"{policy} requires the derived asset to carry no audio, but the "
            f"output reports audio_stream={observed}. Refusing to hand back "
            f"something that does not satisfy the policy."
        )

    receipt = TransformReceipt(
        transform_type=f"audio_policy_{policy.lower()}",
        source_asset_sha256=source_sha,
        source_receipt_ref=source_receipt_ref,
        source_fingerprint=source_fingerprint,
        output_path=str(destination),
        output_sha256=sha256_file(destination),
        parameters={
            "policy": policy,
            "drop_all_audio": True,
            "video_stream_copied": True,
            "replacement_narration_required": policy == AudioPolicy.REPLACE,
        },
        tool_version=_ffmpeg_version(),
        command_fingerprint=_command_fingerprint(command),
        created_at=created_at,
    )
    receipt_path = destination.with_name(destination.name + TRANSFORM_SUFFIX)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt.as_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if not receipt_path.is_file():
        raise AudioPolicyError(
            "the transform receipt could not be written, so the derived asset is "
            "not usable. Bytes without a provenance record are the failure this "
            "layer exists to prevent."
        )

    application = AudioPolicyApplication(
        policy=policy,
        output_path=str(destination),
        derived=True,
        replacement_narration_required=(policy == AudioPolicy.REPLACE),
        narration_source=narration_source if policy == AudioPolicy.REPLACE else None,
        observed_audio_stream=observed,
        receipt_path=str(receipt_path),
        transform_receipt=receipt,
    )
    if policy == AudioPolicy.REPLACE and not narration_source:
        application.notes.append(
            "REPLACE requires a deterministic narration track, but no "
            "narration_source was supplied. The derived asset still carries no "
            "H3 audio, so nothing competes; composition must supply narration "
            "before this shot is publishable."
        )
    return application
