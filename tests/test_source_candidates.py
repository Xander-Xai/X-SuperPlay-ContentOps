"""Source candidate tests.

Run: python tests/test_source_candidates.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.workflow import sources  # noqa: E402
from contentops.workflow.validators import (  # noqa: E402
    source_candidates_validator,
    validators_for,
)


def _candidate(**overrides):
    document = {
        "candidate_id": "SC-001",
        "beat_id": "scene-01",
        "claim_ids": ["C-1"],
        "title": "Open source release page",
        "source_url": "https://example.com/releases",
        "direct_url": "https://example.com/clip.mp4",
        "creator": "Example Project",
        "license": "public_domain",
        "license_text": "CC0 1.0 Universal",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "capture_date": "2026-10-01",
        "status": "candidate",
        "score": {"relevance": 9, "evidence": 8, "rights": 10},
    }
    document.update(overrides)
    return document


def _list(*candidates):
    return {"schema": "contentops.source-candidates/v1",
            "package_id": "pkg", "candidates": list(candidates)}


def _ledger(**overrides):
    asset = {
        "asset_id": "A-1",
        "owner": "Example Project",
        "license": "public_domain",
        "permission_scope": "publishable",
        "source_url": "https://example.com/releases",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "attribution": "Example Project / example.com",
        "source_candidate_id": "SC-001",
    }
    asset.update(overrides)
    return {"schema": "contentops.rights-ledger/v1", "assets": [asset]}


def test_a_complete_candidate_list_passes():
    assert sources.validate_candidates(_list(_candidate())) == []


def test_duplicate_candidate_ids_fail():
    errors = sources.validate_candidates(_list(_candidate(), _candidate()))
    assert any("duplicates" in message for message in errors), errors


def test_a_candidate_list_may_not_clear_itself():
    errors = sources.validate_candidates(_list(_candidate(status="cleared")))
    assert any("status must be 'candidate'" in message for message in errors), errors


def test_a_source_url_must_be_http():
    errors = sources.validate_candidates(_list(_candidate(source_url="example.com/x")))
    assert any("source_url must be an http" in message for message in errors), errors


def test_a_candidate_needs_a_creator():
    errors = sources.validate_candidates(_list(_candidate(creator="")))
    assert any("creator" in message for message in errors), errors


def test_a_non_owned_licence_needs_its_text():
    errors = sources.validate_candidates(_list(_candidate(license_text="")))
    assert any("license_text is required" in message for message in errors), errors


def test_a_non_owned_licence_needs_its_url():
    errors = sources.validate_candidates(_list(_candidate(license_url="")))
    assert any("license_url must be an http" in message for message in errors), errors


def test_an_owned_candidate_needs_no_licence_documents():
    errors = sources.validate_candidates(_list(_candidate(
        license="owned", license_text="", license_url="")))
    assert errors == [], errors


def test_a_capture_date_must_be_a_real_date():
    errors = sources.validate_candidates(_list(_candidate(capture_date="2026-13-01")))
    assert any("capture_date must be YYYY-MM-DD" in message for message in errors), errors


def test_a_future_capture_date_fails():
    errors = sources.validate_candidates(_list(_candidate(capture_date="2099-01-01")))
    assert any("in the future" in message for message in errors), errors


def test_a_score_outside_the_scale_fails():
    errors = sources.validate_candidates(_list(_candidate(
        score={"relevance": 11, "evidence": 8, "rights": 10})))
    assert any("score components" in message for message in errors), errors


def test_the_score_is_the_documented_weighted_average():
    # 9*0.4 + 8*0.4 + 10*0.2 = 8.8
    assert sources.score_of(_candidate()) == 8.8


def test_promotable_lists_an_unknown_licence_as_a_blocker():
    blockers = sources.promotable(
        _list(_candidate(license="unknown", license_text="", license_url="")), "SC-001")
    assert any("license is unknown" in message for message in blockers), blockers


def test_promotable_lists_a_low_score_as_a_blocker():
    blockers = sources.promotable(
        _list(_candidate(score={"relevance": 2, "evidence": 2, "rights": 2})), "SC-001")
    assert any("below the promotion floor" in message for message in blockers), blockers


def test_promotable_passes_a_complete_candidate():
    assert sources.promotable(_list(_candidate()), "SC-001") == []


def test_promotable_refuses_an_unknown_candidate():
    assert sources.promotable(_list(_candidate()), "SC-404")


def test_a_ledger_row_may_descend_from_its_candidate():
    assert sources.validate_ledger_provenance(_ledger(), _list(_candidate())) == []


def test_a_ledger_row_may_have_no_candidate():
    ledger = _ledger()
    ledger["assets"][0].pop("source_candidate_id")
    assert sources.validate_ledger_provenance(ledger, _list(_candidate())) == []


def test_a_licence_disagreement_fails():
    errors = sources.validate_ledger_provenance(
        _ledger(license="licensed"), _list(_candidate()))
    assert any("disagrees with candidate" in message for message in errors), errors


def test_an_unknown_candidate_reference_fails():
    errors = sources.validate_ledger_provenance(_ledger(), _list(_candidate(
        candidate_id="SC-002")))
    assert any("is not in the candidate list" in message for message in errors), errors


def test_assets_stage_runs_the_candidate_validator():
    assert source_candidates_validator in validators_for("assets")


def test_assets_stage_runs_the_provenance_validator():
    from contentops.workflow.validators import ledger_provenance_validator

    assert ledger_provenance_validator in validators_for("assets")


def _assets_stage_errors(ledger, candidates):
    """Run every assets-stage validator the way the gate does."""
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        (folder / "asset-ledger.json").write_text("{}", encoding="utf-8")
        (folder / "rights-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        (folder / "source-candidates.json").write_text(json.dumps(candidates), encoding="utf-8")
        errors = []
        for validator in validators_for("assets"):
            errors.extend(validator(folder / "asset-ledger.json"))
        return errors


def test_the_assets_stage_refuses_a_ledger_that_disagrees_with_its_candidate():
    # The two documents pass on their own; only the cross-check sees this.
    errors = _assets_stage_errors(_ledger(license="owned"), _list(_candidate()))
    assert any("disagrees with candidate" in message for message in errors), errors


def test_the_assets_stage_refuses_a_ledger_citing_an_absent_candidate():
    errors = _assets_stage_errors(_ledger(), _list(_candidate(candidate_id="SC-999")))
    assert any("is not in the candidate list" in message for message in errors), errors


def test_the_assets_stage_passes_a_ledger_that_agrees_with_its_candidate():
    assert _assets_stage_errors(_ledger(), _list(_candidate())) == []


def test_a_nan_score_is_refused():
    errors = sources.validate_candidates(_list(_candidate(
        score={"relevance": float("nan"), "evidence": 8, "rights": 10})))
    assert any("score components" in message for message in errors), errors


def test_promotable_lists_a_missing_licence():
    candidate = _candidate()
    candidate.pop("license")
    blockers = sources.promotable(_list(candidate), "SC-001")
    assert any("is not one of" in message for message in blockers), blockers


def test_promotable_refuses_a_record_that_is_not_a_candidate():
    blockers = sources.promotable(_list(_candidate(status="cleared")), "SC-001")
    assert any("may not promote" in message for message in blockers), blockers


def test_promotable_lists_a_missing_licence_url():
    blockers = sources.promotable(_list(_candidate(license_url="")), "SC-001")
    assert any("license_url is missing" in message for message in blockers), blockers


def test_promotable_lists_an_incomplete_score():
    candidate = _candidate()
    candidate["score"] = {"relevance": 9, "evidence": 8}
    blockers = sources.promotable(_list(candidate), "SC-001")
    assert any("score is incomplete" in message for message in blockers), blockers


def test_a_malformed_candidate_reference_fails():
    errors = sources.validate_ledger_provenance(
        _ledger(source_candidate_id=1), _list(_candidate()))
    assert any("must be a non-empty string" in message for message in errors), errors


def test_a_malformed_url_is_refused_rather_than_raising():
    errors = sources.validate_candidates(_list(_candidate(source_url="https://[::1")))
    assert any("source_url must be an http" in message for message in errors), errors


def test_a_wrong_schema_is_refused():
    document = _list(_candidate())
    document["schema"] = "contentops.something-else/v1"
    errors = sources.validate_candidates(document)
    assert errors and "schema must be" in errors[0], errors


def test_an_empty_candidate_array_is_refused():
    errors = sources.validate_candidates(
        {"schema": "contentops.source-candidates/v1", "candidates": []})
    assert any("non-empty array" in message for message in errors), errors


def test_an_unknown_licence_value_is_refused():
    errors = sources.validate_candidates(_list(_candidate(license="probably-fine")))
    assert any("license must be one of" in message for message in errors), errors


def test_a_direct_url_must_be_http():
    errors = sources.validate_candidates(_list(_candidate(direct_url="file:///c:/x.mp4")))
    assert any("direct_url must be an http" in message for message in errors), errors


def test_claim_ids_must_be_non_empty_strings():
    errors = sources.validate_candidates(_list(_candidate(claim_ids=["C-1", ""])))
    assert any("claim_ids" in message for message in errors), errors


def test_a_document_that_is_not_an_object_is_refused():
    assert sources.validate_candidates([]) == ["source candidates must be a JSON object"]


def test_a_candidate_that_is_not_an_object_is_refused():
    errors = sources.validate_candidates(_list("SC-001"))
    assert any("candidates[0] must be an object" in message for message in errors), errors


def test_a_missing_candidate_id_is_refused():
    candidate = _candidate()
    candidate.pop("candidate_id")
    errors = sources.validate_candidates(_list(candidate))
    assert any("candidate_id must be a non-empty string" in message for message in errors), errors


def test_a_missing_source_url_is_refused():
    candidate = _candidate()
    candidate.pop("source_url")
    errors = sources.validate_candidates(_list(candidate))
    assert any("source_url must name the canonical page" in message for message in errors), errors


def test_a_missing_capture_date_is_refused():
    candidate = _candidate()
    candidate.pop("capture_date")
    errors = sources.validate_candidates(_list(candidate))
    assert any("capture_date must record" in message for message in errors), errors


def test_a_score_that_is_not_an_object_is_refused():
    errors = sources.validate_candidates(_list(_candidate(score=8)))
    assert any("score must be an object" in message for message in errors), errors


def test_promotable_refuses_a_document_without_a_candidate_array():
    blockers = sources.promotable({"schema": sources.SCHEMA}, "SC-001")
    assert any("candidates array" in message for message in blockers), blockers


def test_provenance_refuses_a_ledger_that_is_not_an_object():
    errors = sources.validate_ledger_provenance([], _list(_candidate()))
    assert errors == ["rights ledger must be a JSON object"], errors


def test_provenance_refuses_a_ledger_without_an_asset_array():
    errors = sources.validate_ledger_provenance({"assets": "none"}, _list(_candidate()))
    assert any("assets must be an array" in message for message in errors), errors


def test_provenance_refuses_a_candidate_document_without_an_array():
    errors = sources.validate_ledger_provenance(
        _ledger(), {"schema": sources.SCHEMA, "candidates": "none"})
    assert any("candidates array" in message for message in errors), errors


def test_provenance_skips_an_asset_that_is_not_an_object():
    ledger = _ledger()
    ledger["assets"] = ["A-1", ledger["assets"][0]]
    assert sources.validate_ledger_provenance(ledger, _list(_candidate())) == []


def test_the_assets_stage_reads_a_sibling_candidate_list():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        (folder / "asset-ledger.json").write_text("{}", encoding="utf-8")
        (folder / "source-candidates.json").write_text(
            json.dumps(_list(_candidate())), encoding="utf-8")
        errors = source_candidates_validator(folder / "asset-ledger.json")
        assert errors == [], errors


def main() -> int:
    tests = (
        test_a_complete_candidate_list_passes,
        test_duplicate_candidate_ids_fail,
        test_a_candidate_list_may_not_clear_itself,
        test_a_source_url_must_be_http,
        test_a_candidate_needs_a_creator,
        test_a_non_owned_licence_needs_its_text,
        test_a_non_owned_licence_needs_its_url,
        test_an_owned_candidate_needs_no_licence_documents,
        test_a_capture_date_must_be_a_real_date,
        test_a_future_capture_date_fails,
        test_a_score_outside_the_scale_fails,
        test_the_score_is_the_documented_weighted_average,
        test_promotable_lists_an_unknown_licence_as_a_blocker,
        test_promotable_lists_a_low_score_as_a_blocker,
        test_promotable_passes_a_complete_candidate,
        test_promotable_refuses_an_unknown_candidate,
        test_a_ledger_row_may_descend_from_its_candidate,
        test_a_ledger_row_may_have_no_candidate,
        test_a_licence_disagreement_fails,
        test_an_unknown_candidate_reference_fails,
        test_assets_stage_runs_the_candidate_validator,
        test_assets_stage_runs_the_provenance_validator,
        test_the_assets_stage_refuses_a_ledger_that_disagrees_with_its_candidate,
        test_the_assets_stage_refuses_a_ledger_citing_an_absent_candidate,
        test_the_assets_stage_passes_a_ledger_that_agrees_with_its_candidate,
        test_a_nan_score_is_refused,
        test_promotable_lists_a_missing_licence,
        test_promotable_refuses_a_record_that_is_not_a_candidate,
        test_promotable_lists_a_missing_licence_url,
        test_promotable_lists_an_incomplete_score,
        test_a_malformed_candidate_reference_fails,
        test_a_malformed_url_is_refused_rather_than_raising,
        test_a_wrong_schema_is_refused,
        test_an_empty_candidate_array_is_refused,
        test_an_unknown_licence_value_is_refused,
        test_a_direct_url_must_be_http,
        test_claim_ids_must_be_non_empty_strings,
        test_a_document_that_is_not_an_object_is_refused,
        test_a_candidate_that_is_not_an_object_is_refused,
        test_a_missing_candidate_id_is_refused,
        test_a_missing_source_url_is_refused,
        test_a_missing_capture_date_is_refused,
        test_a_score_that_is_not_an_object_is_refused,
        test_promotable_refuses_a_document_without_a_candidate_array,
        test_provenance_refuses_a_ledger_that_is_not_an_object,
        test_provenance_refuses_a_ledger_without_an_asset_array,
        test_provenance_refuses_a_candidate_document_without_an_array,
        test_provenance_skips_an_asset_that_is_not_an_object,
        test_the_assets_stage_reads_a_sibling_candidate_list,
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
    print("\nAll source candidate tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
