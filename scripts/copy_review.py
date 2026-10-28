#!/usr/bin/env python3
"""Show or record the human review that unlocks the copy gate.

A project's pipeline stops after the copy is written. It continues only when a
person has read the copy and recorded a decision against it. This CLI is how that
decision gets written; the producers call the same module and refuse to run until
the decision exists and still matches the copy.

Usage:
    python scripts/copy_review.py projects/x-superplay-1024
    python scripts/copy_review.py projects/x-superplay-1024 \
        --approve --reviewer Founder --opinion "钩子够硬，第二单元删掉一句"
    python scripts/copy_review.py projects/x-superplay-1024 \
        --request-changes --reviewer Founder --opinion "开场太慢，重写前三句"
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from contentops.workflow import copy_review  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project")
    decision = parser.add_mutually_exclusive_group()
    decision.add_argument("--approve", action="store_true")
    decision.add_argument("--request-changes", action="store_true")
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--opinion", default="")
    parser.add_argument("--show", action="store_true", help="print the gate and exit")
    args = parser.parse_args()

    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project
    project = project.resolve()

    if args.show or not (args.approve or args.request_changes):
        gate = copy_review.status(project)
        print(json.dumps(gate, ensure_ascii=False, indent=2))
        return 0 if gate["ok"] else 4

    status_value = "APPROVED" if args.approve else "CHANGES_REQUESTED"
    reviewed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    try:
        record = copy_review.decide(project, status_value=status_value,
                                    reviewer=args.reviewer, opinion=args.opinion,
                                    reviewed_at=reviewed_at)
    except ValueError as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc)}, ensure_ascii=False))
        return 2

    print(json.dumps({"status": "RECORDED", "record": record,
                      "path": copy_review.RECORD.as_posix()}, ensure_ascii=False, indent=2))
    return 0 if status_value == "APPROVED" else 0


if __name__ == "__main__":
    sys.exit(main())
