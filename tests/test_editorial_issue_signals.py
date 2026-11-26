#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import editorial_issue_signals as issues
import editorial_ops as ops


class IssueTests(unittest.TestCase):
    def setUp(self):
        self.raw = {"incomplete_results": False, "items": [
            {"number": 3, "html_url": "https://github.com/example/tool/issues/3",
             "title": "Support recovery", "body": "Do not retain this raw body",
             "user": {"login": "synthetic"}}]}
        self.stamp = "2026-11-26T00:00:00+00:00"

    def normalize(self):
        return issues.normalize(json.dumps(self.raw).encode(), "example/tool",
                                "recovery", self.stamp, "local_export_unverified")

    def test_preview_and_ingest(self):
        p = self.normalize()
        self.assertNotIn("body", json.dumps(p))
        self.assertNotIn("login", json.dumps(p))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            r = issues.ingest(root, p, 3, "agent", "Reported recovery feature request")
            self.assertEqual(r["status"], "OBSERVED_ONLY")
            self.assertFalse(r["buyer_verified"])
            self.assertEqual(ops.load(root, "signals.csv")[0]["kind"], "issue")
            r = issues.ingest(root, p, 3, "agent", "Another observation")
            self.assertEqual(r["status"], "DUPLICATE")
            self.assertEqual(len(ops.load(root, "signals.csv")), 1)

    def test_wrong_repo_pr_and_incomplete(self):
        self.raw["items"][0]["html_url"] = "https://github.com/other/tool/issues/3"
        with self.assertRaises(ValueError):
            self.normalize()
        self.raw["items"][0]["html_url"] = "https://github.com/example/tool/issues/3"
        self.raw["items"][0]["pull_request"] = {}
        with self.assertRaises(ValueError):
            self.normalize()
        del self.raw["items"][0]["pull_request"]
        self.raw["incomplete_results"] = True
        with self.assertRaises(ValueError):
            self.normalize()

    def test_plain_scope_and_selection(self):
        with self.assertRaises(ValueError):
            issues.scope("example/tool", "repo:other/tool")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                issues.ingest(Path(tmp), self.normalize(), 4, "agent", "Not selected")

    def test_duplicate_preview_rejected(self):
        self.raw["items"].append(dict(self.raw["items"][0]))
        with self.assertRaises(ValueError):
            self.normalize()


if __name__ == "__main__":
    unittest.main()
