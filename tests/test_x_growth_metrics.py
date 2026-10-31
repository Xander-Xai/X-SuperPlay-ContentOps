from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.x_growth_metrics import build_weekly_report  # noqa: E402


class GrowthMetricsTests(unittest.TestCase):
    def request(self, **updates):
        base = {
            "account_id": "demo-account",
            "week_start": "2026-10-26",
            "week_end": "2026-11-01",
            "fixture": True,
            "posts_csv": "date_local,timezone,content_id,mode,topic,source_url,status,x_post_url,post_count,image_status,impressions,likes,reposts,replies,bookmarks,profile_visits,follower_delta,notes,account_handle,icp,proof_grade,experiment_variable,post_published_at\n"
                         "2026-10-27,UTC,p1,source_analysis,topic,https://example.org/source,published,https://x.com/demo/status/1,1,,,,,,,,,,demo-account,audience,P0,hook,2026-10-27T10:00:00Z\n",
            "metric_snapshots_csv": "metric_snapshot_id,content_id,x_post_url,post_published_at,observed_at,timezone,age_window,metric_source,metric_definition_version,data_access,organic_paid,impressions,engagements,likes,reposts,replies,bookmarks,profile_clicks,link_clicks,attributed_follows,qualified_signal_count,missing_reason,notes\n"
                                      "m1,p1,https://x.com/demo/status/1,2026-10-27T10:00:00Z,2026-10-28T10:00:00Z,UTC,T+24H,native_export,v1,operator_export,organic,100,10,2,1,1,0,3,1,0,2,,,\n",
            "account_snapshots_csv": "snapshot_id,account_handle,observed_at,timezone,observation_source,followers_count,following_count,account_profile_visits,account_impressions,platform_reported_net_follows,account_notice_state,data_access,notes\n"
                                       "a1,demo-account,2026-10-26T00:00:00Z,UTC,native_export,1000,100,10,200,4,none,operator_export,\n"
                                       "a2,demo-account,2026-11-01T00:00:00Z,UTC,native_export,1008,101,14,240,6,none,operator_export,\n",
            "manual_interactions": [{"account_id": "demo-account", "occurred_at": "2026-10-28T11:00:00Z", "source": "operator_log", "kind": "reply", "qualified": True}],
            "work_minutes": [{"account_id": "demo-account", "date": "2026-10-28", "minutes": 90, "source": "operator_log"}],
            "feedback": ["Two useful replies; one asked for a concrete example."],
            "failures": ["One planned post missed the image review gate."],
            "next_experiment": "Compare two evidence-first hooks in matched 24-hour windows.",
            "stop_condition": "Stop if a post needs unsupported claims or private data.",
        }
        return {**base, **updates}

    def test_complete_report_preserves_counts_provenance_and_human_review(self):
        result = build_weekly_report(self.request())
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        report = result["report"]
        self.assertEqual(report["original_post_count"], 1)
        self.assertEqual(report["manual_reply_count"], 1)
        self.assertEqual(report["outbound_manual_reply_count"], 1)
        self.assertEqual(report["inbound_qualified_responses"], {"T+24H": 2})
        self.assertNotIn("qualified_responses", report)
        self.assertEqual(report["follower_net"], 8)
        self.assertEqual(report["work_hours"], 1.5)
        self.assertEqual(report["top_content"]["T+24H"]["metrics"]["engagements"][0]["content_id"], "p1")
        self.assertEqual(report["data_kind"], "FIXTURE")
        self.assertFalse(result["execution_authorized"])
        self.assertTrue(result["requires_human_review"])
        self.assertIn("failures", report)
        self.assertIn("stop_condition", report)

    def test_empty_metrics_remain_unknown_not_zero(self):
        request = self.request(metric_snapshots_csv="", account_snapshots_csv="")
        result = build_weekly_report(request)
        self.assertIsNone(result["report"]["top_content"])
        self.assertIsNone(result["report"]["follower_net"])
        self.assertIn("METRICS_UNAVAILABLE", result["report"]["limitations"])

    def test_mixed_account_data_fails_closed(self):
        request = self.request(account_snapshots_csv=self.request()["account_snapshots_csv"].replace("demo-account", "other-account", 1))
        result = build_weekly_report(request)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("ACCOUNT_MISMATCH", result["reasons"])

    def test_bad_or_out_of_window_timestamps_are_rejected(self):
        request = self.request(metric_snapshots_csv=self.request()["metric_snapshots_csv"].replace("2026-10-28T10:00:00Z", "not-a-date"))
        result = build_weekly_report(request)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("INVALID_TIMESTAMP", result["reasons"])

    def test_manual_entries_need_account_time_and_source(self):
        result = build_weekly_report(self.request(manual_interactions=[{"kind": "reply", "qualified": True}]))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("INVALID_MANUAL_RECORD", result["reasons"])

    def test_comparison_is_observational_and_sample_insufficient(self):
        records = [
            {"group": g, "value": v, "metric": "impressions", "age_window": "T+24H", "observed_at": "2026-10-28T10:00:00Z", "source": "native_export"}
            for g, v in (("A", 100), ("B", 120))
        ]
        result = build_weekly_report(self.request(comparison=records))
        self.assertEqual(result["report"]["comparison"]["status"], "INSUFFICIENT_DATA")
        self.assertIn("descriptive", result["report"]["comparison"]["interpretation"].lower())

    def test_fixture_flag_is_required_and_explicit(self):
        result = build_weekly_report(self.request(fixture=None))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("FIXTURE_FLAG_REQUIRED", result["reasons"])

    def test_real_user_supplied_data_is_not_labelled_fixture(self):
        result = build_weekly_report(self.request(fixture=False))
        self.assertEqual(result["report"]["data_kind"], "USER_SUPPLIED_UNVERIFIED")

    def test_fixture_cannot_claim_observed_data_origin(self):
        result = build_weekly_report(self.request(fixture=True, data_origin="observed"))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("FIXTURE_OBSERVED_CONFLICT", result["reasons"])

    def test_invalid_input_types_fail_closed_without_crashing(self):
        cases = [
            self.request(week_start=[]),
            self.request(manual_interactions=[{"account_id": "demo-account", "occurred_at": "2026-10-28T11:00:00Z", "source": "log", "kind": 17}]),
            self.request(account_snapshots_csv=[{"account_handle": "demo-account", "observation_source": "manual", "followers_count": 5}]),
            self.request(posts_csv=[{"account_handle": "demo-account", "status": "published", "mode": 5}]),
        ]
        for request in cases:
            with self.subTest(request=request):
                result = build_weekly_report(request)
                self.assertEqual(result["status"], "BLOCKED")
                self.assertTrue(result["reasons"])

    def test_helper_documents_privacy_filtering_as_caller_precondition(self):
        self.assertIn("caller", build_weekly_report.__doc__.lower())
        self.assertIn("does not", build_weekly_report.__doc__.lower())

    def test_out_of_week_observation_is_refused(self):
        csv_data = self.request()["metric_snapshots_csv"].replace("2026-10-28T10:00:00Z", "2026-11-02T10:00:00Z")
        result = build_weekly_report(self.request(metric_snapshots_csv=csv_data))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("TIMESTAMP_OUT_OF_RANGE", result["reasons"])

    def test_metric_snapshot_must_match_account_bound_post_url(self):
        csv_data = self.request()["metric_snapshots_csv"].replace("https://x.com/demo/status/1", "https://x.com/other/status/9")
        result = build_weekly_report(self.request(metric_snapshots_csv=csv_data))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("INVALID_POST_SOURCE", result["reasons"])

    def test_posts_without_account_identity_fail_closed(self):
        csv_data = self.request()["posts_csv"].replace("demo-account,audience", ",audience")
        result = build_weekly_report(self.request(posts_csv=csv_data))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("ACCOUNT_MISMATCH", result["reasons"])

    def test_missing_decision_is_not_presented_as_a_complete_weekly_review(self):
        result = build_weekly_report(self.request(stop_condition=""))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("WEEKLY_DECISION_REQUIRED", result["reasons"])

    def test_posts_for_other_account_are_not_counted(self):
        posts = self.request()["posts_csv"].replace("demo-account,audience", "other-account,audience")
        result = build_weekly_report(self.request(posts_csv=posts))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("ACCOUNT_MISMATCH", result["reasons"])

    def test_latest_qualified_snapshot_is_selected_per_content_and_age_window(self):
        second = "m2,p1,https://x.com/demo/status/1,2026-10-27T10:00:00Z,2026-10-29T10:00:00Z,UTC,T+24H,native_export,v1,operator_export,organic,100,12,3,1,1,0,3,1,0,7,,,\n"
        csv_data = self.request()["metric_snapshots_csv"] + second
        result = build_weekly_report(self.request(metric_snapshots_csv=csv_data))
        self.assertEqual(result["report"]["inbound_qualified_responses"], {"T+24H": 7})
        self.assertEqual(result["report"]["outbound_manual_reply_count"], 1)

    def test_top_content_is_partitioned_by_metric_and_age_window(self):
        second = "m2,p1,https://x.com/demo/status/1,2026-10-27T10:00:00Z,2026-10-29T10:00:00Z,UTC,T+48H,native_export,v1,operator_export,organic,100,,50,50,0,0,0,0,0,0,1,,,\n"
        result = build_weekly_report(self.request(metric_snapshots_csv=self.request()["metric_snapshots_csv"] + second))
        buckets = result["report"]["top_content"]
        self.assertEqual(set(buckets), {"T+24H", "T+48H"})
        self.assertIn("engagements", buckets["T+24H"]["metrics"])
        self.assertIn("likes", buckets["T+48H"]["metrics"])

    def test_empty_posts_and_interactions_are_unknown_without_coverage_confirmation(self):
        result = build_weekly_report(self.request(posts_csv="", metric_snapshots_csv="", manual_interactions=[]))
        self.assertIsNone(result["report"]["original_post_count"])
        self.assertIsNone(result["report"]["manual_reply_count"])
        self.assertIsNone(result["report"]["outbound_manual_reply_count"])

    def test_explicitly_complete_empty_coverage_allows_zero_counts(self):
        result = build_weekly_report(self.request(posts_csv="", metric_snapshots_csv="", manual_interactions=[], posts_coverage_complete=True, interactions_coverage_complete=True))
        self.assertEqual(result["report"]["original_post_count"], 0)
        self.assertEqual(result["report"]["manual_reply_count"], 0)

    def test_rejects_forged_publication_url(self):
        posts = self.request()["posts_csv"].replace("https://x.com/demo/status/1", "https://evil.example/demo/status/1")
        result = build_weekly_report(self.request(posts_csv=posts, metric_snapshots_csv=""))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("INVALID_POST_SOURCE", result["reasons"])

    def test_publication_urls_are_reported_as_unverified_user_reports(self):
        result = build_weekly_report(self.request())
        self.assertEqual(result["report"]["publication_evidence"], "USER_REPORTED_UNVERIFIED")

    def test_insufficient_comparison_propagates_to_report_status(self):
        records = [{"group": group, "value": 10, "metric": "impressions", "age_window": "T+24H", "observed_at": "2026-10-28T10:00:00Z", "source": "manual"} for group in ("A", "B")]
        result = build_weekly_report(self.request(comparison=records))
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")


if __name__ == "__main__":
    unittest.main()
