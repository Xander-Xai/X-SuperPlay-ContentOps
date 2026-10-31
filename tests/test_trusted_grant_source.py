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

NOW = "2026-10-31T12:00:00+00:00"
OWNERS = ("owner",)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _review(project: Path, **overrides) -> dict:
    payload = {"project": "projects/demo", "state": "PENDING_FOUNDER_REVIEW",
               "reviewer": "owner", "reviewed_at": "2026-10-31T11:30:00Z",
               "decision": "APPROVED", "scores": {"overall": 4}}
    payload.update(overrides)
    _write(project / gs.REVIEW_RELPATH, payload)
    return payload


def _grant(project: Path, review_payload: dict, **overrides) -> dict:
    payload = {
        "schema": gs.GRANT_SCHEMA,
        "grant_id": "grant-1",
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
        "approval": {"record": "receipts/human-review.json",
                     "sha256": gs.record_digest(review_payload)},
    }
    payload.update(overrides)
    _write(project / gs.GRANT_RELPATH, payload)
    return payload


class LoadGrantTests(unittest.TestCase):
    def test_a_grant_anchored_to_an_approved_review_loads(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            review = _review(project)
            _grant(project, review)
            grant = gs.load_grant(project, owner_identities=OWNERS)
        self.assertEqual(grant.grant_id, "grant-1")
        self.assertEqual(grant.operations, ("status",))
        self.assertEqual(grant.provenance, gs.record_digest(review))

    def test_no_grant_record_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.load_grant(Path(raw), owner_identities=OWNERS)
        self.assertEqual(caught.exception.code, "NO_GRANT_RECORD")

    def test_a_wrong_schema_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            review = _review(project)
            _grant(project, review, schema="something.else/v1")
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.load_grant(project, owner_identities=OWNERS)
        self.assertEqual(caught.exception.code, "GRANT_SCHEMA")

    def test_an_unlisted_issuer_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            review = _review(project)
            _grant(project, review, issuer="someone-else")
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.load_grant(project, owner_identities=OWNERS)
        self.assertEqual(caught.exception.code, "ISSUER_NOT_APPROVED")

    def test_an_empty_owner_list_trusts_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            review = _review(project)
            _grant(project, review)
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.load_grant(project, owner_identities=())
        self.assertEqual(caught.exception.code, "ISSUER_NOT_APPROVED")

    def test_a_pending_review_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            review = _review(project, decision=None)
            _grant(project, review)
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.load_grant(project, owner_identities=OWNERS)
        self.assertEqual(caught.exception.code, "APPROVAL_NOT_APPROVED")

    def test_a_review_without_reviewer_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            review = _review(project, reviewer=None)
            _grant(project, review)
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.load_grant(project, owner_identities=OWNERS)
        self.assertEqual(caught.exception.code, "APPROVAL_INVALID")

    def test_a_missing_review_record_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            review = _review(project)
            _grant(project, review)
            (project / gs.REVIEW_RELPATH).unlink()
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.load_grant(project, owner_identities=OWNERS)
        self.assertEqual(caught.exception.code, "APPROVAL_MISSING")

    def test_editing_the_review_after_approval_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            review = _review(project)
            _grant(project, review)
            _review(project, decision="REJECTED")
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.load_grant(project, owner_identities=OWNERS)
        self.assertEqual(caught.exception.code, "APPROVAL_NOT_APPROVED")

    def test_an_edited_score_breaks_the_digest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            review = _review(project)
            _grant(project, review)
            _review(project, scores={"overall": 5})
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.load_grant(project, owner_identities=OWNERS)
        self.assertEqual(caught.exception.code, "APPROVAL_TAMPERED")

    def test_invalid_operations_and_counts_are_refused(self) -> None:
        for override in ({"operations": []}, {"operations": "status"},
                         {"max_uses": 0}, {"max_units": True}):
            with tempfile.TemporaryDirectory() as raw:
                project = Path(raw)
                review = _review(project)
                _grant(project, review, **override)
                with self.assertRaises(gs.GrantSourceError) as caught:
                    gs.load_grant(project, owner_identities=OWNERS)
                self.assertEqual(caught.exception.code, "GRANT_INVALID", override)


class ConsumptionTests(unittest.TestCase):
    def _grant(self, project: Path, **overrides):
        review = _review(project)
        _grant(project, review, **overrides)
        return gs.load_grant(project, owner_identities=OWNERS)

    def test_one_use_is_spent_once(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            grant = self._grant(project)
            spent = gs.consume(project, grant=grant, request_id="req-1", now=NOW)
            self.assertEqual(spent["use"], 1)
            self.assertEqual(gs.consumed_uses(project, "grant-1"), ["use-0001.json"])

    def test_a_second_use_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            grant = self._grant(project)
            gs.consume(project, grant=grant, request_id="req-1", now=NOW)
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.consume(project, grant=grant, request_id="req-2", now=NOW)
        self.assertEqual(caught.exception.code, "USES_EXHAUSTED")

    def test_concurrent_callers_cannot_both_spend_the_last_use(self) -> None:
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
            self.assertEqual(len(gs.consumed_uses(project, "grant-1")), 1)

    def test_an_empty_request_id_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            grant = self._grant(project)
            with self.assertRaises(gs.GrantSourceError) as caught:
                gs.consume(project, grant=grant, request_id="  ", now=NOW)
        self.assertEqual(caught.exception.code, "REQUEST_ID")


if __name__ == "__main__":
    unittest.main()
