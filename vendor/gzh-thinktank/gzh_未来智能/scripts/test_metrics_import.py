#!/usr/bin/env python3
"""Regression tests for measured-window metrics import."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from import_metrics import import_window
from workflow_gate import _conversion_metric_errors


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="metrics-import-") as raw:
        article = Path(raw) / "article"
        article.mkdir()
        (article / "content-brief.yaml").write_text("schema_version: 3\n", encoding="utf-8")
        (article / "metrics.json").write_text(json.dumps({
            "schema_version": 2,
            "t1": {}, "t7": {},
            "conversion": {"follows": 0, "keyword_replies": 0, "lead_magnet_claims": 0, "consultation_requests": 0, "qualified_leads": 0},
            "attribution": {"primary_cta": "cta", "reply_keyword": "AI", "lead_magnet": "资料"},
        }), encoding="utf-8")
        raw_export = Path(raw) / "t1.json"
        raw_export.write_text(json.dumps({"captured_at": "2026-08-09T12:00:00+08:00", "values": {"views": 100, "follows": 4}}), encoding="utf-8")
        assert import_window(article, "t1", raw_export, "manual-export-20260809", None, False) == 0
        assert _conversion_metric_errors(article) == []
        observed = json.loads((article / "metrics.json").read_text(encoding="utf-8"))["t1"]
        assert observed["source_path"].startswith("work/metrics/t1-")
        assert (article / observed["source_path"]).is_file()
        assert import_window(article, "t1", raw_export, "manual-export-20260809", None, False) == 1
        bad = Path(raw) / "bad.json"
        bad.write_text(json.dumps({"captured_at": "2026-08-09T12:00:00+08:00", "values": {"views": -1}}), encoding="utf-8")
        assert import_window(article, "t7", bad, "manual-export-20260815", None, False) == 1
    print("METRICS IMPORT TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
