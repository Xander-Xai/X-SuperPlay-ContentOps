from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from x_learning_loop import analyze, initialize, FILES, CONTEXT_FILE  # noqa: E402


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

    def _context(self, cid, url, *, topic="ai_agent", language="en", exp="CEXP-20261113-001", minutes="10", quality="3"):
        append(self.data / CONTEXT_FILE, content_id=cid, x_post_url=url,
               experiment_id=exp, topic_cluster=topic, language=language,
               founder_minutes=minutes, qualified_conversations=quality)

    def _metric(self, cid, url, impressions=100, clicks=2, window="T+24H",
                access="available", paid="organic", definition="native_v1"):
        append(self.data / FILES[1], metric_snapshot_id=f"sample-{cid}-{window}",
               content_id=cid, x_post_url=url, age_window=window,
               observed_at="2026-11-13T10:00:00+08:00", metric_source="native_manual",
               data_access=access, organic_paid=paid,
               metric_definition_version=definition, impressions=impressions,
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
        self.assertEqual(result["status"], "EXPLORATORY_ONLY")

    def test_compare_requires_scope_and_not_just_aggregate(self):
        with self.assertRaisesRegex(ValueError, "requires valid"):
            analyze(self.data, "x-superplay-english", "T+24H", compare=True)
        self.assertEqual(analyze(self.data, "x-superplay-english", "T+24H")["status"],
                         "EXPLORATORY_ONLY")

    def test_compare_excludes_other_topics_languages_and_versions(self):
        for i in range(1, 6):
            cid, url = self._post(i, "inspiration_ai")
            self._context(cid, url, topic="gaming" if i < 3 else "ai_agent",
                          language="zh" if i == 3 else "en")
            self._metric(cid, url, definition="native_v2" if i == 4 else "native_v1")
        for i in range(6, 11):
            cid, url = self._post(i, "timeline_ai")
            self._context(cid, url)
            self._metric(cid, url)
        result = analyze(self.data, "x-superplay-english", "T+24H",
                         experiment_id="CEXP-20261113-001", topic_cluster="ai_agent",
                         language="en", definition="native_v1", compare=True)
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")
        self.assertEqual(result["skipped"]["metric_definition_mismatch"], 1)

    def test_median_rate_and_pooled_rate_can_diverge(self):
        for i, views in enumerate((10, 10, 10000, 10, 10), 1):
            cid, url = self._post(i, "inspiration_ai")
            self._context(cid, url, minutes="10", quality="2")
            self._metric(cid, url, impressions=views, clicks=1 if views != 10000 else 0)
        for i in range(6, 11):
            cid, url = self._post(i, "timeline_ai")
            self._context(cid, url, minutes="10", quality="2")
            self._metric(cid, url, impressions=100, clicks=4)
        result = analyze(self.data, "x-superplay-english", "T+24H",
                         experiment_id="CEXP-20261113-001", topic_cluster="ai_agent",
                         language="en", definition="native_v1", compare=True)
        by_source = {g["source"]: g for g in result["groups"]}
        self.assertEqual(result["status"], "DESCRIPTIVE_ONLY")
        self.assertEqual(by_source["inspiration_ai"]["median_profile_clicks_per_1000"], 100)
        self.assertLess(by_source["inspiration_ai"]["profile_clicks_per_1000_impressions"], 1)
        self.assertEqual(by_source["timeline_ai"]["quality_per_founder_hour"], 12)
        self.assertIn("inspiration_ai", result["next_experiment"]["recommendation"])

    def test_only_broad_and_ai_is_not_valid_BC_comparison(self):
        for i in range(1, 6):
            cid, url = self._post(i, "inspiration_ai")
            self._context(cid, url)
            self._metric(cid, url)
        for i in range(6, 11):
            cid, url = self._post(i, "inspiration_broad")
            self._context(cid, url)
            self._metric(cid, url)
        result = analyze(self.data, "x-superplay-english", "T+24H",
                         experiment_id="CEXP-20261113-001", topic_cluster="ai_agent",
                         language="en", definition="native_v1", compare=True)
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")

    def test_group_comparison_is_descriptive_only(self):
        for i in range(1, 6):
            cid, url = self._post(i, "inspiration_ai")
            self._metric(cid, url, impressions=1000, clicks=2)
            self._context(cid, url)
        for i in range(6, 11):
            cid, url = self._post(i, "timeline_ai")
            self._metric(cid, url, impressions=100, clicks=3)
            self._context(cid, url)
        result = analyze(self.data, "x-superplay-english", "T+24H",
                         experiment_id="CEXP-20261113-001", topic_cluster="ai_agent",
                         language="en", definition="native_v1", compare=True)
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

    def test_wrong_snapshot_age_is_excluded(self):
        cid, url = self._post(1, "timeline_ai")
        self._metric(cid, url, window="T+72H")
        result = analyze(self.data, "x-superplay-english", "T+72H")
        self.assertEqual(result["skipped"]["snapshot_age_mismatch"], 1)
        self.assertEqual(sum(g["sample_count"] for g in result["groups"]), 0)

    def test_history_persists_scoped_report_and_route_carries_source(self):
        import json
        from types import SimpleNamespace
        from unittest.mock import patch
        from x_learning_loop import main
        for i in range(1, 6):
            cid, url = self._post(i, "inspiration_ai")
            self._context(cid, url)
            self._metric(cid, url)
        for i in range(6, 11):
            cid, url = self._post(i, "timeline_ai")
            self._context(cid, url)
            self._metric(cid, url)
        common = ["--data-dir", str(self.data), "--account", "x-superplay-english"]
        self.assertEqual(main(["analyze", *common, "--compare",
                               "--experiment-id", "CEXP-20261113-001",
                               "--topic-cluster", "ai_agent", "--language", "en",
                               "--definition", "native_v1"]), 0)
        report = json.loads((self.data / "learning" / "latest.json").read_text(encoding="utf-8"))
        self.assertTrue((self.data / "learning" / "history" /
                         (report["report_id"] + ".json")).exists())
        with patch("x_learning_loop.hidden_run",
                   return_value=SimpleNamespace(returncode=0, stdout="ok", stderr="")) as runner:
            self.assertEqual(main(["route", *common, "--report-id", report["report_id"],
                                   "--decision", "CONTINUE", "--reviewer", "Founder",
                                   "--topic", "Agent failure recovery",
                                   "--evidence-url", "https://docs.example.org/source",
                                   "--confirm"]), 0)
            cmd = runner.call_args.args[0]
            self.assertIn("--url", cmd)
            self.assertIn("https://docs.example.org/source", cmd)
            self.assertIn("--by", cmd)
            receipt_path = self.data / "learning" / "handoffs" / (report["report_id"] + "-CONTINUE.json")
            self.assertTrue(receipt_path.is_file())
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertFalse(receipt["publication_authorized"])
            self.assertEqual(receipt["evidence_url"], "https://docs.example.org/source")

    def test_changed_source_blocks_past_report_route(self):
        import json
        from x_learning_loop import main
        for i in range(1, 6):
            cid, url = self._post(i, "inspiration_ai")
            self._context(cid, url)
            self._metric(cid, url)
        for i in range(6, 11):
            cid, url = self._post(i, "timeline_ai")
            self._context(cid, url)
            self._metric(cid, url)
        args = ["--data-dir", str(self.data), "--account", "x-superplay-english"]
        self.assertEqual(main(["analyze", *args, "--compare", "--experiment-id",
                               "CEXP-20261113-001", "--topic-cluster", "ai_agent",
                               "--language", "en", "--definition", "native_v1"]), 0)
        latest = json.loads((self.data / "learning" / "latest.json").read_text(encoding="utf-8"))
        with (self.data / CONTEXT_FILE).open("a", encoding="utf-8") as file:
            file.write("\n")
        self.assertEqual(main(["route", *args, "--report-id", latest["report_id"],
                               "--decision", "CONTINUE", "--reviewer", "Founder",
                               "--topic", "New Agent topic",
                               "--evidence-url", "https://docs.example.org/agent",
                               "--confirm"]), 2)

    def test_route_rejects_stale_report_identity(self):
        import json
        from x_learning_loop import main
        result = analyze(self.data, "x-superplay-english", "T+24H")
        folder = self.data / "learning"
        folder.mkdir()
        (folder / "latest.json").write_text(json.dumps(result), encoding="utf-8")
        code = main(["route", "--data-dir", str(self.data), "--account",
                     "x-superplay-english", "--report-id", "XL-bad",
                     "--decision", "CONTINUE", "--reviewer", "Founder",
                     "--topic", "Agent failure recovery",
                     "--evidence-url", "https://docs.example.org/source", "--confirm"])
        self.assertEqual(code, 2)

    def test_private_storage_guard_rejects_tracked_directory(self):
        from x_learning_loop import initialize
        with self.assertRaisesRegex(ValueError, "ignored .local"):
            initialize(ROOT / "projects" / "x-growth-en" / "metrics")

    def test_account_snapshot_is_context_not_post_attribution(self):
        append(self.data / FILES[2], snapshot_id="s1", account_handle="x-superplay-english",
               observed_at="2026-11-13T05:03:00+08:00",
               observation_source="native_manual_screenshot",
               account_impressions="2711", account_profile_visits="67")
        result = analyze(self.data, "x-superplay-english", "T+24H")
        self.assertEqual(result["account_context"]["account_impressions"], 2711)
        self.assertEqual(result["account_context"]["attribution"], "ACCOUNT_LEVEL_ONLY")


if __name__ == "__main__":
    unittest.main()
