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

from assemble_easel import CaptionOverflowError, _ms, _srt_to_ass  # noqa: E402

LONG_CUE = "这是一段非常长的中文字幕用来验证系统不会安静地截断文本" * 3


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


def test_latin_words_are_not_split_mid_word():
    """A wrap may break between words, never inside ``tests``."""
    from assemble_easel import _wrap

    lines = _wrap("放大这行：All subtitle timing tests passed.", 600, 54)
    assert any("tests" in line for line in lines), lines
    print("[ok] latin words survive a wrap intact")


def test_strict_mode_blocks_oversized_cue():
    """An unfittable cue must stop the build, not lose words silently."""
    with tempfile.TemporaryDirectory() as td:
        srt = Path(td) / "in.srt"
        ass = Path(td) / "out.ass"
        srt.write_text(
            f"1\n00:00:00,000 --> 00:00:05,000\n{LONG_CUE}\n", encoding="utf-8")
        raised = None
        try:
            _srt_to_ass(srt, ass, 1080, 1920, "Noto Sans CJK SC", 54, 134,
                        strict=True)
        except CaptionOverflowError as exc:
            raised = exc
        assert raised is not None, "strict mode silently truncated a long cue"
        assert raised.needed_lines > raised.max_lines, raised.needed_lines
        assert LONG_CUE in raised.text
        assert not ass.exists(), "a partial ASS was written before the failure"


def test_legacy_mode_reports_truncation_instead_of_hiding_it():
    """Legacy behavior still truncates, but the overflow is returned."""
    with tempfile.TemporaryDirectory() as td:
        srt = Path(td) / "in.srt"
        ass = Path(td) / "out.ass"
        srt.write_text(
            f"1\n00:00:00,000 --> 00:00:05,000\n{LONG_CUE}\n", encoding="utf-8")
        overflows = _srt_to_ass(srt, ass, 1080, 1920, "Noto Sans CJK SC", 54, 134)
        assert len(overflows) == 1, overflows
        assert overflows[0]["truncated"] is True
        body = [l for l in ass.read_text(encoding="utf-8").splitlines()
                if l.startswith("Dialogue:")]
        assert len(body) == 1
        assert body[0].count("\\N") <= 1, "truncated cue emitted more than two lines"


def test_short_cue_is_not_reported_as_overflow():
    with tempfile.TemporaryDirectory() as td:
        srt = Path(td) / "in.srt"
        ass = Path(td) / "out.ass"
        srt.write_text("1\n00:00:00,000 --> 00:00:02,000\n能跑，但没跑通\n",
                       encoding="utf-8")
        overflows = _srt_to_ass(srt, ass, 1080, 1920, "Noto Sans CJK SC", 54, 134,
                                strict=True)
        assert overflows == [], overflows


def test_a_closing_mark_never_opens_a_line():
    """Chinese kinsoku: ``。`` must stay with the sentence it closes."""
    from assemble_easel import _wrap

    text = "边界：工具链可用，Web 还不能算交付。"
    # 840 px leaves room for every glyph except the final full stop, which is
    # exactly the break that produced a line containing only "。" before.
    lines = _wrap(text, 840, 54)
    assert "".join(lines) == text, lines
    for line in lines:
        assert line[0] not in "，。、；：！？）》」』】〕…", lines
    print("[ok] a closing mark never opens a line")


def test_an_opening_mark_never_ends_a_line():
    from assemble_easel import _wrap

    text = "这里写一段话（括号里的内容）。"
    # 324 px ends exactly on the opening bracket.
    lines = _wrap(text, 324, 54)
    assert "".join(lines) == text, lines
    for line in lines:
        assert line[-1] not in "（《「『【〔", lines
    print("[ok] an opening mark never ends a line")


def main() -> int:
    failures = []
    tests = (
        test_ass_timestamp_uses_centiseconds,
        test_second_cue_starts_at_the_first_cue_end,
        test_srt_parser_reads_milliseconds,
        test_late_cue_is_not_shifted_into_the_next_one,
        test_latin_words_are_not_split_mid_word,
        test_a_closing_mark_never_opens_a_line,
        test_an_opening_mark_never_ends_a_line,
        test_strict_mode_blocks_oversized_cue,
        test_legacy_mode_reports_truncation_instead_of_hiding_it,
        test_short_cue_is_not_reported_as_overflow,
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
