"""Validate an H3 request completely, locally, before any billing read.

Why this module exists
----------------------
Every rule below is documented by the provider, and every one of them is cheap to
check. Checking them here means a typo costs nothing: no billing read, no task
creation, no quota. Discovering them at the API means a rejected request *after*
the gate has already been consulted, and possibly after a task has been paid for.

All limits verified 2026-10-05 against the documented create-task schema; see
``research/providers/minimax-h3-official-reality.md``.

The rules
---------
**Models**: ``MiniMax-H3`` and ``MiniMax-H3-Max``.

**Resolution**: the enum is ``480P | 768P | 2K``, but availability is
model-dependent. ``MiniMax-H3`` offers ``768P`` and ``2K``. ``MiniMax-H3-Max``
offers ``480P`` and ``768P`` and **does not support ``2K``**.

**Duration**: integer, required. ``MiniMax-H3`` accepts 4\u201315.
``MiniMax-H3-Max`` accepts 5\u201315 and explicitly **not** 4.

**Ratio**: ``adaptive``, ``21:9``, ``16:9``, ``4:3``, ``1:1``, ``3:4``, ``9:16``.
Mode-specific rules:

- **t2va** (text only): ratio is **required** and **cannot be** ``adaptive``.
- **i2va** (a first or last frame): ratio is **always** ``adaptive``; any other
  value is accepted by the API but **ignored**, so ContentOps sends ``adaptive``
  rather than pretending a ratio was honoured.
- **r2va** (reference roles): ratio optional, defaults to ``adaptive``.

**Mutual exclusion**: reference roles and frame roles cannot appear in the same
request. Mixing them is a caller bug, not something to send and let the API reject.

**Prompt**: exactly one non-empty ``text`` item, \u2264 7000 characters.

**References**: \u2264 9 images (\u2264 30 MB each, 256\u20135760 px, aspect 0.4\u20132.5),
\u2264 3 videos (\u2264 50 MB each, per clip 2\u201315 s, total \u2264 15 s, 256\u20135760 px,
aspect 0.4\u20132.5, 23.976\u201360 fps), \u2264 3 audio (\u2264 15 MB each, per clip 2\u201315 s,
total \u2264 15 s), \u2264 12 files in total.

**Frame roles**: at most one ``first_frame`` and one ``last_frame``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from contentops.media.reference_media import (
    ReferenceMediaError,
    ValidatedReference,
    detect_reference_mime,
)
from contentops.media.video_contract import AUDIO_POLICIES, AUDIO_POLICY_REPLACE

__all__ = [
    "ALLOWED_EXTRA_KEYS",
    "EXTRA_SUPPORTED_MODELS",
    "H3_MAX_DURATION_MAX",
    "H3_MAX_DURATION_MIN",
    "H3_DURATION_MAX",
    "H3_DURATION_MIN",
    "H3_MAX_REFERENCE_AUDIO",
    "H3_MAX_REFERENCE_IMAGES",
    "H3_MAX_REFERENCE_VIDEOS",
    "H3_MAX_TOTAL_FILES",
    "H3_MODELS",
    "H3_RATIOS",
    "H3_REQUEST_BODY_MAX_BYTES",
    "H3_RESOLUTIONS",
    "MODEL_DURATIONS",
    "MODEL_RESOLUTIONS",
    "MODEL_TEST_DURATION",
    "PROMPT_EXPANSION_MODES",
    "RequestRejected",
    "ValidatedH3Request",
    "validate_h3_request",
]

#: Documented model identifiers.
H3_MODELS: Tuple[str, ...] = ("MiniMax-H3", "MiniMax-H3-Max")

#: Resolution enum, and what each model actually accepts.
H3_RESOLUTIONS: Tuple[str, ...] = ("480P", "768P", "2K")
MODEL_RESOLUTIONS: Dict[str, Tuple[str, ...]] = {
    "MiniMax-H3": ("768P", "2K"),
    "MiniMax-H3-Max": ("480P", "768P"),
}
#: The provider's own default, recorded so the receipt can state what was implied.
MODEL_DEFAULT_RESOLUTION: Dict[str, str] = {
    "MiniMax-H3": "768P",
    "MiniMax-H3-Max": "768P",
}

#: Duration ranges, integers only.
H3_DURATION_MIN, H3_DURATION_MAX = 4, 15
H3_MAX_DURATION_MIN, H3_MAX_DURATION_MAX = 5, 15
MODEL_DURATIONS: Dict[str, Tuple[int, int]] = {
    "MiniMax-H3": (H3_DURATION_MIN, H3_DURATION_MAX),
    "MiniMax-H3-Max": (H3_MAX_DURATION_MIN, H3_MAX_DURATION_MAX),
}
#: Test default per model: the provider minimum, and nothing shorter.
MODEL_TEST_DURATION: Dict[str, int] = {
    "MiniMax-H3": H3_DURATION_MIN,
    "MiniMax-H3-Max": H3_MAX_DURATION_MIN,
}

H3_RATIOS: Tuple[str, ...] = (
    "adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16",
)
CONCRETE_RATIOS: Tuple[str, ...] = tuple(r for r in H3_RATIOS if r != "adaptive")

#: Modes.
MODES: Tuple[str, ...] = ("T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA")
FRAME_MODES: Tuple[str, ...] = ("I2VA", "FL2VA", "L2VA")
REFERENCE_MODE = "Ref2VA"
TEXT_ONLY_MODE = "T2VA"

#: Prompt cap, per ``text`` item.
MAX_PROMPT_CHARACTERS = 7000

#: Reference limits.
H3_MAX_REFERENCE_IMAGES = 9
H3_MAX_REFERENCE_VIDEOS = 3
H3_MAX_REFERENCE_AUDIO = 3
H3_MAX_TOTAL_FILES = 12
H3_MAX_FIRST_FRAMES = 1
H3_MAX_LAST_FRAMES = 1

#: Per-file size caps, bytes.
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
MAX_AUDIO_BYTES = 15 * 1024 * 1024
H3_REQUEST_BODY_MAX_BYTES = 64 * 1024 * 1024

#: Dimension and aspect limits for image and video inputs.
MIN_INPUT_PIXELS = 256
MAX_INPUT_PIXELS = 5760
MIN_INPUT_ASPECT = 0.4
MAX_INPUT_ASPECT = 2.5
MIN_REFERENCE_CLIP_SECONDS = 2
MAX_REFERENCE_CLIP_SECONDS = 15
MAX_REFERENCE_TOTAL_SECONDS = 15
MIN_REFERENCE_FPS = 23.976
MAX_REFERENCE_FPS = 60

#: Accepted image containers for references. Detection is by content, not by
#: suffix; this tuple only bounds what the operator is expected to supply and
#: produces a clearer message than a container error would.
REFERENCE_IMAGE_SUFFIXES: Tuple[str, ...] = (
    ".jpg", ".jpeg", ".png", ".webp",
)
REFERENCE_VIDEO_SUFFIXES: Tuple[str, ...] = (".mp4", ".mov")
REFERENCE_AUDIO_SUFFIXES: Tuple[str, ...] = (".wav", ".mp3")

#: The documented input set also lists HEIC/HEIF. They are **not** accepted here:
#: no reliable way exists in this environment to verify what a ``.heic`` file
#: actually contains, and declaring a subtype from the suffix is precisely the
#: behaviour this repository forbids. See ``reference_media`` for the full
#: reasoning. Callers should convert to PNG, JPEG or WEBP.
REFERENCE_IMAGE_SUFFIXES_UNSUPPORTED: Tuple[str, ...] = (".heic", ".heif")

#: The only documented generation option, and only on ``MiniMax-H3-Max``. The API
#: sets ``additionalProperties: false`` on ``extra``, so an invented key is a 400
#: whose message names the field rather than the mistake.
PROMPT_EXPANSION_MODES: Tuple[str, ...] = ("disabled", "balanced", "quality")
PROMPT_EXPANSION_DEFAULT = "balanced"
ALLOWED_EXTRA_KEYS: Tuple[str, ...] = ("prompt_expansion_mode",)
EXTRA_SUPPORTED_MODELS: Tuple[str, ...] = ("MiniMax-H3-Max",)


class RequestRejected(ValueError):
    """The request is invalid locally.

    Raised **before** the billing gate and before any task creation, so an invalid
    request costs nothing.
    """


@dataclass
class ValidatedH3Request:
    """A request that has passed every local rule, plus the effective ratio."""

    model: str
    mode: str
    duration_s: int
    resolution: str
    ratio: str
    prompt: str
    first_frame: Optional[Path]
    last_frame: Optional[Path]
    reference_images: List[Path] = field(default_factory=list)
    reference_videos: List[Path] = field(default_factory=list)
    reference_audio: List[Path] = field(default_factory=list)
    #: Each input with the media type actually detected from its content, in the
    #: order it will be sent. The transport consumes these rather than re-deriving
    #: a type from the file name, so there is exactly one media truth per reference.
    references: List[ValidatedReference] = field(default_factory=list)
    #: Generation-affecting options, validated against the documented closed set.
    extra: Dict[str, Any] = field(default_factory=dict)
    #: What will happen to the audio track the provider returns anyway. Validated
    #: locally, because a typo here must not cost a paid generation.
    audio_policy: str = AUDIO_POLICY_REPLACE
    #: True when the caller's ratio was replaced because the mode fixes it.
    ratio_was_coerced: bool = False

    @property
    def total_files(self) -> int:
        return (
            len(self.reference_images)
            + len(self.reference_videos)
            + len(self.reference_audio)
            + (1 if self.first_frame else 0)
            + (1 if self.last_frame else 0)
        )

    def summary(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "mode": self.mode,
            "duration_s": self.duration_s,
            "resolution": self.resolution,
            "ratio": self.ratio,
            "ratio_was_coerced": self.ratio_was_coerced,
            "extra": dict(self.extra),
            "reference_images": len(self.reference_images),
            "reference_videos": len(self.reference_videos),
            "reference_audio": len(self.reference_audio),
            "first_frame": self.first_frame.name if self.first_frame else None,
            "last_frame": self.last_frame.name if self.last_frame else None,
            "total_files": self.total_files,
        }


def _check_existing(path: Path, label: str) -> Path:
    if not path.is_file():
        raise RequestRejected(f"{label} does not exist or is not a file: {path}")
    size = path.stat().st_size
    if size == 0:
        raise RequestRejected(f"{label} is empty: {path}")
    return path


def _check_suffix(path: Path, allowed: Sequence[str], label: str) -> None:
    suffix = path.suffix.lower()
    if suffix not in allowed:
        raise RequestRejected(
            f"{label} {path.name} has unsupported format {suffix!r}; "
            f"accepted: {', '.join(allowed)}"
        )


def _detect_reference(
    path: Path, *, label: str, role_hint: str, role: str = ""
) -> ValidatedReference:
    """Detect the real media type of a reference, rewrapping refusals as rejections.

    Every failure becomes :class:`RequestRejected` so that a caller sees one
    exception type for "this request is invalid", raised in the free local phase
    before any billing read.
    """
    try:
        detected = detect_reference_mime(path, media_kind=role_hint)
    except ReferenceMediaError as exc:
        raise RequestRejected(f"{label} {path.name}: {exc}") from exc
    if not role:
        return detected
    return ValidatedReference(
        path=detected.path,
        role=role,
        media_kind=detected.media_kind,
        mime_type=detected.mime_type,
        detected_container=detected.detected_container,
        declared_extension=detected.declared_extension,
        extension_matches=detected.extension_matches,
    )


def _check_image_properties(path: Path, label: str) -> None:
    """Verify an image input's existence, size, dimensions and aspect.

    Separate from container detection on purpose. These are the documented
    *numeric* limits; the container is a separate question answered from the
    bytes. Keeping them apart means neither check can mask the other.
    """
    _check_existing(path, label)
    _check_suffix(path, REFERENCE_IMAGE_SUFFIXES, label)
    size = path.stat().st_size
    if size > MAX_IMAGE_BYTES:
        raise RequestRejected(
            f"{label} {path.name} is {size} bytes, above the {MAX_IMAGE_BYTES} "
            f"byte limit"
        )
    width, height = _image_dimensions(path, label)
    _check_dimensions(width, height, label)
    _check_aspect(width, height, label)


def _image_dimensions(path: Path, label: str) -> Tuple[int, int]:
    """Read image dimensions with whichever decoder is present."""
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        # Without Pillow, fall back to a header read for the common formats so
        # validation still refuses obviously invalid input.
        return _dimensions_from_header(path, label)
    try:
        with Image.open(path) as image:
            return int(image.size[0]), int(image.size[1])
    except Exception as exc:  # noqa: BLE001
        raise RequestRejected(
            f"{label} {path.name} could not be decoded: {type(exc).__name__}"
        ) from exc


def _dimensions_from_header(path: Path, label: str) -> Tuple[int, int]:
    data = path.read_bytes()[:65536]
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return (
            int.from_bytes(data[16:20], "big"),
            int.from_bytes(data[20:24], "big"),
        )
    if data[:3] == b"\xff\xd8\xff":
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                height = int.from_bytes(data[index + 5 : index + 7], "big")
                width = int.from_bytes(data[index + 7 : index + 9], "big")
                return width, height
            if index + 4 > len(data):
                break
            index += 2 + int.from_bytes(data[index + 2 : index + 4], "big")
    raise RequestRejected(
        f"{label} {path.name} could not be measured: no decoder available and "
        f"the header is not a recognised PNG or JPEG"
    )


def _check_dimensions(width: int, height: int, label: str) -> None:
    for name, value in (("width", width), ("height", height)):
        if value < MIN_INPUT_PIXELS or value > MAX_INPUT_PIXELS:
            raise RequestRejected(
                f"{label} {name} {value} is outside the documented range "
                f"[{MIN_INPUT_PIXELS}, {MAX_INPUT_PIXELS}]"
            )


def _check_aspect(width: int, height: int, label: str) -> None:
    if height <= 0:
        raise RequestRejected(f"{label} has a zero height")
    aspect = width / height
    if aspect < MIN_INPUT_ASPECT or aspect > MAX_INPUT_ASPECT:
        raise RequestRejected(
            f"{label} aspect ratio {aspect:.4f} is outside the documented range "
            f"[{MIN_INPUT_ASPECT}, {MAX_INPUT_ASPECT}]"
        )


def _probe_media(path: Path, label: str) -> Dict[str, Any]:
    """Read container/codec facts for a reference file using ffprobe."""
    import json as _json

    from contentops.media.transport import ffprobe_json  # noqa: PLC0415

    try:
        payload = ffprobe_json(path)
    except Exception as exc:  # noqa: BLE001
        raise RequestRejected(
            f"{label} {path.name} could not be probed: {exc}"
        ) from exc
    streams = payload.get("streams") or []
    if not streams:
        raise RequestRejected(f"{label} {path.name} contains no media streams")
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = payload.get("format", {}).get("duration")
    return {
        "video": video,
        "audio": audio,
        "duration_s": float(duration) if duration not in (None, "N/A") else None,
    }


def _check_extra(model: str, extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate the documented generation options, which form a closed set.

    ``extra`` exists only on ``MiniMax-H3-Max`` and its schema is
    ``additionalProperties: false``. Checking the closed set locally turns an
    invented key from a 400 after the billing gate into a free, explanatory error.

    Returns the options to send, omitting the value when the caller left it at the
    documented default so the request stays as small as the provider allows.
    """
    if not extra:
        return {}
    if model not in EXTRA_SUPPORTED_MODELS:
        raise RequestRejected(
            f"{model} documents no generation options; extra keys are refused "
            f"rather than sent and rejected by the provider"
        )
    unknown = sorted(set(extra) - set(ALLOWED_EXTRA_KEYS))
    if unknown:
        raise RequestRejected(
            f"undocumented generation option(s): {', '.join(unknown)}; the "
            f"documented set is {', '.join(ALLOWED_EXTRA_KEYS)}"
        )
    checked: Dict[str, Any] = {}
    for key, value in extra.items():
        if key == "prompt_expansion_mode":
            if not isinstance(value, str) or value not in PROMPT_EXPANSION_MODES:
                raise RequestRejected(
                    f"prompt_expansion_mode must be one of "
                    f"{', '.join(PROMPT_EXPANSION_MODES)}, got {value!r}"
                )
            if value != PROMPT_EXPANSION_DEFAULT:
                checked[key] = value
    return checked


def _check_encoded_body_size(paths: Sequence[Path]) -> None:
    """Refuse a request whose encoded references would exceed the body cap.

    The documented per-file limits and the 64 MB request cap are independent, and
    Base64 inflates by about a third, so nine legal 30 MB images are a request the
    API will reject on size even though each file passed its own check. Catching it
    locally is the difference between a free error and a refused billable call.

    Computed from file sizes rather than by encoding them: the data URI length is
    exactly ``4 * ceil(n / 3)`` plus a fixed header, so there is no reason to read
    300 MB of inputs to learn a number arithmetic already gives.
    """
    total = 0
    for path in paths:
        try:
            size = path.stat().st_size
        except OSError:
            # Existence and emptiness are already checked per file above.
            continue
        # Base64 emits four characters per three bytes, padded to a multiple of
        # four. The ``data:`` prefix is negligible against a 64 MB cap but is
        # counted so the arithmetic is an upper bound rather than an estimate.
        total += 4 * ((size + 2) // 3) + len(f"data:;base64,{path.name}")
    if total > H3_REQUEST_BODY_MAX_BYTES:
        raise RequestRejected(
            f"encoded references would be about {total} bytes, above the "
            f"documented {H3_REQUEST_BODY_MAX_BYTES} byte request body limit. "
            f"Base64 inflates by about a third; supply a public URL or use fewer "
            f"references."
        )


def validate_h3_request(
    *,
    model: str,
    mode: str,
    duration_s: int,
    resolution: str,
    ratio: Optional[str],
    prompt: str,
    first_frame: Optional[str] = None,
    last_frame: Optional[str] = None,
    reference_images: Sequence[str] = (),
    reference_videos: Sequence[str] = (),
    reference_audio: Sequence[str] = (),
    extra: Optional[Dict[str, Any]] = None,
    audio_policy: str = AUDIO_POLICY_REPLACE,
) -> ValidatedH3Request:
    """Validate everything locally. Raises :class:`RequestRejected` on any breach.

    The order matters: cheap string rules first, then file checks, so the error
    names the cheapest thing that is actually wrong.
    """
    # -- model, mode, resolution, duration, prompt -------------------------
    if model not in H3_MODELS:
        raise RequestRejected(
            f"unknown model {model!r}; supported: {', '.join(H3_MODELS)}"
        )
    if mode not in MODES:
        raise RequestRejected(
            f"unknown mode {mode!r}; supported: {', '.join(MODES)}"
        )

    allowed_resolutions = MODEL_RESOLUTIONS[model]
    if resolution not in H3_RESOLUTIONS:
        raise RequestRejected(
            f"unknown resolution {resolution!r}; the documented enum is "
            f"{', '.join(H3_RESOLUTIONS)}"
        )
    if resolution not in allowed_resolutions:
        raise RequestRejected(
            f"{model} does not support {resolution}; it offers "
            f"{', '.join(allowed_resolutions)}"
        )

    low, high = MODEL_DURATIONS[model]
    if isinstance(duration_s, bool) or not isinstance(duration_s, int):
        raise RequestRejected(
            f"duration must be an integer number of seconds, got "
            f"{duration_s!r} ({type(duration_s).__name__})"
        )
    if duration_s < low or duration_s > high:
        raise RequestRejected(
            f"{model} accepts {low}-{high} second durations, got {duration_s}"
        )

    if not prompt or not prompt.strip():
        raise RequestRejected("the prompt must not be empty; every request needs one text item")
    if len(prompt) > MAX_PROMPT_CHARACTERS:
        raise RequestRejected(
            f"prompt is {len(prompt)} characters, above the documented limit of "
            f"{MAX_PROMPT_CHARACTERS}"
        )

    checked_extra = _check_extra(model, extra)

    # The audio policy is a caller-chosen field, not something the provider sends,
    # so a typo here would otherwise survive until post-generation QC — after the
    # weekly quota has already been spent. It is a non-generation option, so it
    # must fail for free like any other invalid request field.
    if audio_policy not in AUDIO_POLICIES:
        raise RequestRejected(
            f"unknown audio_policy {audio_policy!r}; expected one of "
            f"{', '.join(AUDIO_POLICIES)}. Audio is a non-generation option, so it "
            f"is validated here rather than after the task has been paid for."
        )

    # -- reference counts -------------------------------------------------
    images = [Path(p) for p in reference_images]
    videos = [Path(p) for p in reference_videos]
    audio = [Path(p) for p in reference_audio]
    first = Path(first_frame) if first_frame else None
    last = Path(last_frame) if last_frame else None

    if len(images) > H3_MAX_REFERENCE_IMAGES:
        raise RequestRejected(
            f"{len(images)} reference images exceeds the limit of "
            f"{H3_MAX_REFERENCE_IMAGES}"
        )
    if len(videos) > H3_MAX_REFERENCE_VIDEOS:
        raise RequestRejected(
            f"{len(videos)} reference videos exceeds the limit of "
            f"{H3_MAX_REFERENCE_VIDEOS}"
        )
    if len(audio) > H3_MAX_REFERENCE_AUDIO:
        raise RequestRejected(
            f"{len(audio)} reference audio clips exceeds the limit of "
            f"{H3_MAX_REFERENCE_AUDIO}"
        )

    total_files = len(images) + len(videos) + len(audio) + (1 if first else 0) + (1 if last else 0)
    if total_files > H3_MAX_TOTAL_FILES:
        raise RequestRejected(
            f"{total_files} input files exceeds the documented total of "
            f"{H3_MAX_TOTAL_FILES}"
        )

    has_references = bool(images or videos or audio)
    has_frames = bool(first or last)

    # -- mode / content consistency ---------------------------------------
    if mode == TEXT_ONLY_MODE and (has_references or has_frames):
        raise RequestRejected(
            f"{TEXT_ONLY_MODE} accepts a text item only, but "
            f"{'references' if has_references else 'frames'} were supplied"
        )
    if mode in FRAME_MODES and has_references:
        raise RequestRejected(
            f"{mode} uses frame roles; reference images, videos and audio cannot "
            f"be mixed with them in one request"
        )
    if mode == REFERENCE_MODE and has_frames:
        raise RequestRejected(
            f"{REFERENCE_MODE} uses reference roles; first_frame and last_frame "
            f"cannot be mixed with them in one request"
        )
    if mode == "I2VA" and not has_frames:
        raise RequestRejected(f"{mode} requires a first frame")
    if mode == "FL2VA" and not (first and last):
        raise RequestRejected(f"{mode} requires both a first frame and a last frame")
    if mode == "L2VA" and not last:
        raise RequestRejected(f"{mode} requires a last frame")
    if mode == REFERENCE_MODE and not has_references:
        raise RequestRejected(f"{mode} requires at least one reference asset")
    if first and not last and mode not in FRAME_MODES:
        raise RequestRejected("a first frame was supplied for a mode that cannot use it")

    # -- ratio ------------------------------------------------------------
    coerced = False
    if mode == TEXT_ONLY_MODE:
        # Documented: required, and cannot be adaptive.
        if not ratio:
            raise RequestRejected(
                f"{TEXT_ONLY_MODE} requires an explicit ratio; it cannot be "
                f"omitted or set to 'adaptive'. Choose one of "
                f"{', '.join(CONCRETE_RATIOS)}"
            )
        if ratio == "adaptive":
            raise RequestRejected(
                f"{TEXT_ONLY_MODE} cannot use 'adaptive'; choose one of "
                f"{', '.join(CONCRETE_RATIOS)}"
            )
    elif mode in FRAME_MODES:
        # Documented: the ratio comes from the input image and is always adaptive.
        if ratio and ratio != "adaptive":
            coerced = True
        ratio = "adaptive"
    else:
        if ratio is None:
            ratio = "adaptive"
        elif ratio not in H3_RATIOS:
            raise RequestRejected(
                f"unknown ratio {ratio!r}; supported: {', '.join(H3_RATIOS)}"
            )

    if ratio not in H3_RATIOS:
        raise RequestRejected(
            f"unknown ratio {ratio!r}; supported: {', '.join(H3_RATIOS)}"
        )

    # -- reference files ---------------------------------------------------
    # Detected once, here, and reused by the transport. One media truth per
    # reference: the type that was verified is the type that is declared.
    references: List[ValidatedReference] = []

    for candidate in images:
        _check_image_properties(candidate, "reference image")
        references.append(
            _detect_reference(candidate, label="reference image", role_hint="image",
                              role="reference_image")
        )
    if first is not None:
        _check_image_properties(first, "frame image")
        references.append(
            _detect_reference(first, label="frame image", role_hint="image",
                              role="first_frame")
        )
    if last is not None:
        _check_image_properties(last, "frame image")
        references.append(
            _detect_reference(last, label="frame image", role_hint="image",
                              role="last_frame")
        )

    total_reference_seconds = 0.0
    for candidate in videos:
        _check_existing(candidate, "reference video")
        _check_suffix(candidate, REFERENCE_VIDEO_SUFFIXES, "reference video")
        size = candidate.stat().st_size
        if size > MAX_VIDEO_BYTES:
            raise RequestRejected(
                f"reference video {candidate.name} is {size} bytes, above the "
                f"{MAX_VIDEO_BYTES} byte limit"
            )
        probed = _probe_media(candidate, "reference video")
        references.append(
            _detect_reference(candidate, label="reference video",
                              role_hint="video", role="reference_video")
        )
        stream = probed["video"] or {}
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        _check_dimensions(width, height, f"reference video {candidate.name}")
        _check_aspect(width, height, f"reference video {candidate.name}")
        rate = stream.get("avg_frame_rate") or "0/1"
        try:
            numerator, _, denominator = rate.partition("/")
            fps = float(numerator) / float(denominator or 1)
        except (TypeError, ValueError, ZeroDivisionError):
            fps = 0.0
        if fps and (fps < MIN_REFERENCE_FPS - 0.01 or fps > MAX_REFERENCE_FPS + 0.01):
            raise RequestRejected(
                f"reference video {candidate.name} is {fps:.3f} fps, outside the "
                f"documented range [{MIN_REFERENCE_FPS}, {MAX_REFERENCE_FPS}]"
            )
        seconds = probed["duration_s"]
        if seconds is None:
            raise RequestRejected(
                f"reference video {candidate.name} has no readable duration"
            )
        if seconds < MIN_REFERENCE_CLIP_SECONDS or seconds > MAX_REFERENCE_CLIP_SECONDS:
            raise RequestRejected(
                f"reference video {candidate.name} is {seconds:.2f}s, outside "
                f"the documented per-clip range "
                f"[{MIN_REFERENCE_CLIP_SECONDS}, {MAX_REFERENCE_CLIP_SECONDS}]"
            )
        total_reference_seconds += seconds

    for candidate in audio:
        _check_existing(candidate, "reference audio")
        _check_suffix(candidate, REFERENCE_AUDIO_SUFFIXES, "reference audio")
        size = candidate.stat().st_size
        if size > MAX_AUDIO_BYTES:
            raise RequestRejected(
                f"reference audio {candidate.name} is {size} bytes, above the "
                f"{MAX_AUDIO_BYTES} byte limit"
            )
        probed = _probe_media(candidate, "reference audio")
        references.append(
            _detect_reference(candidate, label="reference audio",
                              role_hint="audio", role="reference_audio")
        )
        seconds = probed["duration_s"]
        if seconds is None:
            raise RequestRejected(
                f"reference audio {candidate.name} has no readable duration"
            )
        if seconds < MIN_REFERENCE_CLIP_SECONDS or seconds > MAX_REFERENCE_CLIP_SECONDS:
            raise RequestRejected(
                f"reference audio {candidate.name} is {seconds:.2f}s, outside "
                f"the documented per-clip range "
                f"[{MIN_REFERENCE_CLIP_SECONDS}, {MAX_REFERENCE_CLIP_SECONDS}]"
            )
        total_reference_seconds += seconds

    if total_reference_seconds > MAX_REFERENCE_TOTAL_SECONDS + 0.01:
        raise RequestRejected(
            f"total reference duration {total_reference_seconds:.2f}s exceeds "
            f"the documented total of {MAX_REFERENCE_TOTAL_SECONDS}s"
        )

    # Individually legal inputs can still breach the combined body cap, because the
    # data URI representation inflates by roughly a third. Measured rather than
    # estimated, and refused here so it costs nothing.
    _check_encoded_body_size(
        images + videos + audio + ([first] if first else []) + ([last] if last else [])
    )

    return ValidatedH3Request(
        model=model,
        mode=mode,
        duration_s=duration_s,
        resolution=resolution,
        ratio=ratio,
        prompt=prompt,
        first_frame=first,
        last_frame=last,
        reference_images=images,
        reference_videos=videos,
        reference_audio=audio,
        references=references,
        extra=checked_extra,
        audio_policy=audio_policy,
        ratio_was_coerced=coerced,
    )