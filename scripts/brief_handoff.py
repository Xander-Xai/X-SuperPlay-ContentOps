#!/usr/bin/env python3
"""Carry an approved brief into the pipeline, and refuse if it is not ready.

This is the adapter between the content router and the existing production
scripts. It does two things and nothing else:

1. It re-derives the approval digest from the brief the project carries. A
   brief that changed after it was approved, a brief with no approval, or a
   brief whose evidence forecast is DEGRADED is refused by name.
2. It writes ``00_brief/handoff.json`` — the record the next stage reads —
   together with the account's pipeline from ``scripts/account_route.py``.

It does not write a script or a storyboard. Those come from a person and the
copy review, which remains the gate before any narration is synthesised.

Usage:
    python scripts/brief_handoff.py projects/e2e-hotspot
    python scripts/brief_handoff.py projects/e2e-hotspot --dry-run
    python scripts/brief_handoff.py projects/e2e-hotspot --json

Exit codes: 0 the handoff record was written (or would be, with --dry-run);
4 the brief is not ready, with the reason in the output.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.routing import handoff  # noqa: E402

BLOCKED_EXIT = 4


def _route(project: Path) -> dict:
    """The account's pipeline, or a named refusal rather than a guess."""
    try:
        import account_route
    except Exception as exc:  # noqa: BLE001 - reported, not hidden
        return {"resolved": False, "reason": f"account_route could not be loaded: {exc}"}
    try:
        return {"resolved": True, **account_route.resolve(project)}
    except account_route.RouteBlocked as exc:
        return {"resolved": False, "code": exc.code, "reason": str(exc)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project")
    parser.add_argument("--dry-run", action="store_true",
                        help="check and report without writing handoff.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    project = Path(args.project)
    package = handoff.read_brief(project)
    verdict = handoff.check(package)
    route = _route(project) if package is not None else {"resolved": False}

    outcome = {
        "project": str(project),
        "status": "READY" if verdict["ok"] else "BLOCKED",
        "reason": verdict["reason"],
        "detail": verdict["detail"],
        "content_digest": verdict.get("content_digest"),
        "dry_run": bool(args.dry_run),
        "pipeline_resolved": bool(route.get("resolved")),
    }

    if verdict["ok"]:
        record = handoff.handoff_record(project, package, route)
        if args.dry_run:
            outcome["would_write"] = str(project / handoff.BRIEF_DIR / handoff.HANDOFF_FILE)
        else:
            outcome["handoff"] = str(handoff.write_handoff(project, record))
        script = handoff.script_state(project)
        outcome["script_ready"] = script["ready"]
        outcome["script_problems"] = script["problems"]
        outcome["next"] = (
            "run scripts/copy_review.py before any narration is synthesised"
            if script["ready"] else
            "write script/lines.json and script/assets.json, then run "
            "scripts/copy_review.py before any narration is synthesised")

    if args.json:
        print(json.dumps(outcome, ensure_ascii=False, indent=2))
    else:
        print(f"project    {outcome['project']}")
        print(f"status     {outcome['status']} ({outcome['reason']})")
        print(f"detail     {outcome['detail']}")
        if outcome.get("handoff"):
            print(f"handoff    {outcome['handoff']}")
        if outcome.get("would_write"):
            print(f"would write {outcome['would_write']} (dry run)")
        if not route.get("resolved"):
            print(f"pipeline   unresolved: {route.get('reason')}")
        if "script_ready" in outcome:
            print(f"script     {'ready' if outcome['script_ready'] else 'not written'}")
            for problem in outcome.get("script_problems") or []:
                print(f"  - {problem}")
        if outcome.get("next"):
            print(f"next       {outcome['next']}")
    return 0 if verdict["ok"] else BLOCKED_EXIT


if __name__ == "__main__":
    sys.exit(main())
