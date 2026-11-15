#!/usr/bin/env python3
"""Describe one prepared Easel task for review; never approve or execute it.

The resulting JSON is a proposal, not an execution grant. The existing
ContentOps execution approval and a separately proven isolation boundary
remain necessary before a real model or gateway call.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import ipaddress
import json
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.easel.agent_workspace import AGENT_EXECUTION_SCOPE, read_agent_workspace  # noqa: E402
from contentops.easel.offline_task import (OfflineTaskError, _ensure_child_dir, _linklike,
                                           _project_file, _require_project_account,
                                           _safe_project)  # noqa: E402
from contentops.skills.grant_source import record_digest  # noqa: E402


def proposal(*, account: str, project_slug: str, run_id: str, service_mode: str, service: str,
             endpoint: str, max_cost: str, currency: str, repo_root: Path = ROOT) -> dict:
    """Return bounded review information without reading credentials or running code."""
    if service_mode not in {"local_gateway", "model_service"}:
        raise ValueError("service mode must be local_gateway or model_service")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,79}", service):
        raise ValueError("service must be a simple model or gateway identifier")
    if len(endpoint) > 512 or any(ord(char) < 33 for char in endpoint):
        raise ValueError("endpoint contains invalid characters")
    parsed = urlsplit(endpoint)
    host = parsed.hostname
    try:
        loopback = bool(host and (host.lower() == "localhost" or ipaddress.ip_address(host).is_loopback))
    except ValueError:
        loopback = False
    allowed_scheme = (parsed.scheme in {"http", "https", "ws", "wss"} and loopback
                      if service_mode == "local_gateway"
                      else parsed.scheme == "https" or (parsed.scheme == "http" and loopback))
    if (not allowed_scheme
            or not host or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment):
        raise ValueError("endpoint is incompatible with the selected service mode or contains credentials, query or fragment")
    try:
        port = parsed.port
        amount = Decimal(max_cost)
    except (ValueError, InvalidOperation):
        raise ValueError("endpoint port or cost limit is invalid") from None
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("endpoint port is invalid")
    if not amount.is_finite() or amount < 0 or amount > 1000000:
        raise ValueError("cost limit must be finite and between 0 and 1000000")
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("currency must be a three-letter uppercase code")
    project, project_rel = _safe_project(repo_root, project_slug)
    state = read_agent_workspace(repo_root=repo_root, account=account,
                                 project_slug=project_slug, run_id=run_id)
    if state.get("input_state") != "CURRENT" or state.get("preparation") != "PREPARED":
        raise ValueError("prepared task is stale, unsafe or cancelled")
    manifest = _project_file(project, f"work/easel-agent-workspaces/{run_id}/workspace.json")
    data = manifest.read_bytes()
    if len(data) > 1024 * 1024:
        raise ValueError("workspace manifest exceeds the permitted size")
    record = json.loads(data.decode("utf-8"))
    if not isinstance(record, dict):
        raise ValueError("workspace manifest is invalid")
    current = read_agent_workspace(repo_root=repo_root, account=account,
                                    project_slug=project_slug, run_id=run_id)
    if (current.get("input_state") != "CURRENT" or current.get("preparation") != "PREPARED"
            or _project_file(project, f"work/easel-agent-workspaces/{run_id}/workspace.json").read_bytes() != data):
        raise ValueError("prepared task changed while the proposal was being assembled")
    result = {
        "schema": "contentops.easel-agent-execution-proposal/v1",
        "project": project_rel, "account": account, "run_id": run_id,
        "workspace_manifest_sha256": hashlib.sha256(data).hexdigest(),
        "dna_sha256": record.get("dna_sha256"),
        "easel_commit": record.get("easel_commit"),
        "overlay_record_sha256": record.get("overlay_record_sha256"),
        "frontend_dist_tree_sha256": record.get("frontend_dist_tree_sha256"),
        "service_mode": service_mode, "service": service, "endpoint": endpoint,
        "execution_scope": dict(AGENT_EXECUTION_SCOPE),
        "max_cost": str(amount), "currency": currency, "max_attempts": 1, "timeout_seconds": 120,
        "cost_enforcement": "NOT_IMPLEMENTED", "endpoint_enforcement": "NOT_IMPLEMENTED",
        "execution_location": "NOT_VERIFIED", "gateway_isolation": "NOT_VERIFIED",
        "output": f"work/easel-agent-workspaces/{run_id}/output/agent-result.json",
        "exit_conditions": ["one result", "failure", "timeout", "cancellation"],
        "isolation": "NOT_VERIFIED", "approval": "NOT_GRANTED",
        "execution_authorized": False, "production_ready": False,
        "publish_authorized": False,
    }
    canonical = json.dumps(result, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    result["proposal_sha256"] = hashlib.sha256(canonical).hexdigest()
    return result


def save_proposal(*, result: dict, project_slug: str, repo_root: Path = ROOT) -> dict:
    """Save a freshly prepared proposal without overwriting another record."""
    project, project_rel = _safe_project(repo_root, project_slug)
    if result.get("project") != project_rel or not re.fullmatch(r"[0-9a-f]{64}", result.get("proposal_sha256", "")):
        raise ValueError("proposal project or digest is invalid")
    run_id = result.get("run_id")
    state = read_agent_workspace(repo_root=repo_root, account=result.get("account"),
                                 project_slug=project_slug, run_id=run_id)
    manifest = _project_file(project, f"work/easel-agent-workspaces/{run_id}/workspace.json")
    if (state.get("input_state") != "CURRENT" or state.get("preparation") != "PREPARED"
            or hashlib.sha256(manifest.read_bytes()).hexdigest() != result.get("workspace_manifest_sha256")):
        raise ValueError("prepared task changed before proposal was saved")
    work = _ensure_child_dir(project, "work")
    directory = work / "easel-agent-proposals"
    if _linklike(directory):
        raise ValueError("proposal directory is linked")
    directory.mkdir(exist_ok=True)
    if not directory.is_dir() or directory.resolve(strict=True).parent != work:
        raise ValueError("proposal directory is unsafe")
    filename = f"easel-agent-proposal-{run_id}-{result['proposal_sha256']}.json"
    target = directory / filename
    data = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if _linklike(target):
        raise ValueError("proposal receipt path is linked")
    if target.exists():
        if not target.is_file() or target.read_bytes() != data:
            raise ValueError("existing proposal receipt differs")
    else:
        with target.open("xb") as stream:
            stream.write(data)
    return {"proposal": result, "approval_evidence": {"record": f"work/easel-agent-proposals/{filename}",
                                                      "sha256": record_digest(result)},
            "request_scope_sha256": "sha256:" + result["proposal_sha256"],
            "approval": "NOT_GRANTED", "execution_authorized": False}


def list_proposals(*, account: str, project_slug: str, repo_root: Path = ROOT) -> dict:
    """List bound proposal identifiers without exposing stored service details."""
    project, project_rel = _safe_project(repo_root, project_slug)
    _require_project_account(project, account)
    work = project / "work"
    directory = work / "easel-agent-proposals"
    if _linklike(work) or _linklike(directory):
        raise ValueError("proposal directory is linked")
    if not directory.exists():
        return {"proposals": [], "unavailable_count": 0}
    if not directory.is_dir() or directory.resolve(strict=True).parent != work.resolve(strict=True):
        raise ValueError("proposal directory is unsafe")
    candidates = []
    for path in directory.glob("easel-agent-proposal-*.json"):
        try:
            if not _linklike(path) and path.is_file():
                candidates.append((path.stat().st_mtime_ns, path))
        except OSError:
            continue
    rows, unavailable = [], 0
    for _, path in sorted(candidates, key=lambda item: (item[0], item[1].name), reverse=True)[:50]:
        try:
            if path.stat().st_size > 32768:
                raise ValueError("proposal too large")
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("invalid proposal")
            body = dict(payload)
            digest = body.pop("proposal_sha256", None)
            run_id = payload.get("run_id")
            canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                    or not isinstance(run_id, str) or str(uuid.UUID(run_id)) != run_id
                    or path.name != f"easel-agent-proposal-{run_id}-{digest}.json"
                    or hashlib.sha256(canonical).hexdigest() != digest
                    or payload.get("schema") != "contentops.easel-agent-execution-proposal/v1"
                    or payload.get("project") != project_rel or payload.get("account") != account
                    or payload.get("execution_authorized") is not False):
                raise ValueError("proposal binding mismatch")
            rows.append({"run_id": run_id, "proposal_sha256": digest,
                         "current_state": "NOT_CHECKED"})
        except (OSError, ValueError, TypeError, UnicodeError):
            unavailable += 1
    return {"proposals": rows, "unavailable_count": unavailable}


def read_saved_proposal(*, account: str, project_slug: str, run_id: str,
                        proposal_sha256: str, repo_root: Path = ROOT) -> dict:
    """Read a single project-bound proposal and report current task state."""
    if (not isinstance(run_id, str) or str(uuid.UUID(run_id)) != run_id
            or not isinstance(proposal_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", proposal_sha256)):
        raise ValueError("proposal identifier is invalid")
    project, project_rel = _safe_project(repo_root, project_slug)
    _require_project_account(project, account)
    path = _project_file(project, f"work/easel-agent-proposals/easel-agent-proposal-{run_id}-{proposal_sha256}.json")
    if path.stat().st_size > 32768:
        raise ValueError("proposal is too large")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("proposal is invalid")
    body = dict(payload)
    declared = body.pop("proposal_sha256", None)
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if (declared != proposal_sha256 or hashlib.sha256(canonical).hexdigest() != declared
            or payload.get("schema") != "contentops.easel-agent-execution-proposal/v1"
            or payload.get("project") != project_rel or payload.get("account") != account
            or payload.get("run_id") != run_id or payload.get("execution_authorized") is not False):
        raise ValueError("proposal binding mismatch")
    state = read_agent_workspace(repo_root=repo_root, account=account,
                                 project_slug=project_slug, run_id=run_id)
    manifest = _project_file(project, f"work/easel-agent-workspaces/{run_id}/workspace.json")
    same = hashlib.sha256(manifest.read_bytes()).hexdigest() == payload.get("workspace_manifest_sha256")
    return {"proposal": payload,
            "task_state": state.get("input_state") if same else "STALE",
            "preparation": state.get("preparation"), "approval": "NOT_CHECKED",
            "execution_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--service-mode", required=True, choices=("local_gateway", "model_service"))
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--max-cost", required=True)
    parser.add_argument("--currency", required=True)
    parser.add_argument("--write", action="store_true",
                        help="save the proposal as ignored project-local evidence; does not grant authority")
    args = parser.parse_args()
    try:
        result = proposal(account=args.account, project_slug=args.project, run_id=args.run_id,
                          service_mode=args.service_mode, service=args.service, endpoint=args.endpoint,
                          max_cost=args.max_cost, currency=args.currency)
        if args.write:
            result = save_proposal(result=result, project_slug=args.project)
    except (OfflineTaskError, OSError, UnicodeError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)[:300]}, ensure_ascii=False))
        return 4
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
