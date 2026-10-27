"""v3 sample-video bridge tests.

Covers the provider-free half of the narration -> video path: the unit to
evidence-placement mapping, the duration split, and the SRT the burn consumes.
No ffmpeg, no provider, no audio file required.

Run: python tests/test_v3_sample_video.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from build_v3_sample_video import (  # noqa: E402
    EVIDENCE_LOCK,
    MIN_CUE_SECONDS,
    UnitTiming,
    _first_paragraph,
    _logical_to_local,
    build_caption_cues,
    placement_for_paragraph,
    render_srt,
    split_group,
    split_phrases,
    srt_timestamp,
)


def test_srt_timestamp_is_milliseconds():
    assert srt_timestamp(0) == "00:00:00,000"
    assert srt_timestamp(6.584) == "00:00:06,584"
    assert srt_timestamp(62.5) == "00:01:02,500"


def test_split_group_prefers_the_nearest_measured_silence():
    intervals = split_group(
        group_start=0.0,
        group_end=15.812688,
        weights=[35, 42],
        silences=[
            (4.0085, 4.307531),
            (6.204156, 6.963594),
            (9.49575, 10.173656),
            (13.272531, 13.578563),
        ],
        labels=["U01/U03"],
    )
    assert len(intervals) == 2
    total = sum(duration for _, duration, _ in intervals)
    assert abs(total - 15.812688) < 1e-6, total
    assert abs(intervals[0][1] - 6.584) < 0.01, intervals[0]
    assert intervals[0][2] == "silence_midpoint"


def test_split_group_falls_back_to_the_character_share():
    intervals = split_group(
        group_start=0.0,
        group_end=154.0,
        weights=[1, 1],
        silences=[],
        labels=["A/B"],
    )
    assert [round(d, 3) for _, d, _ in intervals] == [77.0, 77.0]
    assert intervals[0][2] == "proportional_no_silence"
    assert intervals[1][2] == "group_tail"


def test_single_unit_group_needs_no_boundary():
    intervals = split_group(
        group_start=16.0, group_end=26.0, weights=[10], silences=[], labels=[]
    )
    assert intervals == [(16.0, 10.0, "single_unit_group")]


def test_paragraph_maps_to_the_locked_placement():
    lock = json.loads(EVIDENCE_LOCK.read_text(encoding="utf-8"))
    assert placement_for_paragraph(lock, 1)["placement_id"] == "shot_00"
    assert placement_for_paragraph(lock, 2)["placement_id"] == "shot_01"
    assert placement_for_paragraph(lock, 4)["placement_id"] == "shot_03"
    assert placement_for_paragraph(lock, 6)["placement_id"] == "shot_05"


def test_paragraph_outside_the_lock_is_refused():
    lock = json.loads(EVIDENCE_LOCK.read_text(encoding="utf-8"))
    for paragraph in (0, 7):
        try:
            placement_for_paragraph(lock, paragraph)
        except Exception as exc:  # noqa: BLE001
            assert "outside" in str(exc)
        else:
            raise AssertionError(f"paragraph {paragraph} was accepted")


def test_logical_asset_resolves_against_the_lock_scope():
    local = _logical_to_local(
        "project://sources/screenshots/10-easel-doctor.png",
        "project://easel-review",
    )
    assert local == ROOT / "projects" / "easel-review" / "sources" / "screenshots" / "10-easel-doctor.png"


def test_first_paragraph_accepts_lists_and_ints():
    assert _first_paragraph([4], "U05") == 4
    assert _first_paragraph(3, "U02") == 3


def test_rendered_srt_has_one_cue_per_unit():
    timings = [
        UnitTiming("U01", "第一句", 1, "shot_00", "a.png", 0.0, 6.584),
        UnitTiming("U03", "第二句", 2, "shot_01", "b.png", 6.584, 9.679),
    ]
    text = render_srt(timings)
    assert "00:00:00,000 --> 00:00:06,584" in text
    assert "00:00:06,584 --> 00:00:16,263" in text
    assert text.count("-->") == 2


def test_split_phrases_keeps_a_version_string_intact():
    text = "版本我锁在 v0.2.1。982 个文件，逐个比对过哈希，和上游 tag 完全一致。"
    phrases = split_phrases(text)
    assert len(phrases) > 1
    assert "".join(phrases) == text, phrases
    assert all(phrase != "v0." for phrase in phrases), phrases
    assert any("v0.2.1" in phrase for phrase in phrases), phrases


def test_split_phrases_merges_a_short_opening():
    phrases = split_phrases("但有个坑：网关健康检查探的是写死的默认端口，和实际端口对不上。")
    assert all(len(phrase) >= 6 for phrase in phrases), phrases
    assert "".join(phrases).startswith("但有个坑："), phrases


def test_sentence_cues_are_one_per_unit():
    timings = [
        UnitTiming("U01", "第一句，带逗号。", 1, "shot_00", "a.png", 0.0, 6.0),
        UnitTiming("U03", "第二句。", 2, "shot_01", "b.png", 6.0, 4.0),
    ]
    cues = build_caption_cues(timings, "sentence")
    assert [(c.start_s, c.duration_s, c.text) for c in cues] == [
        (0.0, 6.0, "第一句，带逗号。"),
        (6.0, 4.0, "第二句。"),
    ]


def test_phrase_cues_tile_the_unit_without_drift():
    timings = [
        UnitTiming(
            "U01",
            "装了 Easel 之后，最先要回答的只有一个问题：它到底跑不跑得起来？",
            1, "shot_00", "a.png", 0.0, 6.584,
        ),
        UnitTiming("U05", "但有个坑：网关健康和实际端口对不上。", 4, "shot_03", "b.png", 6.584, 10.0),
    ]
    cues = build_caption_cues(timings, "phrase")
    assert len(cues) > len(timings)
    assert cues[0].start_s == 0.0
    assert abs((cues[-1].start_s + cues[-1].duration_s) - 16.584) < 1e-6
    assert abs(sum(cue.duration_s for cue in cues) - 16.584) < 1e-6
    assert all(cue.duration_s >= MIN_CUE_SECONDS for cue in cues), cues
    for previous, current in zip(cues, cues[1:]):
        assert abs((previous.start_s + previous.duration_s) - current.start_s) < 1e-6


def main() -> int:
    failures = []
    tests = (
        test_srt_timestamp_is_milliseconds,
        test_split_group_prefers_the_nearest_measured_silence,
        test_split_group_falls_back_to_the_character_share,
        test_single_unit_group_needs_no_boundary,
        test_paragraph_maps_to_the_locked_placement,
        test_paragraph_outside_the_lock_is_refused,
        test_logical_asset_resolves_against_the_lock_scope,
        test_first_paragraph_accepts_lists_and_ints,
        test_rendered_srt_has_one_cue_per_unit,
        test_split_phrases_keeps_a_version_string_intact,
        test_split_phrases_merges_a_short_opening,
        test_sentence_cues_are_one_per_unit,
        test_phrase_cues_tile_the_unit_without_drift,
    )
    for fn in tests:
        try:
            fn()
            print(f"[ok] {fn.__name__}")
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print("\nAll v3 sample-video tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
