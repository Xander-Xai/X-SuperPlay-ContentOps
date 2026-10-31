from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

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


def _project(root: Path, *, review_overrides=None, grant_overrides=None) -> Path:
    review = {"project": "projects/demo", "reviewer": "owner",
              "reviewed_at": "2026-10-31T11:30:00Z", "decision": "APPROVED",
              "scores": {"overall": 4}}
    review.update(review_overrides or {})
    _write(root / gs.REVIEW_RELPATH, review)
    grant = {
        "schema": gs.GRANT_SCHEMA, "grant_id": "grant-1", "issuer": "owner",
        "subject": "owner", "skill_id": "media-use", "skill_version": "0.8.222",
        "account": "douyin-1024", "pipeline": "M5", "stage": "media_use",
        "operations": ["status"], "issued_at": "2026-10-31T11:00:00Z",
        "expires_at": "2026-10-31T13:00:00Z", "max_units": 1, "max_uses": 1,
        "approval": {"record": "receipts/human-review.json",
                     "sha256": gs.record_digest(review)},
    }
    grant.update(grant_overrides or {})
    _write(root / gs.GRANT_RELPATH, grant)
    return root


def request(**overrides) -> auth.ExecutionRequest:
    values = dict(request_id="req-1", skill_id="media-use", skill_version="0.8.222",
                  account="douyin-1024", pipeline="M5", stage="media_use",
                  operations=("status",), subject="owner", units=1)
    values.update(overrides)
    return auth.ExecutionRequest(**values)


class _Recorder:
    def __init__(self, ok: bool = True) -> None:
        self.calls: list[str] = []
        self._ok = ok

    def __call__(self, operation: str, req: auth.ExecutionRequest) -> dict:
        self.calls.append(operation)
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

    def test_without_a_grant_record_nothing_runs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            recorder = _Recorder()
            result = run(Path(raw), executor=recorder)
        self._assert_not_executed(result, "NO_TRUSTED_GRANT")
        self.assertEqual(recorder.calls, [])

    def test_a_pending_review_blocks_execution(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw), review_overrides={"decision": None},
                               grant_overrides={})
            # The grade grant digest no longer matches after the review changes.
            recorder = _Recorder()
            result = run(project, executor=recorder)
        self._assert_not_executed(result, "NO_TRUSTED_GRANT")
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
            project = _project(Path(raw),
                               grant_overrides={"skill_version": "0.8.221"})
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

    def test_a_revoked_grant_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw), grant_overrides={"revoked": True})
            recorder = _Recorder()
            result = run(project, executor=recorder)
        self._assert_not_executed(result, auth.REASON_GRANT_REVOKED)
        self.assertEqual(recorder.calls, [])

    def test_an_expired_grant_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw),
                               grant_overrides={"expires_at": "2026-10-31T11:30:00Z"})
            recorder = _Recorder()
            result = run(project, executor=recorder)
        self._assert_not_executed(result, auth.REASON_GRANT_EXPIRED)
        self.assertEqual(recorder.calls, [])

    def test_budget_overflow_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw), grant_overrides={"max_units": 1})
            recorder = _Recorder()
            result = run(project, req=request(units=2), executor=recorder)
        self._assert_not_executed(result, auth.REASON_BUDGET_EXCEEDED)
        self.assertEqual(recorder.calls, [])

    def test_a_router_refusal_cannot_be_overridden_by_a_valid_grant(self) -> None:
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


class ExecutionTests(unittest.TestCase):
    def test_an_authorized_request_runs_once_and_writes_a_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            recorder = _Recorder()
            result = run(project, executor=recorder)
            self.assertEqual(result.decision.state, auth.STATE_AUTHORIZED)
            self.assertEqual(result.execution["state"], auth.STATE_EXECUTED)
            self.assertEqual(recorder.calls, ["status"])
            self.assertTrue(result.receipt_path)
            payload = json.loads(Path(result.receipt_path).read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], gate.GATE_SCHEMA)
        self.assertEqual(payload["request_id"], "req-1")
        self.assertEqual(payload["grant_id"], "grant-1")
        self.assertEqual(payload["execution"]["state"], auth.STATE_EXECUTED)
        self.assertEqual(payload["scope"]["account"], "douyin-1024")

    def test_the_receipt_does_not_record_a_reusable_credential(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            result = run(project, executor=_Recorder())
            text = Path(result.receipt_path).read_text(encoding="utf-8")
        for marker in ("sha256:", "api_key", "Bearer ", "secret"):
            self.assertNotIn(marker, text)

    def test_a_second_request_cannot_reuse_the_single_use_grant(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            first = run(project, executor=_Recorder())
            recorder = _Recorder()
            second = run(project, req=request(request_id="req-2"), executor=recorder)
        self.assertTrue(first.executed)
        self.assertEqual(second.decision.state, auth.STATE_BLOCKED)
        self.assertEqual(second.decision.reason, "USES_EXHAUSTED")
        self.assertEqual(second.execution["state"], "NOT_EXECUTED")
        self.assertEqual(recorder.calls, [])

    def test_an_adapter_failure_is_recorded_and_the_use_stays_spent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            result = run(project, executor=_Recorder(ok=False))
            self.assertEqual(result.decision.state, auth.STATE_AUTHORIZED)
            self.assertEqual(result.execution["state"], "FAILED")
            second = run(project, req=request(request_id="req-2"), executor=_Recorder())
        self.assertEqual(second.decision.reason, "USES_EXHAUSTED")

    def test_an_adapter_exception_is_recorded_not_raised(self) -> None:
        def explode(operation, req):
            raise RuntimeError("runtime lock mismatch")

        with tempfile.TemporaryDirectory() as raw:
            project = _project(Path(raw))
            result = run(project, executor=explode)
        self.assertEqual(result.execution["state"], "FAILED")
        self.assertIn("runtime lock mismatch", result.execution["error"])


class LegacyIndependenceTests(unittest.TestCase):
    def test_the_m5_entry_does_not_import_the_gate(self) -> None:
        source = (ROOT / "scripts" / "m5_production.py").read_text(encoding="utf-8")
        self.assertNotIn("execution_gate", source)
        self.assertNotIn("grant_source", source)


if __name__ == "__main__":
    unittest.main()
