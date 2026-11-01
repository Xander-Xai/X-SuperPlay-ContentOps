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
RESOLVABLE = {"verdict": "RESOLVABLE", "reason": "RESOLVABLE",
              "execution_authorized": False}
REGISTRY_ENTRY = {"id": "media-use", "name": "media-use",
                  "source": {"version": "0.8.222"}}
PROVENANCE = "sha256:" + "a" * 64


def request(**overrides) -> auth.ExecutionRequest:
    values = dict(
        request_id="req-1",
        skill_id="media-use",
        skill_version="0.8.222",
        account="douyin-1024",
        pipeline="M5",
        stage="media_use",
        operations=("resolve", "import"),
        subject="owner",
        units=1,
    )
    values.update(overrides)
    return auth.ExecutionRequest(**values)


def grant(**overrides) -> auth.ExecutionGrant:
    values = dict(
        grant_id="grant-1",
        issuer="owner",
        subject="owner",
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
        provenance=PROVENANCE,
    )
    values.update(overrides)
    return auth.ExecutionGrant(**values)


_UNSET = object()


def decide(request_overrides=None, grant_value=_UNSET, verdict=_UNSET, registry=_UNSET):
    return auth.evaluate(
        request(**(request_overrides or {})),
        verdict=RESOLVABLE if verdict is _UNSET else verdict,
        registry_entry=REGISTRY_ENTRY if registry is _UNSET else registry,
        grant=(grant(**grant_value) if isinstance(grant_value, dict)
               else (grant() if grant_value is _UNSET else grant_value)),
        now=NOW,
    )


class DenyByDefaultTests(unittest.TestCase):
    def test_a_resolvable_verdict_without_a_grant_is_blocked(self) -> None:
        decision = decide(grant_value=None)
        self.assertEqual(decision.state, auth.STATE_BLOCKED)
        self.assertEqual(decision.reason, auth.REASON_NO_GRANT)
        self.assertFalse(decision.execution_authorized)

    def test_no_verdict_is_blocked(self) -> None:
        decision = decide(verdict=None)
        self.assertEqual(decision.reason, auth.REASON_NOT_RESOLVABLE)

    def test_a_blocked_router_verdict_cannot_be_promoted_by_a_grant(self) -> None:
        decision = decide(verdict={"verdict": "BLOCKED", "reason": "MISSING_RUNTIME"})
        self.assertEqual(decision.reason, auth.REASON_NOT_RESOLVABLE)
        self.assertIn("MISSING_RUNTIME", decision.detail)

    def test_a_verdict_that_claims_execution_authority_is_refused(self) -> None:
        forged = {"verdict": "RESOLVABLE", "reason": "RESOLVABLE",
                  "execution_authorized": True}
        decision = decide(verdict=forged)
        self.assertEqual(decision.reason, auth.REASON_UNTRUSTED_VERDICT)
        self.assertFalse(decision.execution_authorized)

    def test_an_omitted_registry_entry_is_refused(self) -> None:
        decision = decide(registry={})
        self.assertEqual(decision.reason, auth.REASON_UNKNOWN_SKILL)

    def test_a_declaration_without_a_version_pin_is_refused(self) -> None:
        decision = decide(registry={"id": "media-use", "name": "media-use", "source": {}})
        self.assertEqual(decision.reason, auth.REASON_VERSION_MISMATCH)

    def test_a_grant_without_provenance_is_refused(self) -> None:
        decision = decide(grant_value={"provenance": ""})
        self.assertEqual(decision.reason, auth.REASON_UNTRUSTED_GRANT)
        self.assertFalse(decision.execution_authorized)

    def test_a_revoked_grant_is_blocked(self) -> None:
        decision = decide(grant_value={"revoked": True,
                                       "revoked_reason": "owner withdrew it"})
        self.assertEqual(decision.reason, auth.REASON_GRANT_REVOKED)
        self.assertIn("owner withdrew it", decision.detail)

    def test_an_expired_grant_is_blocked(self) -> None:
        decision = decide(grant_value={"expires_at": "2026-10-31T11:30:00+00:00"})
        self.assertEqual(decision.reason, auth.REASON_GRANT_EXPIRED)

    def test_a_grant_that_is_not_yet_valid_is_blocked(self) -> None:
        decision = decide(grant_value={"issued_at": "2026-10-31T12:30:00+00:00"})
        self.assertEqual(decision.reason, auth.REASON_GRANT_NOT_YET_VALID)

    def test_a_grant_without_usable_timestamps_is_blocked(self) -> None:
        decision = decide(grant_value={"issued_at": "", "expires_at": ""})
        self.assertEqual(decision.reason, auth.REASON_GRANT_NOT_YET_VALID)

    def test_an_inverted_time_window_is_blocked(self) -> None:
        decision = decide(grant_value={"issued_at": "2026-10-31T13:00:00+00:00",
                                       "expires_at": "2026-10-31T12:10:00+00:00"})
        self.assertEqual(decision.reason, auth.REASON_GRANT_WINDOW_INVALID)

    def test_an_unusable_evaluation_time_fails_closed(self) -> None:
        decision = auth.evaluate(request(), verdict=RESOLVABLE,
                                 registry_entry=REGISTRY_ENTRY,
                                 grant=grant(), now="not-a-timestamp")
        self.assertEqual(decision.state, auth.STATE_BLOCKED)

    def test_a_borrowed_grant_is_blocked(self) -> None:
        decision = decide(request_overrides={"subject": "someone-else"})
        self.assertEqual(decision.reason, auth.REASON_SUBJECT_MISMATCH)
        self.assertFalse(decision.execution_authorized)

    def test_an_operation_outside_the_grant_is_blocked(self) -> None:
        decision = decide(request_overrides={"operations": ("resolve", "import", "publish")})
        self.assertEqual(decision.reason, auth.REASON_OPERATION_NOT_GRANTED)
        self.assertIn("publish", decision.detail)

    def test_a_request_beyond_the_budget_is_blocked(self) -> None:
        decision = decide(request_overrides={"units": 3})
        self.assertEqual(decision.reason, auth.REASON_BUDGET_EXCEEDED)

    def test_an_exhausted_grant_is_blocked(self) -> None:
        decision = decide(grant_value={"max_uses": 1, "uses_consumed": 1})
        self.assertEqual(decision.reason, auth.REASON_USES_EXHAUSTED)


class InputValidationTests(unittest.TestCase):
    def test_empty_identity_fields_are_refused(self) -> None:
        for field in ("request_id", "skill_id", "skill_version", "account",
                      "pipeline", "stage", "subject"):
            decision = decide(request_overrides={field: "  "})
            self.assertEqual(decision.reason, auth.REASON_EMPTY_FIELD, field)

    def test_empty_operations_are_refused(self) -> None:
        self.assertEqual(decide(request_overrides={"operations": ()}).reason,
                         auth.REASON_EMPTY_FIELD)
        self.assertEqual(decide(request_overrides={"operations": ("",)}).reason,
                         auth.REASON_EMPTY_FIELD)

    def test_non_integer_or_out_of_range_units_are_refused(self) -> None:
        for units in (0, -1, True, 1.5, "1", None):
            decision = decide(request_overrides={"units": units})
            self.assertEqual(decision.reason, auth.REASON_INVALID_NUMBER, units)

    def test_invalid_grant_counts_are_refused(self) -> None:
        cases = ({"max_units": 0}, {"max_uses": 0}, {"uses_consumed": -1},
                 {"max_units": True}, {"max_uses": 1.5}, {"uses_consumed": "0"})
        for override in cases:
            decision = decide(grant_value=override)
            self.assertEqual(decision.reason, auth.REASON_INVALID_NUMBER, override)

    def test_empty_grant_identity_is_refused(self) -> None:
        for field in ("grant_id", "issuer", "subject"):
            decision = decide(grant_value={field: ""})
            self.assertEqual(decision.reason, auth.REASON_EMPTY_FIELD, field)


class ContextBindingTests(unittest.TestCase):
    def _assert_context_blocked(self, **overrides) -> None:
        decision = decide(request_overrides=overrides)
        self.assertEqual(decision.reason, auth.REASON_CONTEXT_MISMATCH, overrides)
        self.assertFalse(decision.execution_authorized)

    def test_account_must_match(self) -> None:
        self._assert_context_blocked(account="future-intelligence")

    def test_pipeline_must_match(self) -> None:
        self._assert_context_blocked(pipeline="M4")

    def test_stage_must_match(self) -> None:
        self._assert_context_blocked(stage="compose")

    def test_skill_version_must_match_the_grant(self) -> None:
        # The registry pin is satisfied here, so the mismatch is purely grant-bound.
        decision = decide(request_overrides={"skill_version": "0.8.221"},
                          grant_value={"skill_version": "0.8.222"},
                          registry={"id": "media-use",
                                    "source": {"version": "0.8.221"}})
        self.assertEqual(decision.reason, auth.REASON_CONTEXT_MISMATCH)
        self.assertFalse(decision.execution_authorized)

    def test_the_registry_pins_the_version(self) -> None:
        decision = decide(request_overrides={"skill_version": "0.8.221"},
                          grant_value={"skill_version": "0.8.221"})
        self.assertEqual(decision.reason, auth.REASON_VERSION_MISMATCH)

    def test_the_registry_pins_the_skill_id(self) -> None:
        decision = decide(request_overrides={"skill_id": "other-skill"},
                          grant_value={"skill_id": "other-skill"})
        self.assertEqual(decision.reason, auth.REASON_UNKNOWN_SKILL)


class DelegationTests(unittest.TestCase):
    def test_an_issuer_may_authorize_a_different_subject(self) -> None:
        decision = decide(request_overrides={"subject": "agent-1"},
                          grant_value={"issuer": "owner", "subject": "agent-1"})
        self.assertEqual(decision.state, auth.STATE_AUTHORIZED)
        self.assertTrue(decision.execution_authorized)

    def test_the_delegated_subject_is_still_pinned(self) -> None:
        decision = decide(request_overrides={"subject": "agent-2"},
                          grant_value={"issuer": "owner", "subject": "agent-1"})
        self.assertEqual(decision.reason, auth.REASON_SUBJECT_MISMATCH)


class AuthorizedTests(unittest.TestCase):
    def test_an_exact_grant_authorizes_one_execution(self) -> None:
        decision = decide()
        self.assertEqual(decision.state, auth.STATE_AUTHORIZED)
        self.assertEqual(decision.reason, auth.REASON_AUTHORIZED)
        self.assertTrue(decision.execution_authorized)
        self.assertEqual(decision.grant_id, "grant-1")
        self.assertEqual(decision.request_id, "req-1")

    def test_every_blocked_path_stays_unauthorized(self) -> None:
        scenarios = [
            dict(grant_value=None),
            dict(verdict=None),
            dict(grant_value={"revoked": True}),
            dict(grant_value={"expires_at": "2020-01-01T00:00:00Z"}),
            dict(verdict={"verdict": "BLOCKED", "reason": "UNKNOWN_SKILL"}),
            dict(grant_value={"provenance": ""}),
            dict(request_overrides={"subject": "someone-else"}),
        ]
        for scenario in scenarios:
            decision = decide(**scenario)
            self.assertEqual(decision.state, auth.STATE_BLOCKED, scenario)
            self.assertFalse(decision.execution_authorized, scenario)

    def test_the_decision_does_not_leak_context_or_paths(self) -> None:
        decision = decide()
        payload = decision.as_dict()
        self.assertEqual(set(payload), {"state", "reason", "detail", "request_id",
                                        "grant_id", "execution_authorized"})
        self.assertNotIn(PROVENANCE, str(payload))
        for marker in ("C:\\", "/home/", "api_key", "Bearer ", "token"):
            self.assertNotIn(marker, decision.detail)


if __name__ == "__main__":
    unittest.main()
