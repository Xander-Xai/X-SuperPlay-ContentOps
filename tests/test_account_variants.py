"""Two-account variant policy tests.

One source, two native assets:
  1024 opens on the conflict and re-orders complete units.
  Future Intelligence keeps the full eight-unit engineering walkthrough.
Both stop at PENDING_FOUNDER_REVIEW and claim no publication URL.

Run: python tests/test_account_variants.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "projects"
EXPLORE = PROJECTS / "x-superplay-1024"
BUILD = PROJECTS / "x-superplay-future-intelligence"


def _receipt(slug: Path) -> dict:
    return json.loads((slug / "receipts" / "variant-receipt.json").read_text(encoding="utf-8"))


def _publish(slug: Path) -> dict:
    return json.loads((slug / "receipts" / "publish-package.json").read_text(encoding="utf-8"))


def _storyboard(slug: Path) -> dict:
    return json.loads((slug / "script" / "storyboard.json").read_text(encoding="utf-8"))


def test_each_account_has_a_receipt_and_package():
    for slug in (EXPLORE, BUILD):
        assert (slug / "receipts" / "variant-receipt.json").is_file()
        assert (slug / "receipts" / "publish-package.json").is_file()
        assert (slug / "script" / "storyboard.json").is_file()


def test_one_source_feeds_both_accounts():
    explore = _receipt(EXPLORE)["source"]
    build = _receipt(BUILD)["source"]
    assert explore["narration"] == build["narration"]
    assert explore["narration"].endswith("founder-v3-full/narration.wav")


def test_1024_is_a_complete_unit_reorder_not_a_mid_sentence_cut():
    units = _receipt(EXPLORE)["source"]["units"]
    assert units == ["U05", "U06", "U01", "U07", "U08"]
    assert len(units) == len(set(units)), "a unit was used twice"
    assert units[0].startswith("U"), "must open on a complete unit"
    assert set(units) <= {f"U{i:02d}" for i in range(1, 9)}


def test_future_intelligence_keeps_the_full_order():
    units = _receipt(BUILD)["source"]["units"]
    assert units == [f"U{i:02d}" for i in range(1, 9)]


def test_explore_opens_on_the_conflict_card():
    shots = _storyboard(EXPLORE)["shots"]
    assert shots[0]["placement"] == "shot_03", shots[0]
    assert shots[0]["unit"] == "U05"
    assert "editorial-1024" in shots[0]["image"]


def test_build_uses_the_full_editorial_card_set():
    shots = _storyboard(BUILD)["shots"]
    assert len(shots) == 8
    assert {shot["unit"] for shot in shots} == {f"U{i:02d}" for i in range(1, 9)}


def test_neither_account_claims_publication():
    for slug in (EXPLORE, BUILD):
        receipt = _receipt(slug)
        package = _publish(slug)
        assert receipt["production_ready"] is False
        assert receipt["human_review"] == "PENDING_FOUNDER_REVIEW"
        assert package["publish_status"] == "NOT_PUBLISHED"
        assert package["human_review"] == "PENDING_FOUNDER_REVIEW"
        assert package.get("url") is None, "no URL may be claimed before publishing"


def test_build_has_the_horizontal_derivative_and_explore_does_not():
    build = _publish(BUILD)
    explore = _publish(EXPLORE)
    assert any(asset["width"] == 1920 and asset["height"] == 1080
               for asset in build.get("derived_assets", []))
    assert explore.get("derived_assets") == []


def main() -> int:
    failures = []
    tests = (
        test_each_account_has_a_receipt_and_package,
        test_one_source_feeds_both_accounts,
        test_1024_is_a_complete_unit_reorder_not_a_mid_sentence_cut,
        test_future_intelligence_keeps_the_full_order,
        test_explore_opens_on_the_conflict_card,
        test_build_uses_the_full_editorial_card_set,
        test_neither_account_claims_publication,
        test_build_has_the_horizontal_derivative_and_explore_does_not,
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
    print("\nAll account variant tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
