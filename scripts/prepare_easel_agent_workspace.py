#!/usr/bin/env python3
"""Prepare project-local Agent inputs; never run an Agent or contact a provider.

Read one UTF-8 JSON object from stdin with account, project, brief and idempotency_key fields.
The resulting workspace is explicitly unauthorized until a separate isolated
executor and the required grant exist.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.easel.agent_workspace import prepare_agent_workspace  # noqa: E402
from contentops.easel.offline_task import OfflineTaskError  # noqa: E402


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(32769)
        if len(raw) > 32768:
            raise ValueError("request exceeds 32 KiB")
        request = json.loads(raw.decode("utf-8"))
        if not isinstance(request, dict) or set(request) != {"account", "project", "brief", "idempotency_key"}:
            raise ValueError("request requires account, project, brief and idempotency_key")
        result = prepare_agent_workspace(repo_root=ROOT, account=request["account"],
                                         project_slug=request["project"], brief=request["brief"],
                                         idempotency_key=request["idempotency_key"])
    except (ValueError, UnicodeDecodeError, OfflineTaskError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 4
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
