from __future__ import annotations

import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.skills import grant_source as gs  # noqa: E402
from process_utils import hidden_run, python_executable  # noqa: E402

NOW = "2026-10-31T12:00:00+00:00"
OWNERS = ("owner",)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _evidence(project: Path, **overrides) -> dict:
    payload = {"decision": "APPROVED", "reviewer": "owner",
               "reviewed_at": "2026-10-31T11:30:00Z"}
    payload.update(overrides)
    _write(project / gs.EVIDENCE_RELPATH, payload)
    return payload


def _approval(project: Path, *, evidence: dict = None, **overrides) -> dict:
    payload = {
        "schema": gs.APPROVAL_SCHEMA,
        "purpose": gs.REQUIRED_PURPOSE,
        "approval_id": "apr-1",
        "issuer": "owner",
        "subject": "owner",
        "skill_id": "media-use",
        "skill_version": "0.8.222",
        "account": "douyin-1024",
        "pipeline": "M5",
        "stage": "media_use",
        "operations": ["status"],
        "issued_at": "2026-10-31T11:00:00Z",
        "expires_at": "2026-10-31T13:00:00Z",
        "max_units": 1,
        "max_uses": 1,
    }
    if evidence is not None:
        payload["evidence"] = {"record": "receipts/human-review.json",
                               "sha256": gs.record_digest(evidence)}
    payload.update(overrides)
    _write(project / gs.APPROVAL_RELPATH, payload)
    return payload


class LoadGrantTests(unittest.TestCase):
    def test_a_valid_approval_loads(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            _approval(project)
            grant = gs.load_grant(project, owner_identities=OWNERS)
        self.assertEqual(grant.grant_id, "apr-1")
        self.assertEqual(grant.operations, ("status",))
        self.assertTrue(grant.provenance.startswith("sha256:"))

    def test_no_record_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.load_grant(Path(raw), owner_identities=OWNERS)
        self.assertEqual(caught.exception.code, "NO_GRANT_RECORD")

    def test_wrong_schema_and_purpose_are_refused(self) -> None:
        for override, code in (({"schema": "x/v1"}, "GRANT_SCHEMA"),
                               ({"purpose": "content_review"}, "WRONG_PURPOSE")):
            with tempfile.TemporaryDirectory() as raw:
                project = Path(raw)
                _approval(project, **override)
                with self.assertRaises(gs.GrantSourceError) as caught:
                    gs.load_grant(project, owner_identities=OWNERS)
                self.assertEqual(caught.exception.code, code, override)

    def test_an_unlisted_or_empty_owner_set_trusts_nothing(self) -> None:
        for owners in (("someone-else",), ()):
            with tempfile.TemporaryDirectory() as raw:
                project = Path(raw)
                _approval(project)
                with self.assertRaises(gs.GrantSourceError) as caught:
                    gs.load_grant(project, owner_identities=owners)
                self.assertEqual(caught.exception.code, "ISSUER_NOT_APPROVED", owners)

    def test_a_wildcard_account_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            _approval(project, account="*")
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.load_grant(project, owner_identities=OWNERS)
        self.assertEqual(caught.exception.code, "GRANT_INVALID")

    def test_evidence_is_checked_but_never_required_to_authorize(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            evidence = _evidence(project)
            _approval(project, evidence=evidence)
            self.assertEqual(gs.load_grant(project, owner_identities=OWNERS).grant_id,
                             "apr-1")

    def test_tampered_evidence_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            evidence = _evidence(project)
            _approval(project, evidence=evidence)
            _evidence(project, decision="REJECTED")
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.load_grant(project, owner_identities=OWNERS)
        self.assertEqual(caught.exception.code, "EVIDENCE_TAMPERED")

    def test_invalid_operations_and_counts_are_refused(self) -> None:
        for override in ({"operations": []}, {"operations": "status"},
                         {"max_uses": 0}, {"max_units": True}):
            with tempfile.TemporaryDirectory() as raw:
                project = Path(raw)
                _approval(project, **override)
                with self.assertRaises(gs.GrantSourceError) as caught:
                    gs.load_grant(project, owner_identities=OWNERS)
                self.assertEqual(caught.exception.code, "GRANT_INVALID", override)

    def test_an_unsafe_approval_id_is_refused(self) -> None:
        cases = ("../evil", "..", "a/b", "a\\b", "C:\\abs", "/abs", "a b",
                 ".hidden", "-lead", "x" * 80, "con")
        for approval_id in cases:
            with tempfile.TemporaryDirectory() as raw:
                project = Path(raw) / "project"
                project.mkdir()
                _approval(project, approval_id=approval_id)
                with self.assertRaises(gs.GrantSourceError) as caught:
                    gs.load_grant(project, owner_identities=OWNERS)
                self.assertEqual(caught.exception.code, "UNSAFE_PATH", approval_id)


class PathSafetyTests(unittest.TestCase):
    def _grant(self, project: Path, approval_id: str = "apr-1"):
        _approval(project, approval_id=approval_id)
        return gs.load_grant(project, owner_identities=OWNERS)

    def test_traversal_never_creates_a_file_outside_the_project(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            outside = Path(raw)
            project = outside / "project"
            project.mkdir()
            grant = self._grant(project)
            tampered = gs.ExecutionGrant(**{**grant.__dict__, "grant_id": "../escaped"})
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.consume(project, grant=tampered, request_id="r1", now=NOW)
            self.assertEqual(caught.exception.code, "UNSAFE_PATH")
            self.assertFalse((outside / "escaped").exists())
            self.assertFalse((outside / "escaped").is_dir())

    def test_a_symlinked_receipts_directory_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            outside = Path(raw) / "outside"
            outside.mkdir()
            project = Path(raw) / "project"
            project.mkdir()
            try:
                (project / "receipts").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are not available on this host")
            _approval(project)
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.load_grant(project, owner_identities=OWNERS)
            self.assertEqual(caught.exception.code, "UNSAFE_PATH")

    def test_a_symlinked_grant_directory_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            outside = Path(raw) / "outside"
            outside.mkdir()
            project = Path(raw) / "project"
            project.mkdir()
            grant = self._grant(project)
            try:
                (project / "receipts" / "grants").mkdir(parents=True, exist_ok=True)
                (project / "receipts" / "grants" / grant.grant_id).symlink_to(
                    outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are not available on this host")
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.consume(project, grant=grant, request_id="r1", now=NOW)
            self.assertEqual(caught.exception.code, "UNSAFE_PATH")
            self.assertEqual(list(outside.iterdir()), [])

    def test_a_missing_project_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.load_grant(Path(raw) / "absent", owner_identities=OWNERS)
        self.assertEqual(caught.exception.code, "PROJECT_INVALID")


class ConsumptionTests(unittest.TestCase):
    def _grant(self, project: Path, **overrides):
        _approval(project, **overrides)
        return gs.load_grant(project, owner_identities=OWNERS)

    def test_one_use_is_spent_once(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            grant = self._grant(project)
            spent = gs.consume(project, grant=grant, request_id="req-1", now=NOW)
            self.assertEqual(spent["use"], 1)
            self.assertEqual(gs.consumed_uses(project, "apr-1"), ["use-0001.json"])

    def test_a_second_use_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            grant = self._grant(project)
            gs.consume(project, grant=grant, request_id="req-1", now=NOW)
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.consume(project, grant=grant, request_id="req-2", now=NOW)
        self.assertEqual(caught.exception.code, "USES_EXHAUSTED")

    def test_the_same_request_id_cannot_spend_a_second_use(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            grant = self._grant(project, max_uses=5)
            gs.consume(project, grant=grant, request_id="req-1", now=NOW)
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.consume(project, grant=grant, request_id="req-1", now=NOW)
            self.assertEqual(caught.exception.code, "DUPLICATE_REQUEST")
            self.assertEqual(len(gs.consumed_uses(project, "apr-1")), 1)

    def test_different_grants_do_not_share_a_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            first = self._grant(project, approval_id="apr-a")
            second = self._grant(project, approval_id="apr-b")
            gs.consume(project, grant=first, request_id="r-a", now=NOW)
            gs.consume(project, grant=second, request_id="r-b", now=NOW)
            self.assertEqual(gs.consumed_uses(project, "apr-a"), ["use-0001.json"])
            self.assertEqual(gs.consumed_uses(project, "apr-b"), ["use-0001.json"])

    def test_threads_cannot_both_spend_the_last_use(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            grant = self._grant(project)

            def attempt(index: int) -> bool:
                try:
                    gs.consume(project, grant=grant, request_id=f"req-{index}", now=NOW)
                    return True
                except gs.GrantSourceError:
                    return False

            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(attempt, range(8)))
        self.assertEqual(sum(results), 1, results)

    def test_separate_processes_cannot_both_spend_the_last_use(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            self._grant(project)
            code = (
                "import sys; sys.path[:0]=[r'{src}', r'{scripts}'];"
                "from pathlib import Path;"
                "from contentops.skills import grant_source as gs;"
                "p=Path(r'{project}');"
                "g=gs.load_grant(p, owner_identities=['owner']);"
                "out=[]\n"
                "try:\n"
                "    gs.consume(p, grant=g, request_id=sys.argv[1], now='{now}'); print('WON')\n"
                "except gs.GrantSourceError as e:\n"
                "    print('LOST', e.code)\n"
            ).format(src=str(ROOT / "src"), scripts=str(ROOT / "scripts"),
                     project=str(project), now=NOW)

            def run(index: int):
                return hidden_run([python_executable(), "-c", code, f"req-{index}"],
                                  cwd=str(ROOT)).stdout or ""

            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(run, range(4)))
            self.assertEqual(sum(1 for item in results if "WON" in item), 1, results)


if __name__ == "__main__":
    unittest.main()
