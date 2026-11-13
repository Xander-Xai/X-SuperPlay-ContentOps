from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from x_discussion_candidates import (  # noqa: E402
    HEADERS, INPUT_NAME, OUTPUT_NAME, initialize, rank
)


class CandidateTriageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "private-x"
        initialize(self.data)

    def add(self, id, **fields):
        base = {
            "source_url": f"https://x.com/example/status/{id}",
            "account_handle": "x-superplay-english",
            "language": "en",
            "discovery_source": "inspiration_ai",
            "topic_cluster": "ai_agent",
            "observed_at": "2026-11-13T12:00:00+08:00",
            "source_access": "operator_viewed",
            "author_active": "unknown",
            "trend_signal": "",
            "source_impressions": "",
            "topic_relevance": "4",
            "audience_fit": "4",
            "incremental_value": "4",
            "evidence_quality": "4",
            "discussion_potential": "4",
            "duplication_risk": "1",
            "compliance_risk": "1",
        }
        base.update(fields)
        with (self.data / INPUT_NAME).open("a", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=HEADERS).writerow(base)

    def rows(self):
        with (self.data / OUTPUT_NAME).open(encoding="utf-8", newline="") as file:
            return list(csv.DictReader(file))

    def test_init_never_overwrites_private_file(self):
        path = self.data / INPUT_NAME
        path.write_text("local private content", encoding="utf-8")
        result = initialize(self.data)
        self.assertFalse(result["created"])
        self.assertEqual(path.read_text(encoding="utf-8"), "local private content")

    def test_relevance_and_value_outrank_vanity_impressions(self):
        self.add(1, discovery_source="inspiration_broad",
                 topic_relevance="3", audience_fit="3", incremental_value="3",
                 trend_signal="5", source_impressions="8000000")
        self.add(2, discovery_source="timeline_ai",
                 topic_relevance="5", audience_fit="5", incremental_value="5",
                 source_impressions="100")
        result = rank(self.data, "x-superplay-english", "en")
        self.assertEqual(result["review_candidates"], 2)
        self.assertEqual(self.rows()[0]["discovery_source"], "timeline_ai")
        self.assertEqual(result["publication_authorized"], False)

    def test_risk_blocks_even_trending_topic(self):
        self.add(1, compliance_risk="4", trend_signal="5", author_active="yes")
        self.add(2, duplication_risk="5", trend_signal="5")
        result = rank(self.data, "x-superplay-english", "en")
        self.assertEqual(result["skipped"], 2)
        self.assertTrue(all(row["decision"] == "SKIP" for row in self.rows()))

    def test_missing_scores_and_unviewed_source_are_skipped(self):
        self.add(1, evidence_quality="", source_access="not_found")
        result = rank(self.data, "x-superplay-english", "en")
        self.assertEqual(result["skipped"], 1)
        self.assertIn("MISSING_OR_INVALID_HUMAN_RATING", self.rows()[0]["reason"])
        self.assertIn("SOURCE_NOT_OPERATOR_VERIFIED", self.rows()[0]["reason"])

    def test_dedupe_and_language_account_isolation(self):
        self.add(1)
        self.add(1)
        self.add(2, account_handle="another-account")
        self.add(3, language="zh")
        result = rank(self.data, "x-superplay-english", "en")
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["not_for_this_account"], 2)
        self.assertEqual(result["review_candidates"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertIn("DUPLICATE_SOURCE_URL", self.rows()[1]["reason"])

    def test_invalid_url_and_bad_timestamp_skip(self):
        self.add(1, source_url="https://example.org/a", observed_at="2026-11-13")
        rank(self.data, "x-superplay-english", "en")
        self.assertEqual(self.rows()[0]["decision"], "SKIP")
        self.assertEqual(self.rows()[0]["source_url"], "")

    def test_private_data_guard_in_repository(self):
        with self.assertRaisesRegex(ValueError, "ignored .local"):
            initialize(ROOT / "projects" / "x-growth-en" / "actual-analytics")

    def test_unset_or_nonfinite_score_is_not_ranked(self):
        self.add(1, audience_fit="NaN")
        self.add(2, topic_relevance="inf")
        rank(self.data, "x-superplay-english", "en")
        self.assertTrue(all(x["decision"] == "SKIP" for x in self.rows()))

    def test_empty_dataset_returns_unavailable(self):
        result = rank(self.data, "x-superplay-english", "en")
        self.assertEqual(result["status"], "DATA_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
