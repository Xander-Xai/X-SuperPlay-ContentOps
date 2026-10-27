#!/usr/bin/env python3
"""Build, grade and bundle one evidence cut in a single command.

The steps are already separate tools; running them by hand is how a receipt
gets left behind at an older fingerprint. This driver runs them in order and
stops if the cut does not build:

1. compose the cut from its CutPlan / ClaimMap / asset map (`build_evidence_cut`)
2. render the cover (`build_evidence_cover`)
3. grade the cut (`cut_qc`)
4. write the immutable review bundle (`review_bundle`)

It never records a human decision and never reports production readiness.

Usage::

    python scripts/build_evidence_package.py projects/easel-1024-proof
    python scripts/build_evidence_package.py projects/easel-1024-proof --skip-build
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import build_evidence_cover  # noqa: E402
import build_evidence_cut  # noqa: E402
from contentops.media.cut_qc import qc_cut  # noqa: E402
from contentops.media.review_bundle import write_review_bundle  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("--skip-build", action="store_true",
                        help="grade and bundle the existing render")
    parser.add_argument("--skip-cover", action="store_true")
    args = parser.parse_args()

    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project

    summary = {"project": project.name}
    if not args.skip_build:
        built = build_evidence_cut.build(project)
        if built.get("status") != "OK":
            print(json.dumps({"status": "BLOCKED", "stage": "build",
                              "reason": built.get("reason")}, ensure_ascii=False))
            return 4
        summary["video"] = built["receipt_data"]["output"]

    if not args.skip_cover:
        cover = build_evidence_cover.build(project)
        if not cover.get("png"):
            print(json.dumps({"status": "BLOCKED", "stage": "cover",
                              "reason": cover.get("reason")}, ensure_ascii=False))
            return 5
        summary["cover"] = {"png": cover["png"], "audit": cover.get("audit")}

    report = qc_cut(project)
    summary["qc"] = {"overall": report["overall"],
                     "failed": [c["id"] for c in report["checks"] if not c["ok"]]}

    bundle = write_review_bundle(project)
    summary["review"] = {
        "status": bundle["status"],
        "production_ready": bundle["production_ready"],
        "fingerprint": bundle["review_bundle_fingerprint"],
        "distribution_blocked": bundle["inputs"]["distribution_blocked"],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if report["overall"] != "FAIL" else 3


if __name__ == "__main__":
    sys.exit(main())
