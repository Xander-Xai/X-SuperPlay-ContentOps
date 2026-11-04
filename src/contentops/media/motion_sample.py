"""Technical gate for a short motion sample: checked, never approved.

A motion sample is a 4–8 s, silent 1080×1920 clip used for internal review. It
is not a finished video and it is not a publication candidate. The gate checks
the *file* — dimensions, codec, pixel format, constant frame timing, audio
absence, duration and digest — and stops at ``PENDING_FOUNDER_REVIEW``. A
technical pass never signs G6.

The module is pure: the caller supplies a probe mapping (the CLI runs ffprobe).
That keeps the contract testable offline and keeps process spawning in
``scripts/``. An unavailable probe is a BLOCKED result, never a pass.

What is not claimed
-------------------
A TECHNICALLY_CHECKED sample is not a successful sample. Whether the motion is
usable, faithful and worth keeping is a human decision recorded separately.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "contentops.motion-sample-check/v1"

SAMPLE_MIN_S = 4.0
SAMPLE_MAX_S = 8.0
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_FPS = 30.0
FRAME_TOLERANCE_S = 0.002

_VIDEO_CODECS = ("h264", "libx264")


def _blocked(code: str, detail: str, sha256: Optional[str] = None) -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "state": "BLOCKED",
        "reason": f"{code}: {detail}",
        "review_state": "PENDING_FOUNDER_REVIEW",
        "sha256": sha256,
        "generated": True,
        "evidence_capable": False,
        "production_ready": False,
        "publish_authorized": False,
    }


def _fps(value: Any) -> Optional[float]:
    text = str(value or "").strip()
    if "/" in text:
        numerator, _, denominator = text.partition("/")
        try:
            return float(numerator) / float(denominator)
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _constant_frame_timing(stamps: List[float]) -> Optional[str]:
    """Return a refusal reason, or None when the timestamps are constant 30 fps."""
    if len(stamps) < 2:
        return "frame_timestamps is empty"
    if abs(stamps[0]) > 0.01:
        return f"first frame starts at {stamps[0]:.3f}s, not 0"
    target = 1.0 / TARGET_FPS
    for left, right in zip(stamps, stamps[1:]):
        delta = right - left
        if abs(delta - target) > FRAME_TOLERANCE_S:
            return f"frame gap {delta:.4f}s differs from {target:.4f}s"
    return None


def check_motion_sample(path: Path, *, probe: Dict[str, Any],
                        expected_sha256: Optional[str] = None) -> Dict[str, Any]:
    """Check one short motion sample and return a structured result.

    ``probe`` is the ffprobe-derived mapping the CLI builds. It may instead be
    ``{"error": "FFPROBE_UNAVAILABLE", ...}``, which is BLOCKED, not a pass.
    """
    sample = Path(path)
    if not sample.is_file():
        return _blocked("SAMPLE_MISSING", str(sample))
    try:
        digest = hashlib.sha256(sample.read_bytes()).hexdigest()
    except OSError as exc:
        return _blocked("SAMPLE_READ", str(exc))
    if expected_sha256 and digest != str(expected_sha256).lower():
        return _blocked("SAMPLE_HASH_MISMATCH", "the file digest does not match the expected digest", digest)
    if not isinstance(probe, dict):
        return _blocked("SAMPLE_PROBE", "the probe must be a mapping", digest)
    if probe.get("error"):
        return _blocked(str(probe["error"]), str(probe.get("detail") or ""), digest)

    if probe.get("width") != TARGET_WIDTH or probe.get("height") != TARGET_HEIGHT:
        return _blocked(
            "SAMPLE_DIMENSIONS",
            f"{probe.get('width')}x{probe.get('height')} is not {TARGET_WIDTH}x{TARGET_HEIGHT}",
            digest,
        )
    if str(probe.get("codec_name") or "").lower() not in _VIDEO_CODECS:
        return _blocked("SAMPLE_CODEC", f"{probe.get('codec_name')!r} is not H.264", digest)
    if str(probe.get("pix_fmt") or "").lower() != "yuv420p":
        return _blocked("SAMPLE_PIX_FMT", f"{probe.get('pix_fmt')!r} is not yuv420p", digest)
    if bool(probe.get("has_audio")):
        return _blocked("SAMPLE_AUDIO_PRESENT", "a motion sample must be silent", digest)

    try:
        duration = float(probe.get("duration_s"))
    except (TypeError, ValueError):
        return _blocked("SAMPLE_DURATION", "duration is not numeric", digest)
    if not (SAMPLE_MIN_S <= duration <= SAMPLE_MAX_S):
        return _blocked(
            "SAMPLE_DURATION",
            f"{duration:.3f}s is outside {SAMPLE_MIN_S:.0f}-{SAMPLE_MAX_S:.0f}s",
            digest,
        )

    average = _fps(probe.get("avg_frame_rate"))
    real = _fps(probe.get("r_frame_rate"))
    if average is None or real is None or abs(average - TARGET_FPS) > 0.001 or abs(real - TARGET_FPS) > 0.001:
        return _blocked(
            "SAMPLE_FPS",
            f"avg={probe.get('avg_frame_rate')!r} r={probe.get('r_frame_rate')!r}; expected {TARGET_FPS:.0f}/1",
            digest,
        )

    stamps = probe.get("frame_timestamps")
    if not isinstance(stamps, list) or not stamps:
        return _blocked(
            "SAMPLE_FRAME_TIMING_UNVERIFIED",
            "frame timestamps are required; avg_frame_rate == r_frame_rate is not proof of CFR",
            digest,
        )
    try:
        stamps = [float(value) for value in stamps]
    except (TypeError, ValueError):
        return _blocked("SAMPLE_FRAME_TIMING", "frame timestamps must be numeric", digest)
    timing_problem = _constant_frame_timing(stamps)
    if timing_problem:
        return _blocked("SAMPLE_FRAME_TIMING", timing_problem, digest)

    expected_frames = int(round(duration * TARGET_FPS))
    if abs(len(stamps) - expected_frames) > 1:
        return _blocked(
            "SAMPLE_FRAME_COUNT",
            f"{len(stamps)} frames for {duration:.3f}s at {TARGET_FPS:.0f} fps (expected {expected_frames})",
            digest,
        )

    return {
        "schema": SCHEMA,
        "state": "TECHNICALLY_CHECKED",
        "review_state": "PENDING_FOUNDER_REVIEW",
        "path": str(sample),
        "sha256": digest,
        "duration_s": round(duration, 3),
        "width": TARGET_WIDTH,
        "height": TARGET_HEIGHT,
        "fps": TARGET_FPS,
        "frame_count": len(stamps),
        "audio": False,
        "generated": True,
        "evidence_capable": False,
        "production_ready": False,
        "publish_authorized": False,
        "note": "technical check only; G6 and usability remain a human decision",
    }
