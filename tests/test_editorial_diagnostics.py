#!/usr/bin/env python3
"""Synthetic contract tests: never real account analytics."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import editorial_diagnostics as diag
import platform_learning_loop as learning


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.index, self.snapshots = [], []
        for i in range(6):
            url = "https://example.org/video/" + str(i)
            p = dict(content_id=str(i), post_url=url, platform="bilibili",
                     account_alias="fi", content_format="video", topic_cluster="agent",
                     discovery_source="search", experiment_id="exp",
                     published_at="2026-11-01T00:00:00+00:00", publish_status="reported_published")
            self.index.append(p)
            s = {**p, "window": "T+24H", "observed_at": "2026-11-02T00:00:00+00:00",
                 "metric_definition_version": "native_v1", "organic_paid": "organic",
                 "data_access": "available", "metric_source": "native_export",
                 "ctr": "0.02" if i == 0 else "0.04", "views_or_reads": "100",
                 "saves": "2", "qualified_signals": "1", "founder_hours": "2",
                 "avg_watch_time": "30", "completion_or_retention": "0.4", "impressions": "500"}
            self.snapshots.append(s)

    def run_report(self):
        for name, columns, rows in (
                ("content-index.csv", learning.INDEX_COLUMNS, self.index),
                ("metric-snapshots.csv", learning.SNAPSHOT_COLUMNS, self.snapshots)):
            with (self.root / name).open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
        return diag.diagnostics(self.root, platform="bilibili", account="fi",
                                content_format="video", topic="agent", experiment="exp",
                                window="T+24H", definition="native_v1")

    def test_same_cohort_and_effort(self):
        r = self.run_report()
        self.assertEqual(r["status"], "DESCRIPTIVE_ONLY")
        w = r["works"][0]
        self.assertEqual(w["next_hypothesis"]["variable_to_review"], "title_or_cover")
        self.assertEqual(w["metrics"]["qualified_signals_per_hour"], 0.5)
        self.assertEqual(w["metrics"]["saves_per_1000_views"], 20)
        self.assertFalse(r["publish_authorized"])

    def test_missing_and_zero_are_not_equivalent(self):
        self.snapshots[0]["ctr"] = ""
        self.snapshots[0]["views_or_reads"] = "0"
        self.snapshots[0]["founder_hours"] = "0"
        r = self.run_report()
        self.assertIsNone(r["works"][0]["metrics"]["ctr"])
        self.assertIsNone(r["works"][0]["metrics"]["saves_per_1000_views"])
        self.assertIsNone(r["works"][0]["metrics"]["qualified_signals_per_hour"])
        self.assertEqual(r["coverage"]["ctr"]["missing"], 1)

    def test_paid_wrong_window_duplicate_and_insufficient(self):
        self.snapshots[0]["organic_paid"] = "unknown"
        self.snapshots[1]["observed_at"] = "2026-11-03T00:00:00+00:00"
        self.snapshots.append(dict(self.snapshots[2]))
        r = self.run_report()
        self.assertEqual(r["status"], "INSUFFICIENT_DATA")
        self.assertEqual(r["sample_count"], 3)
        self.assertEqual(r["skipped"]["paid_or_unverifiable"], 1)
        self.assertEqual(r["skipped"]["wrong_time_or_experiment"], 1)
        self.assertEqual(r["skipped"]["duplicate_snapshot"], 1)
        self.assertTrue(all(w["next_hypothesis"] is None for w in r["works"]))

    def test_duplicate_content_url(self):
        self.index[1]["post_url"] = self.index[0]["post_url"]
        r = self.run_report()
        self.assertEqual(r["skipped"]["duplicate_identity"], 2)

    def test_zero_baseline_no_inference(self):
        for s in self.snapshots:
            s["ctr"] = "0"
        r = self.run_report()
        self.assertIsNone(r["works"][0]["comparisons"]["ctr"]["relative_to_peer_median"])


if __name__ == "__main__":
    unittest.main()
