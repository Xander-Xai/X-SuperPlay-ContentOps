#!/usr/bin/env python3
"""Convert a brief's source-bound draft into the M5 production contract.

Usage:
    python scripts/brief_to_m5.py projects/my-episode
    python scripts/brief_to_m5.py projects/my-episode --unapproved-preview
    python scripts/brief_to_m5.py projects/my-episode --dry-run
    python scripts/brief_to_m5.py projects/my-episode --check
    python scripts/brief_to_m5.py projects/my-episode --json

Writes ``script/script.json``, ``script/claims.json``, ``sources/source-refs.json``
and ``receipts/brief-to-m5.json``. It converts; it does not write narration,
approve a claim, register an asset or render anything. The copy review must
already be approved, every placement must have an asset, and every factual
claim must carry an evidence item whose permission and quote verify.

Exit codes: 0 converted (or --check found the files current); 4 the draft
cannot reach M5 and the blockers are printed. ``--unapproved-preview`` only
prepares local preview input; it does not create a brief or copy approval.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.script.m5_bridge import BridgeBlocked, build, check, write  # noqa: E402

BLOCKED_EXIT = 4


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project")
    parser.add_argument("--dry-run", action="store_true", help="convert but write nothing")
    parser.add_argument("--check", action="store_true",
                        help="validate the files already on disk; write nothing")
    parser.add_argument("--unapproved-preview", action="store_true",
                        help="allow an unapproved brief for local draft preview only; grants no copy or publication approval")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    project = Path(args.project)
    try:
        if args.check:
            result = check(project, repo_root=ROOT,
                           allow_unapproved_preview=args.unapproved_preview)
            if not result["ok"]:
                if args.json:
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                else:
                    print("BRIDGE_STALE")
                    for problem in result["problems"]:
                        print(f"  - {problem}")
                return BLOCKED_EXIT
            payload = {"state": "CURRENT", **result["counts"]}
            print(json.dumps(payload, ensure_ascii=False) if args.json
                  else f"CURRENT: {result['counts']['lines']} lines, "
                       f"{result['counts']['claims']} claims")
            return 0

        result = build(project, repo_root=ROOT,
                       allow_unapproved_preview=args.unapproved_preview)
        written = {} if args.dry_run else write(result, project)
        payload = {
            "state": "DRY_RUN" if args.dry_run else "CONVERTED_FOR_M5",
            "preview_only": bool(result.get("preview_only")),
            **result["counts"],
            "written": sorted(written),
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"{payload['state']}: {payload['lines']} lines, "
                  f"{payload['claims']} claims, {payload['source_refs']} source refs")
            for relative in payload["written"]:
                print(f"  wrote {relative}")
        return 0
    except BridgeBlocked as blocked:
        payload = {"state": blocked.code, "detail": blocked.detail,
                   "blockers": blocked.blockers}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"{blocked.code}: {blocked.detail}")
            for blocker in blocked.blockers:
                print(f"  - {blocker}")
        return BLOCKED_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
