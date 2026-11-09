#!/usr/bin/env python3
"""Audit which metric windows are owed, observed, or simply missing.

Why this exists
---------------
The weekly report ranks whatever snapshots exist; it cannot see the snapshots
that should exist and do not. That blind spot is how a data loop breaks
quietly: publication happens, nobody exports the numbers, and ``0`` rows are
indistinguishable from absent rows downstream. Strategy's weekly review then
retires or exploits content on vibes.

This command answers one question per published piece of content: for T+24H,
T+72H and T+7D — is the window not due yet, closed with no snapshot ever
recorded (``DUE_MISSING``), or covered by an observation? A missing value
inside an observed row is reported as missing, never folded into zero.

Inputs are the CSVs the growth track already produces. Nothing is scraped,
imputed or estimated: if the number was never recorded, the audit says
``DUE_MISSING`` and stops there.

Usage
-----
    python scripts/metric_window_audit.py \
        --posts-csv reports/x-posts.csv \
        --snapshots-csv reports/x-metric-snapshots.csv \
        --json

    python scripts/metric_window_audit.py --posts-csv ... --snapshots-csv ... --strict

Exit codes: 0 pass (or nothing due-missing), 1 ``--strict`` and windows are
due-missing, 2 misuse or unreadable input.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.publish.metric_windows import (  # noqa: E402
    DUE_MISSING,
    WindowAuditError,
    audit_content,
    parse_timestamp,
    read_snapshots_csv,
    summarize,
)

POST_FIELDS = ("content_id", "published_at")


def _read_posts_csv(path: Path) -> List[Dict[str, str]]:
    path = Path(path)
    if not path.is_file():
        raise WindowAuditError("POSTS_CSV_MISSING", path.as_posix())
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        absent = [field for field in POST_FIELDS
                  if field not in fieldnames]
        if absent:
            raise WindowAuditError(
                "POSTS_CSV_COLUMNS",
                f"{path.as_posix()} lacks columns: {', '.join(absent)}")
        rows = list(reader)
    for index, row in enumerate(rows, start=2):
        blank = [field for field in POST_FIELDS
                 if not str(row.get(field) or "").strip()]
        if blank:
            raise WindowAuditError(
                "POSTS_CSV_COLUMNS",
                f"{path.as_posix()} line {index} lacks values: {', '.join(blank)}")
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Audit T+24H/72H/7D metric window coverage for published content.")
    parser.add_argument("--posts-csv", required=True,
                        help="CSV with columns: content_id, published_at")
    parser.add_argument("--snapshots-csv", required=True,
                        help="metric_snapshots.csv consumed by x_growth_metrics")
    parser.add_argument("--content-id", action="append", default=[],
                        help="audit only these content ids (repeatable; default: all)")
    parser.add_argument("--now",
                        help="ISO-8601 audit moment (default: actual now)")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 when any due window has no snapshot")
    parser.add_argument("--json", action="store_true", help="full JSON report")
    args = parser.parse_args(argv)

    try:
        posts = _read_posts_csv(Path(args.posts_csv))
        snapshots = read_snapshots_csv(Path(args.snapshots_csv))
        now = parse_timestamp(args.now) if args.now else None
        wanted = {str(value).strip() for value in args.content_id}
        audits: List[Dict[str, Any]] = []
        for post in posts:
            content_id = str(post.get("content_id") or "").strip()
            if wanted and content_id not in wanted:
                continue
            audits.append(audit_content(
                content_id, post.get("published_at"), snapshots, now=now))
    except WindowAuditError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    report = {"audits": audits, "summary": summarize(audits)}
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for audit in audits:
            windows = audit["windows"]
            line = " ".join(
                f"{name}={windows[name]['status']}"
                f"{'(value missing)' if windows[name]['status'] == 'OBSERVED' and windows[name]['impressions_missing'] else ''}"
                for name in windows)
            print(f"{audit['content_id']}: {line}")
        print(json.dumps(report["summary"], ensure_ascii=False))

    if args.strict and report["summary"]["due_missing_total"] > 0:
        print(f"STRICT: {report['summary']['due_missing_total']} window(s) are "
              f"{DUE_MISSING}; the data loop broke somewhere upstream", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
