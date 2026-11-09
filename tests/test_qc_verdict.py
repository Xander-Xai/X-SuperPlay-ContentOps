"""One receipt, one verdict.

The bug this pins: M5 turned any non-FAIL into PASS, and the outer entry point
demanded PASS. A WARN render passed inside and failed outside. These tests fix
both sides to a single function and make the disagreement unrepresentable.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT / "src", ROOT / "scripts"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import produce_video  # noqa: E402
from contentops.media.qc_verdict import BLOCK, PROCEED, adjudicate  # noqa: E402


def _report(overall, *, graded="project://final/sample.mp4"):
    return {"overall": overall, "graded_target": graded, "checks": []}


class AdjudicationTests(unittest.TestCase):
    def test_pass_with_audio_proceeds(self):
        verdict = adjudicate(_report("PASS"), account_bound=True, audio_present=True)
        self.assertEqual(verdict.decision, PROCEED)
        self.assertFalse(verdict.legacy_warn_tolerated)

    def test_warn_blocks_an_account_bound_project(self):
        verdict = adjudicate(_report("WARN"), account_bound=True, audio_present=True)
        self.assertEqual(verdict.decision, BLOCK)
        self.assertIn("account-bound", " ".join(verdict.reasons))

    def test_warn_is_tolerated_only_for_unbound_samples_and_says_so(self):
        verdict = adjudicate(_report("WARN"), account_bound=False, audio_present=True)
        self.assertEqual(verdict.decision, PROCEED)
        self.assertTrue(verdict.legacy_warn_tolerated)

    def test_fail_blocks_whether_or_not_the_project_is_bound(self):
        for bound in (True, False):
            with self.subTest(bound=bound):
                verdict = adjudicate(_report("FAIL"), account_bound=bound, audio_present=True)
                self.assertEqual(verdict.decision, BLOCK)

    def test_a_silent_render_blocks_even_on_pass(self):
        verdict = adjudicate(_report("PASS"), account_bound=False, audio_present=False)
        self.assertEqual(verdict.decision, BLOCK)
        self.assertIn("no audio stream", " ".join(verdict.reasons))

    def test_unreadable_overall_fails_closed(self):
        for value in (None, "", "OK", "PASSED", 1):
            with self.subTest(value=value):
                verdict = adjudicate(_report(value), account_bound=False, audio_present=True)
                self.assertEqual(verdict.decision, BLOCK)

    def test_the_measured_overall_is_never_rewritten(self):
        for value in ("PASS", "WARN", "FAIL"):
            with self.subTest(value=value):
                verdict = adjudicate(_report(value), account_bound=True, audio_present=True)
                self.assertEqual(verdict.overall, value)
                self.assertEqual(verdict.as_dict()["overall"], value)


class EntryPointAgreementTests(unittest.TestCase):
    """produce_video must inherit M5's decision, not invent a second one."""

    def _project(self, tmp: str, *, account: str | None) -> Path:
        project = Path(tmp) / "sample"
        (project / "final").mkdir(parents=True)
        (project / "receipts").mkdir(parents=True)
        (project / "final" / "sample.mp4").write_bytes(b"\0" * 64)
        lines = ["id: sample"]
        if account:
            lines.append(f"account_slug: {account}")
        (project / "project.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return project

    def test_embedded_verdict_is_inherited(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(tmp, account="acct")
            video = project / "final" / "sample.mp4"
            report = _report("WARN")
            report["m5_checks"] = {"verdict": {
                "overall": "WARN", "decision": BLOCK, "account_bound": True,
                "audio_present": True, "reasons": ["warn on account-bound"],
                "legacy_warn_tolerated": False}}
            inherited = produce_video._qc_verdict(project, report, video)
        self.assertEqual(inherited["decision"], BLOCK)

    def test_tampered_embedded_verdict_is_recomputed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(tmp, account="acct")
            video = project / "final" / "sample.mp4"
            report = _report("WARN")
            report["m5_checks"] = {"verdict": {
                "overall": "PASS", "decision": PROCEED, "account_bound": True,
                "audio_present": True, "reasons": [],
                "legacy_warn_tolerated": False}}
            recomputed = produce_video._qc_verdict(project, report, video)
        # The embedded verdict claims PASS for a receipt that measured WARN.
        self.assertEqual(recomputed["overall"], "WARN")
        self.assertEqual(recomputed["decision"], BLOCK)

    def test_account_binding_is_read_from_the_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            bound = self._project(tmp, account="acct")
            self.assertTrue(produce_video._account_bound(bound))
        with tempfile.TemporaryDirectory() as tmp:
            unbound = self._project(tmp, account=None)
            self.assertFalse(produce_video._account_bound(unbound))


class ReuseTests(unittest.TestCase):
    """A tolerated WARN is never reused as an already-QC-passed render."""

    def _seed(self, tmp: str, *, overall: str, graded: str) -> tuple[Path, str, str]:
        project = Path(tmp) / "sample"
        (project / "final").mkdir(parents=True)
        (project / "receipts").mkdir(parents=True)
        video = project / "final" / "sample.mp4"
        video.write_bytes(b"\0" * 128)
        digest = hashlib.sha256(b"inputs").hexdigest()
        video_sha = hashlib.sha256(video.read_bytes()).hexdigest()
        (project / "receipts" / "produce-video.json").write_text(json.dumps({
            "input_sha256": digest, "state": "QC_PASSED", "video_sha256": video_sha,
        }), encoding="utf-8")
        (project / "receipts" / "qc-report-sample.json").write_text(json.dumps({
            "overall": overall, "graded_target": graded, "checks": [],
            "m5_checks": {"audio_stream": True, "verdict": {
                "overall": overall,
                "decision": PROCEED if overall == "PASS" else BLOCK,
                "account_bound": False, "audio_present": True,
                "reasons": [], "legacy_warn_tolerated": overall == "WARN"}},
        }), encoding="utf-8")
        (project / "receipts" / "visual-gate.json").write_text(json.dumps({
            "state": "PASS", "video_sha256": video_sha,
            "contact_sheet": "project://receipts/visual-contact-sheet.png",
        }), encoding="utf-8")
        (project / "receipts" / "visual-contact-sheet.png").write_bytes(b"png")
        (project / "project.yaml").write_text("id: sample\n", encoding="utf-8")
        return project, digest, video_sha

    def test_matching_pass_is_reusable(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, digest, _ = self._seed(
                tmp, overall="PASS", graded="project://final/sample.mp4")
            self.assertIsNotNone(produce_video._reusable(project, digest))

    def test_tolerated_warn_is_not_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, digest, _ = self._seed(
                tmp, overall="WARN", graded="project://final/sample.mp4")
            # Unbound, so adjudication tolerates it — reuse still must not.
            self.assertIsNone(produce_video._reusable(project, digest))

    def test_report_grading_a_different_render_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, digest, _ = self._seed(
                tmp, overall="PASS", graded="project://final/other.mp4")
            self.assertIsNone(produce_video._reusable(project, digest))


if __name__ == "__main__":
    unittest.main(verbosity=2)
