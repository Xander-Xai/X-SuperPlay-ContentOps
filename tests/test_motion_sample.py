"""Motion sample technical gate: a short, silent, 1080x1920 clip is checked, never approved.

Run: python tests/test_motion_sample.py
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media import motion_sample  # noqa: E402


def _timestamps(duration: float, fps: float = 30.0):
    count = int(round(duration * fps))
    return [round(i / fps, 6) for i in range(count)]


def _probe(**overrides):
    data = {
        "duration_s": 6.0,
        "width": 1080,
        "height": 1920,
        "codec_name": "h264",
        "pix_fmt": "yuv420p",
        "avg_frame_rate": "30/1",
        "r_frame_rate": "30/1",
        "has_audio": False,
        "frame_timestamps": _timestamps(6.0),
    }
    data.update(overrides)
    return data


def _sample(tmp: str, data: bytes = b"motion-sample") -> Path:
    path = Path(tmp) / "sample.mp4"
    path.write_bytes(data)
    return path


def _blocked(result, code):
    assert result["state"] == "BLOCKED", result
    assert result["reason"].split(":", 1)[0] == code, result
    return result


def test_a_valid_sample_is_technically_checked_but_never_approved():
    with tempfile.TemporaryDirectory() as tmp:
        path = _sample(tmp)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result = motion_sample.check_motion_sample(path, probe=_probe(), expected_sha256=digest)
    assert result["state"] == "TECHNICALLY_CHECKED"
    assert result["review_state"] == "PENDING_FOUNDER_REVIEW"
    assert result["production_ready"] is False
    assert result["publish_authorized"] is False
    assert result["evidence_capable"] is False
    assert result["generated"] is True
    assert result["sha256"] == digest


def test_wrong_dimensions_are_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        path = _sample(tmp)
        _blocked(motion_sample.check_motion_sample(path, probe=_probe(width=720)), "SAMPLE_DIMENSIONS")


def test_audio_is_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        path = _sample(tmp)
        _blocked(motion_sample.check_motion_sample(path, probe=_probe(has_audio=True)), "SAMPLE_AUDIO_PRESENT")


def test_duration_outside_four_to_eight_seconds_is_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        path = _sample(tmp)
        for duration in (3.9, 8.1):
            _blocked(
                motion_sample.check_motion_sample(
                    path, probe=_probe(duration_s=duration, frame_timestamps=_timestamps(duration))),
                "SAMPLE_DURATION",
            )


def test_hash_mismatch_is_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        path = _sample(tmp)
        _blocked(
            motion_sample.check_motion_sample(path, probe=_probe(), expected_sha256="0" * 64),
            "SAMPLE_HASH_MISMATCH",
        )


def test_missing_file_is_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        _blocked(
            motion_sample.check_motion_sample(Path(tmp) / "nope.mp4", probe=_probe()),
            "SAMPLE_MISSING",
        )


def test_non_constant_frame_timing_is_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        path = _sample(tmp)
        stamps = _timestamps(6.0)
        stamps[90] += 0.2  # a visible gap
        _blocked(
            motion_sample.check_motion_sample(path, probe=_probe(frame_timestamps=stamps)),
            "SAMPLE_FRAME_TIMING",
        )


def test_missing_frame_timestamps_is_blocked_not_passed():
    with tempfile.TemporaryDirectory() as tmp:
        path = _sample(tmp)
        _blocked(
            motion_sample.check_motion_sample(path, probe=_probe(frame_timestamps=[])),
            "SAMPLE_FRAME_TIMING_UNVERIFIED",
        )


def test_ffprobe_unavailable_is_blocked_not_passed():
    with tempfile.TemporaryDirectory() as tmp:
        path = _sample(tmp)
        _blocked(
            motion_sample.check_motion_sample(
                path, probe={"error": "FFPROBE_UNAVAILABLE", "detail": "ffprobe not found"}),
            "FFPROBE_UNAVAILABLE",
        )


def test_the_clip_gate_applies_the_same_rules_with_a_wider_duration_window():
    with tempfile.TemporaryDirectory() as tmp:
        path = _sample(tmp)
        duration = 2.5
        clip = motion_sample.check_motion_clip(
            path, probe=_probe(duration_s=duration, frame_timestamps=_timestamps(duration)),
            min_duration_s=0.0, max_duration_s=8.0, reason_prefix="CLIP",
        )
        assert clip["state"] == "TECHNICALLY_CHECKED", clip
        assert clip["duration_s"] == 2.5
        _blocked(
            motion_sample.check_motion_sample(
                path, probe=_probe(duration_s=duration, frame_timestamps=_timestamps(duration)),
            ),
            "SAMPLE_DURATION",
        )


def test_the_clip_gate_still_refuses_everything_the_sample_gate_refuses():
    with tempfile.TemporaryDirectory() as tmp:
        path = _sample(tmp)
        _blocked(
            motion_sample.check_motion_clip(path, probe=_probe(width=720)),
            "CLIP_DIMENSIONS",
        )
        _blocked(
            motion_sample.check_motion_clip(path, probe=_probe(has_audio=True)),
            "CLIP_AUDIO_PRESENT",
        )
        _blocked(
            motion_sample.check_motion_clip(path, probe=_probe(), expected_sha256="0" * 64),
            "CLIP_HASH_MISMATCH",
        )
        _blocked(
            motion_sample.check_motion_clip(path, probe=_probe(frame_timestamps=[])),
            "CLIP_FRAME_TIMING_UNVERIFIED",
        )
        _blocked(
            motion_sample.check_motion_clip(Path(tmp) / "nope.mp4", probe=_probe()),
            "CLIP_MISSING",
        )
        stamps = _timestamps(6.0)
        stamps[90] += 0.2
        _blocked(
            motion_sample.check_motion_clip(path, probe=_probe(frame_timestamps=stamps)),
            "CLIP_FRAME_TIMING",
        )


def test_the_result_carries_no_self_approval_switch():
    with tempfile.TemporaryDirectory() as tmp:
        path = _sample(tmp)
        result = motion_sample.check_motion_sample(path, probe=_probe())
    assert "approved" not in {key.lower() for key in result}
    assert result["review_state"] == "PENDING_FOUNDER_REVIEW"


TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"ok   {test.__name__}")
        except Exception as exc:  # noqa: BLE001 - a runner reports, it does not hide
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
    total = len(TESTS)
    print(f"{total - failures}/{total} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
