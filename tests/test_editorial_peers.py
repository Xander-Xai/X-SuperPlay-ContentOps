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


if __name__ == "__main__":
    unittest.main()
