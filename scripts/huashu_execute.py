#!/usr/bin/env python3
"""Check whether one Huashu Motion operation would be authorized. Never executes.

This is the operator-facing entry point for the managed execution gate. It
answers one question: *if this project held a matching approval, would the
gate authorize this exact operation?* It verifies the pinned runtime, loads the
project's own approval record, evaluates the request against both, and prints
the verdict.

It deliberately does not run anything:

* the upstream invocation is not configured in this repository, so there is no
  command line to build;
* the use is not consumed, so a check costs the Owner nothing;
* no process is started, no browser is driven, no frame is rendered.

Usage
-----
```
set CONTENTOPS_OWNER_IDENTITIES=owner
set CONTENTOPS_EXECUTION_SUBJECT=owner
python scripts/huashu_execute.py check projects/huashu-motion-sample \
    --operation render --account x-superplay-1024
```

The identity is declared by the environment, not authenticated. Unset
variables mean nothing is trusted.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media import huashu_motion  # noqa: E402
from contentops.skills import huashu_execution  # noqa: E402
from contentops.skills.authorization import evaluate  # noqa: E402
from contentops.skills.grant_source import GrantSourceError, load_grant  # noqa: E402

OWNER_ENV = "CONTENTOPS_OWNER_IDENTITIES"
SUBJECT_ENV = "CONTENTOPS_EXECUTION_SUBJECT"


def _owner_identities() -> list[str]:
    raw = os.environ.get(OWNER_ENV, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _execution_subject() -> str:
    return os.environ.get(SUBJECT_ENV, "").strip()


def _git_probe(root: Path, *args: str) -> tuple[int, str]:
    from process_utils import hidden_run

    result = hidden_run(["git", "-C", str(root), *args], timeout=30)
    return result.returncode, (result.stdout or "").strip()


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="report whether this operation would be authorized")
    check.add_argument("project", help="project directory under projects/")
    check.add_argument("--operation", default="render",
                       choices=sorted(huashu_execution.ALLOWED_OPERATIONS))
    check.add_argument("--account", required=True,
                       help="one concrete business account; a wildcard is refused")
    check.add_argument("--pipeline", default="M5")
    check.add_argument("--stage", default="motion")
    check.add_argument("--root", type=Path, default=huashu_motion.DEFAULT_RUNTIME)
    check.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.command != "check":
        print("only the check command exists; this entry point never executes",
              file=sys.stderr)
        return 2
    project = Path(args.project)
    if not project.is_dir():
        print(f"project not found: {project}", file=sys.stderr)
        return 2
    if args.account.strip() in ("", "*"):
        print("--account must name one concrete account; a wildcard would widen "
              "the approval to accounts nobody approved", file=sys.stderr)
        return 2

    request = huashu_execution.build_request(
        request_id=f"{project.name}-{args.operation}-check",
        operation=args.operation,
        account=args.account,
        pipeline=args.pipeline,
        stage=args.stage,
        subject=_execution_subject(),
    )
    runtime = huashu_motion.verify_runtime(args.root, git_probe=_git_probe)

    grant = None
    grant_error = None
    try:
        grant = load_grant(project, owner_identities=_owner_identities())
    except GrantSourceError as exc:
        grant_error = f"{exc.code}: {exc.detail}"

    decision = evaluate(
        request,
        verdict=huashu_execution.build_verdict(runtime),
        registry_entry=huashu_execution.build_registry_entry(),
        grant=grant,
    )
    payload = {
        "schema": "contentops.huashu-motion-authorization-check/v1",
        "project": project.name,
        "operation": args.operation,
        "runtime": runtime,
        "grant_loaded": grant is not None,
        "grant_error": grant_error,
        "decision": decision.as_dict(),
        "executed": False,
        "runner_configured": False,
        "note": "This check consumes no approval use and starts no process. A "
                "real execution needs the Owner's approval record plus a "
                "configured upstream invocation; see "
                "docs/governance/HUASHU-EXECUTION-AUTHORIZATION-REQUEST.md.",
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"runtime   {runtime.get('status')} {runtime.get('reason', '')}".rstrip())
        print(f"grant     {'loaded' if grant is not None else (grant_error or 'absent')}")
        print(f"decision  {decision.state}/{decision.reason}")
        print(f"detail    {decision.detail}")
        print("executed  no (this command never runs the engine)")
    return 0 if decision.state == "AUTHORIZED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
