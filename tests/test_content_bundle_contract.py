"""Content Bundle consumption contract tests.

The Bundle belongs to Strategy. These tests only prove that a consumer fails
closed on an incomplete or unsafe record.

Run: python tests/test_content_bundle_contract.py
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.content_kernel import (  # noqa: E402
    BundleError,
    consumption_summary,
    load_bundle,
    validate_bundle,
)


def _valid() -> dict:
    return {
        "schema_version": 1,
        "record_type": "content_bundle",
        "bundle_id": "CB-20261101-001",
        "created_at": "2026-11-01T09:00:00+08:00",
        "status": "draft",
        "source": {
            "source_id": "SRC-20261101-001",
            "source_refs": ["repo://X-SuperPlay-ContentOps"],
            "topic_thesis": "Platform placeholders prevent false integration claims",
            "claim_refs": [],
            "permission_refs": [],
            "proof_level": "documented",
        },
        "account_treatments": {
            "explorer": {
                "strategy_account": "account-a",
                "role": "Explore",
                "narrative_angle": "the defect",
                "key_claims": [],
                "cta_intent": None,
                "production_lane": "baseline",
                "execution_profile_hint": "default",
            }
        },
        "asset_requirements": [
            {
                "requirement_id": "AR-001",
                "claim_refs": ["CLM-001"],
                "capability": "real_capture",
                "evidence_role": "direct_evidence",
                "required": True,
                "account_scope": [],
                "platform_scope": [],
                "acceptance": None,
                "fallback_capabilities": [],
            }
        ],
        "assets": {
            "real_evidence_refs": [],
            "reusable_asset_refs": [],
            "generated_asset_refs": [],
            "manual_premium_asset_refs": [],
            "canonical_master_refs": [],
        },
        "aigc_provenance": {
            "required": True,
            "asset_manifest_refs": [],
            "disclosure_review_status": "pending",
        },
        "content_experiments": {"refs": []},
        "platform_adapters": {"refs": []},
        "execution_pointers": [],
        "metric_and_signal_pointers": {
            "metric_snapshot_refs": [],
            "market_signal_refs": [],
            "review_refs": [],
        },
        "invariants": {
            "production_lane_is_strategy_capacity_routing": True,
            "execution_profile_hint_is_not_child_runtime_contract": True,
            "asset_requirement_precedes_provider_resolution": True,
            "asset_requirement_claim_binding_required_for_direct_evidence": True,
            "downstream_records_should_preserve_bundle_id": True,
            "source_is_not_validated_demand": True,
            "bundle_is_not_published_content": True,
            "generated_media_is_not_direct_evidence": True,
            "platform_adaptation_must_not_change_facts": True,
            "credentials_must_not_cross_repository_boundaries": True,
            "business_source_of_truth": "private-business-repo",
            "implementation_source_of_truth": "private-strategy-repo",
        },
    }


def _assert_fails(document, needle):
    failures = validate_bundle(document)
    assert failures, "expected a failure, got none"
    assert any(needle in failure for failure in failures), f"expected {needle!r} in {failures}"


def test_a_complete_bundle_is_consumable():
    assert validate_bundle(_valid()) == []


def test_bundle_without_a_thesis_is_refused():
    document = _valid()
    document["source"]["topic_thesis"] = None
    _assert_fails(document, "topic_thesis is required")


def test_bundle_id_shape_is_enforced():
    document = _valid()
    document["bundle_id"] = "CB-1"
    _assert_fails(document, "bundle_id")


def test_unknown_account_treatment_is_refused():
    document = _valid()
    document["account_treatments"]["third-account"] = document["account_treatments"]["explorer"]
    _assert_fails(document, "not one of")


def test_production_lane_uses_strategy_vocabulary():
    document = _valid()
    document["account_treatments"]["explorer"]["production_lane"] = "BASELINE"
    _assert_fails(document, "production_lane")


def test_execution_profile_hint_uses_the_template_vocabulary():
    document = _valid()
    document["account_treatments"]["explorer"]["execution_profile_hint"] = "strict"
    _assert_fails(document, "execution_profile_hint")


def test_direct_evidence_must_be_bound_to_a_claim():
    document = _valid()
    document["asset_requirements"][0]["claim_refs"] = []
    _assert_fails(document, "no claim_refs")


def test_unknown_capability_is_refused():
    document = _valid()
    document["asset_requirements"][0]["capability"] = "stock_footage"
    _assert_fails(document, "capability")


def test_missing_invariant_is_refused():
    document = _valid()
    document["invariants"].pop("bundle_is_not_published_content")
    _assert_fails(document, "bundle_is_not_published_content")


def test_credential_shaped_field_is_refused():
    document = _valid()
    document["execution_pointers"] = [{"platform": "x", "api_key": "nope"}]
    _assert_fails(document, "credential field")


def test_summary_never_claims_publication():
    summary = consumption_summary(_valid())
    assert summary["is_published"] is False
    assert summary["accounts"] == ["explorer"]
    assert summary["production_lanes"] == {"explorer": "baseline"}


def test_loader_reads_json_and_refuses_an_empty_file():
    tmp = Path(tempfile.mkdtemp(prefix="contentops-bundle-"))
    good = tmp / "bundle.json"
    good.write_text(json.dumps(_valid(), ensure_ascii=False), encoding="utf-8")
    assert load_bundle(good)["bundle_id"] == "CB-20261101-001"

    empty = tmp / "empty.json"
    empty.write_text("   ", encoding="utf-8")
    try:
        load_bundle(empty)
    except BundleError as exc:
        assert exc.code == "BUNDLE_EMPTY"
    else:
        raise AssertionError("expected BundleError BUNDLE_EMPTY")


def test_validation_does_not_mutate_the_document():
    document = _valid()
    before = copy.deepcopy(document)
    validate_bundle(document)
    assert document == before


def main() -> int:
    tests = (
        test_a_complete_bundle_is_consumable,
        test_bundle_without_a_thesis_is_refused,
        test_bundle_id_shape_is_enforced,
        test_unknown_account_treatment_is_refused,
        test_production_lane_uses_strategy_vocabulary,
        test_execution_profile_hint_uses_the_template_vocabulary,
        test_direct_evidence_must_be_bound_to_a_claim,
        test_unknown_capability_is_refused,
        test_missing_invariant_is_refused,
        test_credential_shaped_field_is_refused,
        test_summary_never_claims_publication,
        test_loader_reads_json_and_refuses_an_empty_file,
        test_validation_does_not_mutate_the_document,
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
    print("\nAll content bundle contract tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
