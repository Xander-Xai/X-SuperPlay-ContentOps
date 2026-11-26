#!/usr/bin/env python3
import csv
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import editorial_inbox as inbox
import editorial_ops as ops
import platform_learning_loop as learning


class InboxTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.row = dict(account="x-superplay-english", platform="x", topic="agent",
                        category="pain", source_url="https://example.org/public/1",
                        observed_at="2026-11-26T00:00:00+00:00",
                        observation="Reported recovery problem", reviewer="Founder", confirmed=True)

    def add(self, **kwargs):
        return inbox.add(self.root, **{**self.row, **kwargs})

    def test_link_and_replay(self):
        a = self.add()
        self.assertEqual(self.add()["status"], "DUPLICATE")
        self.assertEqual(inbox.report(self.root)["groups"][0]["states"], {"READY_FOR_REVIEW": 1})
        r = inbox.promote(self.root, a["feedback_id"], "Founder", True)
        self.assertEqual(r["status"], "LINKED")
        self.assertFalse(r["buyer_verified"])
        self.assertFalse(r["publish_authorized"])
        self.assertEqual(inbox.promote(self.root, a["feedback_id"], "Founder", True)["status"], "ALREADY_LINKED")
        self.assertEqual(inbox.report(self.root)["groups"][0]["states"], {"LINKED": 1})
        self.assertEqual(ops.load(self.root, "signals.csv")[0]["kind"], "comment")
        self.assertEqual(ops.plan(self.root)["unique_signals"], 1)

    def test_invalid(self):
        for kwargs in ({"confirmed": False}, {"platform": "bilibili"},
                       {"source_url": "https://example.org/1?token=private"},
                       {"source_url": "https://user:pass@example.org/1"},
                       {"observed_at": "2026-11-26"}, {"category": "buyer"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.add(**kwargs)
        self.assertFalse((self.root / inbox.NAME).exists())

    def test_praise_conflict(self):
        a = self.add(category="praise")
        self.assertEqual(inbox.report(self.root)["groups"][0]["states"], {"OBSERVE_ONLY": 1})
        with self.assertRaises(ValueError):
            inbox.promote(self.root, a["feedback_id"], "Founder", True)
        with self.assertRaises(ValueError):
            self.add()
        self.assertEqual(ops.load(self.root, "signals.csv"), [])

    def test_group_and_confirm(self):
        a = self.add()
        b = self.add(source_url="https://example.org/public/2", category="question")
        self.assertEqual(inbox.report(self.root)["groups"][0]["unique_source_urls"], 2)
        with self.assertRaises(ValueError):
            inbox.promote(self.root, a["feedback_id"], "Founder", False)
        inbox.promote(self.root, a["feedback_id"], "Founder", True)
        inbox.promote(self.root, b["feedback_id"], "Founder", True)
        self.assertEqual(len(ops.load(self.root, "signals.csv")), 2)

    def test_tampering(self):
        self.add()
        path = self.root / inbox.NAME
        path.write_text(path.read_text(encoding="utf-8").replace("public/1", "public/2"), encoding="utf-8")
        with self.assertRaises(ValueError):
            inbox.report(self.root)


    def publication_fixture(self):
        stamp = datetime.now(timezone.utc)
        a = self.add(observed_at=(stamp - timedelta(hours=1)).isoformat())
        metrics = self.root / "metrics"
        learning.initialize(metrics)
        p = dict(content_id="post-1", post_url="https://example.org/post/1",
                 platform="x", account_alias=self.row["account"], content_format="text",
                 discovery_source="comment", topic_cluster="agent", experiment_id="exp",
                 published_at=(stamp - timedelta(days=1)).isoformat(),
                 publish_status="reported_published")
        self.write_index(metrics, [p])
        return a["feedback_id"], metrics, p

    def write_index(self, metrics, rows):
        with (metrics / "content-index.csv").open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=learning.INDEX_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    def test_publication_binding_and_consented_handoff(self):
        ident, metrics, p = self.publication_fixture()
        args = (self.root, metrics, ident, p["content_id"], p["post_url"], "Founder")
        with self.assertRaises(ValueError):
            inbox.publication_binding(*args, False)
        r = inbox.publication_binding(*args, True)
        self.assertEqual(r["status"], "PUBLICATION_LINKED")
        self.assertEqual(inbox.publication_binding(*args, True), r)
        self.assertFalse(r["buyer_verified"])
        with self.assertRaises(ValueError):
            inbox.handoff_lead(self.root, metrics, ident, "Founder", False, True)
        lead = inbox.handoff_lead(self.root, metrics, ident, "Founder", True, True)
        self.assertEqual(lead["local_evidence_ref"], ident)
        self.assertFalse(lead["paid_demand_verified"])
        self.assertNotIn("observation", lead)
        self.assertNotIn("source_url", lead)

    def test_publication_wrong_scope_duplicate_and_stale(self):
        ident, metrics, p = self.publication_fixture()
        args = (self.root, metrics, ident, p["content_id"], p["post_url"], "Founder", True)
        self.write_index(metrics, [{**p, "topic_cluster": "different"}])
        with self.assertRaises(ValueError):
            inbox.publication_binding(*args)
        self.write_index(metrics, [p, {**p, "post_url": "https://example.org/post/2"}])
        with self.assertRaises(ValueError):
            inbox.publication_binding(*args)
        self.write_index(metrics, [p])
        inbox.publication_binding(*args)
        self.write_index(metrics, [{**p, "published_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}])
        with self.assertRaises(ValueError):
            inbox.handoff_lead(self.root, metrics, ident, "Founder", True, True)


if __name__ == "__main__":
    unittest.main()
