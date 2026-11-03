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
from contentops.workflow import copy_review  # noqa: E402
from contentops.workflow import replication  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("--skip-build", action="store_true",
                        help="grade and bundle the existing render")
    parser.add_argument("--skip-cover", action="store_true")
    parser.add_argument("--variants", action="store_true",
                        help="also derive the other platforms' frames from this master")
    args = parser.parse_args()

    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project

    summary = {"project": project.name}
    if not args.skip_build:
        try:
            built = build_evidence_cut.build(project)
        except copy_review.CopyReviewRequired as exc:
            print(json.dumps({"status": "BLOCKED", "stage": "copy_review",
                              "reason": exc.reason, "remedy": exc.remedy}, ensure_ascii=False))
            return 4
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

    # A project that claimed a reference must still honour the plan derived from
    # it. Evidence projects write their storyboard to work/, not script/.
    drift = replication.stage_gate(project, storyboard=project / "work" / "storyboard.json")
    if drift:
        summary["replication"] = {"status": "FAIL", "failed": drift}
    elif (project / "script" / "replication-plan.json").is_file():
        summary["replication"] = {"status": "PASS"}

    bundle = write_review_bundle(project)
    summary["review"] = {
        "status": bundle["status"],
        "production_ready": bundle["production_ready"],
        "fingerprint": bundle["review_bundle_fingerprint"],
        "distribution_blocked": bundle["inputs"]["distribution_blocked"],
    }

    # Deriving the other platforms is opt-in, and only after this cut has its own
    # verdict: a derivative inherits the master's verdict, so deriving a FAIL is
    # the same failure in more shapes.
    if args.variants:
        if report["overall"] == "FAIL":
            summary["variants"] = {"status": "SKIPPED",
                                   "reason": "the master's own QC failed"}
        else:
            import derive_variants  # noqa: E402 - sibling script, same directory

            try:
                derived = derive_variants.derive(project)
                summary["variants"] = {
                    "status": "DERIVED",
                    "variants": derived["variants"],
                    "covers": derived["covers"],
                }
            except SystemExit:
                summary["variants"] = {"status": "BLOCKED",
                                       "reason": "derive_variants refused; see its output"}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    failed = report["overall"] == "FAIL" or bool(drift)
    return 3 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
