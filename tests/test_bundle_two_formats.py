"""One Bundle, two independent production handoffs.

The two content forms share a source and a claim set but never share an
approval. These tests pin that separation, the source-id mapping, and the fact
that a handoff is a plan rather than a published work.

Run: python tests/test_bundle_two_formats.py
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
    GRAPHIC_TEXT,
    VIDEO,
    HandoffError,
    build_handoff,
    bundle_digest,
    write_handoff,
)


def _bundle() -> dict:
    return {
        "schema_version": 1,
        "record_type": "content_bundle",
        "bundle_id": "CB-20261102-001",
        "created_at": "2026-11-02T00:00:00Z",
        "status": "draft",
        "source": {
            "source_id": "SRC-20261102-001",
            "source_refs": ["repo://X-SuperPlay-ContentOps#test"],
            "topic_thesis": "A tested claim, not a generated assertion.",
            "claim_refs": ["C1"],
            "permission_refs": ["OWNED-BY-OPERATOR"],
            "proof_level": "direct",
        },
        "account_treatments": {
            "explorer": {
                "strategy_account": "X超玩•1024",
                "role": "Explore",
                "narrative_angle": "What broke.",
                "key_claims": ["C1"],
                "cta_intent": "discuss",
                "production_lane": "baseline",
                "execution_profile_hint": "default",
            },
            "thinktank": {
                "strategy_account": "X超玩•未来智能",
                "role": "Build",
                "narrative_angle": "How it was fixed.",
                "key_claims": ["C1"],
                "cta_intent": "reproduce",
                "production_lane": "baseline",
                "execution_profile_hint": "default",
            },
        },
        "asset_requirements": [{
            "requirement_id": "AR-001",
            "claim_refs": ["C1"],
            "capability": "real_capture",
            "evidence_role": "direct_evidence",
            "required": True,
            "account_scope": ["explorer"],
            "platform_scope": [],
            "acceptance": "A real screenshot with a hash.",
            "fallback_capabilities": [],
        }],
        "assets": {
            "real_evidence_refs": ["project://sources/screenshot.png"],
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
            "business_source_of_truth": "Xander-Xai/X-SuperPlay-OPC-Blueprint",
            "implementation_source_of_truth": "Xander-Xai/X-SuperPlay-Strategy",
        },
    }


def _raises(code, fn):
    try:
        fn()
    except HandoffError as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(f"expected HandoffError {code}")


def test_one_bundle_builds_two_independent_handoffs():
    bundle = _bundle()
    video = build_handoff(
        bundle, "explorer", VIDEO,
        project_slug="bundle-video",
        source_map={"SRC-20261102-001": "SRC-RUNTIME-001"},
    )
    graphic = build_handoff(
        bundle, "thinktank", GRAPHIC_TEXT,
        project_slug="bundle-graphic",
        source_map={"SRC-20261102-001": "SRC-RUNTIME-001"},
    )
    assert video["bundle_sha256"] == graphic["bundle_sha256"] == bundle_digest(bundle)
    assert video["state"] == "READY_FOR_PRODUCTION"
    assert graphic["state"] == "READY_FOR_MANUAL_PACKAGE"
    assert video["content_format"] != graphic["content_format"]
    assert video["human_review"] == graphic["human_review"] == "NOT_STARTED"
    assert video["publish_authorized"] is False
    assert graphic["publish_authorized"] is False
    assert video["production_ready"] is False
    assert graphic["production_ready"] is False


def test_unknown_account_is_refused():
    _raises("ACCOUNT_TREATMENT_MISSING", lambda: build_handoff(
        _bundle(), "different-account", VIDEO,
        project_slug="p", source_map={"SRC-20261102-001": "SRC-1"}))


def test_source_mapping_must_name_the_bundle_source():
    _raises("SOURCE_MAP_INCOMPLETE", lambda: build_handoff(
        _bundle(), "explorer", VIDEO,
        project_slug="p", source_map={"SRC-OTHER": "SRC-1"}))


def test_source_mapping_cannot_be_a_path():
    _raises("SOURCE_MAP_INVALID", lambda: build_handoff(
        _bundle(), "explorer", VIDEO,
        project_slug="p", source_map={"SRC-20261102-001": "../../etc/passwd"}))


def test_project_slug_cannot_escape():
    _raises("PROJECT_SLUG_INVALID", lambda: build_handoff(
        _bundle(), "explorer", VIDEO,
        project_slug="../escape", source_map={"SRC-20261102-001": "SRC-1"}))


def test_broken_bundle_invariant_is_refused():
    bundle = copy.deepcopy(_bundle())
    bundle["invariants"]["bundle_is_not_published_content"] = False
    _raises("BUNDLE_INVALID", lambda: build_handoff(
        bundle, "explorer", VIDEO,
        project_slug="p", source_map={"SRC-20261102-001": "SRC-1"}))


def test_video_bundle_cannot_target_an_editorial_platform():
    _raises("PLATFORM_FORMAT_MISMATCH", lambda: build_handoff(
        _bundle(), "explorer", VIDEO,
        project_slug="p", source_map={"SRC-20261102-001": "SRC-1"},
        platform_id="wechat_article", registry_root=ROOT))


def test_planned_graphic_platform_is_a_named_blocker_not_an_execution():
    handoff = build_handoff(
        _bundle(), "explorer", GRAPHIC_TEXT,
        project_slug="p", source_map={"SRC-20261102-001": "SRC-1"},
        platform_id="wechat_article", registry_root=ROOT)
    assert handoff["state"] == "READY_FOR_MANUAL_PACKAGE"
    assert "PLATFORM_PLACEHOLDER" in handoff["blockers"]
    assert handoff["platform"]["status"] == "PLANNED"
    assert handoff["publish_authorized"] is False


def test_integrated_platform_still_stops_at_manual_package():
    handoff = build_handoff(
        _bundle(), "explorer", GRAPHIC_TEXT,
        project_slug="p", source_map={"SRC-20261102-001": "SRC-1"},
        platform_id="x", registry_root=ROOT)
    assert handoff["platform"]["status"] == "INTEGRATED"
    assert handoff["platform"]["delivery"] == "MANUAL_PACKAGE_ONLY"
    assert handoff["publish_authorized"] is False


def test_handoff_writes_only_inside_the_project_receipts():
    handoff = build_handoff(
        _bundle(), "explorer", VIDEO,
        project_slug="p", source_map={"SRC-20261102-001": "SRC-1"})
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        target = write_handoff(project, handoff)
        assert target == project.resolve() / "receipts" / "bundle-handoff-video.json"
        saved = json.loads(target.read_text(encoding="utf-8"))
        assert saved["bundle_id"] == "CB-20261102-001"
        assert saved["publish_authorized"] is False


TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok   {test.__name__}")
    print(f"{len(TESTS) - failures}/{len(TESTS)} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
