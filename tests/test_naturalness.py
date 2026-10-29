"""Naturalness and caption-integrity tests.

Run: python tests/test_naturalness.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.quality.naturalness import metrics, validate_naturalness  # noqa: E402
from contentops.quality.subtitle import (  # noqa: E402
    normalize_spoken,
    validate_caption_agreement,
)
import check_caption_text  # noqa: E402


def _doc(**overrides):
    document = {
        "schema": "contentops.naturalness/v1",
        "narrative_voice": "controlled-colloquial",
        "colloquial_budget": 2,
        "max_consecutive": 1,
        "allowed_human_touches": ["direct_address", "short_pause"],
        "fact_lock_tokens": ["v0.2.1"],
        "source_text": "这个版本是 v0.2.1。",
        "humanized_text": "这次装的是 v0.2.1。",
        "lines": [
            {"unit_id": "U01", "text": "这个版本是 v0.2.1。", "human_touch": "none"},
            {"unit_id": "U02", "text": "你先看结果。", "human_touch": "direct_address",
             "delivery_note": "看着镜头"},
        ],
    }
    document.update(overrides)
    return document


def _codes(errors):
    return " | ".join(errors)


def test_a_bounded_script_passes():
    assert validate_naturalness(_doc()) == []


def test_controlled_colloquial_must_declare_a_budget():
    errors = validate_naturalness(_doc(colloquial_budget=None))
    assert any("colloquial_budget" in message for message in errors), _codes(errors)


def test_controlled_colloquial_must_declare_allowed_touches():
    errors = validate_naturalness(_doc(allowed_human_touches=[]))
    assert any("which human touches it allows" in message for message in errors), _codes(errors)


def test_an_undeclared_touch_is_refused():
    document = _doc()
    document["lines"][1]["human_touch"] = "aside"
    errors = validate_naturalness(document)
    assert any("undeclared human touch" in message for message in errors), _codes(errors)


def test_a_touch_needs_a_delivery_note():
    document = _doc()
    document["lines"][1]["delivery_note"] = ""
    errors = validate_naturalness(document)
    assert any("delivery_note" in message for message in errors), _codes(errors)


def test_the_budget_is_enforced():
    errors = validate_naturalness(_doc(colloquial_budget=0))
    assert any("exceeds budget" in message for message in errors), _codes(errors)


def test_consecutive_touches_are_enforced():
    document = _doc(colloquial_budget=5, max_consecutive=1)
    document["lines"][0]["human_touch"] = "direct_address"
    document["lines"][0]["delivery_note"] = "看着镜头"
    errors = validate_naturalness(document)
    assert any("consecutive human touches" in message for message in errors), _codes(errors)


def test_a_filler_that_became_a_tic_is_refused():
    document = _doc(colloquial_budget=5, max_consecutive=5)
    document["lines"][0]["text"] = "其实这个版本是 v0.2.1，其实也没变，其实一样。"
    errors = validate_naturalness(document)
    assert any("filler" in message for message in errors), _codes(errors)


def test_a_fact_lock_cannot_be_invented():
    errors = validate_naturalness(_doc(fact_lock_tokens=["v9.9.9"]))
    assert any("not present in the source" in message for message in errors), _codes(errors)


def test_a_rewrite_may_not_drop_a_fact_lock():
    errors = validate_naturalness(_doc(humanized_text="这次装了一个新版本。"))
    assert any("dropped fact-lock tokens" in message for message in errors), _codes(errors)


def test_a_fact_lock_without_source_is_refused():
    errors = validate_naturalness(_doc(source_text=""))
    assert any("without the source_text" in message for message in errors), _codes(errors)


def test_duplicate_unit_ids_are_refused():
    document = _doc()
    document["lines"][1]["unit_id"] = "U01"
    errors = validate_naturalness(document)
    assert any("duplicate unit_id" in message for message in errors), _codes(errors)


def test_metrics_report_the_numbers_a_receipt_cites():
    numbers = metrics(_doc())
    assert numbers["line_count"] == 2
    assert numbers["touch_count"] == 1
    assert numbers["longest_touch_streak"] == 1


def _srt(*cues):
    blocks = []
    for index, (start, end, text) in enumerate(cues, start=1):
        blocks.append(f"{index}\n{start} --> {end}\n{text}")
    return "\n\n".join(blocks) + "\n"


def test_normalize_ignores_punctuation_spacing_and_pause_markers():
    assert normalize_spoken("先跑 <#0.5#> 一次。") == normalize_spoken("先跑一次")


def test_a_caption_that_transcribes_the_narration_passes():
    with tempfile.TemporaryDirectory() as td:
        srt = Path(td) / "default.srt"
        srt.write_text(_srt(("00:00:00,000", "00:00:02,000", "先跑一次，"),
                            ("00:00:02,000", "00:00:04,000", "再看结果。")), encoding="utf-8")
        assert validate_caption_agreement(srt, "先跑一次，再看结果。") == []


def test_a_stale_caption_is_refused():
    with tempfile.TemporaryDirectory() as td:
        srt = Path(td) / "default.srt"
        srt.write_text(_srt(("00:00:00,000", "00:00:02,000", "先跑一次，"),
                            ("00:00:02,000", "00:00:04,000", "再看版本。")), encoding="utf-8")
        errors = validate_caption_agreement(srt, "先跑一次，再看结果。")
        assert errors and "does not transcribe" in errors[0], errors


def test_an_empty_narration_cannot_agree_with_anything():
    with tempfile.TemporaryDirectory() as td:
        srt = Path(td) / "default.srt"
        srt.write_text(_srt(("00:00:00,000", "00:00:02,000", "先跑一次")), encoding="utf-8")
        errors = validate_caption_agreement(srt, "")
        assert errors and "empty" in errors[0], errors


def test_caption_cli_exit_codes():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        srt = folder / "default.srt"
        srt.write_text(_srt(("00:00:00,000", "00:00:02,000", "先跑一次，"),
                            ("00:00:02,000", "00:00:04,000", "再看结果。")), encoding="utf-8")
        good = folder / "good.txt"
        good.write_text("先跑一次，再看结果。\n", encoding="utf-8")
        bad = folder / "bad.txt"
        bad.write_text("先跑一次，再看版本。\n", encoding="utf-8")
        assert check_caption_text.main(["--srt", str(srt), "--narration", str(good)]) == 0
        assert check_caption_text.main(["--srt", str(srt), "--narration", str(bad)]) == 1


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
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
    print("\nAll naturalness tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
