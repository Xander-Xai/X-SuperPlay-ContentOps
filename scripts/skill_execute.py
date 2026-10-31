#!/usr/bin/env python3
"""Execute one media-use operation through the managed authorization gate.

Chain: Router -> Authorization -> Existing adapter -> Receipt.

Every refusal is printed as a machine-readable receipt and exits non-zero. The
adapter's own gates (runtime lock, offline-only, no paid path) still run; a grant
authorizes the attempt, it never replaces a check.

Only read-only operations are exposed here. ``resolve``, ``adopt`` and ``ingest``
write into a project, so exposing them needs a separate decision: the grant
vocabulary must name those verbs and their effects first.

Usage
-----
```
python scripts/skill_execute.py projects/m5-media-use --operation status
python scripts/skill_execute.py projects/m5-media-use --operation doctor --json
```
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import skill_route  # noqa: E402
from contentops.media.media_use_adapter import MediaUseAdapter  # noqa: E402
from contentops.skills.authorization import ExecutionRequest  # noqa: E402
from contentops.skills.execution_gate import execute  # noqa: E402

SKILL_ID = "media-use"
ALLOWED_OPERATIONS = ("status", "doctor")
OWNER_ENV = "CONTENTOPS_OWNER_IDENTITIES"


def _owner_identities() -> list[str]:
    raw = os.environ.get(OWNER_ENV, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _operation_executor(operation: str):
    def run(_operation: str, _request: ExecutionRequest) -> Dict[str, Any]:
        adapter = MediaUseAdapter()
        if operation == "status":
            status = adapter.status(refresh=True)
            return {"ok": bool(status.usable), "receipt": status.as_dict()}
        if operation == "doctor":
            doctor = adapter.doctor()
            return {"ok": True, "receipt": doctor.as_dict()}
        return {"ok": False, "error": f"unsupported operation {operation!r}"}

    return run


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="project directory under projects/")
    parser.add_argument("--operation", default="status", choices=ALLOWED_OPERATIONS)
    parser.add_argument("--account", default="*")
    parser.add_argument("--pipeline", default="M5")
    parser.add_argument("--stage", default="media_use")
    parser.add_argument("--subject", default="owner")
    parser.add_argument("--request-id", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    project = Path(args.project)
    if not project.is_dir():
        print(f"project not found: {project}", file=sys.stderr)
        return 2

    entry = next((item for item in skill_route.registry_entries()
                  if item.get("id") == SKILL_ID), None)
    account = None if args.account == "*" else args.account
    verdict = skill_route.resolve_capability(
        SKILL_ID, account=account, pipeline=args.pipeline, stage=args.stage)
    request_id = args.request_id or f"{project.name}-{args.operation}"

    result = execute(
        ExecutionRequest(
            request_id=request_id,
            skill_id=SKILL_ID,
            skill_version=str((entry or {}).get("source", {}).get("version") or ""),
            account=args.account,
            pipeline=args.pipeline,
            stage=args.stage,
            operations=(args.operation,),
            subject=args.subject,
        ),
        verdict=verdict,
        registry_entry=entry,
        project_dir=project,
        owner_identities=_owner_identities(),
        executor=_operation_executor(args.operation),
    )

    payload = result.as_dict()
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"decision   {result.decision.state}/{result.decision.reason}")
        print(f"detail     {result.decision.detail}")
        if result.receipt_path:
            print(f"receipt    {result.receipt_path}")
        print(f"execution  {result.execution.get('state')}")
    return 0 if result.executed else 1


if __name__ == "__main__":
    raise SystemExit(main())
