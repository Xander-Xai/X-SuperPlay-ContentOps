#!/usr/bin/env python3
"""Import creator-exported metrics and write a review receipt. No network.

Usage
-----
    python scripts/metrics_review.py projects/my-video
    python scripts/metrics_review.py projects/my-video --exports ~/Downloads/yt-export

The operator puts the platform's own export (plus a small JSON wrapper) under
``<project>/metrics/exports/``. This script validates it, imports what is there,
records what was refused, and writes ``receipts/metrics-review.json``.

It never logs in, never scrapes, never estimates a missing figure and never
touches the script, the QC verdict or ``production_ready``.

Exit codes
----------
0  every export imported
2  no export directory
3  at least one export was refused (the valid ones were still imported)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT / "src", ROOT / "scripts"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from contentops.manual_metrics import write_review  # noqa: E402


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def main() -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(
        description="Import creator-exported metrics into a review receipt. "
                    "Offline: no login, no scraping, no estimation.")
    parser.add_argument("project", help="project directory, e.g. projects/my-video")
    parser.add_argument("--exports", default=None,
                        help="export directory (default: <project>/metrics/exports)")
    args = parser.parse_args()

    project = Path(args.project)
    if not project.is_absolute():
        project = (ROOT / args.project).resolve()
    if not project.is_dir():
        print(json.dumps({"status": "BLOCKED", "reason": f"no such project: {project}"},
                         ensure_ascii=False))
        return 2

    exports = Path(args.exports) if args.exports else project / "metrics" / "exports"
    if not exports.is_dir():
        print(json.dumps({
            "status": "BLOCKED",
            "reason": f"no export directory at {exports}; drop the platform export there first",
            "imported": 0, "rejected": 0,
        }, ensure_ascii=False))
        return 2

    payload = write_review(project, export_dir=exports)
    print(json.dumps({
        "status": "OK" if not payload["rejected"] else "PARTIAL",
        "receipt": "project://receipts/metrics-review.json",
        "imported": len(payload["imported"]),
        "rejected": payload["rejected"],
        "observations": payload["observations"],
        "next_variable": payload["next_variable"],
        "network_used": False,
        "production_ready": False,
    }, ensure_ascii=False, indent=2))
    return 0 if not payload["rejected"] else 3


if __name__ == "__main__":
    sys.exit(main())
