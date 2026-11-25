"""FI duration planning and measured QC; no rendering or publishing."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import qc_video
from contentops.routing.account_profile import load_profile
from contentops.script.draft import _duration_targets, ScriptBlocked


class DurationTests(unittest.TestCase):
    def test_profile_and_explicit_target(self):
        fi = load_profile(ROOT, "x-superplay-future-intelligence")
        other = load_profile(ROOT, "x-superplay-1024")
        self.assertEqual(fi.target_duration_s, (30, 300))
        self.assertEqual(fi.manual_recording, "FORBIDDEN")
        self.assertEqual(_duration_targets(fi), (30, 300, 90))
        for seconds in (30, 60, 150, 300):
            self.assertEqual(_duration_targets(fi, seconds), (30, 300, seconds))
        for seconds in (29, 301, float("nan")):
            with self.assertRaises(ScriptBlocked):
                _duration_targets(fi, seconds)
        self.assertEqual(_duration_targets(other), (45, 60, 45))
        with self.assertRaises(ScriptBlocked):
            _duration_targets(other, 150)

    def test_measured_qc(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "project.yaml").write_text("account_slug: x-superplay-future-intelligence\n", encoding="utf-8")
            for seconds in (30, 60, 150, 300):
                self.assertEqual(qc_video.duration_check(p, seconds)["severity"], "PASS")
            self.assertEqual(qc_video.duration_check(p, 300.001)["severity"], "FAIL")
            self.assertEqual(qc_video.duration_check(p, 15)["severity"], "WARN")
            (p / "project.yaml").write_text("account_slug: x-superplay-1024\n", encoding="utf-8")
            self.assertEqual(qc_video.duration_check(p, 121)["severity"], "WARN")
            self.assertEqual(qc_video.duration_check(p, 120)["severity"], "PASS")


if __name__ == "__main__":
    unittest.main()
