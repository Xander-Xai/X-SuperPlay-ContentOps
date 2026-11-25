"""Synthetic variant and business-handoff acceptance tests."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import editorial_feedback as feedback
import platform_learning_loop as learning


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ops = Path(tmp.name) / "ops"
        self.metrics = Path(tmp.name) / "metrics"
        feedback.init_links(self.ops)
        learning.initialize(self.metrics)

    def add(self, path, fields, row):
        with path.open("a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=fields).writerow(row)

    def item(self, n, variant, variable="hook"):
        ident, url = str(n), "https://example.org/post/" + str(n)
        row = dict(content_id=ident, post_url=url, platform="bilibili",
                   account_alias="x-superplay-future-intelligence", content_format="video",
                   discovery_source="search", topic_cluster="agent", experiment_id="exp",
                   published_at="2026-11-20T10:00:00+08:00", publish_status="reported_published")
        self.add(self.metrics / "content-index.csv", learning.INDEX_COLUMNS, row)
        snap = {k: v for k, v in row.items() if k in learning.SNAPSHOT_COLUMNS}
        snap.update(observed_at="2026-11-21T10:00:00+08:00", window="T+24H",
                    metric_definition_version="native_v1", organic_paid="organic",
                    data_access="available", metric_source="native_manual",
                    views_or_reads="100", saves="5" if variant == "a" else "10")
        self.add(self.metrics / "metric-snapshots.csv", learning.SNAPSHOT_COLUMNS, snap)
        self.add(self.ops / "experiment-links.csv", feedback.LINKS,
                 dict(content_id=ident, post_url=url, experiment_id="exp",
                      variable=variable, variant=variant))
        return ident, url

    def review(self):
        return feedback.review(self.ops, self.metrics, experiment="exp", variable="hook",
                               platform="bilibili", account="x-superplay-future-intelligence",
                               content_format="video", topic="agent", window="T+24H",
                               definition="native_v1", primary="views_or_reads", interest="saves")

    def test_variants(self):
        for n in range(10):
            self.item(n, "a" if n < 5 else "b")
        result = self.review()
        self.assertEqual(result["status"], "DESCRIPTIVE_ONLY")
        self.assertEqual([g["variant"] for g in result["groups"]], ["a", "b"])
        self.assertEqual(result["groups"][1]["median_interest_per_1000_post"], 100)
        self.assertFalse(result["publish_authorized"])

    def test_small_sample(self):
        self.item(1, "a")
        self.assertEqual(self.review()["status"], "INSUFFICIENT_DATA")

    def test_mixed_variables(self):
        self.item(1, "a", "title")
        with self.assertRaises(ValueError):
            self.review()

    def test_lead_consent_and_link(self):
        ident, url = self.item(1, "a")
        args = dict(content_id=ident, post_url=url, category="agent", evidence_ref="local-1",
                    reviewer="Founder", confirmed=True)
        with self.assertRaises(ValueError):
            feedback.lead(self.ops, self.metrics, consent=False, **args)
        result = feedback.lead(self.ops, self.metrics, consent=True, **args)
        self.assertFalse(result["paid_demand_verified"])
        self.assertEqual(result["external_action"], "none")
        with self.assertRaises(ValueError):
            feedback.lead(self.ops, self.metrics, consent=True, **args)


if __name__ == "__main__":
    unittest.main()
