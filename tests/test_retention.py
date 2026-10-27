"""Retention-gate tests.

The gate must catch one visual held too long, missing captions, and a missing
cover/CTA. It is a warning gate, not a taste score.

Run: python tests/test_retention.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.optimization.retention import (  # noqa: E402
    evaluate_retention,
    longest_visual_run,
)


def _storyboard(*durations_and_assets):
    shots = []
    cursor = 0.0
    for duration, asset in durations_and_assets:
        shots.append({"image": asset, "duration": duration})
        cursor += duration
    return {"shots": shots}


def _result(storyboard, **overrides):
    spec = {"account": "test", "cta": "关注", "retention": {"max_static_hold_s": 10, "max_hook_s": 3}}
    spec.update(overrides.pop("spec", {}))
    return evaluate_retention(
        storyboard=storyboard,
        spec=spec,
        captions_burned=overrides.pop("captions_burned", True),
        caption_cues=overrides.pop("caption_cues", 10),
        intro_duration=overrides.pop("intro_duration", 2.5),
        cover_exists=overrides.pop("cover_exists", True),
    )


def test_longest_run_merges_consecutive_same_asset():
    run = longest_visual_run(_storyboard((10, "a"), (5, "a"))["shots"])
    assert run["seconds"] == 15.0
    assert run["asset"] == "a"


def test_longest_run_breaks_on_new_asset():
    run = longest_visual_run(_storyboard((10, "a"), (3, "b"), (4, "b"))["shots"])
    assert run["seconds"] == 10.0


def test_static_hold_over_limit_is_a_warning():
    result = _result(_storyboard((20, "a")))
    assert result["overall"] == "WARN"
    assert "static_hold" in result["failures"]


def test_static_hold_within_limit_passes():
    result = _result(_storyboard((5, "a"), (4, "b")))
    assert result["overall"] == "PASS"
    assert result["failures"] == []


def test_missing_captions_is_a_warning():
    result = _result(_storyboard((5, "a")), captions_burned=False, caption_cues=0)
    assert "captions" in result["failures"]


def test_missing_cover_or_cta_is_a_warning():
    assert "cover" in _result(_storyboard((5, "a")), cover_exists=False)["failures"]
    result = _result(_storyboard((5, "a")), spec={"cta": ""})
    assert "cta" in result["failures"]


def test_long_hook_is_a_warning():
    result = _result(_storyboard((5, "a")), intro_duration=8.0)
    assert "hook_short_enough" in result["failures"]


def main() -> int:
    failures = []
    tests = (
        test_longest_run_merges_consecutive_same_asset,
        test_longest_run_breaks_on_new_asset,
        test_static_hold_over_limit_is_a_warning,
        test_static_hold_within_limit_passes,
        test_missing_captions_is_a_warning,
        test_missing_cover_or_cta_is_a_warning,
        test_long_hook_is_a_warning,
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
    print("\nAll retention tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
