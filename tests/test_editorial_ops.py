"""Synthetic offline tests; no real account actions."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import editorial_ops as ops


class EditorialTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = ops.init(Path(tmp.name))
        self.topic = dict(zip(ops.FIELDS["topics.csv"], [
            "agent", "x-superplay-english", "x", "text", "developers", "recovery",
            "agent-series", "What failed?", "Discuss", "2026-11-26",
            "10", "low", "Founder", "9", "9", "9", "9", "9", "9"]))
        self.signal = dict(zip(ops.FIELDS["signals.csv"], [
            "s1", "agent", "issue", "https://example.org/issue/1",
            "2026-11-26T00:00:00+08:00", "Synthetic problem"]))

    def add(self, name, row):
        with (self.directory / name).open("a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=ops.FIELDS[name]).writerow(row)

    def test_dedup_and_plan(self):
        self.add("signals.csv", self.signal)
        self.add("signals.csv", dict(self.signal, signal_id="s2"))
        self.add("topics.csv", self.topic)
        ops.init(self.directory)
        report = ops.plan(self.directory)
        item = report["queue"][0]
        self.assertEqual(item["decision"], "CANDIDATE")
        self.assertEqual(item["unique_source_urls"], 1)
        self.assertEqual(item["cost_lane"], "L1")
        self.assertEqual(item["score"], 90)
        self.assertFalse(item["publish_authorized"])
        ops.save(self.directory, report)
        self.assertTrue((self.directory / "editorial-plan.json").is_file())

    def test_no_evidence(self):
        self.add("topics.csv", self.topic)
        self.assertEqual(ops.plan(self.directory)["queue"][0]["decision"], "NEEDS_EVIDENCE")

    def test_invalid_score(self):
        self.add("topics.csv", dict(self.topic, demand="11"))
        with self.assertRaises(ValueError):
            ops.plan(self.directory)

    def test_wrong_platform(self):
        self.add("topics.csv", dict(self.topic, platform="douyin"))
        with self.assertRaises(ValueError):
            ops.plan(self.directory)

    def test_bad_source(self):
        self.add("signals.csv", dict(self.signal, source_url="https://user:pw@example.org/a"))
        with self.assertRaises(ValueError):
            ops.plan(self.directory)

    def test_cost(self):
        self.assertEqual(ops.lane(10, "high"), "L3")
        self.assertEqual(ops.lane(45, "low"), "L2")

    def test_hotspot_import(self):
        path = self.directory / "candidates.json"
        candidate = {"account_id": "x-superplay-english", "url": self.signal["source_url"],
                     "title": "Synthetic", "collected_at": self.signal["observed_at"],
                     "relevance": {"accepted": True}}
        path.write_text(json.dumps([candidate, dict(candidate, account_id="other")]), encoding="utf-8")
        self.assertEqual(ops.import_hotspots(self.directory, path, "agent", "x-superplay-english")["added"], 1)
        self.assertEqual(ops.import_hotspots(self.directory, path, "agent", "x-superplay-english")["added"], 0)

    def test_dashboard_and_handoff(self):
        self.add("signals.csv", self.signal)
        self.add("topics.csv", dict(self.topic, angle="<script>alert(1)</script>"))
        report = ops.plan(self.directory)
        ops.dashboard(self.directory, report)
        page = (self.directory / "editorial-workspace.html").read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>", page)
        ident = report["queue"][0]["id"]
        with self.assertRaises(ValueError):
            ops.prepare_handoff(self.directory, report, ident, "Founder", False)
        result = ops.prepare_handoff(self.directory, report, ident, "Founder", True)
        self.assertIn("--url", result["argv"])
        self.assertFalse(result["publish_authorized"])

    def test_local_only(self):
        with self.assertRaises(ValueError):
            ops.local_dir(ops.ROOT / "docs")


if __name__ == "__main__":
    unittest.main()
