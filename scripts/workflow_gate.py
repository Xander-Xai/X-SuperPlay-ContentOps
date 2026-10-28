#!/usr/bin/env python3
"""CLI for the ordered production contract.

    python scripts/workflow_gate.py init      --project projects/<slug> --slug <slug>
    python scripts/workflow_gate.py status    --project projects/<slug>
    python scripts/workflow_gate.py check     --project projects/<slug> --stage brief
    python scripts/workflow_gate.py approve   --project projects/<slug> --stage brief \
                                              --reviewer "Founder" --confirm
    python scripts/workflow_gate.py reconcile --project projects/<slug>

Exit codes: 0 = the requested operation succeeded, 1 = the gate refused or the
check failed, 2 = usage error. There is no --force flag; a refused gate is the
answer, not an obstacle.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.workflow import (  # noqa: E402
    CONTRACT_ID,
    WorkflowError,
    approve_stage,
    check_stage,
    current_stage,
    load_workflow,
    new_workflow,
    policy_lock,
    reconcile,
    save_workflow,
)
from contentops.workflow.validators import validators_for  # noqa: E402

WORKFLOW_FILE = "workflow.json"


def _resolve_project(value: str) -> Path:
    path = Path(value).resolve()
    if not path.is_dir():
        raise WorkflowError("PROJECT_MISSING", f"{path} is not a directory")
    return path


def _workflow_path(project: Path) -> Path:
    return project / WORKFLOW_FILE


def _load(project: Path) -> dict:
    return load_workflow(_workflow_path(project))


def _emit(value: object, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return
    if isinstance(value, dict) and "stages" in value:
        _print_status(value)
        return
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _print_status(document: dict) -> None:
    lock = policy_lock(document)
    print(f"contract : {lock['contract']}")
    print(f"slug     : {document.get('slug')}")
    print(f"account  : {document.get('account') or '-'}")
    print(f"current  : {current_stage(document) or 'complete'}")
    print()
    print(f"{'stage':<12} {'status':<17} {'stale':<6} reviewer")
    print("-" * 58)
    for stage in document.get("stages", []):
        approval = stage.get("approval") or {}
        print(f"{stage['id']:<12} {stage['status']:<17} "
              f"{('yes' if stage.get('stale') else 'no'):<6} "
              f"{approval.get('reviewer', '-')}")
        if stage.get("stale_reason"):
            print(f"  ! {stage['stale_reason']}")


def cmd_init(args: argparse.Namespace) -> int:
    project = _resolve_project(args.project)
    target = _workflow_path(project)
    if target.exists() and not args.replace:
        print(f"refusing to overwrite {target}; pass --replace to recreate", file=sys.stderr)
        return 1
    document = new_workflow(args.slug or project.name, args.account or "", CONTRACT_ID)
    save_workflow(target, document)
    print(f"created {target}")
    print(f"next: python scripts/workflow_gate.py check --project {project} --stage brief")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    project = _resolve_project(args.project)
    document = _load(project)
    reconcile(project, document)
    _emit(document, args.json)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    project = _resolve_project(args.project)
    document = _load(project)
    result = check_stage(project, document, args.stage,
                         validators=validators_for(args.stage))
    save_workflow(_workflow_path(project), document)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        state = "READY_FOR_REVIEW" if result["ok"] else "BLOCKED"
        print(f"[{state}] {args.stage}")
        for message in result["errors"]:
            print(f"  - {message}")
        for message in result["warnings"]:
            print(f"  ~ {message}")
        if result["ok"]:
            print(f"approve with: --stage {args.stage} --reviewer <name> --confirm")
    return 0 if result["ok"] else 1


def cmd_approve(args: argparse.Namespace) -> int:
    project = _resolve_project(args.project)
    document = _load(project)
    result = approve_stage(project, document, args.stage, args.reviewer,
                           confirm=args.confirm, note=args.note or "")
    save_workflow(_workflow_path(project), document)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[APPROVED] {args.stage} by {result['reviewer']}")
        print(f"next: {current_stage(document) or 'complete'}")
    return 0


def cmd_reconcile(args: argparse.Namespace) -> int:
    project = _resolve_project(args.project)
    document = _load(project)
    changes = reconcile(project, document)
    save_workflow(_workflow_path(project), document)
    if args.json:
        print(json.dumps(changes, ensure_ascii=False, indent=2))
    else:
        if not changes:
            print("no staleness changes")
        for change in changes:
            print(f"{change['stage']}: stale={change['stale']} {change['reason']}".strip())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ordered production contract gate")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create workflow.json")
    init.add_argument("--project", required=True)
    init.add_argument("--slug", default="")
    init.add_argument("--account", default="")
    init.add_argument("--replace", action="store_true")
    init.set_defaults(func=cmd_init)

    status = sub.add_parser("status", help="show stage states")
    status.add_argument("--project", required=True)
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    check = sub.add_parser("check", help="deterministic stage check")
    check.add_argument("--project", required=True)
    check.add_argument("--stage", required=True)
    check.add_argument("--json", action="store_true")
    check.set_defaults(func=cmd_check)

    approve = sub.add_parser("approve", help="record a named approval")
    approve.add_argument("--project", required=True)
    approve.add_argument("--stage", required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--note", default="")
    approve.add_argument("--confirm", action="store_true")
    approve.add_argument("--json", action="store_true")
    approve.set_defaults(func=cmd_approve)

    rec = sub.add_parser("reconcile", help="recompute staleness")
    rec.add_argument("--project", required=True)
    rec.add_argument("--json", action="store_true")
    rec.set_defaults(func=cmd_reconcile)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    print(
        "note: the ordered production contract is declared but not wired into any "
        "producer; the enforced human gate is the copy review "
        "(python scripts/copy_review.py <project>).",
        file=sys.stderr,
    )
    try:
        return args.func(args)
    except WorkflowError as exc:
        print(f"[{exc.code}] {exc.detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
