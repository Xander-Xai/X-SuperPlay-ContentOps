"""Synthetic peer baseline tests."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import editorial_peers as peers
import editorial_ops as ops


class PeerTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.d = Path(t.name)
        peers.init(self.d)

    def add(self, n, value, fmt="video", age="2026-11-21T10:00:00+08:00",
            peer="peer-1", url=None):
        ident = "case-" + str(n)
        row = dict(case_id=ident, topic="agent", platform="bilibili",
                   source_url=url or "https://example.org/post/" + str(n), observed_at=age,
                   hook="Synthetic hook", format=fmt, lesson="Synthetic lesson",
                   metric_name="views", metric_value=str(value))
        ctx = dict(case_id=ident, peer_alias=peer, published_at="2026-11-20T10:00:00+08:00",
                   definition="native-v1", window="T+24H", organic_paid="organic")
        for name, fields, record in [("peers.csv", ops.FIELDS["peers.csv"], row),
                                      ("peer-context.csv", peers.FIELDS, ctx)]:
            with (self.d / name).open("a", encoding="utf-8", newline="") as f:
                csv.DictWriter(f, fieldnames=fields).writerow(record)

    def test_outlier(self):
        for n in range(5):
            self.add(n, 100)
        self.add(5, 300)
        result = peers.analyze(self.d)["results"][0]
        self.assertEqual(result["case_id"], "case-5")
        self.assertEqual(result["ratio_to_peer_median"], 3)
        self.assertEqual(result["status"], "OBSERVED_OUTLIER")

    def test_no_cross_format_or_account(self):
        for n in range(5):
            self.add(n, 100)
        self.add(5, 300, fmt="text")
        self.add(6, 300, peer="peer-2")
        self.assertTrue(all(r["status"] == "INSUFFICIENT_BASELINE" for r in peers.analyze(self.d)["results"]))

    def test_age_and_duplicate(self):
        self.add(1, 10, age="2026-11-24T10:00:00+08:00")
        self.assertEqual(peers.analyze(self.d)["skipped"]["wrong_age"], 1)
        self.add(2, 10, url="https://example.org/same")
        self.add(3, 10, url="https://example.org/same")
        with self.assertRaises(ValueError):
            peers.analyze(self.d)



    def test_creative_patterns_comparable_only_within_cohort(self):
        import editorial_peer_patterns as patterns
        patterns.init(self.d)
        for n in range(10):
            self.add(n, 100 if n < 5 else 300)
            row = dict(case_id="case-" + str(n), hook_type="question" if n < 5 else "result",
                       title_promise="tutorial", cover_type="diagram", narrative="walkthrough",
                       evidence_location="opening at 00:00", original_application="Use own verified example",
                       reviewer="Synthetic")
            with (self.d / "peer-patterns.csv").open("a", encoding="utf-8", newline="") as f:
                csv.DictWriter(f, fieldnames=patterns.FIELDS).writerow(row)
        result = patterns.analyze(self.d)
        hooks = [x for x in result["comparisons"] if x["dimension"] == "hook_type"]
        self.assertEqual(len(hooks), 2)
        self.assertTrue(all(x["status"] == "DESCRIPTIVE_ONLY" for x in hooks))
        self.assertTrue(all(x["status"] == "INSUFFICIENT_DATA" for x in result["comparisons"]
                            if x["dimension"] != "hook_type"))
        self.assertFalse(result["publish_authorized"])
        self.assertEqual(len(result["cases"]), 10)

    def test_creative_pattern_unknown_case_refused(self):
        import editorial_peer_patterns as patterns
        patterns.init(self.d)
        row = dict(case_id="case-1", hook_type="unknown", title_promise="unknown",
                   cover_type="unknown", narrative="unknown", evidence_location="not reviewed",
                   original_application="no application", reviewer="Synthetic")
        with (self.d / "peer-patterns.csv").open("a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=patterns.FIELDS).writerow(row)
        with self.assertRaisesRegex(ValueError, "unknown peer case"):
            patterns.analyze(self.d)


if __name__ == "__main__":
    unittest.main()
