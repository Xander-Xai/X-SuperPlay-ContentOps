"""Bounded experiment fixtures; no real publication or strategy mutation."""
import csv
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import editorial_experiments as experiments
import editorial_feedback as feedback
import platform_learning_loop as learning


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.d = Path(temp.name) / "ops"
        self.m = Path(temp.name) / "metrics"
        feedback.init_links(self.d)
        learning.initialize(self.m)
        self.kw = dict(experiment="exp", account="x-superplay-future-intelligence", platform="bilibili",
                       topic="agent", variable="hook", a="Question", b="Result", hypothesis="Test framing",
                       start="2026-11-20", end="2026-11-26", reviewer="Fixture", confirmed=True,
                       today=date(2026, 11, 19))

    def test_plan_bounds(self):
        for changes in ({"variable": "duration"}, {"confirmed": False}, {"end": "2027-01-01"},
                        {"start": "2026-11-18"}, {"b": "Question"}):
            with self.assertRaises(ValueError):
                experiments.create(self.d, **dict(self.kw, **changes))
        result = experiments.create(self.d, **self.kw)
        self.assertFalse(result["dna_changed"])
        with self.assertRaises(FileExistsError):
            experiments.create(self.d, **self.kw)

    def add(self, path, cols, row):
        with path.open("a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=cols).writerow(row)

    def item(self, n, arm, stamp="2026-11-20T10:00:00+08:00"):
        ident, url = str(n), "https://example.org/post/" + str(n)
        row = dict(content_id=ident, post_url=url, platform="bilibili",
                   account_alias=self.kw["account"], content_format="video", discovery_source="search",
                   topic_cluster="agent", experiment_id="exp", published_at=stamp, publish_status="reported_published")
        self.add(self.m / "content-index.csv", learning.INDEX_COLUMNS, row)
        snap = {k: v for k, v in row.items() if k in learning.SNAPSHOT_COLUMNS}
        snap.update(observed_at="2026-11-21T10:00:00+08:00", window="T+24H",
                    metric_definition_version="native_v1", organic_paid="organic", data_access="available",
                    metric_source="native_manual", views_or_reads="100", saves="5" if arm == "a" else "10")
        self.add(self.m / "metric-snapshots.csv", learning.SNAPSHOT_COLUMNS, snap)
        self.add(self.d / "experiment-links.csv", feedback.LINKS,
                 dict(content_id=ident, post_url=url, experiment_id="exp", variable="hook", variant=arm))

    def review(self):
        return experiments.review(self.d, self.m, experiment="exp", reviewer="Fixture", confirmed=True)

    def test_review_and_dna_drift(self):
        experiments.create(self.d, **self.kw)
        for n in range(10):
            self.item(n, "a" if n < 5 else "b")
        result = self.review()
        self.assertEqual(result["observed_priority"], "b")
        self.assertFalse(result["publish_authorized"])
        with patch.object(experiments, "dna_hash", return_value="different"):
            with self.assertRaises(ValueError):
                self.review()

    def test_out_of_period(self):
        experiments.create(self.d, **self.kw)
        self.item(0, "a", "2026-11-18T10:00:00+08:00")
        with self.assertRaises(ValueError):
            self.review()



    def test_guardrail_regression_overrides_b_followup(self):
        experiments.create(self.d, **self.kw, min_primary_ratio=0.8)
        for n in range(10):
            self.item(n, "a" if n < 5 else "b")
        path = self.m / "metric-snapshots.csv"
        rows = learning._load(path, learning.SNAPSHOT_COLUMNS)
        for row in rows[5:]:
            row["views_or_reads"] = "50"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=learning.SNAPSHOT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        result = self.review()
        self.assertEqual(result["observed_priority"], "b")
        self.assertEqual(result["guardrails"]["status"], "REGRESSION")
        self.assertEqual(result["next_action"], "HOLD_FOR_GUARDRAIL_OR_MORE_DATA")

    def test_guardrails_pass_or_fail_closed(self):
        cfg = experiments.guardrail_config(0.8, 0.9)
        groups = {"a": {"median_primary": 100, "sample_count": 5,
                        "qualified_signals_per_hour": 2, "effort_sample_count": 5},
                  "b": {"median_primary": 90, "sample_count": 5,
                        "qualified_signals_per_hour": 2, "effort_sample_count": 5}}
        self.assertEqual(experiments.evaluate_guardrails(cfg, groups)["status"], "PASS")
        groups["b"]["effort_sample_count"] = 4
        self.assertEqual(experiments.evaluate_guardrails(cfg, groups)["status"], "INSUFFICIENT_DATA")
        with self.assertRaises(ValueError):
            experiments.guardrail_config(float("nan"))
        with self.assertRaises(ValueError):
            experiments.guardrail_config(1.1)


if __name__ == "__main__":
    unittest.main()
