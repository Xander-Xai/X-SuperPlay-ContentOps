"""Synthetic workbench and series checks, no external services."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import editorial_ops as ops
import editorial_workspace as workspace
import editorial_series as series
import platform_learning_loop as learning


def add(path, fields, row):
    with path.open("a", encoding="utf-8", newline="") as f:
        csv.DictWriter(f, fieldnames=fields).writerow(row)


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.d = ops.init(Path(t.name))
        topic = dict(zip(ops.FIELDS["topics.csv"], [
            "agent", "x-superplay-english", "x", "text", "developers", "recovery",
            "agent-series", "<script>alert(1)</script>", "Discuss", "2026-11-26",
            "10", "low", "Founder", "9", "9", "9", "9", "9", "9"]))
        add(self.d / "topics.csv", ops.FIELDS["topics.csv"], topic)
        self.rev, report = workspace.snapshot(self.d)
        self.ident = report["queue"][0]["id"]

    def test_edit_stale_and_validation(self):
        rev, report = workspace.edit(self.d, self.ident, self.rev, {"minutes": "30"})
        self.assertNotEqual(rev, self.rev)
        self.assertEqual(report["queue"][0]["cost_lane"], "L2")
        with self.assertRaises(ValueError):
            workspace.edit(self.d, self.ident, self.rev, {"minutes": "10"})
        with self.assertRaises(ValueError):
            workspace.edit(self.d, self.ident, rev, {"minutes": "900"})
        self.assertEqual(workspace.snapshot(self.d)[0], rev)

    def test_immutable_and_routed(self):
        with self.assertRaises(ValueError):
            workspace.edit(self.d, self.ident, self.rev, {"account": "other"})
        (self.d / ("route-" + self.ident + ".json")).write_text(
            json.dumps({"status": "ROUTED_FOR_HUMAN_REVIEW"}), encoding="utf-8")
        with self.assertRaises(ValueError):
            workspace.edit(self.d, self.ident, self.rev, {"hook": "new"})
        self.assertIn("editing locked", workspace.render(self.d, "fixture"))

    def test_html_escaped(self):
        page = workspace.render(self.d, "fixture")
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)


    def test_daily_capacity_is_read_only_and_integrated(self):
        add(self.d / "signals.csv", ops.FIELDS["signals.csv"],
            dict(signal_id="signal-1", topic="agent", kind="issue",
                 source_url="https://example.org/issue/1",
                 observed_at="2026-11-26T00:00:00+00:00", observation="Synthetic problem"))
        before = workspace.revision(self.d)
        page = workspace.render(self.d, "fixture", "2026-11-26", 15)
        self.assertIn("Daily capacity", page)
        self.assertIn("10 / 15 estimated minutes", page)
        self.assertIn("demand URLs 1", page)
        self.assertIn("#candidate-" + self.ident, page)
        self.assertEqual(workspace.revision(self.d), before)
        self.assertFalse((self.d / ("route-" + self.ident + ".json")).exists())
        with self.assertRaises(ValueError):
            workspace.render(self.d, "fixture", "2026-11-26", None)


    def test_lifecycle_link_and_due_windows(self):
        import editorial_lifecycle as lifecycle
        from contentops.workflow import new_workflow
        metrics = self.d / "metrics"
        learning.initialize(metrics)
        lifecycle.initialize(self.d)
        root = self.d / "projects"
        project = root / "fixture"
        project.mkdir(parents=True)
        # X text has a separate pipeline; link only the publication in this fixture.
        add(self.d / "lifecycle-links.csv", lifecycle.FIELDS,
            dict(candidate_id=self.ident, project_slug="", content_id="post",
                 post_url="https://x.com/example/status/1", definition="native_v1"))
        row = dict(content_id="post", post_url="https://x.com/example/status/1",
                   platform="x", account_alias="x-superplay-english", content_format="text",
                   topic_cluster="agent", discovery_source="search", experiment_id="exp",
                   published_at="2026-11-26T00:00:00+00:00", publish_status="reported_published")
        add(metrics / "content-index.csv", learning.INDEX_COLUMNS, row)
        before = (metrics / "content-index.csv").read_bytes()
        report = lifecycle.report(self.d, ops.plan(self.d), metrics, root, "2026-11-27T00:00:00+00:00")
        item = report["items"][0]
        self.assertEqual(item["publication"]["windows"]["T+24H"], "DUE")
        self.assertEqual(item["publication"]["windows"]["T+72H"], "NOT_DUE")
        self.assertFalse(report["publish_authorized"])
        self.assertEqual((metrics / "content-index.csv").read_bytes(), before)
        self.assertIn("Lifecycle (local records)", workspace.render(self.d, "fixture", metrics=metrics, projects=root))
        q = dict(ops.plan(self.d)["queue"][0], format="video")
        from contentops.workflow import CONTRACT_ID
        workflow = new_workflow("fixture", q["account"], CONTRACT_ID)
        path = project / "workflow.json"
        path.write_text(json.dumps(workflow), encoding="utf-8")
        raw = path.read_bytes()
        self.assertEqual(lifecycle.project_status(root, "fixture", q)["state"], "WORKFLOW_REVIEW_REQUIRED")
        self.assertEqual(path.read_bytes(), raw)
        q["account"] = "wrong"
        self.assertEqual(lifecycle.project_status(root, "fixture", q)["state"], "WORKFLOW_SCOPE_MISMATCH")


class SeriesTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.d = Path(t.name) / "ops"
        self.m = Path(t.name) / "metrics"
        series.init(self.d)
        learning.initialize(self.m)

    def item(self, n, label, saves):
        ident, url = str(n), "https://example.org/post/" + str(n)
        row = dict(content_id=ident, post_url=url, platform="bilibili",
                   account_alias="x-superplay-future-intelligence", content_format="video",
                   discovery_source="search", topic_cluster="agent", experiment_id="exp",
                   published_at="2026-11-20T10:00:00+08:00", publish_status="reported_published")
        add(self.m / "content-index.csv", learning.INDEX_COLUMNS, row)
        snap = {k: v for k, v in row.items() if k in learning.SNAPSHOT_COLUMNS}
        snap.update(observed_at="2026-11-21T10:00:00+08:00", window="T+24H",
                    metric_definition_version="native_v1", organic_paid="organic",
                    data_access="available", metric_source="native_manual",
                    views_or_reads="100", saves=str(saves))
        add(self.m / "metric-snapshots.csv", learning.SNAPSHOT_COLUMNS, snap)
        add(self.d / "series-links.csv", series.FIELDS, dict(content_id=ident, post_url=url,
                                                          experiment_id="exp", series=label))

    def review(self):
        return series.review(self.d, self.m, experiment="exp", platform="bilibili",
                             account="x-superplay-future-intelligence", content_format="video",
                             topic="agent", window="T+24H", definition="native_v1",
                             primary="views_or_reads", interest="saves")

    def test_comparable_and_insufficient(self):
        self.item(0, "a", 5)
        self.assertIsNone(self.review()["research_priority"])
        for n in range(1, 10):
            self.item(n, "a" if n < 5 else "b", 5 if n < 5 else 10)
        result = self.review()
        self.assertEqual(result["research_priority"], "b")
        self.assertEqual(result["status"], "DESCRIPTIVE_ONLY")
        self.assertFalse(result["publish_authorized"])

    def test_tie(self):
        for n in range(10):
            self.item(n, "a" if n < 5 else "b", 5)
        self.assertIsNone(self.review()["research_priority"])



    def test_series_schedule_reuses_plan_and_distinguishes_route(self):
        for topic, url in (("agent", "https://example.org/issue/1"), ("other", "https://example.org/issue/2")):
            add(self.d / "signals.csv", ops.FIELDS["signals.csv"],
                dict(signal_id=topic, topic=topic, kind="issue", source_url=url,
                     observed_at="2026-11-26T00:00:00+00:00", observation="Fixture"))
        for topic, angle, day in (("agent", "first", "2026-11-26"),
                                  ("agent", "second", "2026-11-27"),
                                  ("other", "third", "2026-12-03")):
            row = dict(zip(ops.FIELDS["topics.csv"], [
                topic, "x-superplay-future-intelligence", "bilibili", "video", "devs", angle,
                "agent-series", "Hook", "CTA", day, "20", "low", "Fixture",
                "9", "9", "9", "9", "9", "9"]))
            add(self.d / "topics.csv", ops.FIELDS["topics.csv"], row)
        first = next(q for q in ops.plan(self.d)["queue"] if q["angle"] == "first")
        (self.d / ("route-" + first["id"] + ".json")).write_text("{}", encoding="utf-8")
        kw = dict(series="agent-series", account="x-superplay-future-intelligence",
                  platform="bilibili", content_format="video", start="2026-11-26",
                  end="2026-12-09", weekly_target=2)
        result = series.schedule(self.d, **kw)
        self.assertEqual([w["planning_gap"] for w in result["weeks"]], [0, 1])
        self.assertEqual([e["status"] for e in result["episodes"]],
                         ["ROUTE_RECEIPT_EXISTS", "REUSED_SOURCE_REVIEW", "NEW_SOURCE_REVIEW"])
        self.assertFalse(result["publish_authorized"])
        with self.assertRaises(ValueError):
            series.schedule(self.d, **dict(kw, end="2026-12-08"))


if __name__ == "__main__":
    unittest.main()
