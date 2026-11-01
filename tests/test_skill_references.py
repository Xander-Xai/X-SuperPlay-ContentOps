"""Tests for the skill reference integrity check.

The check exists because five installed content skills describe commands and
modules that live on an unmerged branch. A skill that names code this checkout
does not have is a false capability, and the only honest way to keep that
visible is to make it a test failure when the record stops matching reality.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scripts", ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import check_skill_references as csr  # noqa: E402

STATUS_FILE = ROOT / "runtime" / "content-skill-status.json"


def _status(**overrides):
    record = {
        "schema": "contentops.content-skill-status/v1",
        "skills": [
            {
                "id": "demo-skill",
                "file": "demo-skill/SKILL.md",
                "state": "UNMERGED",
                "references": [],
            }
        ],
    }
    record.update(overrides)
    return record


class SkillReferenceStatusTests(unittest.TestCase):
    def test_status_file_is_valid_and_declares_the_installed_skills(self) -> None:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "contentops.content-skill-status/v1")
        ids = {skill["id"] for skill in data["skills"]}
        self.assertIn("x-superplay-broll-production", ids)
        self.assertIn("x-superplay-capture-plan", ids)
        self.assertIn("x-superplay-source-research", ids)
        self.assertIn("x-superplay-design-direction", ids)
        self.assertIn("x-superplay-copy-orchestrator", ids)
        for skill in data["skills"]:
            self.assertIn(skill["state"], ("UNMERGED", "MERGED", "DECLARED"))
            for ref in skill["references"]:
                self.assertTrue(ref["path"].startswith(tuple(csr.REPO_ROOTS)))
                self.assertIn("note", ref)

    def test_recorded_paths_are_absent_on_this_branch(self) -> None:
        """A recorded reference must not exist here, or the record is stale."""
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        for skill in data["skills"]:
            for ref in skill["references"]:
                self.assertFalse(
                    (ROOT / ref["path"]).exists(),
                    f"{ref['path']} exists on this branch; update the status record",
                )


class SkillReferenceCheckTests(unittest.TestCase):
    def test_undocumented_reference_is_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            repo = base / "repo"
            repo.mkdir()
            store = base / "store"
            skill_dir = store / "demo-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "Run `python scripts/ghost_command.py` to continue.\n",
                encoding="utf-8",
            )
            with mock.patch.object(csr, "ROOT", repo):
                failures, _ = csr.check(_status(), store)
        codes = {failure["code"] for failure in failures}
        self.assertIn("UNDOCUMENTED_REFERENCE", codes)

    def test_recorded_reference_that_now_exists_is_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            repo = base / "repo"
            (repo / "scripts").mkdir(parents=True)
            (repo / "scripts" / "now_here.py").write_text("# landed\n", encoding="utf-8")
            status = _status(skills=[
                {
                    "id": "demo-skill",
                    "file": "demo-skill/SKILL.md",
                    "state": "UNMERGED",
                    "references": [{"path": "scripts/now_here.py", "note": "merged"}],
                }
            ])
            with mock.patch.object(csr, "ROOT", repo):
                failures, _ = csr.check(status, None)
        codes = {failure["code"] for failure in failures}
        self.assertIn("RECORD_STALE", codes)

    def test_merged_state_without_the_code_is_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            repo = base / "repo"
            repo.mkdir()
            status = _status(skills=[
                {
                    "id": "demo-skill",
                    "file": "demo-skill/SKILL.md",
                    "state": "MERGED",
                    "references": [{"path": "scripts/absent.py", "note": "claimed"}],
                }
            ])
            with mock.patch.object(csr, "ROOT", repo):
                failures, _ = csr.check(status, None)
        codes = {failure["code"] for failure in failures}
        self.assertIn("STATE_MISMATCH", codes)

    def test_absent_store_skips_the_reference_scan(self) -> None:
        """A CI checkout has no shared store. That is a skip, not a failure."""
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            with mock.patch.object(csr, "ROOT", repo):
                failures, _ = csr.check(_status(), None)
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
