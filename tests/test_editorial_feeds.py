"""Feed format/security and idempotency checks; no live network."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import editorial_feeds as feeds
import editorial_ops as ops


RSS = b'<rss version="2.0"><channel><item><title>Agent failure</title><link>https://example.org/a</link></item></channel></rss>'
ATOM = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>New</title><link href="https://example.org/b"/></entry></feed>'


class FeedTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(feeds.parse(RSS)[0], [("Agent failure", "https://example.org/a")])
        self.assertEqual(feeds.parse(ATOM)[0], [("New", "https://example.org/b")])
        raw = json.dumps({"version": "https://jsonfeed.org/version/1.1",
                          "items": [{"title": "Third", "url": "https://example.org/c"}]}).encode()
        self.assertEqual(feeds.parse(raw)[0][0][0], "Third")

    def test_reject_xml_and_urls(self):
        with self.assertRaises(ValueError):
            feeds.parse(b'<!DOCTYPE rss [<!ENTITY foo "x">]><rss/>')
        with self.assertRaises(ValueError):
            feeds.public_url("https://user:pass@example.org/a")
        with self.assertRaises(ValueError):
            feeds.public_url("https://example.org/a?token=hidden")
        with self.assertRaises(ValueError):
            feeds.parse(b"x" * (feeds.LIMIT + 1))

    def test_idempotency(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            kw = dict(topic="agent", source_id="rsshub")
            self.assertEqual(feeds.ingest(d, RSS, **kw)["added"], 1)
            self.assertEqual(feeds.ingest(d, RSS, **kw)["added"], 0)
            self.assertEqual(len(ops.load(d, "signals.csv")), 1)
            self.assertFalse(feeds.ingest(d, ATOM, **kw)["demand_verified"])

    def test_network_confirmation(self):
        with patch.object(feeds, "fetch") as fetch:
            self.assertEqual(feeds.main(["--url", "https://example.org/feed",
                                        "--source-id", "test", "--topic", "agent"]), 1)
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
