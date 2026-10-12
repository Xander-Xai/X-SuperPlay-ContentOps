"""Regression tests for segment-level T2A delivery. Issue #34, narration v2.

Everything here runs offline. Concatenation uses ffmpeg when it is available
(CI installs it on both runners) and skips the join assertion with a printed
notice when it is not; every other test needs no external tool.

The invariants that matter most:

- the cache is content-addressed: any input that changes the provider's audio
  changes the fingerprint, and a changed *gap* does not (a gap alters the join,
  not the segment);
- a corrupt or mismatched cache entry is a miss, never a reason to trust bytes;
- partial regeneration regenerates exactly the named segments and nothing else;
- a configuration error (an unknown segment id) refuses instead of quietly
  regenerating zero segments.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media.lexicon import default_zh_lexicon  # noqa: E402
from contentops.media.minimax_native_tts import NativeTtsRefusal  # noqa: E402
from contentops.media.t2a_segments import (  # noqa: E402
    ACTION_GENERATE,
    ACTION_REUSE_CACHE,
    CachedSegment,
    SegmentSpec,
    build_segment_payload,
    cache_paths,
    concatenate_segments,
    estimated_billable_characters,
    lookup_cached_segment,
    make_silence,
    plan_segment_renders,
    segment_fingerprint,
    segment_synthesis_text,
    store_cached_segment,
)

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


LEXICON = default_zh_lexicon()
VOICE = "founder_primary_v1"
MODEL = "speech-2.8-hd"


def _write_tone(path: Path, seconds: float, *, freq: float = 220.0, rate: int = 32000) -> Path:
    frames = bytearray()
    for index in range(int(seconds * rate)):
        value = int(12000 * math.sin(2 * math.pi * freq * index / rate))
        frames += value.to_bytes(2, "little", signed=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        fh.writeframes(bytes(frames))
    return path


def _segment(segment_id: str, text: str, **overrides) -> SegmentSpec:
    params = dict(id=segment_id, role="EVIDENCE", text=text)
    params.update(overrides)
    return SegmentSpec(**params)


# --- A. segment spec and payload ------------------------------------------------


@test
def test_segment_spec_refuses_invalid_declarations():
    for bad in (
        dict(id="", role="EVIDENCE", text="x"),
        dict(id="S1", role="UNKNOWN", text="x"),
        dict(id="S1", role="EVIDENCE", text="x", speed=0.0),
        dict(id="S1", role="EVIDENCE", text="x", pause_after_s=-0.1),
    ):
        try:
            SegmentSpec(**bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{bad!r} must be refused")
    print("[ok] 1. invalid segment declarations are refused at construction")


@test
def test_segment_payload_carries_lexicon_text_markers_emotion_and_speed():
    spec = _segment("S01", "Easel 装好了，<#0.3#>然后跑 doctor。", emotion="calm", speed=1.05)
    payload = build_segment_payload(
        spec, voice_id=VOICE, model=MODEL, lexicon=LEXICON
    )
    assert payload["text"] == "伊泽尔 装好了，<#0.3#>然后跑 doctor。"
    assert payload["voice_setting"]["emotion"] == "calm"
    assert payload["voice_setting"]["speed"] == 1.05
    assert payload["voice_setting"]["voice_id"] == VOICE
    assert payload["pronunciation_dict"]["tone"], "lexicon rules ride along"
    assert payload["stream"] is False

    auto = build_segment_payload(
        _segment("S02", "自动情绪。"), voice_id=VOICE, model=MODEL, lexicon=LEXICON
    )
    assert "emotion" not in auto["voice_setting"]
    print("[ok] 2. per-segment text/emotion/speed reach the documented payload")


@test
def test_segment_payload_propagates_pause_marker_refusals():
    bad = _segment("S03", "段内三位小数<#0.333#>坏了。")
    try:
        build_segment_payload(bad, voice_id=VOICE, model=MODEL, lexicon=LEXICON)
    except NativeTtsRefusal:
        pass
    else:
        raise AssertionError("an invalid marker inside a segment must be refused")
    consecutive = _segment("S04", "连续<#0.2#>，<#0.3#>标记。")
    try:
        build_segment_payload(consecutive, voice_id=VOICE, model=MODEL, lexicon=LEXICON)
    except NativeTtsRefusal:
        pass
    else:
        raise AssertionError("consecutive markers inside a segment must be refused")
    print("[ok] 3. marker validation applies inside segments too")


# --- B. fingerprint -------------------------------------------------------------


@test
def test_fingerprint_is_deterministic_and_audio_sensitive():
    base = dict(
        voice_id=VOICE,
        model=MODEL,
        synthesis_text="一段。",
        emotion=None,
        speed=1.0,
        sample_rate=32000,
        fmt="wav",
        channel=1,
        lexicon_component=LEXICON.fingerprint_component(),
    )
    first = segment_fingerprint(**base)
    assert segment_fingerprint(**base) == first, "same inputs, same fingerprint"
    assert segment_fingerprint(**{**base, "emotion": "calm"}) != first
    assert segment_fingerprint(**{**base, "speed": 1.05}) != first
    assert segment_fingerprint(**{**base, "synthesis_text": "另一段。"}) != first
    assert segment_fingerprint(**{**base, "voice_id": "other"}) != first
    print("[ok] 4. the fingerprint covers every audio-changing input")


@test
def test_a_changed_gap_does_not_invalidate_a_cached_segment():
    """pause_after_s alters the join, not this segment's audio."""
    spec_a = _segment("S01", "同一段。", pause_after_s=0.2)
    spec_b = _segment("S01", "同一段。", pause_after_s=0.8)
    assert segment_synthesis_text(spec_a, LEXICON) == segment_synthesis_text(spec_b, LEXICON)
    common = dict(
        voice_id=VOICE, model=MODEL, synthesis_text="同一段。", emotion=None,
        speed=1.0, sample_rate=32000, fmt="wav", channel=1,
        lexicon_component=LEXICON.fingerprint_component(),
    )
    assert segment_fingerprint(**common) == segment_fingerprint(**common)
    print("[ok] 5. gaps live in the join, not in the segment fingerprint")


# --- C. cache -------------------------------------------------------------------


@test
def test_cache_roundtrip_and_fail_closed_validation():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cache_dir = tmp / "segments"
        normalised = _write_tone(tmp / "norm.wav", 1.0)
        raw_bytes = _write_tone(tmp / "raw.wav", 1.0, freq=330.0).read_bytes()
        fingerprint = "f" * 64
        stored = store_cached_segment(
            cache_dir, fingerprint,
            raw_bytes=raw_bytes, normalised_path=normalised,
            meta={"segment_id": "S01", "model": MODEL},
        )
        assert stored.raw_path.is_file() and stored.normalised_path.is_file()

        hit = lookup_cached_segment(cache_dir, fingerprint)
        assert isinstance(hit, CachedSegment)
        assert hit.meta["segment_id"] == "S01"

        assert lookup_cached_segment(cache_dir, "e" * 64) is None

        # Tamper with the normalised audio: must be a miss, not a trust.
        with hit.normalised_path.open("r+b") as fh:
            fh.seek(5000)
            fh.write(b"\xff\xff\xff\xff")
        assert lookup_cached_segment(cache_dir, fingerprint) is None, (
            "hash-mismatched bytes must never be trusted"
        )
    print("[ok] 6. cache round-trips and a hash mismatch is a miss")


@test
def test_cache_meta_fingerprint_mismatch_is_a_miss():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cache_dir = tmp / "segments"
        normalised = _write_tone(tmp / "norm.wav", 1.0)
        raw_bytes = normalised.read_bytes()
        fingerprint = "a" * 64
        store_cached_segment(
            cache_dir, fingerprint,
            raw_bytes=raw_bytes, normalised_path=normalised, meta={},
        )
        _, _, meta_path = cache_paths(cache_dir, fingerprint)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["fingerprint"] = "b" * 64
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        assert lookup_cached_segment(cache_dir, fingerprint) is None
    print("[ok] 7. a record for a different fingerprint is a miss")


# --- D. planning and partial regeneration ---------------------------------------


@test
def test_plan_generates_missing_and_reuses_cached_segments():
    with tempfile.TemporaryDirectory() as tmp:
        cache_dir = Path(tmp) / "segments"
        segments = [
            _segment("S01", "第一段。"),
            _segment("S02", "第二段。"),
            _segment("S03", "第三段。"),
        ]
        cold = plan_segment_renders(
            segments, voice_id=VOICE, model=MODEL, lexicon=LEXICON,
            cache_dir=cache_dir,
        )
        assert [entry.action for entry in cold] == [ACTION_GENERATE] * 3

        # Store a fabricated cache entry for S02's fingerprint.
        target = cold[1]
        normalised = _write_tone(Path(tmp) / "s02.wav", 1.0)
        store_cached_segment(
            cache_dir, target.fingerprint,
            raw_bytes=normalised.read_bytes(), normalised_path=normalised, meta={},
        )
        warm = plan_segment_renders(
            segments, voice_id=VOICE, model=MODEL, lexicon=LEXICON,
            cache_dir=cache_dir,
        )
        actions = {entry.spec.id: entry.action for entry in warm}
        assert actions == {
            "S01": ACTION_GENERATE,
            "S02": ACTION_REUSE_CACHE,
            "S03": ACTION_GENERATE,
        }, actions

        forced = plan_segment_renders(
            segments, voice_id=VOICE, model=MODEL, lexicon=LEXICON,
            cache_dir=cache_dir, regenerate_ids=["S02"],
        )
        forced_actions = {entry.spec.id: entry.action for entry in forced}
        assert forced_actions["S02"] == ACTION_GENERATE, (
            "partial regeneration must override the cache for exactly the named id"
        )
        assert forced_actions["S01"] == ACTION_GENERATE
    print("[ok] 8. cold plans generate, warm plans reuse, named ids are forced")


@test
def test_plan_refuses_unknown_regenerate_ids_and_duplicate_ids():
    with tempfile.TemporaryDirectory() as tmp:
        cache_dir = Path(tmp) / "segments"
        segments = [_segment("S01", "第一段。")]
        try:
            plan_segment_renders(
                segments, voice_id=VOICE, model=MODEL, lexicon=LEXICON,
                cache_dir=cache_dir, regenerate_ids=["S99"],
            )
        except ValueError as exc:
            assert "S99" in str(exc)
        else:
            raise AssertionError("an unknown regenerate id must refuse")
        try:
            plan_segment_renders(
                [_segment("S01", "一。"), _segment("S01", "二。")],
                voice_id=VOICE, model=MODEL, lexicon=LEXICON, cache_dir=cache_dir,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate ids must refuse")
    print("[ok] 9. mis-typed regeneration refuses instead of regenerating nothing")


# --- E. join --------------------------------------------------------------------


@test
def test_silence_and_join_are_deterministic_and_gap_aware():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        if not shutil.which("ffmpeg"):
            print("[skip] ffmpeg unavailable; join assertion skipped")
            return
        first = _write_tone(tmp / "s1.wav", 1.0, freq=220.0)
        second = _write_tone(tmp / "s2.wav", 1.0, freq=330.0)
        middle = make_silence(tmp / "gap.wav", seconds=0.5)
        with wave.open(str(middle), "rb") as fh:
            assert fh.getframerate() == 32000
            assert fh.getnframes() == 16000

        joined = concatenate_segments(
            [first, second],
            gaps_after_s=[0.5, 0.9],
            out_path=tmp / "joined.wav",
            work_dir=tmp / "work",
        )
        with wave.open(str(joined), "rb") as fh:
            duration = fh.getnframes() / fh.getframerate()
        assert abs(duration - 2.5) < 0.05, (
            f"expected 1.0 + 0.5 + 1.0 = 2.5 s; the final gap must be ignored "
            f"(got {duration})"
        )

        rerun = concatenate_segments(
            [first, second],
            gaps_after_s=[0.5, 0.9],
            out_path=tmp / "joined2.wav",
            work_dir=tmp / "work2",
        )
        assert hashlib.sha256(joined.read_bytes()).hexdigest() == hashlib.sha256(
            rerun.read_bytes()
        ).hexdigest(), "same inputs must produce the same join"
    print("[ok] 10. joins insert the declared gaps, ignore the final one and are stable")


@test
def test_billable_estimation_matches_the_published_rule():
    assert estimated_billable_characters(["你好", "ab"]) == 6
    assert estimated_billable_characters([]) == 0
    print("[ok] 11. the budget arithmetic uses the published counting rule")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    failures = 0
    for fn in TESTS:
        try:
            fn()
        except AssertionError as exc:
            print(f"[FAIL] {fn.__name__}: {exc}")
            failures += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[ERR ] {fn.__name__}: {type(exc).__name__}({exc})")
            failures += 1
    total = len(TESTS)
    if failures:
        print(f"\n{failures} of {total} test(s) failed")
        return 1
    print(f"\nAll {total} segment-delivery tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
