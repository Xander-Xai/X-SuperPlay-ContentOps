#!/usr/bin/env python3
"""Turn an approved brief into copy and a storyboard — and stop.

Usage:
    python scripts/brief_script.py projects/my-episode
    python scripts/brief_script.py projects/my-episode --dry-run
    python scripts/brief_script.py projects/my-episode --check
    python scripts/brief_script.py projects/my-episode --json

What it writes, into ``script/``: ``lines.json`` (the narration contract the cut
planner reads), ``claim-map.json`` (the repository's own claim contract),
``storyboard.json`` (shots with their capture needs) and ``master.md`` (the
readable copy). It also writes ``00_brief/script-report.json``: the mapping from
each claim to its source, which is what a reviewer checks.

It writes no captions, synthesises no narration, renders nothing and publishes
nothing. The copy review is still the gate before any of that.

Exit codes: 0 the draft was written (or is valid, with --check); 4 the brief
cannot become a script and the reason is printed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.script import ScriptBlocked, build, check, write  # noqa: E402

BLOCKED_EXIT = 4


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project")
    parser.add_argument("--dry-run", action="store_true", help="build but write nothing")
    parser.add_argument("--check", action="store_true",
                        help="validate a draft already on disk; write nothing")
    parser.add_argument("--evidence", default=None,
                        help="evidence pack (default: 00_brief/evidence-pack.json)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    project = Path(args.project)
    if not project.is_absolute():
        project = (ROOT / project).resolve()

    if args.check:
        verdict = check(project)
        payload = verdict
        code = 0 if verdict["ok"] else BLOCKED_EXIT
    else:
        try:
            draft = build(project, pack_path=Path(args.evidence) if args.evidence else None)
        except ScriptBlocked as exc:
            payload = {"status": "BLOCKED", "code": exc.code, "detail": exc.detail,
                       "project": str(project)}
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"project    {project}")
                print(f"status     BLOCKED ({exc.code})")
                print(f"detail     {exc.detail}")
            return BLOCKED_EXIT
        written = {} if args.dry_run else {name: str(path) for name, path in
                                           write(draft).items()}
        verdict = check(project) if not args.dry_run else {"ok": True, "reason": "DRY_RUN"}
        payload = {"status": "DRAFTED" if verdict.get("ok") else "DRAFT_INVALID",
                   "project": str(project), "account_id": draft.account_id,
                   "brief_id": draft.brief_id, "written": written,
                   "claims": draft.report["claims"],
                   "storyboard": draft.report["storyboard"],
                   "check": verdict,
                   "next": "run scripts/copy_review.py <project> --approve --reviewer <name>"}
        code = 0 if verdict.get("ok") else BLOCKED_EXIT

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return code

    if args.check:
        print(f"project    {project}")
        print(f"draft      {'OK' if payload['ok'] else payload['reason']}")
        for failure in payload.get("failures") or []:
            print(f"  - {failure}")
        gate = payload.get("copy_review") or {}
        print(f"copy gate  {gate.get('state')} — {gate.get('detail')}")
        return code

    print(f"project    {payload['project']}")
    print(f"status     {payload['status']} · brief {payload['brief_id']}")
    for name, path in payload["written"].items():
        print(f"  wrote {name:16} {path}")
    print(f"claims     {len(payload['claims'])} "
          f"({sum(1 for c in payload['claims'] if c['support_status'] == 'PARTIAL')} "
          f"partial, stated with a limitation)")
    print(f"storyboard {payload['storyboard']['shots']} shots · "
          f"{payload['storyboard']['duration_s']} s · "
          f"{payload['storyboard']['needs_capture']} need a capture")
    print(f"copy gate  {(payload.get('check', {}).get('copy_review') or {}).get('state')}")
    print(f"next       {payload['next']}")
    return code


if __name__ == "__main__":
    sys.exit(main())
