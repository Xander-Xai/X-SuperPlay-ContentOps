"""Subtitle burn timing regression tests.

The burn adapter converts SRT to ASS. ASS timestamps are ``H:MM:SS.cc`` --
centiseconds -- not milliseconds. An earlier version emitted
``0:00:06.584`` for 6.584 s, which libass reads as 6 s + 584 cs = 11.84 s,
so every cue was stretched by a factor of ten. QC only checked that a subtitle
was *present*, so the desynchronisation survived a green run and was found by
extracting frames from a real render.

Run: python tests/test_subtitle_timing.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from assemble_easel import _ms, _srt_to_ass  # noqa: E402


def _convert(srt_text: str) -> str:
    with tempfile.TemporaryDirectory() as td:
        srt = Path(td) / "in.srt"
        ass = Path(td) / "out.ass"
        srt.write_text(srt_text, encoding="utf-8")
        _srt_to_ass(srt, ass, 1080, 1920, "Noto Sans CJK SC", 54, 134)
        return ass.read_text(encoding="utf-8")


def _dialogues(ass_text: str) -> list[tuple[str, str, str]]:
    rows = []
    for line in ass_text.splitlines():
        if line.startswith("Dialogue:"):
            parts = line.split(",", 9)
            rows.append((parts[1].strip(), parts[2].strip(), parts[9]))
    return rows


def test_ass_timestamp_uses_centiseconds():
    """6.584 s must be emitted as 0:00:06.58, not 0:00:06.584."""
    ass = _convert(
        "1\n00:00:00,000 --> 00:00:06,584\n第一句\n\n"
        "2\n00:00:06,584 --> 00:00:16,263\n第二句\n"
    )
    rows = _dialogues(ass)
    assert len(rows) == 2, rows
    first_start, first_end, first_text = rows[0]
    assert first_start == "0:00:00.00", first_start
    assert first_end == "0:00:06.58", first_end
    assert ".584" not in ass, "a millisecond field survived into the ASS body"
    assert "第一句" in first_text


def test_second_cue_starts_at_the_first_cue_end():
    ass = _convert(
        "1\n00:00:00,000 --> 00:00:06,584\n第一句\n\n"
        "2\n00:00:06,584 --> 00:00:16,263\n第二句\n"
    )
    rows = _dialogues(ass)
    assert rows[1][0] == "0:00:06.58", rows[1][0]
    assert rows[1][1] == "0:00:16.26", rows[1][1]


def test_srt_parser_reads_milliseconds():
    """The SRT side must stay milliseconds; only the ASS side is centiseconds."""
    assert _ms("00:00:06,584") == 6584
    assert _ms("00:01:02,005") == 62005


def test_late_cue_is_not_shifted_into_the_next_one():
    """A cue at 26.5 s must not be emitted as 265 s of centiseconds."""
    ass = _convert(
        "1\n00:00:16,263 --> 00:00:26,585\n最后一句\n"
    )
    rows = _dialogues(ass)
    assert rows[0][0] == "0:00:16.26", rows[0][0]
    assert rows[0][1] == "0:00:26.58", rows[0][1]


def main() -> int:
    failures = []
    tests = (
        test_ass_timestamp_uses_centiseconds,
        test_second_cue_starts_at_the_first_cue_end,
        test_srt_parser_reads_milliseconds,
        test_late_cue_is_not_shifted_into_the_next_one,
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
    print("\nAll subtitle timing tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
