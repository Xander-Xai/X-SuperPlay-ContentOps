from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from platform_learning_loop import (  # noqa: E402
    INDEX_COLUMNS, SNAPSHOT_COLUMNS, analyze, handoff, initialize,
    _report_markdown,
)


def append(file: Path, columns, **values):
    with file.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writerow(values)


class CrossPlatformLearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "local-only"
        initialize(self.directory)

    def content(self, n, source="search", platform="youtube", fmt="video",
                account="ai_lab", topic="agent", status="reported_published"):
        cid = f"content-{n}"
        url = f"https://www.youtube.com/watch?v=synthetic{n}"
        append(self.directory / "content-index.csv", INDEX_COLUMNS,
               content_id=cid, platform=platform, account_alias=account,
               content_format=fmt, discovery_source=source, topic_cluster=topic,
               experiment_id="exp-001", post_url=url, publish_status=status,
               published_at="2026-11-12T10:00:00+08:00")
        return cid, url

    def metric(self, cid, url, views="1000", saves="20", platform="youtube",
               fmt="video", account="ai_lab", age="T+24H",
               definition="native_v1", paid="organic", observed=None):
        append(self.directory / "metric-snapshots.csv", SNAPSHOT_COLUMNS,
               metric_snapshot_id=f"metric-{cid}", content_id=cid,
               experiment_id="exp-001", platform=platform,
               observed_at=observed or "2026-11-13T10:00:00+08:00",
               published_at="2026-11-12T10:00:00+08:00",
               post_url=url, account_alias=account, content_format=fmt,
               window=age, metric_source="native_manual",
               metric_definition_version=definition, data_access="available",
               organic_paid=paid, views_or_reads=views, saves=saves)

    def review(self, **kwargs):
        default = dict(platform="youtube", account="ai_lab", content_format="video",
                       topic_cluster="agent", window="T+24H",
                       metric_name="views_or_reads", definition="native_v1",
                       interest_metric="saves")
        default.update(kwargs)
        return analyze(self.directory, **default)

    def test_init_is_idempotent_no_data_overwrite(self):
        index = self.directory / "content-index.csv"
        old = index.read_text(encoding="utf-8")
        result = initialize(self.directory)
        self.assertEqual(index.read_text(encoding="utf-8"), old)
        self.assertEqual(result["created"], [])

    def test_two_discovery_surfaces_are_descriptive_not_causal(self):
        for i in range(1, 6):
            cid, url = self.content(i, source="search")
            self.metric(cid, url, views="1000", saves="10")
        for i in range(6, 11):
            cid, url = self.content(i, source="recommendation")
            self.metric(cid, url, views="100", saves="5")
        report = self.review()
        self.assertEqual(report["status"], "DESCRIPTIVE_ONLY")
        group = {g["discovery_source"]: g for g in report["groups"]}
        self.assertEqual(group["search"]["interest_per_1000_primary"], 10)
        self.assertEqual(group["recommendation"]["interest_per_1000_primary"], 50)
        self.assertIsNone(report["handoff"]["proposed_topic"])
        self.assertFalse(report["handoff"]["production_authorized"])
        self.assertIn("NOT official", report["source_interpretation"])

    def test_missing_not_zero(self):
        cid, url = self.content(1)
        self.metric(cid, url, saves="")
        report = self.review()
        group = report["groups"][0]
        self.assertIsNone(group["interest_per_1000_primary"])
        self.assertEqual(group["missing_interest"], 1)

    def test_no_cross_platform_or_format(self):
        cid, url = self.content(1)
        self.metric(cid, url)
        other, other_url = self.content(2, platform="tiktok")
        self.metric(other, other_url, platform="tiktok")
        different, diff_url = self.content(3, fmt="shorts")
        self.metric(different, diff_url, fmt="shorts")
        self.assertEqual(self.review()["groups"][0]["sample_count"], 1)

    def test_paid_and_wrong_age_are_excluded(self):
        cid, url = self.content(1)
        self.metric(cid, url, paid="paid")
        cid, url = self.content(2)
        self.metric(cid, url, observed="2026-11-20T10:00:00+08:00")
        report = self.review()
        self.assertEqual(report["groups"], [])
        self.assertEqual(report["skipped"]["paid_or_unverifiable_snapshot"], 1)
        self.assertEqual(report["skipped"]["wrong_age_window"], 1)

    def test_duplicate_snapshots_are_skipped(self):
        cid, url = self.content(1)
        self.metric(cid, url)
        self.metric(cid, url)
        report = self.review()
        self.assertEqual(report["skipped"]["duplicate_snapshot"], 1)
        self.assertEqual(report["groups"], [])

    def test_inconsistent_metric_version_is_not_mixed(self):
        cid, url = self.content(1)
        self.metric(cid, url, definition="another_definition")
        self.assertEqual(self.review()["groups"], [])

    def test_publication_and_experiment_mismatch(self):
        cid, url = self.content(1, status="draft")
        self.metric(cid, url)
        self.assertEqual(self.review()["skipped"]["not_published"], 1)
        cid, url = self.content(2)
        self.metric(cid, url)
        path = self.directory / "metric-snapshots.csv"
        text = path.read_text(encoding="utf-8").replace("exp-001", "exp-002")
        path.write_text(text, encoding="utf-8")
        self.assertEqual(self.review()["skipped"]["experiment_mismatch"], 1)

    def test_handoff_explicit_manual_review_no_publish(self):
        result = self.review(platform="x", account="x-superplay-english",
                             content_format="reply_text", topic_cluster="ai_agent")
        folder = self.directory / "learning"
        folder.mkdir()
        (folder / "latest.json").write_text(json.dumps(result), encoding="utf-8")
        with patch("platform_learning_loop.hidden_run", return_value=SimpleNamespace(
                returncode=0, stdout='{"status":"BRIEF_READY"}', stderr="")) as runner:
            receipt = handoff(self.directory, account_profile="x-superplay-english",
                              topic="Agent recovery design", reviewer="Founder",
                              evidence_url="https://docs.example.org/agent-design")
            self.assertEqual(receipt["status"], "ROUTED_FOR_HUMAN_REVIEW")
            self.assertFalse(receipt["published"])
            self.assertFalse(receipt["production_authorized"])
            self.assertIn("content_route.py", str(runner.call_args))

    def test_handoff_rejects_cross_platform_profile(self):
        result = self.review()
        folder = self.directory / "learning"
        folder.mkdir()
        (folder / "latest.json").write_text(json.dumps(result), encoding="utf-8")
        with patch("platform_learning_loop.hidden_run") as runner:
            with self.assertRaisesRegex(ValueError, "does not authorize this platform"):
                handoff(self.directory, account_profile="x-superplay-english",
                        topic="Agent recovery design", reviewer="Founder",
                        evidence_url="https://docs.example.org/agent-design")
            runner.assert_not_called()

    def test_local_guard_refuses_tracked_repo_write(self):
        with self.assertRaisesRegex(ValueError, "ignored .local"):
            initialize(ROOT / "projects" / "x-growth-en" / "analytics")

    def test_missing_definition_or_unsupported_metric_fails(self):
        with self.assertRaises(ValueError):
            self.review(definition="Untrusted Version!")
        with self.assertRaises(ValueError):
            self.review(metric_name="trending_score")


if __name__ == "__main__":
    unittest.main()
