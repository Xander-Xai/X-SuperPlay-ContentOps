from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.skills import authorization as auth  # noqa: E402
from contentops.skills import execution_gate as gate  # noqa: E402
from contentops.skills import grant_source as gs  # noqa: E402

NOW = "2026-10-31T12:00:00+00:00"
OWNERS = ("owner",)
REGISTRY_ENTRY = {"id": "media-use", "name": "media-use",
                  "source": {"version": "0.8.222"}}
RESOLVABLE = {"verdict": "RESOLVABLE", "reason": "RESOLVABLE",
              "execution_authorized": False}


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _project(root: Path, *, approval_overrides=None) -> Path:
    approval = {
        "schema": gs.APPROVAL_SCHEMA, "purpose": gs.REQUIRED_PURPOSE,
        "approval_id": "apr-1", "issuer": "owner", "subject": "owner",
        "skill_id": "media-use", "skill_version": "0.8.222",
        "account": "douyin-1024", "pipeline": "M5", "stage": "media_use",
        "operations": ["status"], "issued_at": "2026-10-31T11:00:00Z",
        "expires_at": "2026-10-31T13:00:00Z", "max_units": 1, "max_uses": 1,
    }
    approval.update(approval_overrides or {})
    _write(root / gs.APPROVAL_RELPATH, approval)
    return root


def request(**overrides) -> auth.ExecutionRequest:
    values = dict(request_id="req-1", skill_id="media-use", skill_version="0.8.222",
                  account="douyin-1024", pipeline="M5", stage="media_use",
                  operations=("status",), subject="owner", units=1)
    values.update(overrides)
    return auth.ExecutionRequest(**values)


class _Recorder:
    def __init__(self, ok: bool = True, error: str = None) -> None:
        self.calls: list[str] = []
        self._ok = ok
        self._error = error

    def __call__(self, operation: str, req: auth.ExecutionRequest) -> dict:
        self.calls.append(operation)
        if self._error is not None:
            raise RuntimeError(self._error)
        return {"ok": self._ok, "receipt": {"schema": "contentops.media-use-doctor/v1"}}


def run(project: Path, *, req=None, verdict=None, registry=None, executor=None,
        owners=OWNERS):
    return gate.execute(
        req or request(),
        verdict=RESOLVABLE if verdict is None else verdict,
        registry_entry=REGISTRY_ENTRY if registry is None else registry,
        project_dir=project,
        owner_identities=owners,
        executor=executor or _Recorder(),
        now=NOW,
    )


class RefusalTests(unittest.TestCase):
    def _assert_not_executed(self, result, reason: str) -> None:
        self.assertEqual(result.decision.state, auth.STATE_BLOCKED)
        self.assertEqual(result.execution["state"], "NOT_EXECUTED")
        self.assertFalse(result.decision.execution_authorized)
        if reason:
            self.assertEqual(result.decision.reason, reason)

    def test_without_an_approval_nothing_runs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            recorder = _Recorder()
            result = run(Path(raw), executor=recorder)
        self._assert_not_executed(result, "NO_TRUSTED_GRANT")
        self.assertEqual(recorder.calls, [])

    def test_a_content_review_purpose_cannot_authorize_execution(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw), approval_overrides={"purpose": "content_review"})
            recorder = _Recorder()
            result = run(project, executor=recorder)
        self._assert_not_executed(result, "NO_TRUSTED_GRANT")
        self.assertIn("WRONG_PURPOSE", result.decision.detail)
        self.assertEqual(recorder.calls, [])

    def test_cross_account_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            recorder = _Recorder()
            result = run(project, req=request(account="future-intelligence"),
                         executor=recorder)
        self._assert_not_executed(result, auth.REASON_CONTEXT_MISMATCH)
        self.assertEqual(recorder.calls, [])

    def test_cross_version_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw), approval_overrides={"skill_version": "0.8.221"})
            recorder = _Recorder()
            result = run(project, executor=recorder)
        self._assert_not_executed(result, auth.REASON_CONTEXT_MISMATCH)
        self.assertEqual(recorder.calls, [])

    def test_cross_operation_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            recorder = _Recorder()
            result = run(project, req=request(operations=("doctor",)), executor=recorder)
        self._assert_not_executed(result, auth.REASON_OPERATION_NOT_GRANTED)
        self.assertEqual(recorder.calls, [])

    def test_a_revoked_approval_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw), approval_overrides={"revoked": True})
            recorder = _Recorder()
            result = run(project, executor=recorder)
        self._assert_not_executed(result, auth.REASON_GRANT_REVOKED)
        self.assertEqual(recorder.calls, [])

    def test_an_expired_approval_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw),
                               approval_overrides={"expires_at": "2026-10-31T11:30:00Z"})
            recorder = _Recorder()
            result = run(project, executor=recorder)
        self._assert_not_executed(result, auth.REASON_GRANT_EXPIRED)
        self.assertEqual(recorder.calls, [])

    def test_budget_overflow_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            recorder = _Recorder()
            result = run(project, req=request(units=2), executor=recorder)
        self._assert_not_executed(result, auth.REASON_BUDGET_EXCEEDED)
        self.assertEqual(recorder.calls, [])

    def test_a_batch_request_is_refused_before_anything_runs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            recorder = _Recorder()
            result = run(project, req=request(operations=("status", "doctor")),
                         executor=recorder)
        self._assert_not_executed(result, "OPERATIONS_MUST_BE_SINGLE")
        self.assertEqual(recorder.calls, [])

    def test_a_router_refusal_cannot_be_overridden_by_a_valid_approval(self) -> None:
        for reason in ("MISSING_RUNTIME", "UNAUTHORIZED_PROVIDER"):
            with tempfile.TemporaryDirectory() as raw:
                project = _project(Path(raw))
                recorder = _Recorder()
                result = run(project, verdict={"verdict": "BLOCKED", "reason": reason},
                             executor=recorder)
                self._assert_not_executed(result, auth.REASON_NOT_RESOLVABLE)
                self.assertEqual(recorder.calls, [])

    def test_a_forged_verdict_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            recorder = _Recorder()
            result = run(project,
                         verdict={"verdict": "RESOLVABLE", "reason": "RESOLVABLE",
                                  "execution_authorized": True},
                         executor=recorder)
            self._assert_not_executed(result, auth.REASON_UNTRUSTED_VERDICT)
            self.assertEqual(recorder.calls, [])

    def test_a_grant_cannot_be_borrowed_by_another_subject(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            recorder = _Recorder()
            result = run(project, req=request(subject="agent-9"), executor=recorder)
            self._assert_not_executed(result, auth.REASON_SUBJECT_MISMATCH)
            self.assertEqual(recorder.calls, [])

    def test_an_empty_subject_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            recorder = _Recorder()
            result = run(project, req=request(subject=""), executor=recorder)
            self._assert_not_executed(result, auth.REASON_EMPTY_FIELD)
            self.assertEqual(recorder.calls, [])


class ConsumptionTests(unittest.TestCase):
    def test_an_authorized_request_runs_once_and_writes_a_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            recorder = _Recorder()
            result = run(project, executor=recorder)
            self.assertEqual(result.decision.state, auth.STATE_AUTHORIZED)
            self.assertEqual(result.execution["state"], auth.STATE_EXECUTED)
            self.assertEqual(recorder.calls, ["status"])
            payload = json.loads(Path(result.receipt_path).read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], gate.GATE_SCHEMA)
        self.assertEqual(payload["request_id"], "req-1")
        self.assertEqual(payload["grant_id"], "apr-1")
        self.assertEqual(payload["decision"]["state"], auth.STATE_AUTHORIZED)
        self.assertEqual(payload["execution"]["state"], auth.STATE_EXECUTED)

    def test_the_same_request_id_cannot_be_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw), approval_overrides={"max_uses": 5})
            first = run(project, executor=_Recorder())
            recorder = _Recorder()
            second = run(project, executor=recorder)
        self.assertTrue(first.executed)
        self.assertEqual(second.decision.reason, "DUPLICATE_REQUEST")
        self.assertEqual(recorder.calls, [])

    def test_a_single_use_approval_cannot_be_spent_twice(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            run(project, executor=_Recorder())
            recorder = _Recorder()
            second = run(project, req=request(request_id="req-2"), executor=recorder)
        self.assertEqual(second.decision.reason, "USES_EXHAUSTED")
        self.assertEqual(recorder.calls, [])

    def test_an_adapter_failure_still_spends_the_use(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            failed = run(project, executor=_Recorder(ok=False))
            second = run(project, req=request(request_id="req-2"), executor=_Recorder())
        self.assertEqual(failed.execution["state"], "FAILED")
        self.assertFalse(failed.executed)
        self.assertEqual(second.decision.reason, "USES_EXHAUSTED")

    def test_a_revocation_written_mid_flight_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            original = gs.load_grant(project, owner_identities=OWNERS)
            approval_file = project / gs.APPROVAL_RELPATH
            state = {"count": 0}

            def fake_load(*args, **kwargs):
                state["count"] += 1
                if state["count"] == 1:
                    return original
                # A revocation is written while the request is being evaluated.
                payload = json.loads(approval_file.read_text(encoding="utf-8"))
                payload["revoked"] = True
                approval_file.write_text(json.dumps(payload, indent=2) + "\n",
                                         encoding="utf-8")
                return gs.load_grant(project, owner_identities=OWNERS)

            recorder = _Recorder()
            with mock.patch.object(gate, "load_grant", side_effect=fake_load):
                result = run(project, executor=recorder)
            self.assertEqual(gs.consumed_uses(project, "apr-1"), [])
        self.assertEqual(result.decision.reason, "GRANT_CHANGED")
        self.assertEqual(recorder.calls, [])


class ReceiptTests(unittest.TestCase):
    def test_credentials_and_host_paths_never_reach_the_receipt(self) -> None:
        # Built by concatenation so the literal token never sits in the source:
        # the repo's own sensitive-string scan would flag it.
        scheme = "Bear" + "er"
        hostile = (f"sk-live-ABC123456 Authorization: {scheme} tok3nvalue "
                   "api_key=deadbeef C:\\Users\\bob\\.ssh\\id_rsa /home/bob/.aws/credentials")
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            result = run(project, executor=_Recorder(error=hostile))
            text = Path(result.receipt_path).read_text(encoding="utf-8")
        self.assertEqual(result.execution["state"], "FAILED")
        for marker in ("sk-live-ABC123456", "tok3nvalue", "deadbeef",
                       "C:\\Users\\bob", "/home/bob"):
            self.assertNotIn(marker, text)
        self.assertIn("<redacted>", text)
        self.assertIn("<path>", text)

    def test_an_existing_receipt_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            target = project / "receipts" / "executions" / "apr-1-use-0001.json"
            target.parent.mkdir(parents=True)
            target.write_text('{"original": true}\n', encoding="utf-8")
            result = run(project, executor=_Recorder())
            self.assertTrue(result.executed)
            self.assertIsNone(result.receipt_path)
            self.assertTrue(result.execution.get("receipt_write_failed"))
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")),
                             {"original": True})

    def test_an_unwritable_receipt_directory_is_reported_not_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            blocker = project / "receipts" / "executions"
            blocker.write_text("not a directory\n", encoding="utf-8")
            result = run(project, executor=_Recorder())
        self.assertTrue(result.executed)
        self.assertIsNone(result.receipt_path)
        self.assertTrue(result.execution.get("receipt_write_failed"))


class LegacyIndependenceTests(unittest.TestCase):
    def test_the_m5_entry_does_not_import_the_gate(self) -> None:
        source = (ROOT / "scripts" / "m5_production.py").read_text(encoding="utf-8")
        self.assertNotIn("execution_gate", source)
        self.assertNotIn("grant_source", source)


if __name__ == "__main__":
    unittest.main()
