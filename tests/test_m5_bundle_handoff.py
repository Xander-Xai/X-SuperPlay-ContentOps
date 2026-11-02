"""M5 can only consume media after a Bundle handoff binds its sources.

Run: python tests/test_m5_bundle_handoff.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import m5_production  # noqa: E402

BUNDLE = {
    "schema_version": 1,
    "record_type": "content_bundle",
    "bundle_id": "CB-20261102-002",
    "created_at": "2026-11-02T00:00:00Z",
    "status": "draft",
    "source": {
        "source_id": "SRC-20261102-002",
        "source_refs": ["repo://X-SuperPlay-ContentOps#bundle-test"],
        "topic_thesis": "A real source, bound before production.",
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
        }
    },
    "asset_requirements": [{
        "requirement_id": "AR-001",
        "claim_refs": ["C1"],
        "capability": "real_capture",
        "evidence_role": "direct_evidence",
        "required": True,
        "account_scope": ["explorer"],
        "platform_scope": [],
        "acceptance": "A real screenshot.",
        "fallback_capabilities": [],
    }],
    "assets": {
        "real_evidence_refs": ["project://sources/screenshot.png"],
        "reusable_asset_refs": [],
        "generated_asset_refs": [],
        "manual_premium_asset_refs": [],
        "canonical_master_refs": [],
    },
    "aigc_provenance": {"required": True, "asset_manifest_refs": [],
                        "disclosure_review_status": "pending"},
    "content_experiments": {"refs": []},
    "platform_adapters": {"refs": []},
    "execution_pointers": [],
    "metric_and_signal_pointers": {
        "metric_snapshot_refs": [], "market_signal_refs": [], "review_refs": []},
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


def _project(tmp: Path) -> Path:
    (tmp / "project.yaml").write_text("id: bundle-video\n", encoding="utf-8")
    (tmp / "bundle.json").write_text(json.dumps(BUNDLE), encoding="utf-8")
    return tmp


def test_absent_bundle_keeps_the_historical_path():
    with tempfile.TemporaryDirectory() as tmp:
        project = _project(Path(tmp))
        assert m5_production.stage_bundle(project, {"id": "bundle-video"}) == {
            "state": "NOT_CONFIGURED"}


def test_valid_bundle_writes_a_video_handoff():
    with tempfile.TemporaryDirectory() as tmp:
        project = _project(Path(tmp))
        stage = m5_production.stage_bundle(project, {
            "id": "bundle-video",
            "content_bundle": {
                "path": "bundle.json",
                "account": "explorer",
                "source_map": {"SRC-20261102-002": "SRC-RUNTIME-002"},
            },
        })
        assert stage["state"] == "READY_FOR_PRODUCTION"
        assert stage["bundle_id"] == "CB-20261102-002"
        assert stage["handoff"] == "receipts/bundle-handoff-video.json"
        saved = json.loads((project / stage["handoff"]).read_text(encoding="utf-8"))
        assert saved["content_format"] == "VIDEO"
        assert saved["source_map"] == {"SRC-20261102-002": "SRC-RUNTIME-002"}
        assert saved["bundle_path"] == "bundle.json"
        assert saved["bundle_scope"] == "project"
        assert saved["publish_authorized"] is False


def test_handoff_path_survives_a_windows_short_path_alias():
    """The caller may pass a project path living under an 8.3-aliased parent.

    On a GitHub Windows runner the temp dir's parent chain arrives as
    ``C:\\Users\\RUNNER~1\\...`` while ``write_handoff`` resolves it to
    ``C:\\Users\\runneradmin\\...``. A raw ``relative_to`` raises ValueError
    because the two spellings differ. The stage must resolve both sides.

    The alias is applied to the *parent* directory: 8.3 applies to directory
    components, and the project slug itself must stay a plain name.
    """
    if sys.platform != "win32":
        return  # 8.3 aliases are a Windows spelling difference; elsewhere identical

    import ctypes

    with tempfile.TemporaryDirectory() as tmp:
        project = _project(Path(tmp))
        parent = project.parent
        short_buffer = ctypes.create_unicode_buffer(4096)
        if ctypes.windll.kernel32.GetShortPathNameW(str(parent), short_buffer,
                                                    len(short_buffer)) == 0:
            return  # short names disabled on this volume; the alias test cannot run
        aliased_parent = Path(short_buffer.value)
        aliased = aliased_parent / project.name
        if aliased.resolve() == project.resolve() and \
                str(aliased) == str(project.resolve()):
            return  # this spelling matches the long form; nothing to distinguish

        stage = m5_production.stage_bundle(aliased, {
            "id": "bundle-video",
            "content_bundle": {
                "path": "bundle.json",
                "account": "explorer",
                "source_map": {"SRC-20261102-002": "SRC-RUNTIME-002"},
            },
        })
        assert stage["state"] == "READY_FOR_PRODUCTION"
        assert stage["handoff"] == "receipts/bundle-handoff-video.json"
        saved = json.loads((project / stage["handoff"]).read_text(encoding="utf-8"))
        assert saved["content_format"] == "VIDEO"


def test_broken_source_mapping_blocks_video():
    with tempfile.TemporaryDirectory() as tmp:
        project = _project(Path(tmp))
        try:
            m5_production.stage_bundle(project, {
                "id": "bundle-video",
                "content_bundle": {
                    "path": "bundle.json",
                    "account": "explorer",
                    "source_map": {"SRC-WRONG": "SRC-RUNTIME-002"},
                },
            })
        except m5_production.M5Blocked as exc:
            assert "SOURCE_MAP_INCOMPLETE" in str(exc)
        else:
            raise AssertionError("a wrong source map must block the video run")


def test_a_bundle_change_revokes_the_existing_review():
    with tempfile.TemporaryDirectory(dir=ROOT / "projects") as tmp:
        project = Path(tmp)
        (project / "receipts").mkdir()
        (project / "receipts" / "human-review.json").write_text(json.dumps({
            "project": "p",
            "reviewer": "Xander",
            "reviewed_at": "2026-11-02",
            "decision": "SHIP",
            "bundle_sha256": "a" * 64,
        }), encoding="utf-8")
        review = m5_production.stage_review(
            project, "bundle-video",
            {"report": {"overall": "WARN", "checks": []}},
            bundle={"bundle_id": "CB-1", "bundle_sha256": "b" * 64},
        )
        saved = json.loads((project / "receipts" / "human-review.json")
                           .read_text(encoding="utf-8"))
    assert review["state"] == "PENDING_FOUNDER_REVIEW"
    assert review["production_ready"] is False
    assert review["review_revoked_reason"] == "BUNDLE_CHANGED"
    assert review["revoked_review"]["reviewer"] == "Xander"
    assert saved["reviewer"] is None


def test_an_unchanged_bundle_keeps_no_revocation_marker():
    with tempfile.TemporaryDirectory(dir=ROOT / "projects") as tmp:
        project = Path(tmp)
        (project / "receipts").mkdir()
        same = "c" * 64
        (project / "receipts" / "human-review.json").write_text(json.dumps({
            "project": "p", "reviewer": "Xander", "decision": "SHIP",
            "bundle_sha256": same,
        }), encoding="utf-8")
        review = m5_production.stage_review(
            project, "bundle-video",
            {"report": {"overall": "WARN", "checks": []}},
            bundle={"bundle_id": "CB-1", "bundle_sha256": same},
        )
    assert "review_revoked_reason" not in review
    assert review["bundle_sha256"] == same


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
