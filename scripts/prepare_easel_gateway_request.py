#!/usr/bin/env python3
"""Build a bounded OpenClaw gateway request for review, without sending it.

The request contains project evidence and must remain in process memory. This
module never reads gateway credentials, opens a network connection, starts an
Agent, or grants authority. Gateway-side isolation and a task-specific grant
must be independently established before a future transport may dispatch it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "src", ROOT / "scripts"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from contentops.easel.agent_workspace import MAX_AGENT_PROMPT_BYTES, read_agent_workspace  # noqa: E402
from contentops.easel.offline_task import OfflineTaskError, _project_file, _safe_project  # noqa: E402
from prepare_easel_agent_proposal import read_saved_proposal  # noqa: E402


def prepare(*, account: str, project_slug: str, run_id: str, proposal_sha256: str,
            agent_id: str, repo_root: Path = ROOT) -> dict:
    if not isinstance(agent_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", agent_id):
        raise ValueError("gateway agent id is invalid")
    saved = read_saved_proposal(account=account, project_slug=project_slug, run_id=run_id,
                                proposal_sha256=proposal_sha256, repo_root=repo_root)
    proposal = saved["proposal"]
    if (proposal.get("service_mode") != "local_gateway" or proposal.get("timeout_seconds") != 120
            or saved.get("task_state") != "CURRENT" or saved.get("preparation") != "PREPARED"):
        raise ValueError("proposal or task is not a current local gateway preparation")
    project, _ = _safe_project(repo_root, project_slug)
    prompt_path = _project_file(project, f"work/easel-agent-workspaces/{run_id}/input/prompt.txt")
    if prompt_path.stat().st_size > MAX_AGENT_PROMPT_BYTES:
        raise ValueError("gateway prompt exceeds size limit")
    prompt_bytes = prompt_path.read_bytes()
    if len(prompt_bytes) > MAX_AGENT_PROMPT_BYTES:
        raise ValueError("gateway prompt exceeds size limit")
    prompt = prompt_bytes.decode("utf-8")
    if not prompt.strip():
        raise ValueError("gateway prompt is empty")
    manifest_path = _project_file(project, f"work/easel-agent-workspaces/{run_id}/workspace.json")
    if manifest_path.stat().st_size > 1024 * 1024:
        raise ValueError("workspace manifest exceeds size limit")
    manifest_bytes = manifest_path.read_bytes()
    if (len(manifest_bytes) > 1024 * 1024
            or hashlib.sha256(manifest_bytes).hexdigest() != proposal.get("workspace_manifest_sha256")):
        raise ValueError("workspace manifest changed after proposal")
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    if (not isinstance(manifest, dict) or not isinstance(manifest.get("input_sha256"), dict)
            or manifest["input_sha256"].get("prompt.txt") != hashlib.sha256(prompt_bytes).hexdigest()):
        raise ValueError("gateway prompt does not match the prepared task inputs")
    # Recheck after reading so an outdated or cancelled workspace is not
    # silently presented as the current task. This is not an isolation proof.
    current = read_agent_workspace(repo_root=repo_root, account=account,
                                   project_slug=project_slug, run_id=run_id)
    if current.get("input_state") != "CURRENT" or current.get("preparation") != "PREPARED":
        raise ValueError("workspace changed or was cancelled during preparation")
    params = {"agentId": agent_id, "sessionKey": f"agent:{agent_id}:contentops-{run_id}",
              "message": prompt, "deliver": False, "idempotencyKey": run_id, "timeout": 120}
    return {"method": "agent", "params": params, "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
            "proposal_sha256": proposal_sha256, "gateway_isolation": "NOT_VERIFIED",
            "authorization": "NOT_GRANTED", "execution_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--proposal-sha256", required=True)
    parser.add_argument("--agent-id", required=True)
    args = parser.parse_args()
    try:
        prepared = prepare(account=args.account, project_slug=args.project, run_id=args.run_id,
                           proposal_sha256=args.proposal_sha256, agent_id=args.agent_id)
        params = prepared["params"]
        summary = {key: value for key, value in prepared.items() if key != "params"}
        summary["params"] = {key: value for key, value in params.items() if key != "message"}
        summary["prompt_bytes"] = len(params["message"].encode("utf-8"))
    except (OfflineTaskError, OSError, UnicodeError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)[:300]}, ensure_ascii=False))
        return 4
    print(json.dumps({"status": "PREPARED_NOT_SENT", **summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
