"""Synthetic official-response contract fixtures; no network or real account."""
import csv
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import video_metric_intake as intake
import platform_learning_loop as learning

PUBLISHED = "2026-11-25T00:00:00+00:00"
OBSERVED = "2026-11-26T00:00:00+00:00"


class IntakeTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.d = Path(t.name)
        learning.initialize(self.d)
        self.kw = dict(platform="douyin", account="x-superplay-1024", content_id="fixture",
                       video_id="123456", observed_at=OBSERVED, confirmed=True)
        self.index("douyin", self.kw["account"], "123456")

    def index(self, platform, account, ident):
        url = "https://www.douyin.com/video/" if platform == "douyin" else "https://www.bilibili.com/video/"
        with (self.d / "content-index.csv").open("a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=learning.INDEX_COLUMNS).writerow(dict(
                content_id="fixture", platform=platform, account_alias=account, content_format="video",
                discovery_source="search", topic_cluster="agent", experiment_id="exp",
                post_url=url + ident, published_at=PUBLISHED, publish_status="reported_published"))

    def payload(self, **kw):
        row = dict(video_id="123456", create_time=int(datetime.fromisoformat(PUBLISHED).timestamp()),
                   item_id="private-opaque-id", title="private text",
                   statistics={"play_count": 100, "digg_count": 0, "download_count": 9, "share_count": 3})
        row.update(kw)
        return json.dumps({"data": {"error_code": 0, "list": [row]}, "extra": {"error_code": 0}}).encode()

    def test_douyin_import_replay_no_organic_inference(self):
        raw = self.payload()
        result = intake.import_observation(self.d, raw, **self.kw)
        self.assertEqual(result["status"], "IMPORTED")
        self.assertFalse(result["benchmark_eligible"])
        self.assertEqual(intake.import_observation(self.d, raw, **self.kw)["status"], "REPLAYED")
        row, = learning._load(self.d / "metric-snapshots.csv", learning.SNAPSHOT_COLUMNS)
        self.assertEqual(row["views_or_reads"], "100")
        self.assertEqual(row["likes"], "0")
        self.assertEqual(row["saves"], "")
        self.assertEqual(row["organic_paid"], "unknown")
        self.assertNotIn("private", str(row))
        report = learning.analyze(self.d, platform="douyin", account=self.kw["account"], content_format="video",
                                  topic_cluster="agent", window="T+24H", metric_name="views_or_reads",
                                  definition="douyin_api_counts_v1", interest_metric="shares")
        self.assertEqual(report["status"], "INSUFFICIENT_DATA")
        self.assertEqual(report["groups"], [])

    def test_reject_mismatch_and_conflict(self):
        for raw in (self.payload(video_id="999"), self.payload(create_time=0),
                    self.payload(statistics={"play_count": True}),
                    json.dumps({"data": {"error_code": 123}}).encode()):
            with self.assertRaises(ValueError):
                intake.import_observation(self.d, raw, **self.kw)
        with self.assertRaises(ValueError):
            intake.import_observation(self.d, self.payload(), **dict(self.kw, confirmed=False))
        with self.assertRaises(ValueError):
            intake.import_observation(self.d, self.payload(), **dict(self.kw, observed_at=PUBLISHED))
        intake.import_observation(self.d, self.payload(), **self.kw)
        with self.assertRaises(ValueError):
            intake.import_observation(self.d, self.payload(statistics={"play_count": 101}), **self.kw)

    def test_bilibili_public_receipt_not_smoke(self):
        account = "x-superplay-future-intelligence"
        bvid = "BV1234567890"
        self.index("bilibili", account, bvid)
        doc = dict(schema="contentops.bilibili-metrics/v1", platform="bilibili", channel="api_public",
                   account_slug=account, bvid=bvid, mode="ACCOUNT_DELIVERY", bvid_source="project",
                   fetched_at=OBSERVED, metrics={"view": 20, "favorite": 1},
                   modifies_script=False, modifies_qc=False, modifies_production_ready=False)
        kw = dict(self.kw, platform="bilibili", account=account, video_id=bvid)
        with self.assertRaises(ValueError):
            intake.import_observation(self.d, json.dumps(dict(doc, mode="TRANSPORT_SMOKE")).encode(), **kw)
        result = intake.import_observation(self.d, json.dumps(doc).encode(), **kw)
        self.assertFalse(result["benchmark_eligible"])
        row, = learning._load(self.d / "metric-snapshots.csv", learning.SNAPSHOT_COLUMNS)
        self.assertEqual((row["metric_source"], row["saves"], row["organic_paid"]), ("api_public", "1", "unknown"))


if __name__ == "__main__":
    unittest.main()
