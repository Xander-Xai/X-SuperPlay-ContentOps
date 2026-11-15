#!/usr/bin/env python3
"""Collect an existing candidate result into project drafts and receipts.

Reads UTF-8 JSON on stdin with account, project, run_id and exit_code. The only
input file is the selected workspace's output/agent-result.json. This does not
execute a process, verify its origin or authorize production or publication.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.easel.agent_result import AgentResultError, collect_workspace_result  # noqa: E402
from contentops.easel.offline_task import OfflineTaskError  # noqa: E402


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(32769)
        if len(raw) > 32768:
            raise ValueError("request exceeds 32 KiB")
        request = json.loads(raw.decode("utf-8"))
        if (not isinstance(request, dict) or set(request) != {"account", "project", "run_id", "exit_code"}
                or type(request["exit_code"]) is not int):
            raise ValueError("request requires account, project, run_id and integer exit_code")
        result = collect_workspace_result(repo_root=ROOT, account=request["account"],
                                          project_slug=request["project"], run_id=request["run_id"],
                                          exit_code=request["exit_code"])
    except (OSError, UnicodeDecodeError, ValueError, TypeError, OfflineTaskError, AgentResultError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 4
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
