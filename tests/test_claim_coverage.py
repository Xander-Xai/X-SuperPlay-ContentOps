"""Per-claim evidence coverage tests.

Run: python tests/test_claim_coverage.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.evidence.claim_map import ClaimMap  # noqa: E402
from contentops.media.claim_coverage import (  # noqa: E402
    evidence_mode_policy,
    validate_claim_coverage,
)
from contentops.media.cut_plan import CutPlan  # noqa: E402

SHA = "a" * 64


def _evidence(claim_id, kind="terminal_recording"):
    return {
        "evidence_id": f"E-{claim_id}",
        "kind": kind,
        "sha256": SHA,
        "logical_path": "project://work/raw/cap.mp4",
        "permission_scope": "publishable",
    }


def _claim(claim_id, *, kind="runtime", about="cli", status="SUPPORTED",
           limitation="", with_evidence=True):
    item = {
        "claim_id": claim_id,
        "revision": 1,
        "text": f"claim {claim_id}",
        "kind": kind,
        "assertion_about": about,
        "support_status": status,
        "permission_scope": "publishable",
        "limitation": limitation,
        "evidence": [_evidence(claim_id)] if with_evidence else [],
        "appearances": [],
    }
    return item


def _claim_map(*claims):
    return ClaimMap.from_dict({
        "schema": "contentops.claim-map/v1",
        "map_id": "MAP-T",
        "package_id": "pkg",
        "claims": list(claims),
    })


def _placement(pid, asset, claims, *, bearing=True):
    return {
        "placement_id": pid,
        "start_ms": 0,
        "end_ms": 2000,
        "asset_id": asset,
        "source_time_range": "00:00.000-00:02.000",
        "crop": {"x": 0, "y": 0, "width": 1080, "height": 1920,
                 "source_width": 1080, "source_height": 1920},
        "reading_class": "reading",
        "semantic_progress": "shows the result",
        "claim_ids": list(claims),
        "caption_cue_ids": [],
        "claim_bearing": bearing,
        "context_first": False,
        "context_placement_id": None,
        "transition": "cut",
    }


def _cut_plan(*placements):
    return CutPlan.from_dict({
        "schema": "contentops.cut-plan/v1",
        "package_id": "pkg",
        "target": {"width": 1080, "height": 1920, "duration_ms_range": [1000, 5000]},
        "placements": list(placements),
    })


def test_a_supported_claim_backed_by_a_recording_passes():
    result = validate_claim_coverage(
        _cut_plan(_placement("P-1", "A-REAL", ["C-1"])),
        _claim_map(_claim("C-1")),
        {"A-REAL": {"kind": "recording"}},
    )
    assert result.ok, result.errors
    assert result.covered == ["C-1"]


def test_a_supported_claim_shown_only_on_a_card_fails():
    result = validate_claim_coverage(
        _cut_plan(_placement("P-1", "A-CARD", ["C-1"])),
        _claim_map(_claim("C-1")),
        {"A-CARD": {"kind": "card"}},
    )
    assert not result.ok
    assert any("non-evidence" in message for message in result.errors), result.errors


def test_a_blocked_claim_may_not_be_cited():
    result = validate_claim_coverage(
        _cut_plan(_placement("P-1", "A-REAL", ["C-1"])),
        # A judgement claim carries no CLI/UI evidence requirement, so this is a
        # valid BLOCKED claim; our gate still refuses to cite it.
        _claim_map(_claim("C-1", kind="judgement", about="none",
                          status="BLOCKED", with_evidence=False)),
        {"A-REAL": {"kind": "recording"}},
    )
    assert not result.ok
    assert any("BLOCKED" in message for message in result.errors), result.errors


def test_a_partial_factual_claim_may_not_carry_a_video_beat():
    result = validate_claim_coverage(
        _cut_plan(_placement("P-1", "A-REAL", ["C-1"])),
        _claim_map(_claim("C-1", status="PARTIAL", limitation="only on Windows")),
        {"A-REAL": {"kind": "recording"}},
    )
    assert not result.ok
    assert any("PARTIAL" in message for message in result.errors), result.errors


def test_an_unknown_claim_id_fails():
    result = validate_claim_coverage(
        _cut_plan(_placement("P-1", "A-REAL", ["C-404"])),
        _claim_map(_claim("C-1")),
        {"A-REAL": {"kind": "recording"}},
    )
    assert not result.ok
    assert any("unknown claim" in message for message in result.errors), result.errors


def test_a_judgement_beat_is_allowed_without_real_capture():
    result = validate_claim_coverage(
        _cut_plan(_placement("P-1", "A-CARD", ["C-1"])),
        _claim_map(_claim("C-1", kind="judgement", about="judgement",
                          status="PARTIAL", limitation="my read of the evidence")),
        {"A-CARD": {"kind": "card"}},
    )
    assert result.ok, result.errors


def test_a_supported_claim_that_never_appears_is_reported_not_failed():
    result = validate_claim_coverage(
        _cut_plan(_placement("P-1", "A-REAL", [], bearing=False)),
        _claim_map(_claim("C-1")),
        {"A-REAL": {"kind": "recording"}},
    )
    assert result.ok, result.errors
    assert result.uncovered == ["C-1"]
    assert any("never appears" in message for message in result.warnings)


def test_a_claim_bearing_placement_without_claims_fails():
    # CutPlan.validate already refuses this shape, so this exercises the
    # defensive rule for a plan built by another path.
    plan = SimpleNamespace(placements=[
        SimpleNamespace(placement_id="P-1", asset_id="A-REAL",
                        claim_ids=[], claim_bearing=True, shots=[]),
    ])
    result = validate_claim_coverage(
        plan,
        _claim_map(_claim("C-1")),
        {"A-REAL": {"kind": "recording"}},
    )
    assert not result.ok
    assert any("cites no claim" in message for message in result.errors)


def test_duplicate_claim_ids_are_a_warning():
    result = validate_claim_coverage(
        _cut_plan(_placement("P-1", "A-REAL", ["C-1", "C-1"])),
        _claim_map(_claim("C-1")),
        {"A-REAL": {"kind": "recording"}},
    )
    assert result.ok, result.errors
    assert any("duplicate" in message for message in result.warnings)


def test_asset_map_is_optional_for_structural_checks():
    result = validate_claim_coverage(
        _cut_plan(_placement("P-1", "A-CARD", ["C-1"])),
        _claim_map(_claim("C-1")),
        None,
    )
    assert result.ok, result.errors


def test_storyboard_validator_passes_with_sibling_files():
    from contentops.workflow.validators import claim_coverage_validator

    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        (folder / "cut-plan.json").write_text(json.dumps({
            "schema": "contentops.cut-plan/v1", "package_id": "pkg",
            "target": {"width": 1080, "height": 1920, "duration_ms_range": [1000, 5000]},
            "placements": [_placement("P-1", "A-REAL", ["C-1"])],
        }), encoding="utf-8")
        (folder / "claim-map.json").write_text(json.dumps({
            "schema": "contentops.claim-map/v1", "map_id": "MAP-T", "package_id": "pkg",
            "claims": [_claim("C-1")],
        }), encoding="utf-8")
        (folder / "assets.json").write_text(json.dumps({
            "schema": "contentops.asset-map/v1",
            "assets": {"A-REAL": {"kind": "recording"}},
        }), encoding="utf-8")
        assert claim_coverage_validator(folder / "cut-plan.json") == []


def test_storyboard_validator_reports_a_missing_claim_map():
    from contentops.workflow.validators import claim_coverage_validator

    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        (folder / "cut-plan.json").write_text(json.dumps({
            "schema": "contentops.cut-plan/v1", "package_id": "pkg",
            "target": {"width": 1080, "height": 1920, "duration_ms_range": [1000, 5000]},
            "placements": [_placement("P-1", "A-REAL", ["C-1"])],
        }), encoding="utf-8")
        errors = claim_coverage_validator(folder / "cut-plan.json")
        assert any("claim-map.json missing" in message for message in errors), errors


def test_stage_validators_are_wired_to_the_contract():
    from contentops.workflow.validators import (
        candidate_validator,
        claim_coverage_validator,
        forecast_validator,
        script_rhythm_validator,
        validators_for,
    )

    assert script_rhythm_validator in validators_for("script")
    assert claim_coverage_validator in validators_for("storyboard")
    assert candidate_validator in validators_for("brief")
    assert forecast_validator in validators_for("brief")


def test_evidence_mode_policy_is_explicit():
    assert evidence_mode_policy("EVIDENCE_LED")["ratio_severity"] == "FAIL"
    assert evidence_mode_policy("EVIDENCE_LED")["require_claim_coverage"] is False
    assert evidence_mode_policy("CLAIM_LED")["ratio_severity"] == "WARN"
    assert evidence_mode_policy("CLAIM_LED")["require_claim_coverage"] is True
    assert evidence_mode_policy("EXPLANATORY")["ratio_severity"] == "INFO"
    try:
        evidence_mode_policy("SOMETHING_ELSE")
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown evidence mode must be refused")


def main() -> int:
    tests = (
        test_a_supported_claim_backed_by_a_recording_passes,
        test_a_supported_claim_shown_only_on_a_card_fails,
        test_a_blocked_claim_may_not_be_cited,
        test_a_partial_factual_claim_may_not_carry_a_video_beat,
        test_an_unknown_claim_id_fails,
        test_a_judgement_beat_is_allowed_without_real_capture,
        test_a_supported_claim_that_never_appears_is_reported_not_failed,
        test_a_claim_bearing_placement_without_claims_fails,
        test_duplicate_claim_ids_are_a_warning,
        test_asset_map_is_optional_for_structural_checks,
        test_storyboard_validator_passes_with_sibling_files,
        test_storyboard_validator_reports_a_missing_claim_map,
        test_stage_validators_are_wired_to_the_contract,
        test_evidence_mode_policy_is_explicit,
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
    print("\nAll claim coverage tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
