"""Offline X API contract fixtures; no network or real account."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import editorial_x_observe as observe

STAMP = "2026-11-26T00:00:00+00:00"
def raw(value=100):
    return json.dumps({"data": [{"id": "123", "author_id": "456", "created_at": "2026-11-25T00:00:00Z",
        "lang": "en", "text": "do not store raw text", "public_metrics": {"impression_count": value, "like_count": 0}}]}).encode()


class ObserveTests(unittest.TestCase):
    def test_missing_is_not_zero(self):
        rows, missing = observe.normalize(raw(), ["123", "999"], STAMP)
        self.assertEqual(missing, ["999"])
        self.assertEqual(rows[0]["metrics"]["like_count"], 0)
        self.assertIsNone(rows[0]["metrics"]["reply_count"])
        self.assertFalse(rows[0]["benchmark_eligible"])
        self.assertNotIn("text", rows[0])

    def test_bad_metrics_or_identity(self):
        for v in (True, -1, "100"):
            with self.assertRaises(ValueError):
                observe.normalize(raw(v), ["123"], STAMP)
        with self.assertRaises(ValueError):
            observe.normalize(raw(), ["999"], STAMP)

    def test_confirmation_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            with patch.object(observe, "fetch") as fetch:
                with self.assertRaises(ValueError):
                    observe.collect(d, post_ids=["123"], topic="agent", confirmed=False)
                fetch.assert_not_called()
            kw = dict(post_ids=["123"], topic="agent", confirmed=True, raw=raw(), observed_at=STAMP)
            self.assertEqual(observe.collect(d, **kw), observe.collect(d, **kw))
            self.assertEqual(len(list(d.glob("x-peer-*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
