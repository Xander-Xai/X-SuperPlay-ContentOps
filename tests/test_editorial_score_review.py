#!/usr/bin/env python3
import csv
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import editorial_score_review as review
import editorial_ops as ops
import platform_learning_loop as learning


def write(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


class ScoreTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.data = ops.init(self.root / "editorial")
        self.metrics = self.root / "metrics"
        learning.initialize(self.metrics)
        self.account = "x-superplay-future-intelligence"
        self.scope = dict(platform="bilibili", account=self.account, topic="agent",
                          experiment="exp", window="T+24H", definition="native_v1",
                          metric="impressions")
        stamp = datetime.now(timezone.utc)
        self.frozen_at = (stamp - timedelta(days=3)).isoformat()
        self.published = (stamp - timedelta(days=2)).isoformat()
        self.observed = (stamp - timedelta(days=1)).isoformat()
        write(self.data / "signals.csv", ops.FIELDS["signals.csv"], [
            dict(signal_id="signal-1", topic="agent", kind="comment",
                 source_url="https://example.org/question/1", observed_at=self.frozen_at,
                 observation="Synthetic question")])
        rows = []
        for i in range(10):
            row = dict(topic="agent", account=self.account, platform="bilibili", format="video",
                       audience="developers", angle=f"angle-{i}", series="series", hook="hook",
                       cta="next step", planned_date=stamp.date().isoformat(), minutes="10",
                       risk="low", reviewer="Founder", **{k:"8" for k in ops.WEIGHTS})
            row["demand"] = str(7 + i // 3)
            row["reach"] = str(7 + i % 3)
            rows.append(row)
        write(self.data / "topics.csv", ops.FIELDS["topics.csv"], rows)
        self.candidates = ops.plan(self.data)["queue"]
        self.posts = []
        self.snapshots = []
        for i, q in enumerate(self.candidates):
            cid, url = f"content-{i}", f"https://example.org/post/{i}"
            self.posts.append(dict(content_id=cid, post_url=url, platform="bilibili",
                                   account_alias=self.account, content_format="video",
                                   discovery_source="comment", topic_cluster="agent",
                                   experiment_id="exp", published_at=self.published,
                                   publish_status="reported_published"))
            self.snapshots.append(dict(metric_snapshot_id=f"snapshot-{i}", content_id=cid,
                                       post_url=url, platform="bilibili", account_alias=self.account,
                                       content_format="video", experiment_id="exp",
                                       published_at=self.published, observed_at=self.observed,
                                       window="T+24H", metric_definition_version="native_v1",
                                       metric_source="native_manual", data_access="available",
                                       organic_paid="organic", impressions=str(q["score"]*10)))
        self.save()

    def save(self):
        write(self.metrics / "content-index.csv", learning.INDEX_COLUMNS, self.posts)
        write(self.metrics / "metric-snapshots.csv", learning.SNAPSHOT_COLUMNS, self.snapshots)

    def bind(self, i):
        ident = self.candidates[i]["id"]
        with patch.object(review, "now", return_value=self.frozen_at):
            f = review.freeze(self.data, ident, "Founder", True)
        p = self.posts[i]
        l = review.link(self.data, self.metrics, ident, p["content_id"], p["post_url"], "Founder", True)
        return f, l

    def test_rank_ties_and_constant(self):
        self.assertAlmostEqual(review.spearman([1, 1, 3], [4, 4, 8]), 1)
        self.assertAlmostEqual(review.spearman([1, 2, 3], [3, 2, 1]), -1)
        self.assertIsNone(review.spearman([1, 1, 1], [1, 2, 3]))

    def test_full_pipeline_and_missing_data(self):
        for i in range(10):
            self.bind(i)
        r = review.review(self.data, self.metrics, **self.scope)
        self.assertEqual(r["status"], "DESCRIPTIVE_ONLY")
        self.assertAlmostEqual(r["spearman"], 1)
        self.assertFalse(r["weights_updated"])
        self.snapshots[0]["organic_paid"] = "unknown"
        self.save()
        r = review.review(self.data, self.metrics, **self.scope)
        self.assertEqual(r["status"], "INSUFFICIENT_DATA")
        self.assertEqual(r["sample_count"], 9)
        self.assertIsNone(r["spearman"])

    def test_replay_and_duplicate_binding(self):
        f, l = self.bind(0)
        self.assertEqual(self.bind(0), (f, l))
        ident = self.candidates[1]["id"]
        with patch.object(review, "now", return_value=self.frozen_at):
            review.freeze(self.data, ident, "Founder", True)
        with self.assertRaises(ValueError):
            review.link(self.data, self.metrics, ident, l["content_id"], l["post_url"], "Founder", True)

    def test_retrospective_and_confirmation_refused(self):
        ident = self.candidates[0]["id"]
        with self.assertRaises(ValueError):
            review.freeze(self.data, ident, "Founder", False)
        review.freeze(self.data, ident, "Founder", True)
        p = self.posts[0]
        with self.assertRaises(ValueError):
            review.link(self.data, self.metrics, ident, p["content_id"], p["post_url"], "Founder", True)

    def test_index_changed_after_binding(self):
        self.bind(0)
        self.posts[0]["published_at"] = self.observed
        self.save()
        with self.assertRaises(ValueError):
            review.review(self.data, self.metrics, **self.scope)


if __name__ == "__main__":
    unittest.main()
