"""Synthetic workbench and series checks, no external services."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import editorial_ops as ops
import editorial_workspace as workspace
import editorial_series as series
import platform_learning_loop as learning


def add(path, fields, row):
    with path.open("a", encoding="utf-8", newline="") as f:
        csv.DictWriter(f, fieldnames=fields).writerow(row)


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.d = ops.init(Path(t.name))
        topic = dict(zip(ops.FIELDS["topics.csv"], [
            "agent", "x-superplay-english", "x", "text", "developers", "recovery",
            "agent-series", "<script>alert(1)</script>", "Discuss", "2026-11-26",
            "10", "low", "Founder", "9", "9", "9", "9", "9", "9"]))
        add(self.d / "topics.csv", ops.FIELDS["topics.csv"], topic)
        self.rev, report = workspace.snapshot(self.d)
        self.ident = report["queue"][0]["id"]

    def test_edit_stale_and_validation(self):
        rev, report = workspace.edit(self.d, self.ident, self.rev, {"minutes": "30"})
        self.assertNotEqual(rev, self.rev)
        self.assertEqual(report["queue"][0]["cost_lane"], "L2")
        with self.assertRaises(ValueError):
            workspace.edit(self.d, self.ident, self.rev, {"minutes": "10"})
        with self.assertRaises(ValueError):
            workspace.edit(self.d, self.ident, rev, {"minutes": "900"})
        self.assertEqual(workspace.snapshot(self.d)[0], rev)

    def test_immutable_and_routed(self):
        with self.assertRaises(ValueError):
            workspace.edit(self.d, self.ident, self.rev, {"account": "other"})
        (self.d / ("route-" + self.ident + ".json")).write_text(
            json.dumps({"status": "ROUTED_FOR_HUMAN_REVIEW"}), encoding="utf-8")
        with self.assertRaises(ValueError):
            workspace.edit(self.d, self.ident, self.rev, {"hook": "new"})
        self.assertIn("editing locked", workspace.render(self.d, "fixture"))

    def test_html_escaped(self):
        page = workspace.render(self.d, "fixture")
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)


    def test_daily_capacity_is_read_only_and_integrated(self):
        add(self.d / "signals.csv", ops.FIELDS["signals.csv"],
            dict(signal_id="signal-1", topic="agent", kind="issue",
                 source_url="https://example.org/issue/1",
                 observed_at="2026-11-26T00:00:00+00:00", observation="Synthetic problem"))
        before = workspace.revision(self.d)
        page = workspace.render(self.d, "fixture", "2026-11-26", 15)
        self.assertIn("Daily capacity", page)
        self.assertIn("10 / 15 estimated minutes", page)
        self.assertIn("demand URLs 1", page)
        self.assertIn("#candidate-" + self.ident, page)
        self.assertEqual(workspace.revision(self.d), before)
        self.assertFalse((self.d / ("route-" + self.ident + ".json")).exists())
        with self.assertRaises(ValueError):
            workspace.render(self.d, "fixture", "2026-11-26", None)


class SeriesTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.d = Path(t.name) / "ops"
        self.m = Path(t.name) / "metrics"
        series.init(self.d)
        learning.initialize(self.m)

    def item(self, n, label, saves):
        ident, url = str(n), "https://example.org/post/" + str(n)
        row = dict(content_id=ident, post_url=url, platform="bilibili",
                   account_alias="x-superplay-future-intelligence", content_format="video",
                   discovery_source="search", topic_cluster="agent", experiment_id="exp",
                   published_at="2026-11-20T10:00:00+08:00", publish_status="reported_published")
        add(self.m / "content-index.csv", learning.INDEX_COLUMNS, row)
        snap = {k: v for k, v in row.items() if k in learning.SNAPSHOT_COLUMNS}
        snap.update(observed_at="2026-11-21T10:00:00+08:00", window="T+24H",
                    metric_definition_version="native_v1", organic_paid="organic",
                    data_access="available", metric_source="native_manual",
                    views_or_reads="100", saves=str(saves))
        add(self.m / "metric-snapshots.csv", learning.SNAPSHOT_COLUMNS, snap)
        add(self.d / "series-links.csv", series.FIELDS, dict(content_id=ident, post_url=url,
                                                          experiment_id="exp", series=label))

    def review(self):
        return series.review(self.d, self.m, experiment="exp", platform="bilibili",
                             account="x-superplay-future-intelligence", content_format="video",
                             topic="agent", window="T+24H", definition="native_v1",
                             primary="views_or_reads", interest="saves")

    def test_comparable_and_insufficient(self):
        self.item(0, "a", 5)
        self.assertIsNone(self.review()["research_priority"])
        for n in range(1, 10):
            self.item(n, "a" if n < 5 else "b", 5 if n < 5 else 10)
        result = self.review()
        self.assertEqual(result["research_priority"], "b")
        self.assertEqual(result["status"], "DESCRIPTIVE_ONLY")
        self.assertFalse(result["publish_authorized"])

    def test_tie(self):
        for n in range(10):
            self.item(n, "a" if n < 5 else "b", 5)
        self.assertIsNone(self.review()["research_priority"])


if __name__ == "__main__":
    unittest.main()
