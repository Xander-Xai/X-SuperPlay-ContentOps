"""Redaction lineage contract tests.

Run: python tests/test_evidence_redaction.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.evidence.redaction import RedactionReceipt  # noqa: E402
from contentops.evidence._common import ContractError  # noqa: E402

RAW = "a" * 64
OUT = "b" * 64


def base(**overrides):
    document = {
        "schema": "contentops.redaction-transform/v1",
        "redaction_id": "RED-20261027-001",
        "raw_source": {"logical_path": "project://work/raw/cap.mp4", "sha256": RAW},
        "output": {"logical_path": "project://work/redacted/cap.mp4", "sha256": OUT},
        "source_dimensions": {"width": 1100, "height": 700},
        "masks": [{
            "mask_id": "M1",
            "reason": "account name in the title bar",
            "time_range": "00:00.000-00:04.000",
            "rect": {"x": 0, "y": 0, "width": 300, "height": 40},
        }],
        "audio_policy": "REMOVED",
        "audio_removed": True,
        "tool": {"name": "ffmpeg", "version": "8.1.1"},
        "review_status": "APPROVED",
        "reviewer": "Founder",
        "reviewed_at": "2026-10-27T12:00:00Z",
        "publishable_scope": True,
        "notes": [],
    }
    document.update(overrides)
    return document


def rejects(code, **overrides):
    try:
        RedactionReceipt.from_dict(base(**overrides))
    except ContractError as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(f"a receipt with {overrides} was accepted")


def test_a_reviewed_derivative_links_to_its_raw_source():
    receipt = RedactionReceipt.from_dict(base())
    assert receipt.audio_removed is True
    assert receipt.masks[0]["mask_id"] == "M1"
    assert receipt.to_dict()["raw_source"]["sha256"] == RAW
    print("[ok] a reviewed derivative is linked to its raw source")


def test_the_raw_source_is_never_overwritten_or_aliased():
    rejects("RAW_EQUALS_OUTPUT", output={
        "logical_path": "project://work/redacted/cap.mp4", "sha256": RAW})
    rejects("RAW_OVERWRITTEN", output={
        "logical_path": "project://work/raw/cap.mp4", "sha256": OUT})
    print("[ok] raw == output, by hash or by path, is refused")


def test_a_mask_must_stay_inside_the_source_frame():
    for rect in (
        {"x": 900, "y": 0, "width": 300, "height": 40},
        {"x": 0, "y": 690, "width": 300, "height": 40},
        {"x": 0, "y": 0, "width": 0, "height": 40},
    ):
        rejects("MASK_OUT_OF_BOUNDS" if rect["width"] else "INVALID_MASK",
                masks=[{"mask_id": "M1", "reason": "x",
                        "time_range": "00:00.000-00:02.000", "rect": rect}])
    print("[ok] masks outside the source frame or with zero area are refused")


def test_a_publishable_derivative_needs_approval_and_no_audio():
    rejects("REVIEW_NOT_APPROVED", review_status="PENDING")
    rejects("AUDIO_RETAINED", audio_policy="KEPT_APPROVED", audio_removed=False)

    internal = RedactionReceipt.from_dict(base(
        publishable_scope=False, review_status="PENDING",
        audio_policy="KEPT_APPROVED", audio_removed=False,
        reviewer=None, reviewed_at=None,
    ))
    assert internal.publishable_scope is False
    print("[ok] publishable requires APPROVED review and removed audio")


def test_audio_state_cannot_contradict_the_policy():
    rejects("AUDIO_STATE_CONTRADICTION", audio_removed=False)
    print("[ok] audio_removed disagreeing with audio_policy is refused")


def test_duplicate_and_malformed_masks_are_refused():
    mask = {"mask_id": "M1", "reason": "x",
            "time_range": "00:00.000-00:02.000",
            "rect": {"x": 0, "y": 0, "width": 10, "height": 10}}
    rejects("DUPLICATE_MASK_ID", masks=[mask, dict(mask)])
    rejects("INVALID_TIME_RANGE", masks=[{**mask, "time_range": "00:02.000-00:02.000"}])
    rejects("UNKNOWN_FIELD", extra="x")
    print("[ok] duplicate masks, empty ranges and unknown fields are refused")


def main() -> int:
    failures = []
    tests = (
        test_a_reviewed_derivative_links_to_its_raw_source,
        test_the_raw_source_is_never_overwritten_or_aliased,
        test_a_mask_must_stay_inside_the_source_frame,
        test_a_publishable_derivative_needs_approval_and_no_audio,
        test_audio_state_cannot_contradict_the_policy,
        test_duplicate_and_malformed_masks_are_refused,
    )
    for fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(tests)} redaction tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
