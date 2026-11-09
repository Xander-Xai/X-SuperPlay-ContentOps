"""Manual metrics: import what the creator exported, refuse the rest.

The failure mode worth guarding is not a wrong number — it is a plausible one.
A pipeline that fills a missing metric with an average produces a report nobody
can tell apart from a complete one. Every case below checks that a defect is
rejected loudly instead.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.manual_metrics import (  # noqa: E402
    MetricsRejected,
    SCHEMA_REPORT,
    load_report,
    load_reports,
    review,
    write_review,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _export(tmp: str, payload=None, *, source_name="youtube.csv",
            source_bytes=b"video,views\nabc,1200\n") -> tuple[Path, Path]:
    export_dir = Path(tmp) / "metrics" / "exports"
    export_dir.mkdir(parents=True)
    source = export_dir / source_name
    source.write_bytes(source_bytes)
    report = {
        "schema": SCHEMA_REPORT,
        "platform": "youtube",
        "work_url": "https://www.youtube.com/watch?v=abc123",
        "export_date": "2026-11-08",
        "source_file": source_name,
        "source_sha256": _sha(source),
        "metrics": {"views": 1200, "ctr": 0.042, "avg_view_duration_s": 38.5},
    }
    if payload:
        report.update(payload)
    path = export_dir / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return export_dir, path


class AcceptanceTests(unittest.TestCase):
    def test_a_complete_export_is_imported(self):
        with tempfile.TemporaryDirectory() as tmp:
            export_dir, path = _export(tmp)
            report = load_report(path, export_dir=export_dir)
        self.assertEqual(report.platform, "youtube")
        self.assertEqual(report.metrics["views"], 1200.0)
        self.assertEqual(report.export_date, "2026-11-08")

    def test_observations_are_factual_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            export_dir, path = _export(tmp)
            report = load_report(path, export_dir=export_dir)
            payload = review([report])
        self.assertEqual(len(payload["observations"]), 3)
        self.assertTrue(any("views=1200" in line for line in payload["observations"]))

    def test_metrics_are_never_estimated_upwards(self):
        with tempfile.TemporaryDirectory() as tmp:
            export_dir, path = _export(tmp, {"metrics": {"views": 1200}})
            report = load_report(path, export_dir=export_dir)
        # Only what was reported exists. No ctr, no view duration, no zero-fill.
        self.assertEqual(set(report.metrics), {"views"})


class RejectionTests(unittest.TestCase):
    def _reasons(self, tmp, payload):
        export_dir, path = _export(tmp, payload)
        with self.assertRaises(MetricsRejected) as ctx:
            load_report(path, export_dir=export_dir)
        return ctx.exception.reasons

    def test_every_missing_field_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            export_dir, path = _export(tmp)
            doc = json.loads(path.read_text(encoding="utf-8"))
            for key in ("platform", "work_url", "export_date"):
                doc.pop(key)
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(MetricsRejected) as ctx:
                load_report(path, export_dir=export_dir)
        reasons = " ".join(ctx.exception.reasons)
        for key in ("platform", "work_url", "export_date"):
            self.assertIn(key, reasons)

    def test_a_non_numeric_metric_is_rejected(self):
        reasons = self._reasons(tempfile.mkdtemp(),
                                {"metrics": {"views": "about 1200"}})
        self.assertTrue(any("must be a number" in r for r in reasons))

    def test_a_boolean_metric_is_rejected(self):
        reasons = self._reasons(tempfile.mkdtemp(), {"metrics": {"published": True}})
        self.assertTrue(any("must be a number" in r for r in reasons))

    def test_a_hash_mismatch_is_rejected(self):
        reasons = self._reasons(tempfile.mkdtemp(), {"source_sha256": "0" * 64})
        self.assertTrue(any("does not match" in r for r in reasons))

    def test_a_source_file_outside_the_export_dir_is_rejected(self):
        reasons = self._reasons(tempfile.mkdtemp(), {"source_file": "../secret.csv"})
        self.assertTrue(any("inside the export directory" in r for r in reasons))

    def test_a_non_http_url_is_rejected(self):
        reasons = self._reasons(tempfile.mkdtemp(), {"work_url": "ftp://example.com/x"})
        self.assertTrue(any("work_url" in r for r in reasons))

    def test_an_unreadable_schema_is_rejected(self):
        reasons = self._reasons(tempfile.mkdtemp(), {"schema": "v2"})
        self.assertTrue(any("schema" in r for r in reasons))


class ReviewTests(unittest.TestCase):
    def test_a_reporting_gap_becomes_the_next_variable(self):
        with tempfile.TemporaryDirectory() as tmp:
            export_dir, first = _export(tmp)
            full = load_report(first, export_dir=export_dir)
            source = export_dir / "youtube-2.csv"
            source.write_bytes(b"video,views\nxyz,900\n")
            second_doc = {
                "schema": SCHEMA_REPORT, "platform": "youtube",
                "work_url": "https://www.youtube.com/watch?v=xyz789",
                "export_date": "2026-11-09", "source_file": "youtube-2.csv",
                "source_sha256": _sha(source),
                "metrics": {"views": 900, "watch_time_min": 71},
            }
            (export_dir / "report2.json").write_text(json.dumps(second_doc), encoding="utf-8")
            reports, rejected = load_reports(export_dir)
            payload = review(reports, rejected)

        names = {r.platform for r in reports}
        self.assertEqual(names, {"youtube"})
        self.assertEqual(payload["rejected"], [])
        # ctr / avg_view_duration_s appear in one export only.
        self.assertIn(payload["next_variable"]["name"], {"ctr", "avg_view_duration_s"})
        self.assertIn("prescribes no edit", payload["next_variable"]["note"])

    def test_metrics_never_claim_to_modify_the_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            export_dir, path = _export(tmp)
            report = load_report(path, export_dir=export_dir)
            payload = review([report])
        self.assertFalse(payload["constraints"]["modifies_script"])
        self.assertFalse(payload["constraints"]["modifies_qc"])
        self.assertFalse(payload["constraints"]["modifies_production_ready"])
        self.assertFalse(payload["production_ready"])
        self.assertFalse(payload["publish_authorized"])
        self.assertNotIn("qc_verdict", payload)

    def test_an_empty_export_dir_is_reported_not_invented(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "sample"
            payload = write_review(project)
            written = json.loads(
                (project / "receipts" / "metrics-review.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["observations"], [])
        self.assertIsNone(payload["next_variable"])
        self.assertTrue(written["rejected"])
        self.assertFalse(written["network_used"])

    def test_a_rejected_export_does_not_hide_a_valid_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            export_dir, _ = _export(tmp)
            (export_dir / "broken.json").write_text("{not json", encoding="utf-8")
            reports, rejected = load_reports(export_dir)
        self.assertEqual(len(reports), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["file"], "broken.json")


class NoNetworkTests(unittest.TestCase):
    def test_the_module_opens_no_socket(self):
        source = (ROOT / "src" / "contentops" / "manual_metrics.py").read_text(encoding="utf-8")
        self.assertNotIn("import socket", source)
        self.assertNotIn("urllib.request", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("http.client", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
