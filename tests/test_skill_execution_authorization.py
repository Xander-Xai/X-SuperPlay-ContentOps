from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.skills import authorization as auth  # noqa: E402

NOW = "2026-10-31T12:00:00+00:00"
RESOLVABLE = {"verdict": "RESOLVABLE", "reason": "RESOLVABLE"}
REGISTRY_ENTRY = {"id": "media-use", "name": "media-use",
                  "source": {"version": "0.8.222"}}


def request(**overrides) -> auth.ExecutionRequest:
    values = dict(
        request_id="req-1",
        skill_id="media-use",
        skill_version="0.8.222",
        account="douyin-1024",
        pipeline="M5",
        stage="media_use",
        operations=("resolve", "import"),
        caller="owner",
        units=1,
    )
    values.update(overrides)
    return auth.ExecutionRequest(**values)


def grant(**overrides) -> auth.ExecutionGrant:
    values = dict(
        grant_id="grant-1",
        principal="owner",
        skill_id="media-use",
        skill_version="0.8.222",
        account="douyin-1024",
        pipeline="M5",
        stage="media_use",
        operations=("resolve", "import"),
        issued_at="2026-10-31T11:00:00+00:00",
        expires_at="2026-10-31T13:00:00+00:00",
        max_units=2,
        max_uses=1,
        uses_consumed=0,
    )
    values.update(overrides)
    return auth.ExecutionGrant(**values)


class DenyByDefaultTests(unittest.TestCase):
    def test_a_resolvable_verdict_without_a_grant_is_blocked(self) -> None:
        decision = auth.evaluate(request(), verdict=RESOLVABLE, now=NOW)
        self.assertEqual(decision.state, auth.STATE_BLOCKED)
        self.assertEqual(decision.reason, auth.REASON_NO_GRANT)
        self.assertFalse(decision.execution_authorized)

    def test_no_verdict_is_blocked(self) -> None:
        decision = auth.evaluate(request(), verdict=None, grant=grant(), now=NOW)
        self.assertEqual(decision.reason, auth.REASON_NOT_RESOLVABLE)
        self.assertFalse(decision.execution_authorized)

    def test_a_blocked_router_verdict_cannot_be_promoted_by_a_grant(self) -> None:
        blocked = {"verdict": "BLOCKED", "reason": "MISSING_RUNTIME"}
        decision = auth.evaluate(request(), verdict=blocked, grant=grant(), now=NOW)
        self.assertEqual(decision.reason, auth.REASON_NOT_RESOLVABLE)
        self.assertIn("MISSING_RUNTIME", decision.detail)
        self.assertFalse(decision.execution_authorized)

    def test_a_revoked_grant_is_blocked(self) -> None:
        decision = auth.evaluate(
            request(), verdict=RESOLVABLE,
            grant=grant(revoked=True, revoked_reason="owner withdrew it"), now=NOW)
        self.assertEqual(decision.reason, auth.REASON_GRANT_REVOKED)
        self.assertIn("owner withdrew it", decision.detail)
        self.assertFalse(decision.execution_authorized)

    def test_an_expired_grant_is_blocked(self) -> None:
        decision = auth.evaluate(
            request(), verdict=RESOLVABLE,
            grant=grant(expires_at="2026-10-31T11:30:00+00:00"), now=NOW)
        self.assertEqual(decision.reason, auth.REASON_GRANT_EXPIRED)

    def test_a_grant_that_is_not_yet_valid_is_blocked(self) -> None:
        decision = auth.evaluate(
            request(), verdict=RESOLVABLE,
            grant=grant(issued_at="2026-10-31T12:30:00+00:00"), now=NOW)
        self.assertEqual(decision.reason, auth.REASON_GRANT_NOT_YET_VALID)

    def test_a_grant_without_usable_timestamps_is_blocked(self) -> None:
        decision = auth.evaluate(
            request(), verdict=RESOLVABLE,
            grant=grant(issued_at="", expires_at=""), now=NOW)
        self.assertEqual(decision.reason, auth.REASON_GRANT_NOT_YET_VALID)

    def test_a_borrowed_grant_is_blocked(self) -> None:
        decision = auth.evaluate(
            request(caller="someone-else"), verdict=RESOLVABLE, grant=grant(), now=NOW)
        self.assertEqual(decision.reason, auth.REASON_CALLER_MISMATCH)
        self.assertFalse(decision.execution_authorized)

    def test_an_operation_outside_the_grant_is_blocked(self) -> None:
        decision = auth.evaluate(
            request(operations=("resolve", "import", "publish")),
            verdict=RESOLVABLE, grant=grant(), now=NOW)
        self.assertEqual(decision.reason, auth.REASON_OPERATION_NOT_GRANTED)
        self.assertIn("publish", decision.detail)

    def test_a_request_beyond_the_budget_is_blocked(self) -> None:
        decision = auth.evaluate(
            request(units=3), verdict=RESOLVABLE, grant=grant(max_units=2), now=NOW)
        self.assertEqual(decision.reason, auth.REASON_BUDGET_EXCEEDED)

    def test_an_exhausted_grant_is_blocked(self) -> None:
        decision = auth.evaluate(
            request(), verdict=RESOLVABLE,
            grant=grant(max_uses=1, uses_consumed=1), now=NOW)
        self.assertEqual(decision.reason, auth.REASON_USES_EXHAUSTED)


class ContextBindingTests(unittest.TestCase):
    def _assert_context_blocked(self, **overrides) -> None:
        decision = auth.evaluate(request(**overrides), verdict=RESOLVABLE,
                                 grant=grant(), now=NOW)
        self.assertEqual(decision.reason, auth.REASON_CONTEXT_MISMATCH, overrides)
        self.assertFalse(decision.execution_authorized)

    def test_account_must_match(self) -> None:
        self._assert_context_blocked(account="future-intelligence")

    def test_pipeline_must_match(self) -> None:
        self._assert_context_blocked(pipeline="M4")

    def test_stage_must_match(self) -> None:
        self._assert_context_blocked(stage="compose")

    def test_skill_version_must_match(self) -> None:
        self._assert_context_blocked(skill_version="0.8.221")

    def test_the_registry_pins_the_version(self) -> None:
        decision = auth.evaluate(
            request(skill_version="0.8.221"), verdict=RESOLVABLE,
            grant=grant(skill_version="0.8.221"), now=NOW,
            registry_entry=REGISTRY_ENTRY)
        self.assertEqual(decision.reason, auth.REASON_VERSION_MISMATCH)

    def test_the_registry_pins_the_skill_id(self) -> None:
        decision = auth.evaluate(
            request(skill_id="other-skill"), verdict=RESOLVABLE, grant=grant(),
            now=NOW, registry_entry=REGISTRY_ENTRY)
        self.assertEqual(decision.reason, auth.REASON_UNKNOWN_SKILL)


class AuthorizedTests(unittest.TestCase):
    def test_an_exact_grant_authorizes_one_execution(self) -> None:
        decision = auth.evaluate(request(), verdict=RESOLVABLE,
                                 grant=grant(), now=NOW, registry_entry=REGISTRY_ENTRY)
        self.assertEqual(decision.state, auth.STATE_AUTHORIZED)
        self.assertEqual(decision.reason, auth.REASON_AUTHORIZED)
        self.assertTrue(decision.execution_authorized)
        self.assertEqual(decision.grant_id, "grant-1")
        self.assertEqual(decision.request_id, "req-1")

    def test_every_blocked_path_stays_unauthorized(self) -> None:
        scenarios = [
            dict(verdict=None, grant=grant()),
            dict(verdict=RESOLVABLE, grant=None),
            dict(verdict=RESOLVABLE, grant=grant(revoked=True)),
            dict(verdict=RESOLVABLE, grant=grant(expires_at="2020-01-01T00:00:00Z")),
            dict(verdict={"verdict": "BLOCKED", "reason": "UNKNOWN_SKILL"}, grant=grant()),
        ]
        for scenario in scenarios:
            decision = auth.evaluate(request(), now=NOW, **scenario)
            self.assertEqual(decision.state, auth.STATE_BLOCKED, scenario)
            self.assertFalse(decision.execution_authorized, scenario)

    def test_the_decision_records_do_not_leak_a_capability(self) -> None:
        decision = auth.evaluate(request(), verdict=RESOLVABLE, grant=grant(),
                                 now=NOW, registry_entry=REGISTRY_ENTRY)
        payload = decision.as_dict()
        self.assertNotIn("capability", payload)
        self.assertNotIn("adapter", payload)
        self.assertEqual(set(payload), {"state", "reason", "detail", "request_id",
                                        "grant_id", "execution_authorized"})


if __name__ == "__main__":
    unittest.main()
