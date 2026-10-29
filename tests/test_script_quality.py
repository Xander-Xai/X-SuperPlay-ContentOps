"""Pre-render script quality gate tests.

Each test builds a throwaway project in a temp directory and breaks exactly one
thing, so a failure names the rule that stopped it. The defects these rules
describe are the ones actually observed in a discarded cut, not invented.

Run: python tests/test_script_quality.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_script_quality import check_project  # noqa: E402

BEATS = [
    {"placement_id": "P-01", "text": "先说结论。", "layout": "hook"},
    {"placement_id": "P-02", "text": "再给证据。", "layout": "evidence"},
    {"placement_id": "P-03", "text": "然后是边界。", "layout": "diagram"},
    {"placement_id": "P-04", "text": "需要复现，评论区说你的技术栈。", "layout": "cta"},
]
SHOTS = [
    {"source": "clip:a", "source_type": "title_card", "duration": 3.0},
    {"source": "clip:b", "source_type": "real_screenshot", "duration": 3.0},
    {"source": "clip:c", "source_type": "diagram", "duration": 3.0},
    {"source": "clip:d", "source_type": "title_card", "duration": 3.0},
]
SRT = """1
00:00:00,000 --> 00:00:03,000
先说结论。

2
00:00:03,000 --> 00:00:06,000
再给证据。

3
00:00:06,000 --> 00:00:09,000
然后是边界。

4
00:00:09,000 --> 00:00:12,000
需要复现，评论区说你的技术栈。
"""


def _project(**overrides) -> Path:
    """A project that passes every rule, then mutates one document."""
    tmp = Path(tempfile.mkdtemp(prefix="sq-"))
    (tmp / "script").mkdir(parents=True, exist_ok=True)
    (tmp / "assets" / "captions").mkdir(parents=True, exist_ok=True)

    lines = {"schema": "contentops.audio-first-lines/v1", "beats": [dict(b) for b in BEATS],
             "cta": "需要复现，评论区说你的技术栈。"}
    storyboard = {"subtitle": "assets/captions/cut.srt", "shots": [dict(s) for s in SHOTS]}
    master_rows = len(BEATS)
    srt = SRT

    for key, value in overrides.items():
        if key == "lines":
            lines.update(value)
        elif key == "beats":
            lines["beats"] = value
        elif key == "shots":
            storyboard["shots"] = value
        elif key == "storyboard":
            storyboard.update(value)
        elif key == "master_rows":
            master_rows = value
        elif key == "srt":
            srt = value
        elif key == "drop_cta":
            lines.pop("cta", None)

    (tmp / "script" / "lines.json").write_text(
        json.dumps(lines, ensure_ascii=False), encoding="utf-8")
    (tmp / "script" / "storyboard.json").write_text(
        json.dumps(storyboard, ensure_ascii=False), encoding="utf-8")
    table = "\n".join(
        f"| {i + 1} | beat {i + 1} | frame {i + 1} |" for i in range(master_rows))
    (tmp / "script" / "master.md").write_text(
        f"| # | 口播 | 画面 |\n|---|---|---|\n{table}\n", encoding="utf-8")
    (tmp / "assets" / "captions" / "cut.srt").write_text(srt, encoding="utf-8")
    return tmp


def _rules(report: dict) -> set:
    return {finding["rule"].split()[0] for finding in report["failures"]}


def test_a_well_formed_project_passes():
    report = check_project(_project())
    assert report["failures"] == [], report["failures"]
    assert report["evaluable"] is True


def test_a_silent_shot_with_no_narration_fails():
    """The 2.85 s stock B-roll dropped in to cover silence."""
    srt = SRT.replace("3\n00:00:06,000 --> 00:00:09,000\n然后是边界。\n",
                      "3\n00:00:06,000 --> 00:00:07,000\n然后是边界。\n")
    report = check_project(_project(srt=srt))
    assert "SQ01" in _rules(report), report["failures"]


def test_a_shot_may_be_silent_when_it_says_why():
    shots = [dict(s) for s in SHOTS]
    shots[2]["justification"] = "deliberate 3 s hold on the diagram"
    srt = SRT.replace("3\n00:00:06,000 --> 00:00:09,000\n然后是边界。\n",
                      "3\n00:00:06,000 --> 00:00:07,000\n然后是边界。\n")
    report = check_project(_project(shots=shots, srt=srt))
    assert "SQ01" not in _rules(report), report["failures"]


def test_an_unclassifiable_source_type_fails():
    """vector_animation is in neither qc_video set, so the ratio silently reads 0."""
    shots = [dict(s) for s in SHOTS]
    shots[2]["source_type"] = "vector_animation"
    report = check_project(_project(shots=shots))
    assert "SQ02" in _rules(report), report["failures"]


def test_an_undeclared_layout_fails():
    beats = [dict(b) for b in BEATS]
    beats[1].pop("layout")
    report = check_project(_project(beats=beats))
    assert "SQ03" in _rules(report), report["failures"]


def test_one_layout_carrying_most_beats_fails():
    beats = [dict(b) for b in BEATS]
    for beat in beats[:3]:
        beat["layout"] = "title_plus_two_cards"
    report = check_project(_project(beats=beats))
    assert "SQ04" in _rules(report), report["failures"]


def test_a_short_cut_is_not_judged_on_layout_concentration():
    """Two beats cannot be repetitive; the ratio says nothing at that length."""
    beats = [dict(b) for b in BEATS[:2]]
    beats[0]["layout"] = beats[1]["layout"] = "same"
    shots = [dict(s) for s in SHOTS[:2]]
    srt = "1\n00:00:00,000 --> 00:00:03,000\na\n\n2\n00:00:03,000 --> 00:00:06,000\nb\n"
    report = check_project(_project(beats=beats, shots=shots, srt=srt, master_rows=2))
    assert "SQ04" not in _rules(report), report["failures"]


def test_a_presenter_shown_once_fails_unless_scoped():
    beats = [dict(b) for b in BEATS]
    beats[0]["role"] = "presenter"
    report = check_project(_project(beats=beats))
    assert "SQ05" in _rules(report), report["failures"]


def test_a_presenter_scoped_explicitly_passes():
    beats = [dict(b) for b in BEATS]
    beats[0]["role"] = "presenter"
    report = check_project(
        _project(beats=beats, lines={"presenter_scope": "opening only, by design"}))
    assert "SQ05" not in _rules(report), report["failures"]


def test_script_table_drifting_from_the_beats_fails():
    """The exact defect: master.md listed 5 beats, lines.json held 12."""
    report = check_project(_project(master_rows=2))
    assert "SQ06" in _rules(report), report["failures"]


def test_a_subtitle_pointer_to_a_missing_file_fails():
    report = check_project(_project(storyboard={"subtitle": "assets/captions/cut.srt.bak"}))
    assert "SQ06" in _rules(report), report["failures"]


def test_a_storyboard_shorter_than_the_captions_fails():
    shots = [dict(s) for s in SHOTS]
    shots[3]["duration"] = 0.5
    report = check_project(_project(shots=shots))
    assert "SQ06" in _rules(report), report["failures"]


def test_a_missing_call_to_action_fails():
    beats = [dict(b) for b in BEATS]
    beats[3]["text"] = "先把边界写清楚，再谈自动化。"
    report = check_project(_project(beats=beats, drop_cta=True))
    assert "SQ07" in _rules(report), report["failures"]


def main() -> int:
    failures = []
    tests = (
        test_a_well_formed_project_passes,
        test_a_silent_shot_with_no_narration_fails,
        test_a_shot_may_be_silent_when_it_says_why,
        test_an_unclassifiable_source_type_fails,
        test_an_undeclared_layout_fails,
        test_one_layout_carrying_most_beats_fails,
        test_a_short_cut_is_not_judged_on_layout_concentration,
        test_a_presenter_shown_once_fails_unless_scoped,
        test_a_presenter_scoped_explicitly_passes,
        test_script_table_drifting_from_the_beats_fails,
        test_a_subtitle_pointer_to_a_missing_file_fails,
        test_a_storyboard_shorter_than_the_captions_fails,
        test_a_missing_call_to_action_fails,
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
    print("\nAll script quality tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
