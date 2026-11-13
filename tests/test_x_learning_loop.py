from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from x_learning_loop import analyze, initialize, FILES  # noqa: E402


def append(path, **fields):
    with path.open("r", newline="", encoding="utf-8") as handle:
        columns = next(csv.reader(handle))
    with path.open("a", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=columns).writerow(fields)


class XLocalLearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "private"
        initialize(self.data)

    def _post(self, number, group, account="x-superplay-english", mode="reply"):
        cid = f"test-{number}"
        url = f"https://x.com/test/status/{number}"
        append(self.data / FILES[0], content_id=cid, mode=mode, status="published",
               x_post_url=url, account_handle=account,
               experiment_variable=f"source:{group}",
               post_published_at="2026-11-12T10:00:00+08:00")
        return cid, url

    def _metric(self, cid, url, impressions=100, clicks=2, window="T+24H",
                access="available", paid="organic"):
        append(self.data / FILES[1], metric_snapshot_id=f"sample-{cid}-{window}",
               content_id=cid, x_post_url=url, age_window=window,
               observed_at="2026-11-13T10:00:00+08:00", metric_source="native_manual",
               data_access=access, organic_paid=paid, impressions=impressions,
               profile_clicks=clicks)

    def test_init_is_idempotent_and_does_not_overwrite(self):
        path = self.data / FILES[0]
        path.write_text("original private content", encoding="utf-8")
        result = initialize(self.data)
        self.assertEqual(path.read_text(encoding="utf-8"), "original private content")
        self.assertIn(FILES[0], result["existing_preserved"])

    def test_missing_metrics_are_not_treated_as_zero(self):
        cid, url = self._post(1, "inspiration_ai")
        self._metric(cid, url, clicks="")
        result = analyze(self.data, "x-superplay-english", "T+24H")
        group = next(g for g in result["groups"] if g["source"] == "inspiration_ai")
        self.assertEqual(group["sample_count"], 1)
        self.assertIsNone(group["profile_clicks_per_1000_impressions"])
        self.assertEqual(group["profile_clicks_missing"], 1)
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")

    def test_group_comparison_is_descriptive_only(self):
        for i in range(1, 6):
            cid, url = self._post(i, "inspiration_ai")
            self._metric(cid, url, impressions=1000, clicks=2)
        for i in range(6, 11):
            cid, url = self._post(i, "timeline_ai")
            self._metric(cid, url, impressions=100, clicks=3)
        result = analyze(self.data, "x-superplay-english", "T+24H")
        self.assertEqual(result["status"], "DESCRIPTIVE_ONLY")
        self.assertEqual(result["next_experiment"]["approval"], "FOUNDER_REVIEW_REQUIRED")
        self.assertEqual(result["next_experiment"]["proposed_topic"], None)
        values = {g["source"]: g for g in result["groups"]}
        self.assertEqual(values["inspiration_ai"]["median_impressions"], 1000)
        self.assertEqual(values["inspiration_ai"]["profile_clicks_per_1000_impressions"], 2)
        self.assertEqual(values["timeline_ai"]["profile_clicks_per_1000_impressions"], 30)

    def test_mixed_account_and_paid_are_excluded(self):
        cid, url = self._post(1, "timeline_ai", account="other-account")
        self._metric(cid, url, impressions=5000)
        cid, url = self._post(2, "timeline_ai")
        self._metric(cid, url, impressions=3000, paid="paid")
        result = analyze(self.data, "x-superplay-english", "T+24H")
        self.assertEqual(sum(g["sample_count"] for g in result["groups"]), 0)
        self.assertEqual(result["skipped"]["invalid_provenance_or_paid"], 1)

    def test_duplicate_snapshot_does_not_double_count(self):
        cid, url = self._post(1, "inspiration_broad")
        self._metric(cid, url)
        self._metric(cid, url, impressions=900)
        result = analyze(self.data, "x-superplay-english", "T+24H")
        self.assertEqual(result["skipped"]["duplicate_snapshot_window"], 1)
        self.assertEqual(sum(g["sample_count"] for g in result["groups"]), 0)

    def test_draft_and_bad_url_not_mistaken_for_publication(self):
        cid, url = self._post(1, "timeline_ai")
        self._metric(cid, url)
        append(self.data / FILES[0], content_id="d-1", mode="reply", status="draft",
               x_post_url="https://x.com/a/status/22", account_handle="x-superplay-english",
               experiment_variable="source:timeline_ai",
               post_published_at="2026-11-12T10:00:00+08:00")
        append(self.data / FILES[0], content_id="d-2", mode="reply", status="published",
               x_post_url="https://example.com/status/23", account_handle="x-superplay-english",
               experiment_variable="source:timeline_ai",
               post_published_at="2026-11-12T10:00:00+08:00")
        result = analyze(self.data, "x-superplay-english", "T+24H")
        self.assertEqual(sum(g["sample_count"] for g in result["groups"]), 1)
        self.assertEqual(result["skipped"]["unpublished_or_unverified_state"], 1)
        self.assertEqual(result["skipped"]["invalid_post_url_or_time"], 1)

    def test_account_snapshot_is_context_not_post_attribution(self):
        append(self.data / FILES[2], snapshot_id="s1", account_handle="x-superplay-english",
               observed_at="2026-11-13T05:03:00+08:00",
               observation_source="native_manual_screenshot",
               account_impressions="110600", account_profile_visits="464")
        result = analyze(self.data, "x-superplay-english", "T+24H")
        self.assertEqual(result["account_context"]["account_impressions"], 110600)
        self.assertEqual(result["account_context"]["attribution"], "ACCOUNT_LEVEL_ONLY")


if __name__ == "__main__":
    unittest.main()
