#!/usr/bin/env python3
"""Inspect the existing execution approval's binding to one Easel proposal.

This is a read-only preparation step. A matching binding does not authorize a
run: the managed execution gate must still evaluate and atomically consume
the grant, and the Windows isolation boundary must be proven first.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.easel.agent_workspace import AGENT_EXECUTION_SCOPE, read_agent_workspace  # noqa: E402
from contentops.easel.offline_task import OfflineTaskError, _project_file, _safe_project  # noqa: E402
from contentops.skills.grant_source import (GrantSourceError, consumed_uses, load_grant,
                                             record_digest)  # noqa: E402
from contentops.skills.authorization import ExecutionRequest, evaluate  # noqa: E402


def inspect(*, account: str, project_slug: str, run_id: str, proposal_sha256: str,
            owner_identities: list[str], repo_root: Path = ROOT) -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", proposal_sha256):
        raise ValueError("proposal digest must be a lowercase SHA-256")
    project, project_rel = _safe_project(repo_root, project_slug)
    state = read_agent_workspace(repo_root=repo_root, account=account,
                                 project_slug=project_slug, run_id=run_id)
    if state.get("input_state") != "CURRENT" or state.get("preparation") != "PREPARED":
        raise ValueError("prepared task is stale, unsafe or cancelled")
    relative = f"work/easel-agent-proposals/easel-agent-proposal-{run_id}-{proposal_sha256}.json"
    proposal_path = _project_file(project, relative)
    if proposal_path.stat().st_size > 32768:
        raise ValueError("proposal is too large")
    payload = json.loads(proposal_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("proposal must be an object")
    body = dict(payload)
    declared = body.pop("proposal_sha256", None)
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    if (payload.get("schema") != "contentops.easel-agent-execution-proposal/v1"
            or declared != proposal_sha256 or hashlib.sha256(canonical).hexdigest() != declared
            or payload.get("project") != project_rel or payload.get("account") != account
            or payload.get("run_id") != run_id or payload.get("max_attempts") != 1
            or payload.get("service_mode") not in {"local_gateway", "model_service"}
            or payload.get("execution_scope") != AGENT_EXECUTION_SCOPE
            or payload.get("execution_authorized") is not False):
        raise ValueError("proposal identity or contents do not match")
    manifest = _project_file(project, f"work/easel-agent-workspaces/{run_id}/workspace.json")
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != payload.get("workspace_manifest_sha256"):
        raise ValueError("proposal was created for different workspace inputs")
    approval = _project_file(project, "receipts/skill-execution-approval.json")
    if approval.stat().st_size > 32768:
        raise ValueError("approval is too large")
    record = json.loads(approval.read_text(encoding="utf-8"))
    if (not isinstance(record, dict) or record.get("evidence") !=
            {"record": relative, "sha256": record_digest(payload)}):
        raise ValueError("approval does not bind this exact proposal")
    grant = load_grant(project, owner_identities=owner_identities)
    if (grant.provenance != record_digest(record) or grant.account != account
            or grant.max_uses != 1 or grant.max_units != 1
            or grant.request_scope_sha256 != "sha256:" + proposal_sha256
            or grant.skill_id != AGENT_EXECUTION_SCOPE["skill_id"]
            or grant.skill_version != AGENT_EXECUTION_SCOPE["skill_version"]
            or grant.pipeline != AGENT_EXECUTION_SCOPE["pipeline"]
            or grant.stage != AGENT_EXECUTION_SCOPE["stage"]
            or grant.operations != (AGENT_EXECUTION_SCOPE["operation"],)):
        raise ValueError("approval changed or does not bind the exact task and operation")
    # Match the existing managed gate's host-declared subject convention.
    # This label is not authenticated and cannot itself authorize execution.
    subject = os.environ.get("CONTENTOPS_EXECUTION_SUBJECT", "").strip()
    request = ExecutionRequest(request_id=run_id, skill_id=AGENT_EXECUTION_SCOPE["skill_id"],
        skill_version=AGENT_EXECUTION_SCOPE["skill_version"], account=account,
        pipeline=AGENT_EXECUTION_SCOPE["pipeline"], stage=AGENT_EXECUTION_SCOPE["stage"],
        operations=(AGENT_EXECUTION_SCOPE["operation"],), subject=subject,
        request_scope_sha256="sha256:" + proposal_sha256)
    uses = len(consumed_uses(project, grant.grant_id))
    try:
        issued = datetime.fromisoformat(grant.issued_at.replace("Z", "+00:00"))
        expires = datetime.fromisoformat(grant.expires_at.replace("Z", "+00:00"))
        issued = issued if issued.tzinfo else issued.replace(tzinfo=timezone.utc)
        expires = expires if expires.tzinfo else expires.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        time_state = ("INVALID_WINDOW" if issued >= expires else
                      "NOT_YET_VALID" if now < issued else
                      "EXPIRED" if now >= expires else "CURRENT")
    except (ValueError, OverflowError):
        time_state = "INVALID_WINDOW"
    precheck = ("REVOKED" if grant.revoked else "USES_EXHAUSTED" if uses >= grant.max_uses
                else time_state if time_state != "CURRENT" else "SUBJECT_UNSET" if not subject
                else "SUBJECT_MISMATCH" if subject != grant.subject else "PENDING_FULL_GATE")
    registry_file = _project_file(Path(repo_root), "runtime/skill-registry.json")
    if registry_file.stat().st_size > 1024 * 1024:
        raise ValueError("skill registry is too large")
    registry = json.loads(registry_file.read_text(encoding="utf-8"))
    if (not isinstance(registry, dict) or registry.get("schema") != "contentops.skill-registry/v1"
            or not isinstance(registry.get("skills"), list)):
        raise ValueError("skill registry is invalid")
    entries = [item for item in registry["skills"] if isinstance(item, dict)
               and (item.get("id") == request.skill_id or item.get("name") == request.skill_id)]
    # The current registry has no Agent entry. Its exact-match rejection does
    # not inspect runtime paths or provider configuration. If an entry is later
    # added, defer the preview until that live resolution path is reviewed.
    preview = {"state": "NOT_CHECKED", "reason": "REGISTERED_CAPABILITY_REQUIRES_REVIEW"}
    if not entries:
        router_path = _project_file(Path(repo_root), "scripts/skill_route.py")
        spec = importlib.util.spec_from_file_location("contentops_easel_skill_router", router_path)
        if spec is None or spec.loader is None:
            raise ValueError("skill router is unavailable")
        router = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(router)
        verdict = router.resolve_capability(request.skill_id, account=account,
                                            pipeline=request.pipeline, stage=request.stage,
                                            registry=registry)
        decision = evaluate(request, verdict=verdict, registry_entry=None,
                            grant=replace(grant, uses_consumed=uses))
        preview = {"state": decision.state, "reason": decision.reason,
                   "router_reason": verdict.get("reason")}
    return {"schema": "contentops.easel-agent-approval-inspection/v1",
            "project": project_rel, "account": account, "run_id": run_id,
            "proposal_sha256": proposal_sha256, "approval_id": grant.grant_id,
            "approval_digest": grant.provenance,
            "execution_request": asdict(request),
            "grant_scope": {"skill_id": grant.skill_id, "skill_version": grant.skill_version,
                            "pipeline": grant.pipeline, "stage": grant.stage,
                            "operations": list(grant.operations), "subject": grant.subject,
                            "issued_at": grant.issued_at, "expires_at": grant.expires_at,
                            "revoked": grant.revoked},
            "uses_consumed": uses,
            "binding": "MATCHED_UNSIGNED", "precheck": precheck,
            "grant_decision": "READ_ONLY_PREVIEW", "authorization_preview": preview,
            "remaining_requirements": ["registry resolution and complete grant evaluation",
                                       "verified Windows isolation and process restrictions",
                                       "a reviewed, task-scoped provider path; the current router rejects network and paid providers",
                                       "authorized provider connection and single-use consumption"],
            "isolation": "NOT_VERIFIED", "execution_authorized": False,
            "production_ready": False, "publish_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--proposal-sha256", required=True)
    args = parser.parse_args()
    owners = [item.strip() for item in os.environ.get("CONTENTOPS_OWNER_IDENTITIES", "").split(",") if item.strip()]
    try:
        result = inspect(account=args.account, project_slug=args.project, run_id=args.run_id,
                         proposal_sha256=args.proposal_sha256, owner_identities=owners)
    except (OfflineTaskError, GrantSourceError, OSError, UnicodeError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)[:300]}, ensure_ascii=False))
        return 4
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
