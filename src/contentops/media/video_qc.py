"""Video technical QC: measured facts only.

What this may conclude
----------------------
That a file is an MP4, decodes end to end, runs 4.4 s at 768x1344 and 24 fps,
carries an AAC track, has no black run longer than half a second, and does not
freeze. It may **not** conclude that a shot is cinematic, beautiful or
publishable. Those are human judgements, and an automated gate that reports
"publishable" teaches the pipeline to trust itself.

Tolerances, and why they exist
------------------------------
M2.0 measured real H3 output against its own request:

| Property | Requested | Delivered |
|---|---|---|
| duration | 4.000 s | **4.458 s** |
| dimensions (9:16) | 768x1360 | **768x1344** |
| audio | not requested | **AAC present** |

Every one of those would fail an equality check, and all three are normal
provider behaviour. So duration and aspect are compared with documented
thresholds, and the *requested and actual values are both recorded* so the
deviation stays visible rather than being absorbed into a pass.

Black frames
------------
A frame is black when its mean luma is below ``BLACK_FRAME_LUMA_MAX`` and its
luma spread is below ``BLACK_FRAME_SPREAD_MAX``. Both are needed: a dark but
detailed shot is not a black frame.

An **intentional** short fade must not be failed merely because one frame is dark,
so a black run is only a failure past ``BLACK_RUN_MAX_SECONDS``, and the measured
values are reported either way.

Freeze / stall
--------------
Consecutive frames are compared by mean absolute difference on a downscaled
luma image. A run whose per-frame difference stays below
``FREEZE_FRAME_DIFF_MAX`` for longer than ``FREEZE_RUN_MAX_SECONDS`` is a stall.
The threshold is duration-aware: an intentionally static composition is not
automatically defective.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

__all__ = [
    "ASPECT_TOLERANCE",
    "AudioPolicy",
    "BLACK_FRAME_LUMA_MAX",
    "BLACK_FRAME_SPREAD_MAX",
    "BLACK_RUN_MAX_SECONDS",
    "DURATION_TOLERANCE_SECONDS",
    "FREEZE_FRAME_DIFF_MAX",
    "FREEZE_RUN_MAX_SECONDS",
    "HAVE_FFMPEG",
    "HAVE_FFPROBE",
    "MIN_OUTPUT_BYTES",
    "CONTAINER_PREFERENCE",
    "RESOLUTION_SHORT_EDGE_BANDS",
    "VideoTechnicalQC",
    "resolution_label_for",
    "measure_video",
    "technical_video_qc",
]

HAVE_FFPROBE = bool(shutil.which("ffprobe"))
HAVE_FFMPEG = bool(shutil.which("ffmpeg"))

#: A generated clip smaller than this is a truncated response, not a render.
MIN_OUTPUT_BYTES = 1024

#: Duration is compared with a tolerance, never for equality. M2.0 measured a
#: 4.000 s request delivered as 4.458 s.
DURATION_TOLERANCE_SECONDS = 1.0

#: Aspect ratio tolerance. M2.0 measured 9:16 requested and 768x1344 delivered,
#: i.e. 0.5647 against 0.5625. Exact equality would reject correct output.
ASPECT_TOLERANCE = 0.02

BLACK_FRAME_LUMA_MAX = 16.0
BLACK_FRAME_SPREAD_MAX = 6.0
#: Below this a black run is an intentional fade rather than a defect.
BLACK_RUN_MAX_SECONDS = 0.5

#: A frame counts as "not moving" when its mean absolute difference from the
#: previous frame is at or below this, on a 0..1 scale.
#:
#: Calibrated by measurement, not guesswork. A 320x568 h264 clip of genuinely
#: moving test content measures a mean per-frame difference around 0.008; a
#: genuinely frozen clip measures exactly 0.0. The threshold therefore sits an
#: order of magnitude below real motion and just above numerical noise. The first
#: value used here, 0.35, was forty times too high and flagged healthy footage as
#: stalled, which is why it is written down as measured rather than chosen.
FREEZE_FRAME_DIFF_MAX = 0.002
#: Duration-aware: a static composition held for a second is not a stall.
FREEZE_RUN_MAX_SECONDS = 1.5

#: Analysis resolution. Full-resolution frame differencing is slow and no more
#: informative than a grid for detecting a frozen render.
ANALYSIS_WIDTH = 160
#: Upper bound on sampled frames, so a long clip stays cheap.
MAX_ANALYSIS_FRAMES = 240
#: Floor on the sampling interval. Must be finer than the freeze threshold, or a
#: frozen run cannot be measured at all.
MIN_SAMPLE_INTERVAL_SECONDS = 0.2


class AudioPolicy:
    """Re-exported so QC callers need only import this module."""

    KEEP = "KEEP"
    MUTE = "MUTE"
    REPLACE = "REPLACE"
    ALL = (KEEP, MUTE, REPLACE)


@dataclass
class VideoTechnicalQC:
    """Measured facts about one video file."""

    approved: bool = False
    reasons: List[str] = field(default_factory=list)
    container: Optional[str] = None
    codec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_s: Optional[float] = None
    fps: Optional[float] = None
    has_audio: bool = False
    audio_codec: Optional[str] = None
    file_bytes: int = 0
    aspect_ratio: Optional[float] = None
    decodable: bool = False
    #: Informational observations that are **not** failures. Kept separate from
    #: ``reasons`` so a note can never quietly turn ``approved`` false.
    notes: List[str] = field(default_factory=list)
    longest_black_run_s: Optional[float] = None
    black_frame_count: int = 0
    longest_freeze_run_s: Optional[float] = None
    max_frame_diff: Optional[float] = None
    mean_frame_diff: Optional[float] = None
    analysed_frames: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "reasons": list(self.reasons),
            "container": self.container,
            "codec": self.codec,
            "width": self.width,
            "height": self.height,
            "duration_s": self.duration_s,
            "fps": self.fps,
            "has_audio": self.has_audio,
            "audio_codec": self.audio_codec,
            "file_bytes": self.file_bytes,
            "aspect_ratio": self.aspect_ratio,
            "notes": list(self.notes),
            "decodable": self.decodable,
            "longest_black_run_s": self.longest_black_run_s,
            "black_frame_count": self.black_frame_count,
            "longest_freeze_run_s": self.longest_freeze_run_s,
            "max_frame_diff": self.max_frame_diff,
            "mean_frame_diff": self.mean_frame_diff,
            "analysed_frames": self.analysed_frames,
        }


def _run(
    command: List[str], timeout: int = 300, binary: bool = False
) -> subprocess.CompletedProcess:
    """Run a media tool with no console window.

    Routed through process_utils, because a direct subprocess here would both
    violate the repository's subprocess policy and flash a console on Windows.

    ``binary=True`` is required for ffmpeg ``rawvideo`` output: the default text
    mode would hand back a ``str``, and a frame buffer is bytes.
    """
    from process_utils import hidden_run  # noqa: PLC0415

    return hidden_run(command, timeout=timeout, text=not binary)


def _probe(path: Path) -> Dict[str, Any]:
    import json as _json  # noqa: PLC0415

    from contentops.media.transport import ffprobe_json  # noqa: PLC0415

    return ffprobe_json(path)


#: ffprobe reports a comma-separated family, not one container. An MP4 written by
#: ffmpeg comes back as "mov,mp4,m4a,3gp,3g2,mj2", so taking the first token would
#: label every MP4 as "mov". Preference order picks the container an operator would
#: name.
CONTAINER_PREFERENCE: tuple = ("mp4", "matroska", "webm", "mov", "mpegts", "avi", "quicktime")


def _normalise_container(format_name: Optional[str]) -> Optional[str]:
    """Pick the container a human would name from ffprobe's format family."""
    if not format_name:
        return None
    candidates = [token.strip().lower() for token in str(format_name).split(",") if token.strip()]
    for preferred in CONTAINER_PREFERENCE:
        if preferred in candidates:
            return preferred
    return candidates[0] if candidates else None


def _parse_rate(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    numerator, _, denominator = str(value).partition("/")
    try:
        den = float(denominator or 1)
        if den == 0:
            return None
        return float(numerator) / den
    except (TypeError, ValueError):
        return None


def measure_video(path) -> VideoTechnicalQC:
    """Measure one video file. Never raises for a merely-bad video.

    Every problem is reported in ``reasons`` so the caller gets one object
    describing everything wrong, rather than an exception on the first fault.
    """
    result = VideoTechnicalQC()
    target = Path(path)

    if not target.is_file():
        result.reasons.append(f"file does not exist: {target}")
        return result
    size = target.stat().st_size
    result.file_bytes = size
    if size == 0:
        result.reasons.append("file is empty")
        return result
    if size < MIN_OUTPUT_BYTES:
        result.reasons.append(
            f"file is only {size} bytes; treating it as a truncated response "
            f"rather than a render"
        )
    if not HAVE_FFPROBE:
        result.reasons.append("ffprobe is unavailable, so the file cannot be measured")
        return result

    try:
        payload = _probe(target)
    except Exception as exc:  # noqa: BLE001
        result.reasons.append(f"file could not be probed: {exc}")
        return result

    fmt = payload.get("format") or {}
    result.container = _normalise_container(fmt.get("format_name"))
    streams = payload.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        result.reasons.append("file contains no video stream")
        return result
    result.codec = video.get("codec_name")
    result.width = int(video.get("width") or 0)
    result.height = int(video.get("height") or 0)
    result.fps = _parse_rate(video.get("avg_frame_rate"))
    result.has_audio = audio is not None
    result.audio_codec = audio.get("codec_name") if audio else None
    duration = fmt.get("duration")
    try:
        result.duration_s = float(duration) if duration not in (None, "N/A") else None
    except (TypeError, ValueError):
        result.duration_s = None
    if result.duration_s is None and video.get("duration"):
        try:
            result.duration_s = float(video["duration"])
        except (TypeError, ValueError):
            result.duration_s = None
    if result.width and result.height:
        result.aspect_ratio = round(result.width / result.height, 6)
    if not result.width or not result.height:
        result.reasons.append("decoded video has a zero dimension")
        return result
    if result.duration_s is None:
        result.reasons.append("video duration could not be read")

    # Full decodability: decode the whole file, discarding output.
    if HAVE_FFMPEG:
        decoded = _run([
            "ffmpeg", "-v", "error", "-nostdin", "-i", str(target),
            "-f", "null", "-",
        ], timeout=600)
        result.decodable = decoded.returncode == 0
        if not result.decodable:
            detail = (decoded.stderr or "").strip()[-200:]
            result.reasons.append(
                f"video does not decode end to end: {detail or 'ffmpeg reported errors'}"
            )
    else:
        # Not a soft degradation. Without ffmpeg there is no end-to-end decode and
        # no black/freeze analysis, and a truncated clip with readable headers would
        # otherwise pass a gate that claims to have measured both. FAIL is FAIL: an
        # unverifiable file is not an approved file.
        result.reasons.append(
            "ffmpeg is unavailable, so end-to-end decodability and black/freeze "
            "analysis could not be measured; this file is unverified, not approved"
        )

    _analyse_frames(target, result)
    result.approved = not result.reasons
    return result


def _analyse_frames(path: Path, result: VideoTechnicalQC) -> None:
    """Sample frames and measure blackness and frame-to-frame difference."""
    if not HAVE_FFMPEG or not result.fps:
        return
    # Sample a few times per second, not a few times per clip. The earlier code
    # derived the stride from the frame count, which for a short clip collapsed to
    # one sample per *second* and made a multi-second freeze look like a fraction
    # of a second. A freeze threshold can only be trusted at a resolution finer
    # than the threshold itself.
    seconds_per_sample = max(
        MIN_SAMPLE_INTERVAL_SECONDS,
        (result.duration_s or 0) / max(1, MAX_ANALYSIS_FRAMES),
    )
    raw = _run([
        "ffmpeg", "-v", "error", "-nostdin", "-i", str(path),
        "-vf", f"fps=1/{seconds_per_sample:.4f},scale={ANALYSIS_WIDTH}:-2,format=gray",
        "-f", "rawvideo", "-",
    ], timeout=600, binary=True)
    if raw.returncode != 0 or not raw.stdout:
        return

    # scale=-2 keeps the height even; derive it so the buffer can be framed.
    height = _scaled_height(result)
    frame_bytes = ANALYSIS_WIDTH * max(2, height)
    frames = [
        raw.stdout[offset : offset + frame_bytes]
        for offset in range(0, len(raw.stdout) - frame_bytes + 1, frame_bytes)
    ]
    if not frames:
        return
    result.analysed_frames = len(frames)

    diffs: List[float] = []
    previous: Optional[bytes] = None
    black_run = 0.0
    longest_black = 0.0
    freeze_run = 0.0
    longest_freeze = 0.0

    for frame in frames:
        # rawvideo gray frames are bytes, so iteration yields ints already.
        mean = sum(frame) / len(frame)
        spread = max(frame) - min(frame)
        if mean <= BLACK_FRAME_LUMA_MAX and spread <= BLACK_FRAME_SPREAD_MAX:
            black_run += seconds_per_sample
            longest_black = max(longest_black, black_run)
            result.black_frame_count += 1
        else:
            black_run = 0.0

        if previous is not None:
            difference = sum(abs(a - b) for a, b in zip(frame, previous)) / len(frame)
            diffs.append(difference / 255.0)
            if difference / 255.0 <= FREEZE_FRAME_DIFF_MAX:
                freeze_run += seconds_per_sample
                longest_freeze = max(longest_freeze, freeze_run)
            else:
                freeze_run = 0.0
        previous = frame

    result.longest_black_run_s = round(longest_black, 4)
    result.longest_freeze_run_s = round(longest_freeze, 4)
    if diffs:
        result.mean_frame_diff = round(sum(diffs) / len(diffs), 6)
        result.max_frame_diff = round(max(diffs), 6)

    if longest_black > BLACK_RUN_MAX_SECONDS:
        result.reasons.append(
            f"black run of {longest_black:.2f}s exceeds "
            f"{BLACK_RUN_MAX_SECONDS}s; a short dark run would be an "
            f"intentional fade"
        )
    if longest_freeze > FREEZE_RUN_MAX_SECONDS:
        result.reasons.append(
            f"frozen run of {longest_freeze:.2f}s exceeds "
            f"{FREEZE_RUN_MAX_SECONDS}s; the render appears stalled"
        )


def _scaled_height(result: VideoTechnicalQC) -> int:
    if not result.width or not result.height:
        return 2
    scaled = int(round(result.height * ANALYSIS_WIDTH / result.width))
    return max(2, scaled - (scaled % 2))


def technical_video_qc(
    path,
    *,
    expected_duration_s: Optional[int] = None,
    duration_tolerance_s: float = DURATION_TOLERANCE_SECONDS,
    expected_ratio: Optional[str] = None,
    aspect_tolerance: float = ASPECT_TOLERANCE,
    expected_resolution: Optional[str] = None,
    audio_policy: str = AudioPolicy.REPLACE,
) -> VideoTechnicalQC:
    """Measure a video and check it against what was requested.

    Args:
        expected_duration_s: requested duration, compared with a tolerance.
        expected_ratio: requested ratio such as ``"9:16"``, compared with a
            tolerance. Never exact equality.
        expected_resolution: requested resolution label, recorded for comparison.
        audio_policy: what will happen to the generated audio track. Recorded in
            the result so the decision travels with the measurement.

    Returns:
        A :class:`VideoTechnicalQC`. ``approved`` means technically sound; it never
        means publishable.
    """
    result = measure_video(path)
    result.reasons = list(result.reasons)

    if expected_duration_s is not None and result.duration_s is not None:
        delta = abs(result.duration_s - float(expected_duration_s))
        if delta > duration_tolerance_s:
            result.reasons.append(
                f"duration {result.duration_s:.3f}s differs from the requested "
                f"{expected_duration_s}s by {delta:.3f}s, beyond the "
                f"{duration_tolerance_s}s tolerance"
            )

    if expected_ratio:
        wanted = _ratio_to_float(expected_ratio)
        if wanted and result.aspect_ratio:
            deviation = abs(result.aspect_ratio - wanted) / wanted
            if deviation > aspect_tolerance:
                result.reasons.append(
                    f"aspect ratio {result.aspect_ratio} deviates from the "
                    f"requested {expected_ratio} ({wanted}) by "
                    f"{deviation:.4f}, beyond the {aspect_tolerance} tolerance"
                )

    if expected_resolution and result.width and result.height:
        actual_label = resolution_label_for(result.height)
        if actual_label and actual_label != expected_resolution:
            # A note, never a failure. M2.0 already showed a 768P request
            # arriving as 768x1344, so the short edge is what the provider
            # actually controls and the label is a request, not a guarantee.
            result.notes.append(
                f"resolution label: requested {expected_resolution}, short edge "
                f"({min(result.width, result.height)}px) implies {actual_label}"
            )

    if audio_policy not in AudioPolicy.ALL:
        result.reasons.append(
            f"unknown audio policy {audio_policy!r}; expected one of "
            f"{', '.join(AudioPolicy.ALL)}"
        )

    result.approved = not result.reasons
    return result


def _ratio_to_float(ratio: str) -> Optional[float]:
    try:
        if ":" in ratio:
            width, _, height = ratio.partition(":")
            return float(width) / float(height)
        return float(ratio)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


#: Short-edge thresholds for the documented resolution labels. The provider picks
#: the exact dimensions, so the label is inferred from the short edge and treated
#: as a note rather than a guarantee.
RESOLUTION_SHORT_EDGE_BANDS: tuple = (
    (480, "480P"),
    (768, "768P"),
)


def resolution_label_for(short_edge: int) -> Optional[str]:
    """Infer the provider's resolution label from the short edge.

    ``2K`` has no reliable short edge, because a 2K portrait frame is 2560x1440
    while a 2K landscape frame is 2560x1440 as well; only the labels that map
    cleanly onto a short edge are inferred.
    """
    for threshold, label in RESOLUTION_SHORT_EDGE_BANDS:
        if short_edge <= threshold + 64:
            return label
    return None