#!/usr/bin/env python3
"""Check or record a human review of a project's final copy.

Examples:
    python scripts/copy_review.py projects/my-episode --check
    python scripts/copy_review.py projects/my-episode --approve \
        --reviewer "Founder" --opinion "Reviewed the final narration" --confirm
    python scripts/copy_review.py projects/my-episode --request-changes \
        --reviewer "Founder" --opinion "Add a source citation" --confirm

A decision is bound to the current copy fingerprint. This command never edits
copy, approves an unchanged or stale fingerprint on behalf of another caller,
or runs production or publication steps.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.workflow import copy_review  # noqa: E402


def _project_path(value: str) -> Path:
    supplied = Path(value)
    candidate = supplied if supplied.is_absolute() else ROOT / supplied
    project = candidate.resolve()
    projects_root = (ROOT / "projects").resolve()
    try:
        relative_project = project.relative_to(projects_root)
    except ValueError:
        raise ValueError("PROJECT_OUTSIDE_REPO: project must be under projects/<slug>") from None
    # checkout_guard exempts only projects/_local/ on a dirty main checkout,
    # so that sandbox must be able to sign its own copy review. Allow exactly
    # that one two-level shape; refuse any other nesting.
    local_sandbox = (len(relative_project.parts) == 2
                     and relative_project.parts[0] == "_local")
    if not local_sandbox and len(relative_project.parts) != 1:
        raise ValueError(
            "PROJECT_INVALID: name projects/<slug> or projects/_local/<slug>")
    if not project.is_dir():
        raise ValueError("PROJECT_MISSING: project directory does not exist")
    return project


def _emit(payload: Dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"project  {payload.get('project', '-')}")
    print(f"action   {payload.get('action', '-')}")
    print(f"state    {(payload.get('gate') or {}).get('state', payload.get('state', '-'))}")
    gate = payload.get("gate") or {}
    if gate.get("detail"):
        print(f"detail   {gate['detail']}")
    if gate.get("remedy"):
        print(f"next     {gate['remedy']}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", help="project directory under projects/<slug>")
    parser.add_argument("--check", action="store_true",
                        help="check the current fingerprint and review receipt (default)")
    decision = parser.add_mutually_exclusive_group()
    decision.add_argument("--approve", action="store_true",
                          help="record approval of the current copy fingerprint")
    decision.add_argument("--request-changes", action="store_true",
                          help="record that the copy needs changes")
    parser.add_argument("--reviewer", help="name of the human reviewer")
    parser.add_argument("--opinion", help="written review rationale")
    parser.add_argument("--confirm", action="store_true",
                        help="confirm this human review decision")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    has_decision = args.approve or args.request_changes
    if args.check and has_decision:
        parser.error("--check cannot be combined with a review decision")
    if has_decision and not args.confirm:
        parser.error("--approve/--request-changes requires explicit --confirm")
    if has_decision and (not args.reviewer or not args.reviewer.strip()):
        parser.error("a review decision requires --reviewer with a non-empty name")
    if has_decision and (not args.opinion or not args.opinion.strip()):
        parser.error("a review decision requires --opinion with a written rationale")
    if not has_decision and (args.reviewer or args.opinion or args.confirm):
        parser.error("--reviewer, --opinion and --confirm require a decision flag")

    try:
        project = _project_path(args.project)
        action = "CHECK"
        if has_decision:
            # Research-then-copy: a signed pre-copy research gate must be
            # current before any copy decision can be recorded.
            from contentops.workflow import preresearch

            research = preresearch.check(project)
            if not research["ok"]:
                raise ValueError(
                    f"PRECOPY_RESEARCH_REQUIRED: {research['state']}: {research['detail']}")
            status_value = "APPROVED" if args.approve else "CHANGES_REQUESTED"
            reviewed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
                "+00:00", "Z")
            copy_review.decide(
                project,
                status_value=status_value,
                reviewer=args.reviewer,
                opinion=args.opinion,
                reviewed_at=reviewed_at,
            )
            action = "APPROVAL_RECORDED" if args.approve else "CHANGES_REQUESTED_RECORDED"
        gate = copy_review.status(project)
    except (OSError, ValueError) as exc:
        message = str(exc)
        code = message.split(":", 1)[0] if ":" in message else "COPY_REVIEW_BLOCKED"
        payload = {"project": args.project, "action": "BLOCKED", "state": "BLOCKED",
                   "code": code, "detail": message}
        _emit(payload, args.json)
        return 1

    # Resolve ROOT too: Windows may return a long-name project path while the
    # caller supplied the same temp directory through its 8.3 short alias.
    payload = {"project": project.relative_to(ROOT.resolve()).as_posix(), "action": action,
               "state": gate["state"], "ok": gate["ok"], "gate": gate}
    _emit(payload, args.json)
    if has_decision:
        return 0
    return 0 if gate["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
