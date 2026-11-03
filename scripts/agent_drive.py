"""Drive ContentOps from a coding agent: plan, then run one allowlisted step.

    python scripts/agent_drive.py status
    python scripts/agent_drive.py plan --project projects/bundle-dual-line-video
    python scripts/agent_drive.py run --project projects/bundle-dual-line-video \
        --step produce-video --execute

Without ``--execute`` a run only prints the argv it would use. The driver has no
publish, credential, install or approval step; `human-review` is listed in the
plan and refused when asked to run it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.easel.driver import (  # noqa: E402
    DriverError,
    build_plan,
    detect_hosts,
    next_step,
    run_step,
)


def _fail(exc: DriverError) -> int:
    print(json.dumps({"ok": False, "error": exc.code, "detail": exc.detail},
                     ensure_ascii=False, indent=2))
    return 4


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="report which coding-agent hosts exist")
    status.add_argument("--json", action="store_true")

    plan = sub.add_parser("plan", help="print the ordered step plan for a project")
    plan.add_argument("--project", required=True)
    plan.add_argument("--json", action="store_true")

    run = sub.add_parser("run", help="resolve or execute one step")
    run.add_argument("--project", required=True)
    run.add_argument("--step", required=True)
    run.add_argument("--execute", action="store_true",
                     help="actually run the step; without this only argv is printed")
    run.add_argument("--timeout", type=int, default=1800)
    run.add_argument("--json", action="store_true")

    args = parser.parse_args()

    try:
        if args.command == "status":
            hosts = detect_hosts()
            payload = {"schema": "contentops.agent-driver/v1", "agent_hosts": hosts,
                       "any_available": any(hosts.values()),
                       "note": "A detected host is a runtime, not an authority."}
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                for name, present in hosts.items():
                    print(f"{name:10s} {'present' if present else 'absent'}")
            return 0

        if args.command == "plan":
            payload = build_plan(Path(args.project), ROOT)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"project    {payload['project']} ({payload['format']})")
                for step in payload["steps"]:
                    mark = "human" if not step["runnable"] else (
                        "ready" if step["ready"] else "pending")
                    print(f"  {step['id']:18s} {mark:8s} {' '.join(step['argv'])}")
                upcoming = next_step(payload)
                print(f"next       {upcoming['id'] if upcoming else 'none'}")
            return 0

        receipt = run_step(Path(args.project), args.step, root=ROOT,
                           execute=args.execute, timeout=args.timeout)
        if args.json:
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
        elif receipt.get("executed"):
            print(f"step       {receipt['step']}")
            print(f"status     {receipt['status']} (returncode {receipt['returncode']})")
            print(f"receipt    {receipt['receipt']}")
        else:
            print(f"step       {receipt['step']}")
            print(f"argv       {' '.join(receipt['argv'])}")
            print("executed   false (pass --execute to run it)")
        return 0 if not receipt.get("executed") or receipt["status"] == "OK" else 1
    except DriverError as exc:
        return _fail(exc)


if __name__ == "__main__":
    raise SystemExit(main())
