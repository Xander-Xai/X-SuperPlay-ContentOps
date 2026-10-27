"""CutPlan contract tests.

Run: python tests/test_cut_plan.py
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.media.cut_plan import CutPlan  # noqa: E402
from contentops.evidence.claim_map import ClaimMap  # noqa: E402
from contentops.evidence._common import ContractError  # noqa: E402

SHA = "a" * 64


def placement(placement_id, start, end, **overrides):
    item = {
        "placement_id": placement_id,
        "start_ms": start,
        "end_ms": end,
        "asset_id": "A-001",
        "source_time_range": "00:01.000-00:06.000",
        "crop": {"x": 0, "y": 0, "width": 1080, "height": 1920,
                 "source_width": 1100, "source_height": 2000},
        "reading_class": "non_reading",
        "semantic_progress": "shows the failing check",
        "claim_ids": ["C-001"],
        "caption_cue_ids": [],
        "claim_bearing": True,
        "context_first": False,
        "context_placement_id": None,
        "transition": "cut",
    }
    item.update(overrides)
    return item


def document(placements=None, target=None):
    return {
        "schema": "contentops.cut-plan/v1",
        "package_id": "easel-1024-proof",
        "target": target or {
            "width": 1080,
            "height": 1920,
            "duration_ms_range": [4000, 9000],
            "caption_safe_area": {"x": 54, "y": 1500, "width": 972, "height": 300},
            "min_reading_hold_ms": 2000,
        },
        "placements": placements if placements is not None else [
            placement("P-001", 0, 3000, reading_class="reading",
                      caption_cue_ids=["cue-001"]),
            placement("P-002", 3000, 8000, caption_cue_ids=["cue-002"]),
        ],
    }


def fixed(**overrides):
    doc = document()
    doc["schema"] = "contentops.cut-plan/v1"
    doc.update(overrides)
    return doc


def rejects(code, **overrides):
    try:
        CutPlan.from_dict(fixed(**overrides))
    except ContractError as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(f"a cut plan with {overrides} was accepted")


def test_a_valid_cut_plan_is_accepted():
    plan = CutPlan.from_dict(fixed())
    assert plan.claim_ids() == {"C-001"}
    assert plan.to_dict()["placements"][0]["start_ms"] == 0
    print("[ok] a monotonic cut plan with a safe area is accepted")


def test_overlapping_and_duplicate_placements_are_refused():
    rejects("OVERLAPPING_PLACEMENTS", placements=[
        placement("P-001", 0, 4000),
        placement("P-002", 3000, 8000),
    ])
    rejects("DUPLICATE_PLACEMENT_ID", placements=[
        placement("P-001", 0, 4000),
        placement("P-001", 4000, 8000),
    ])
    print("[ok] overlapping ranges and duplicate ids are refused")


def test_the_cut_must_match_its_target_duration():
    rejects("CUT_TOO_SHORT", placements=[placement("P-001", 0, 3000)])
    rejects("CUT_TOO_LONG", target={
        "width": 1080, "height": 1920,
        "duration_ms_range": [1000, 4000],
    })
    print("[ok] a cut outside its declared duration range is refused")


def test_a_crop_must_stay_inside_its_source():
    rejects("CROP_OUT_OF_BOUNDS", placements=[placement(
        "P-001", 0, 4000,
        crop={"x": 100, "y": 0, "width": 1080, "height": 1920,
              "source_width": 1100, "source_height": 2000})])
    rejects("CROP_OUT_OF_BOUNDS", placements=[placement(
        "P-001", 0, 4000,
        crop={"x": 0, "y": 900, "width": 1080, "height": 1920,
              "source_width": 1100, "source_height": 2000})])
    print("[ok] a crop outside its source frame is refused")


def test_context_must_precede_the_crop_and_share_its_asset():
    rejects("CONTEXT_AFTER_CROP", placements=[
        placement("P-001", 0, 4000, context_first=True,
                  context_placement_id="P-002"),
        placement("P-002", 4000, 8000),
    ])
    rejects("CONTEXT_ASSET_MISMATCH", placements=[
        placement("P-001", 0, 4000),
        placement("P-002", 4000, 8000, asset_id="A-002", context_first=True,
                  context_placement_id="P-001"),
    ])
    rejects("UNKNOWN_CONTEXT_PLACEMENT", placements=[
        placement("P-001", 0, 4000, context_first=True,
                  context_placement_id="P-999"),
    ])
    good = CutPlan.from_dict(fixed(placements=[
        placement("P-001", 0, 4000),
        placement("P-002", 4000, 8000, context_first=True,
                  context_placement_id="P-001"),
    ]))
    assert good.placements[1].context_first is True
    print("[ok] context must be earlier and from the same asset")


def test_claims_cues_and_assets_must_be_declared():
    rejects("CLAIM_BEARING_WITHOUT_CLAIM", placements=[
        placement("P-001", 0, 8000, claim_ids=[])])
    rejects("DUPLICATE_CAPTION_CUE", placements=[
        placement("P-001", 0, 4000, caption_cue_ids=["cue-1"]),
        placement("P-002", 4000, 8000, caption_cue_ids=["cue-1"]),
    ])
    plan = CutPlan.from_dict(fixed())

    claim_map = ClaimMap.from_dict({
        "schema": "contentops.claim-map/v1",
        "map_id": "MAP-001",
        "package_id": "easel-1024-proof",
        "claims": [{
            "claim_id": "C-001", "revision": 1, "text": "x",
            "kind": "runtime", "assertion_about": "cli",
            "support_status": "SUPPORTED", "permission_scope": "publishable",
            "evidence": [{"evidence_id": "E-001", "kind": "terminal_recording",
                          "sha256": SHA, "logical_path": "project://a.mp4",
                          "permission_scope": "publishable"}],
            "appearances": [],
        }],
    })
    plan.validate_claims(claim_map)

    bad_map = copy.deepcopy(claim_map)
    bad_map.claims[0].claim_id = "C-999"
    try:
        plan.validate_claims(bad_map)
    except ContractError as exc:
        assert exc.code == "UNKNOWN_CLAIM", exc
    else:
        raise AssertionError("an unknown claim id was accepted")

    try:
        plan.validate_assets(["A-404"])
    except ContractError as exc:
        assert exc.code == "UNKNOWN_ASSET", exc
    else:
        raise AssertionError("an unknown asset id was accepted")
    print("[ok] claims, caption cues and assets must resolve")


def test_a_reading_hold_shorter_than_the_policy_is_refused():
    rejects("READING_HOLD_TOO_SHORT", placements=[
        placement("P-001", 0, 1000, reading_class="reading"),
        placement("P-002", 1000, 8000),
    ])
    print("[ok] a reading hold below the declared minimum is refused")


def test_the_safe_area_must_fit_the_frame():
    rejects("INVALID_TARGET", target={
        "width": 1080, "height": 1920,
        "duration_ms_range": [4000, 9000],
        "caption_safe_area": {"x": 100, "y": 1500, "width": 1080, "height": 300},
    })
    print("[ok] a caption safe area outside the frame is refused")


def test_the_fingerprint_changes_when_a_placement_moves():
    original = CutPlan.from_dict(fixed())
    moved = CutPlan.from_dict(fixed(placements=[
        placement("P-001", 0, 3500, reading_class="reading",
                  caption_cue_ids=["cue-001"]),
        placement("P-002", 3500, 8000, caption_cue_ids=["cue-002"]),
    ]))
    assert original.fingerprint() != moved.fingerprint()
    print("[ok] the cut-plan fingerprint changes when timing changes")


def main() -> int:
    failures = []
    tests = (
        test_a_valid_cut_plan_is_accepted,
        test_overlapping_and_duplicate_placements_are_refused,
        test_the_cut_must_match_its_target_duration,
        test_a_crop_must_stay_inside_its_source,
        test_context_must_precede_the_crop_and_share_its_asset,
        test_claims_cues_and_assets_must_be_declared,
        test_a_reading_hold_shorter_than_the_policy_is_refused,
        test_the_safe_area_must_fit_the_frame,
        test_the_fingerprint_changes_when_a_placement_moves,
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
    print(f"\nAll {len(tests)} cut-plan tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
