"""Delivery is refused until every condition is met, and publishing never is.

The adversary here is not a remote server. It is a local script with a valid
draft file and a working CLI, which is exactly how a delivery bypass happens:
the packer checked things, the dispatcher only checked that the file existed.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.platforms.delivery_gate import (  # noqa: E402
    DRAFT_ONLY,
    REFUSED,
    authorize_delivery,
    load_registry_rows,
)


def _draft(platform_id, **overrides):
    draft = {
        "platform_id": platform_id,
        "publish_authorized": False,
        "validation": {"ok": True, "errors": []},
        "rights": {"cleared": True},
    }
    draft.update(overrides)
    return draft


class RealRegistryTests(unittest.TestCase):
    """Against the registry as it actually ships: nothing is deliverable yet."""

    def setUp(self):
        self.rows = load_registry_rows(ROOT)

    def test_registry_is_the_single_source(self):
        self.assertTrue((ROOT / "config" / "registry" / "platforms.json").is_file())
        self.assertGreaterEqual(len(self.rows), 5)

    def test_wechat_draft_is_refused_because_delivery_is_not_implemented(self):
        decision = authorize_delivery(_draft("wechat_article"), registry_rows=self.rows)
        self.assertEqual(decision.outcome, REFUSED)
        self.assertIn("PLATFORM_DELIVERY_NOT_IMPLEMENTED", " ".join(decision.reasons))

    def test_douyin_is_refused_before_any_capability_check(self):
        decision = authorize_delivery(_draft("douyin"), registry_rows=self.rows)
        self.assertEqual(decision.outcome, REFUSED)
        self.assertIn("DOUYIN", " ".join(decision.reasons))

    def test_an_unregistered_platform_is_refused(self):
        decision = authorize_delivery(_draft("some_new_platform"), registry_rows=self.rows)
        self.assertEqual(decision.outcome, REFUSED)
        self.assertIn("PLATFORM_NOT_IN_REGISTRY", " ".join(decision.reasons))


class ConditionTests(unittest.TestCase):
    """Each condition is checked independently, with its own reason."""

    def setUp(self):
        # A registry row that *is* capable, so the checks below are not masked by
        # the "not implemented" refusal.
        self.rows = [{
            "platform_id": "wechat_article",
            "draft_support": "SUPPORTED",
            "publish_mode": "MANUAL_ONLY",
        }]

    def test_delivery_without_adapter_validation_is_refused(self):
        decision = authorize_delivery(
            _draft("wechat_article", validation=None), registry_rows=self.rows)
        self.assertEqual(decision.outcome, REFUSED)
        self.assertIn("MISSING_ADAPTER_VALIDATION", " ".join(decision.reasons))

    def test_failed_adapter_validation_is_refused(self):
        decision = authorize_delivery(
            _draft("wechat_article", validation={"ok": False, "errors": ["title too long"]}),
            registry_rows=self.rows)
        self.assertEqual(decision.outcome, REFUSED)
        self.assertIn("ADAPTER_VALIDATION_FAILED", " ".join(decision.reasons))

    def test_a_draft_cannot_assert_publish_authorization(self):
        decision = authorize_delivery(
            _draft("wechat_article", publish_authorized=True), registry_rows=self.rows)
        self.assertEqual(decision.outcome, REFUSED)
        self.assertIn("DRAFT_ASSERTS_PUBLISH_AUTHORIZATION", " ".join(decision.reasons))

    def test_uncleared_rights_are_refused(self):
        decision = authorize_delivery(
            _draft("wechat_article", rights={"cleared": False}), registry_rows=self.rows)
        self.assertEqual(decision.outcome, REFUSED)
        self.assertIn("RIGHTS_NOT_CLEARED", " ".join(decision.reasons))

    def test_missing_rights_block_is_refused(self):
        decision = authorize_delivery(
            _draft("wechat_article", rights=None), registry_rows=self.rows)
        self.assertEqual(decision.outcome, REFUSED)

    def test_wechat_mass_send_is_refused_even_when_capable(self):
        decision = authorize_delivery(
            _draft("wechat_article"), registry_rows=self.rows, mode="mass_send")
        self.assertEqual(decision.outcome, REFUSED)
        self.assertIn("WECHAT_MASS_SEND_REFUSED", " ".join(decision.reasons))

    def test_publishing_is_refused_even_when_capable(self):
        rows = [{"platform_id": "x", "draft_support": "SUPPORTED",
                 "publish_mode": "MANUAL_ONLY"}]
        decision = authorize_delivery(
            _draft("x"), registry_rows=rows, mode="publish")
        self.assertEqual(decision.outcome, REFUSED)
        self.assertIn("PUBLISHING_NOT_INTEGRATED", " ".join(decision.reasons))


class NotADeadlockTests(unittest.TestCase):
    """The gate must be satisfiable, or it is just a wall."""

    def setUp(self):
        self.rows = [{
            "platform_id": "wechat_article",
            "draft_support": "SUPPORTED",
            "publish_mode": "MANUAL_ONLY",
        }]

    def test_a_capable_platform_reaches_its_draft_boundary(self):
        decision = authorize_delivery(_draft("wechat_article"), registry_rows=self.rows)
        self.assertEqual(decision.outcome, DRAFT_ONLY)
        self.assertTrue(decision.allowed)

    def test_no_outcome_ever_permits_publishing(self):
        decision = authorize_delivery(_draft("wechat_article"), registry_rows=self.rows)
        self.assertFalse(decision.may_publish)
        self.assertFalse(decision.as_dict()["may_publish"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
