"""One review decision covers every asset that shares its source and licence.

Run: python tests/test_rights_batch.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.media.rights_gate import RightsError, validate_declared_asset  # noqa: E402
from contentops.media.rights_batch import apply_batch_decision, review_batch  # noqa: E402


def _asset(asset_id, sha="a" * 64):
    return {
        "id": asset_id, "sha256": sha, "type": "REAL_SCREENSHOT",
        "origin": "https://github.com/adongwanai/AgentGuide/blob/ad78b0e/README.md",
        "permission": "LICENSED", "license": "CC-BY-4.0",
        "review_scope": "video:agentguide-learning-roadmap",
        "modifications": "cropped and resized to 1080x1920",
        "repo_path": f"assets/{asset_id}.png",
    }


def _manifest(*assets):
    return {"schema": "contentops.m5-assets/v1", "assets": list(assets)}


def test_a_batch_groups_assets_that_share_a_source_and_licence():
    manifest = _manifest(_asset("one"), _asset("two", "b" * 64))
    batches = review_batch(manifest)
    assert len(batches) == 1
    batch = batches[0]
    assert batch["asset_ids"] == ["one", "two"]
    assert batch["license"] == "CC-BY-4.0"
    assert batch["decision"] == "PENDING_HUMAN_REVIEW"
    assert "one" in batch["sha256"] and "two" in batch["sha256"]


def test_a_request_to_review_does_not_clear_anything():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        manifest = _manifest(_asset("one"))
        batches = review_batch(manifest)
        assert batches[0]["decision"] == "PENDING_HUMAN_REVIEW"
        with_rights = apply_batch_decision(project, manifest, batches, decisions={})
        try:
            validate_declared_asset(with_rights["assets"][0], project)
        except RightsError:
            return
        raise AssertionError("an unreviewed asset passed the rights gate")


def test_one_named_decision_clears_every_matching_asset():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        manifest = _manifest(_asset("one"), _asset("two", "b" * 64))
        batches = review_batch(manifest)
        decisions = {batches[0]["batch_id"]: {
            "reviewer": "Founder", "reviewed_at": "2026-11-23",
            "attribution": "AgentGuide contributors / adongwanai, CC BY 4.0",
        }}
        cleared = apply_batch_decision(project, manifest, batches, decisions=decisions)
        for asset in cleared["assets"]:
            record = validate_declared_asset(asset, project)
            assert record["license_id"] == "CC-BY-4.0"
            assert record["reviewed_by"] == "Founder"
            assert asset["rights_review_status"] == "REVIEWED"
            assert asset["rights_review_record"] == f"assets/{asset['id']}.rights.json"
            saved = json.loads((project / asset["rights_review_record"]).read_text(encoding="utf-8"))
            assert saved["asset_sha256"] == asset["sha256"]
            assert saved["review_scope"] == "video:agentguide-learning-roadmap"
            assert saved["modifications"] == "cropped and resized to 1080x1920"


def test_a_changed_hash_is_not_covered_by_an_earlier_decision():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        original = _manifest(_asset("one"))
        batches = review_batch(original)
        decisions = {batches[0]["batch_id"]: {
            "reviewer": "Founder", "reviewed_at": "2026-11-23",
            "attribution": "AgentGuide contributors / adongwanai, CC BY 4.0",
        }}

        changed = _manifest(_asset("one", "c" * 64))
        again = review_batch(changed)
        assert again[0]["decision"] == "PENDING_HUMAN_REVIEW"
        assert again[0]["batch_id"] != batches[0]["batch_id"]
        try:
            apply_batch_decision(project, changed, batches, decisions=decisions)
        except ValueError as exc:
            assert "stale" in str(exc).lower()
        else:
            raise AssertionError("stale batch decision cleared changed bytes")
        assert not (project / "assets/one.rights.json").exists()


def main() -> int:
    tests = (
        test_a_batch_groups_assets_that_share_a_source_and_licence,
        test_a_request_to_review_does_not_clear_anything,
        test_one_named_decision_clears_every_matching_asset,
        test_a_changed_hash_is_not_covered_by_an_earlier_decision,
    )
    failures = []
    for test in tests:
        try:
            test()
        except Exception as exc:
            failures.append(f"{test.__name__}: {exc}")
            print(f"[FAIL] {test.__name__}: {exc}")
        else:
            print(f"[ok] {test.__name__}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print("\nAll rights batch tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
