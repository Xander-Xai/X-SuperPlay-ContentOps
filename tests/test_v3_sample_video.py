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
    UnitTiming,
    _first_paragraph,
    _logical_to_local,
    placement_for_paragraph,
    render_srt,
    split_group,
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
