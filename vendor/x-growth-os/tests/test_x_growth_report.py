import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.x_growth_report import diagnose, rate, valid_x_url


class XGrowthReportTests(unittest.TestCase):
    def test_no_data_does_not_invent_performance(self):
        result = diagnose([], [], [])
        self.assertEqual(result["verified_published_posts"], 0)
        self.assertTrue(result["needs_native_metrics"])
        self.assertTrue(result["needs_account_follower_history"])

    def test_owner_confirmation_is_not_a_verifiable_url(self):
        post = {"content_id": "p1", "status": "reported_published_url_pending", "x_post_url": ""}
        result = diagnose([post], [], [])
        self.assertEqual(result["verified_published_posts"], 0)
        self.assertEqual(result["owner_reported_published_url_pending"], ["p1"])
        self.assertTrue(result["needs_actual_post_urls"])

    def test_malformed_verified_row_is_rejected(self):
        post = {"content_id": "p1", "status": "published", "x_post_url": "https://github.com/abc"}
        self.assertEqual(diagnose([post], [], [])["published_rows_without_valid_url"], ["p1"])
        self.assertTrue(valid_x_url("https://x.com/example/status/1234567"))

    def test_missing_components_do_not_turn_into_zero(self):
        self.assertIsNone(rate(None, 5))
        self.assertIsNone(rate(1, 0))
        post = {"content_id": "p", "status": "published", "x_post_url": "https://x.com/a/status/123"}
        snap = {"content_id": "p", "age_window": "T+24H", "data_access": "available",
                "observed_at": "2026-10-27T10:00:00+08:00", "impressions": "100",
                "likes": "2", "reposts": "", "replies": "1", "bookmarks": "0"}
        out = diagnose([post], [snap], [])["age_matched_windows"]["T+24H"]["per_post"][0]
        self.assertEqual(out["impressions"], 100)
        self.assertIsNone(out["interaction_rate"])

    def test_duplicate_snapshots_not_summed_and_followers_account_only(self):
        post = {"content_id": "p", "status": "published", "x_post_url": "https://x.com/a/status/123"}
        base = {"content_id": "p", "age_window": "T+24H", "data_access": "available",
                "likes": "1", "reposts": "0", "replies": "0", "bookmarks": "0"}
        s1 = dict(base, observed_at="2026-10-27T09:00:00+08:00", impressions="40")
        s2 = dict(base, observed_at="2026-10-27T10:00:00+08:00", impressions="70")
        accounts = [
            {"account_handle": "@a", "observed_at": "2026-10-26T10:00:00+08:00", "followers_count": "100"},
            {"account_handle": "@a", "observed_at": "2026-10-27T10:00:00+08:00", "followers_count": "98"},
        ]
        report = diagnose([post], [s1, s2], accounts)
        self.assertEqual(report["age_matched_windows"]["T+24H"]["median_observed_impressions"], 70)
        self.assertEqual(report["account_followers"]["@a"]["net_change_observed"], -2)
        self.assertEqual(report["verified_published_posts"], 1)


if __name__ == "__main__":
    unittest.main()
