"""Offline, dependency-injected contract tests for PySceneDetect scene candidates."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.media import scene_analysis as scenes  # noqa: E402


class SceneAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        (self.project / "assets").mkdir()
        self.video = self.project / "assets" / "reference.mp4"
        self.video.write_bytes(b"test-only-video-payload")

    def tearDown(self):
        self.temp.cleanup()

    def test_candidate_receipt_bound_to_file_and_not_approved(self):
        calls = []
        def detector(path, threshold):
            calls.append((path, threshold))
            return [(0, 1.25), (1.25, 3.75)]
        result = scenes.analyze(self.project, "assets/reference.mp4", detector=detector)
        self.assertEqual(result["state"], "CANDIDATES_READY")
        self.assertEqual(result["scene_count"], 2)
        self.assertEqual(result["source_sha256"], hashlib.sha256(self.video.read_bytes()).hexdigest())
        self.assertEqual(result["scenes"][1]["duration_seconds"], 2.5)
        self.assertFalse(result["scenes"][0]["evidence_capable"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["publish_authorized"])
        self.assertEqual(calls, [(self.video.resolve(), 27.0)])
        receipt = scenes.write_receipt(self.project, result)
        self.assertEqual(json.loads(receipt.read_text(encoding="utf-8"))["source_sha256"],
                         result["source_sha256"])
        self.assertFalse((self.project / "script" / "storyboard.json").exists())

    def test_empty_detector_does_not_become_approval(self):
        result = scenes.analyze(self.project, "assets/reference.mp4",
                                detector=lambda *_: [])
        self.assertEqual(result["state"], "NO_SCENES_DETECTED")
        self.assertFalse(result["production_ready"])

    def test_source_outside_project_rejected(self):
        with self.assertRaisesRegex(scenes.SceneAnalysisError, "SOURCE_OUTSIDE_PROJECT"):
            scenes.analyze(self.project, "../reference.mp4", detector=lambda *_: [])
        outside = self.project.parent / "out-of-scope.mp4"
        outside.write_bytes(b"external")
        try:
            with self.assertRaisesRegex(scenes.SceneAnalysisError, "SOURCE_OUTSIDE_PROJECT"):
                scenes.analyze(self.project, str(outside), detector=lambda *_: [])
        finally:
            outside.unlink()

    def test_invalid_thresholds_and_nonvideo_rejected(self):
        for number in (0, -1, 256, float("nan"), float("inf")):
            with self.assertRaisesRegex(scenes.SceneAnalysisError, "INVALID_THRESHOLD"):
                scenes.analyze(self.project, "assets/reference.mp4",
                               threshold=number, detector=lambda *_: [])
        self.video.rename(self.project / "assets" / "reference.txt")
        with self.assertRaisesRegex(scenes.SceneAnalysisError, "UNSUPPORTED_SOURCE_VIDEO"):
            scenes.analyze(self.project, "assets/reference.txt", detector=lambda *_: [])

    def test_overlapping_or_malformed_scenes_rejected(self):
        for rows in ([(-1, 1)], [(0, 0)], [(0, 2), (1, 3)],
                     [(0, float("inf"))], [("not-a-time", 1)]):
            with self.assertRaises(scenes.SceneAnalysisError):
                scenes.analyze(self.project, "assets/reference.mp4",
                               detector=lambda *_: rows)

    def test_detector_error_never_creates_receipt(self):
        def failed(*_):
            raise scenes.SceneDetectorUnavailable("PYSCENEDETECT_NOT_INSTALLED")
        with self.assertRaises(scenes.SceneDetectorUnavailable):
            scenes.analyze(self.project, "assets/reference.mp4", detector=failed)
        self.assertFalse((self.project / "receipts").exists())

    def test_receipt_symlink_escape_rejected(self):
        outside = self.project / "outside"
        outside.mkdir()
        link = self.project / "receipts"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        # An in-project symlink is allowed by the current guarded local path policy.
        link.unlink()
        with tempfile.TemporaryDirectory() as separate:
            try:
                link.symlink_to(separate, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(scenes.SceneAnalysisError, "RECEIPTS_OUTSIDE_PROJECT"):
                scenes.write_receipt(self.project, {"state": "BLOCKED"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
