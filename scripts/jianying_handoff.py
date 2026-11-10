#!/usr/bin/env python3
"""Write a 剪映 draft from an accepted project, for a human to finish.

This is a handoff command, not a render command. It reads the project's accepted
``receipts/media-manifest.json`` timeline and its subtitle cues, writes one
JianYing draft folder under the project, and records a receipt. It never exports,
never opens JianYing, and never claims the video is ready or publishable.

Usage:
  python scripts/jianying_handoff.py --project projects/<slug>
  python scripts/jianying_handoff.py --project projects/<slug> --name my-cut
  python scripts/jianying_handoff.py --project projects/<slug> --replace

Exit codes:
  0  draft written, receipt recorded
  4  refused (see the receipt's refusal code), nothing was written
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

from contentops.media.jianying_handoff import (  # noqa: E402
    HandoffError,
    PINNED_VERSION,
    build_handoff,
    write_receipt,
)


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", required=True, help="project directory")
    parser.add_argument("--name", default=None,
                        help="draft name; defaults to <project>-handoff")
    parser.add_argument("--drafts-dir", default=None,
                        help="drafts root; must stay inside the project "
                             "(default work/jianying/drafts)")
    parser.add_argument("--subtitles", default=None,
                        help="subtitle file; defaults to the path receipts/subtitles.json names")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--replace", action="store_true",
                        help="overwrite an existing draft of the same name")
    parser.add_argument("--no-receipt", action="store_true",
                        help="skip writing receipts/jianying-handoff.json (the draft is still written)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    project = Path(args.project)
    if not project.is_absolute():
        project = (ROOT / project).resolve()
    try:
        receipt = build_handoff(
            project,
            drafts_dir=Path(args.drafts_dir) if args.drafts_dir else None,
            draft_name=args.name,
            fps=args.fps,
            replace=args.replace,
            subtitles=Path(args.subtitles) if args.subtitles else None,
        )
    except HandoffError as exc:
        print(json.dumps({"state": "REFUSED", "code": exc.code,
                          "reason": exc.detail}, ensure_ascii=False), file=sys.stderr)
        return 4

    path = None
    if not args.no_receipt:
        path = write_receipt(project, receipt)
        receipt = dict(receipt, receipt=path.relative_to(project).as_posix())

    if args.json:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    else:
        print(f"draft            {receipt['draft']['path']}")
        print(f"library          {receipt['library']['package']} "
              f"{receipt['library']['version']} ({receipt['library']['license']})")
        print(f"shots / cues     {len(receipt['inputs']['placements'])} / "
              f"{receipt['inputs']['cues']}  ({receipt['inputs']['duration_s']} s)")
        print(f"export           none — open the draft in 剪映 and export by hand")
        print(f"production_ready {receipt['production_ready']}  "
              f"({receipt['human_review']})")
        if path:
            print(f"receipt          {path.relative_to(project).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
