"""Quality-gate tests: one verdict, sayable scripts, readable subtitles.

Run: python tests/test_quality_gates.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.quality import (  # noqa: E402
    CheckResult,
    build_report,
    parse_srt,
    validate_script_rhythm,
    validate_srt,
    verdict,
)

LINE = "验证" * 11  # exactly 22 characters, the 6 s bound at 220 cpm


def _script(**overrides):
    document = {
        "schema": "contentops.script-rhythm/v1",
        "target_seconds": 60,
        "speech_rate_cpm": 220,
        "hook_unit_id": "U01",
        "declared_first_person": False,
        "lines": [{"unit_id": "U01", "text": "结论在前"}] +
                 [{"unit_id": f"U{i:02d}", "text": LINE} for i in range(2, 11)],
    }
    document.update(overrides)
    return document


def _write(td, name, text):
    path = Path(td) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _validate_script(document):
    with tempfile.TemporaryDirectory() as td:
        path = _write(td, "script.json", json.dumps(document, ensure_ascii=False))
        return validate_script_rhythm(path)


# --- report -------------------------------------------------------------

def test_verdict_ranks_fail_over_warn_over_pass():
    assert verdict([CheckResult("a", True)]) == "PASS"
    assert verdict([CheckResult("a", False, "WARN")]) == "WARN"
    assert verdict([CheckResult("a", False, "WARN"), CheckResult("b", False, "FAIL")]) == "FAIL"


def test_report_is_deterministic_and_never_claims_ready():
    checks = [CheckResult("zeta", True), CheckResult("alpha", False, "WARN", "soft")]
    first = build_report("final.mp4", checks)
    second = build_report("final.mp4", list(reversed(checks)))
    assert json.dumps(first, sort_keys=True, ensure_ascii=False) == \
        json.dumps(second, sort_keys=True, ensure_ascii=False)
    assert first["verdict"] == "WARN"
    assert first["production_ready"] is False
    assert first["human_review"] == "PENDING"


def test_report_refuses_a_blank_target():
    try:
        build_report("  ", [])
    except ValueError:
        return
    raise AssertionError("a report without a graded target must be refused")


# --- script rhythm ------------------------------------------------------

def test_a_sayable_script_passes():
    assert _validate_script(_script()) == []


def test_an_over_long_line_is_refused():
    document = _script()
    document["lines"][1]["text"] = "验" * 30
    errors = _validate_script(document)
    assert any("line bound" in message for message in errors), errors


def test_an_over_long_hook_is_refused():
    document = _script()
    document["lines"][0]["text"] = "这是一个明显超过三秒钟的钩子句子内容还要更长"
    errors = _validate_script(document)
    assert any("hook bound" in message for message in errors), errors


def test_template_marketing_language_is_refused():
    document = _script()
    document["lines"][1]["text"] = "家人们一定要看"
    errors = _validate_script(document)
    assert any("template marketing" in message for message in errors), errors


def test_undeclared_first_person_is_refused():
    document = _script()
    document["lines"][1]["text"] = "我验证了这件事"
    errors = _validate_script(document)
    assert any("first person" in message for message in errors), errors


def test_a_script_outside_its_duration_window_is_refused():
    document = _script(lines=[{"unit_id": "U01", "text": "结论在前"}])
    errors = _validate_script(document)
    assert any("outside" in message for message in errors), errors


def test_three_identical_connectives_are_refused():
    document = _script()
    for offset in range(3):
        document["lines"][1 + offset]["text"] = "然后" + "验" * 18
    errors = _validate_script(document)
    assert any("consecutive" in message for message in errors), errors


def test_a_suspense_chain_of_questions_is_refused():
    document = _script()
    for offset in range(8):
        document["lines"][1 + offset]["text"] = "这样真的可行吗？"
    errors = _validate_script(document)
    assert any("suspense chain" in message for message in errors), errors


# --- subtitles ----------------------------------------------------------

VALID_SRT = (
    "1\n00:00:00,000 --> 00:00:02,000\n第一句字幕\n\n"
    "2\n00:00:02,000 --> 00:00:04,000\n第二句字幕\n"
)


def test_parse_and_validate_a_clean_srt():
    with tempfile.TemporaryDirectory() as td:
        path = _write(td, "captions.srt", VALID_SRT)
        assert len(parse_srt(VALID_SRT)) == 2
        assert validate_srt(path) == []


def test_overlapping_cues_are_refused():
    text = (
        "1\n00:00:00,000 --> 00:00:02,000\n第一句字幕\n\n"
        "2\n00:00:01,500 --> 00:00:04,000\n第二句字幕\n"
    )
    with tempfile.TemporaryDirectory() as td:
        errors = validate_srt(_write(td, "captions.srt", text))
    assert any("overlaps" in message for message in errors), errors


def test_an_empty_cue_is_refused():
    text = "1\n00:00:00,000 --> 00:00:02,000\n\n"
    with tempfile.TemporaryDirectory() as td:
        errors = validate_srt(_write(td, "captions.srt", text))
    assert any("empty" in message for message in errors), errors


def test_an_over_long_caption_line_is_refused():
    text = "1\n00:00:00,000 --> 00:00:02,000\n" + "字" * 30 + "\n"
    with tempfile.TemporaryDirectory() as td:
        errors = validate_srt(_write(td, "captions.srt", text))
    assert any("char budget" in message for message in errors), errors


def test_a_file_without_cues_is_refused():
    with tempfile.TemporaryDirectory() as td:
        errors = validate_srt(_write(td, "captions.srt", "not a subtitle\n"))
    assert any("no readable cues" in message for message in errors), errors


def main() -> int:
    tests = (
        test_verdict_ranks_fail_over_warn_over_pass,
        test_report_is_deterministic_and_never_claims_ready,
        test_report_refuses_a_blank_target,
        test_a_sayable_script_passes,
        test_an_over_long_line_is_refused,
        test_an_over_long_hook_is_refused,
        test_template_marketing_language_is_refused,
        test_undeclared_first_person_is_refused,
        test_a_script_outside_its_duration_window_is_refused,
        test_three_identical_connectives_are_refused,
        test_a_suspense_chain_of_questions_is_refused,
        test_parse_and_validate_a_clean_srt,
        test_overlapping_cues_are_refused,
        test_an_empty_cue_is_refused,
        test_an_over_long_caption_line_is_refused,
        test_a_file_without_cues_is_refused,
    )
    failures = []
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
    print("\nAll quality gate tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
