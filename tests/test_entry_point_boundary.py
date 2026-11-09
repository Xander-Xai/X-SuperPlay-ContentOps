"""Two video entry points, one that may reach review.

`run_v1` used to describe itself as the production path and label its output
``READY_FOR_HUMAN_REVIEW``. Anyone reading a receipt could not tell it apart from
`produce_video`. These tests pin the boundary in the place that matters: the
account workflow cannot be entered through the diagnostic door.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT / "src", ROOT / "scripts"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import run_v1  # noqa: E402


def _project(tmp: str, *, account: str | None) -> Path:
    project = Path(tmp) / "sample"
    project.mkdir(parents=True)
    lines = ["id: sample", "title: sample"]
    if account:
        lines.append(f"account_slug: {account}")
    (project / "project.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return project


class AccountBoundaryTests(unittest.TestCase):
    def test_account_bound_project_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(tmp, account="x-superplay-future-intelligence")
            result = run_v1.run(project, engine="fallback")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("produce_video.py", result["reason"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["publish_authorized"])
        self.assertFalse(result["eligible_for_human_review"])
        self.assertEqual(result["state"], "DIAGNOSTIC_ONLY")

    def test_account_id_is_treated_as_an_account_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "sample"
            project.mkdir()
            (project / "project.yaml").write_text(
                "id: sample\naccount_id: acct-9\n", encoding="utf-8")
            result = run_v1.run(project, engine="fallback")
        self.assertEqual(result["status"], "BLOCKED")

    def test_the_refusal_is_not_bypassable_from_the_cli(self):
        """The gate lives in run(), so `--engine` cannot route around it."""
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(tmp, account="acct")
            for engine in ("easel", "fallback"):
                with self.subTest(engine=engine):
                    self.assertEqual(
                        run_v1.run(project, engine=engine)["status"], "BLOCKED")


class LabellingTests(unittest.TestCase):
    def test_role_constant_is_diagnostic(self):
        self.assertEqual(run_v1.ENTRY_POINT_ROLE, "DIAGNOSTIC_ONLY")

    def test_no_path_still_claims_readiness_for_review(self):
        source = (ROOT / "scripts" / "run_v1.py").read_text(encoding="utf-8")
        self.assertNotIn('"READY_FOR_HUMAN_REVIEW"', source)
        self.assertIn("DIAGNOSTIC_ONLY", source)

    def test_help_text_calls_itself_diagnostic(self):
        text = (ROOT / "scripts" / "run_v1.py").read_text(encoding="utf-8")
        main_block = text[text.index("def main()"):]
        self.assertIn("DIAGNOSTIC", main_block)
        self.assertTrue("produce_video.py" in main_block
                        or "PRODUCTION_ENTRY_POINT" in main_block)

    def test_module_docstring_names_the_production_entry_point(self):
        doc = run_v1.__doc__ or ""
        self.assertIn("produce_video.py", doc)
        self.assertIn("NOT a production entry point", doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
