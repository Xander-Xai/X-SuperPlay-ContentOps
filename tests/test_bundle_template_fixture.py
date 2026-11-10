"""Cross-repo Content Bundle contract fixture tests.

Strategy owns the Bundle template
(``90-Templates/content-bundle.yaml``); ContentOps consumes it. The existing
contract tests (``test_content_bundle_contract.py``) pin the consumer's rules
with hand-written records. This suite adds the missing half: a fixture frozen
from the *actual* Strategy template structure
(``tests/fixtures/content_bundle_strategy_template_v1.json``), so that a
template reshape on the Strategy side fails a test here first instead of
breaking a handoff at runtime.

If this suite fails after a Strategy update: re-derive the fixture from the
template, keep ``_provenance`` accurate, and never widen the consumer to
accept a shape the template does not have.

Run: python tests/test_bundle_template_fixture.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.content_kernel import (  # noqa: E402
    consumption_summary,
    load_bundle,
    validate_bundle,
)

FIXTURE = ROOT / "tests" / "fixtures" / "content_bundle_strategy_template_v1.json"

#: Top-level keys of the Strategy template, verbatim. A template reshape that
#: adds or removes a key must update this list in the same commit as the
#: fixture — that diff *is* the cross-repo contract change record.
TEMPLATE_TOP_LEVEL_KEYS = {
    "schema_version", "record_type", "bundle_id", "created_at", "status",
    "source", "account_treatments", "asset_requirements", "assets",
    "aigc_provenance", "content_experiments", "platform_adapters",
    "execution_pointers", "metric_and_signal_pointers", "invariants",
}


def _fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_loads_through_the_real_loader():
    document = load_bundle(FIXTURE)
    assert document["record_type"] == "content_bundle"


def test_fixture_passes_the_consumer_contract():
    failures = validate_bundle(load_bundle(FIXTURE))
    assert failures == [], failures


def test_fixture_keeps_the_template_top_level_shape():
    document = _fixture()
    keys = set(document) - {"_provenance"}
    assert keys == TEMPLATE_TOP_LEVEL_KEYS, sorted(
        keys ^ TEMPLATE_TOP_LEVEL_KEYS)


def test_fixture_carries_both_account_treatments():
    treatments = _fixture()["account_treatments"]
    assert set(treatments) == {"explorer", "thinktank"}
    assert treatments["explorer"]["role"] == "Explore"
    assert treatments["thinktank"]["role"] == "Build"


def test_direct_evidence_requirement_is_claim_bound():
    requirements = _fixture()["asset_requirements"]
    assert requirements, "template fixture must carry at least one requirement"
    for requirement in requirements:
        if requirement["evidence_role"] == "direct_evidence":
            assert requirement["claim_refs"], requirement["requirement_id"]


def test_fixture_invariants_carry_the_required_invariants():
    invariants = _fixture()["invariants"]
    for name in (
        "bundle_is_not_published_content",
        "generated_media_is_not_direct_evidence",
        "credentials_must_not_cross_repository_boundaries",
        "platform_adaptation_must_not_change_facts",
    ):
        assert invariants.get(name) is True, name


def test_fixture_declares_aigc_provenance_obligation():
    provenance = _fixture()["aigc_provenance"]
    assert provenance["required"] is True
    assert provenance["disclosure_review_status"] in (
        "pending", "disclosed", "reviewed")


def test_provenance_names_the_strategy_template():
    provenance = _fixture()["_provenance"]
    assert "X-SuperPlay-Strategy" in provenance["source"]
    assert "content-bundle.yaml" in provenance["source"]


def test_summary_stays_honest_about_publication():
    summary = consumption_summary(load_bundle(FIXTURE))
    assert summary["is_published"] is False
    assert summary["bundle_id"] == _fixture()["bundle_id"]
    assert summary["source_id"] == _fixture()["source"]["source_id"]


def main() -> int:
    tests = (
        test_fixture_loads_through_the_real_loader,
        test_fixture_passes_the_consumer_contract,
        test_fixture_keeps_the_template_top_level_shape,
        test_fixture_carries_both_account_treatments,
        test_direct_evidence_requirement_is_claim_bound,
        test_fixture_invariants_carry_the_required_invariants,
        test_fixture_declares_aigc_provenance_obligation,
        test_provenance_names_the_strategy_template,
        test_summary_stays_honest_about_publication,
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
    print("\nAll bundle template fixture tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
