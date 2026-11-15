"""Parse the OpenClaw agent-exec result without asserting provenance or approval."""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from .offline_task import (_acquire_project_lock, _ensure_child_dir, _linklike, _load_dna, _project_file,
                           _release_project_lock, _require_project_account, _safe_project)

MAX_RESULT_BYTES = 2 * 1024 * 1024


class AgentResultError(ValueError):
    pass


def _unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate result field")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError("non-finite result value")


def parse_openclaw_result(stdout: bytes, *, exit_code: int) -> dict[str, Any]:
    """Validate a bounded JSON envelope and extract a draft candidate.

    Parsing alone cannot prove which process produced these bytes, whether a
    sandbox was effective, or whether execution was authorized. The caller
    must establish and record those facts independently before importing output.
    """
    if type(exit_code) is not int:
        raise AgentResultError("exit code must be an integer")
    if not isinstance(stdout, bytes) or len(stdout) > MAX_RESULT_BYTES:
        raise AgentResultError("result exceeds the permitted size")
    digest = hashlib.sha256(stdout).hexdigest()
    try:
        value = json.loads(stdout.decode("utf-8"), object_pairs_hook=_unique_fields,
                           parse_constant=_invalid_constant)
    except (UnicodeDecodeError, ValueError):
        raise AgentResultError("result is not a valid UTF-8 JSON envelope") from None
    if not isinstance(value, dict):
        raise AgentResultError("result envelope must be an object")
    if exit_code != 0 or value.get("ok") is not True or value.get("status") != "ok":
        return {"status": "FAILED", "result_sha256": digest,
                "reason": "AGENT_EXECUTION_FAILED", "draft": None,
                "provenance": "UNVERIFIED", "production_ready": False,
                "publish_authorized": False}
    if value.get("error") is not None or value.get("codeModeEngaged") is True:
        raise AgentResultError("result contains an error or unexpected code mode")
    bridge = value.get("bridgeCalls")
    if bridge is not None:
        if (not isinstance(bridge, dict)
                or any(type(v) is not int or v < 0 for v in bridge.values())):
            raise AgentResultError("bridge call summary is invalid")
        if any(bridge.values()):
            raise AgentResultError("result reports nested bridge calls")
    text = value.get("final")
    if not isinstance(text, str) or not text.strip():
        raise AgentResultError("successful result has no final text")
    summary = value.get("toolSummary")
    if summary is not None:
        if not isinstance(summary, dict):
            raise AgentResultError("tool summary is invalid")
        calls = summary.get("calls")
        if calls is not None and (type(calls) is not int or calls != 0):
            raise AgentResultError("result reports tool calls")
    tool_audit = ("REPORTED_ZERO" if isinstance(summary, dict)
                  and type(summary.get("calls")) is int and summary["calls"] == 0
                  else "NOT_REPORTED")
    return {"status": "DRAFT_CANDIDATE", "result_sha256": digest,
            "draft": text, "draft_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "provenance": "UNVERIFIED", "isolation": "NOT_VERIFIED",
            "tool_call_audit": tool_audit,
            "execution_authorized": False, "human_review": "PENDING",
            "production_ready": False, "publish_authorized": False}


def _record_unverified_result(*, repo_root: Path, account: str, project_slug: str,
                              run_id: str, stdout: bytes, exit_code: int,
                              capture_record_sha256: str | None = None) -> dict[str, Any]:
    """Store explicitly unverified result bytes as a project-local candidate.

    This is not a real-Agent execution receipt: imported bytes carry no trusted
    runner, grant or isolation proof. No review or production state is changed.
    """
    if type(exit_code) is not int:
        raise AgentResultError("exit code must be an integer")
    try:
        if not isinstance(run_id, str) or str(uuid.UUID(run_id)) != run_id:
            raise ValueError("invalid run ID")
    except ValueError:
        raise AgentResultError("run ID must be a canonical UUID") from None
    root = Path(repo_root).resolve(strict=True)
    project, project_rel = _safe_project(root, project_slug)
    _require_project_account(project, account)
    dna = _load_dna(account, root)
    from .agent_workspace import read_agent_workspace
    state = read_agent_workspace(repo_root=root, account=account, project_slug=project_slug, run_id=run_id)
    if state["input_state"] != "CURRENT":
        raise AgentResultError("workspace inputs are stale")
    if state["preparation"] != "PREPARED":
        raise AgentResultError("workspace was cancelled")
    base = f"work/easel-agent-workspaces/{run_id}"
    manifest_path = _project_file(project, f"{base}/workspace.json")
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise AgentResultError("workspace manifest is unreadable") from None
    if (not isinstance(manifest, dict) or manifest.get("schema") != "contentops.easel-agent-workspace/v1"
            or manifest.get("run_id") != run_id or manifest.get("account") != account
            or manifest.get("project") != project_rel or manifest.get("dna_sha256") != dna["dna_sha256"]
            or manifest.get("workspace") != base):
        raise AgentResultError("workspace identity or account DNA changed")
    inputs = manifest.get("input_sha256")
    if not isinstance(inputs, dict) or not inputs:
        raise AgentResultError("workspace input manifest is invalid")
    for relative, expected in inputs.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise AgentResultError("workspace input manifest is invalid")
        path = _project_file(project, f"{base}/input/{relative}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise AgentResultError("workspace input changed")
    if not isinstance(stdout, bytes):
        raise AgentResultError("result must be bytes")
    try:
        parsed = parse_openclaw_result(stdout, exit_code=exit_code)
    except AgentResultError:
        # Persist a bounded reason code, not raw provider output or exception
        # text. The result remains explicitly unverified and unauthorized.
        parsed = {"status": "FAILED", "result_sha256": hashlib.sha256(stdout).hexdigest(),
                  "reason": "RESULT_INVALID_OR_TOOL_CALLS", "draft": None}
    # The attempt binds the reported exit and capture record as well as bytes.
    # Uncaptured successful results keep the original ID; prior receipts remain
    # readable when a capture-bearing retry receives a new ID.
    identity = f"contentops-easel-agent-result:{run_id}:{parsed['result_sha256']}"
    if exit_code != 0:
        identity += f":exit:{exit_code}"
    if capture_record_sha256:
        identity += f":capture:{capture_record_sha256}"
    attempt_id = str(uuid.uuid5(uuid.NAMESPACE_URL, identity))
    receipts = _ensure_child_dir(project, "receipts")
    draft_rel = None
    if parsed.get("draft") is not None:
        drafts = _ensure_child_dir(project, "drafts")
        draft_rel = f"drafts/easel-agent-unverified-{attempt_id}.md"
        draft_path = drafts / f"easel-agent-unverified-{attempt_id}.md"
        draft_bytes = parsed["draft"].encode("utf-8")
        if _linklike(draft_path):
            raise AgentResultError("candidate draft path is linked")
        if draft_path.exists():
            if not draft_path.is_file() or draft_path.read_bytes() != draft_bytes:
                raise AgentResultError("existing partial candidate does not match")
        else:
            with draft_path.open("xb") as stream:
                stream.write(draft_bytes)
    record = {"schema": "contentops.easel-agent-result-import/v1", "attempt_id": attempt_id,
              "run_id": run_id, "account": account, "project": project_rel,
              "workspace_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
              "easel_commit": manifest.get("easel_commit"),
              "overlay_record_sha256": manifest.get("overlay_record_sha256"),
              "overlay_verification": manifest.get("overlay_verification", "NOT_ESTABLISHED"),
              "frontend_build_manifest_sha256": manifest.get("frontend_build_manifest_sha256"),
              "frontend_dist_tree_sha256": manifest.get("frontend_dist_tree_sha256"),
              "frontend_build": manifest.get("frontend_build", "UNVERIFIED"),
              "profile_sha256": manifest.get("profile_sha256"),
              "skill_sha256": manifest.get("skill_sha256"),
              "skill_reference_sha256": manifest.get("skill_reference_sha256"),
              "evidence_state": manifest.get("evidence_state", "UNKNOWN"),
              "evidence_pack_sha256": manifest.get("evidence_pack_sha256"),
              "dna_sha256": dna["dna_sha256"], "result_sha256": parsed["result_sha256"],
              "draft": {"path": draft_rel, "sha256": parsed.get("draft_sha256")} if draft_rel else None,
              "status": "IMPORTED_UNVERIFIED" if draft_rel else "FAILED",
              "failure_reason": parsed.get("reason"),
              "capture_record_sha256": capture_record_sha256,
              "capture_binding": "CONSISTENT_UNSIGNED" if capture_record_sha256 else "NOT_AVAILABLE",
              "tool_call_audit": parsed.get("tool_call_audit", "NOT_REPORTED"),
              "source": "UNVERIFIED_RESULT_BYTES", "agent_execution": "NOT_PROVEN",
              "isolation": "NOT_VERIFIED", "execution_authorized": False,
              "human_review": "PENDING", "production_ready": False, "publish_authorized": False}
    if exit_code != 0:
        record["reported_exit_code"] = exit_code
    receipt_path = receipts / f"easel-agent-import-{attempt_id}.json"
    if _linklike(receipt_path):
        raise AgentResultError("candidate receipt path is linked")
    if receipt_path.exists():
        try:
            existing = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            raise AgentResultError("existing candidate receipt is unreadable") from None
        if existing != record:
            raise AgentResultError("existing candidate receipt does not match")
    else:
        with receipt_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    return record


def record_unverified_result(*, repo_root: Path, account: str, project_slug: str,
                             run_id: str, stdout: bytes, exit_code: int) -> dict[str, Any]:
    """Serialize result import with preparation and pre-execution cancellation."""
    root = Path(repo_root).resolve(strict=True)
    project, _ = _safe_project(root, project_slug)
    _require_project_account(project, account)
    lock = project / ".easel-offline-task.lock"
    if _linklike(lock):
        raise AgentResultError("project lock is linked")
    fd = _acquire_project_lock(lock)
    try:
        return _record_unverified_result(repo_root=root, account=account,
                                         project_slug=project_slug, run_id=run_id,
                                         stdout=stdout, exit_code=exit_code)
    finally:
        _release_project_lock(fd)


def read_unverified_result(*, repo_root: Path, account: str, project_slug: str,
                           attempt_id: str) -> dict[str, Any]:
    """Read only a bound, digest-checked imported candidate and its receipt."""
    try:
        if not isinstance(attempt_id, str) or str(uuid.UUID(attempt_id)) != attempt_id:
            raise ValueError("invalid attempt")
    except ValueError:
        raise AgentResultError("attempt ID must be a canonical UUID") from None
    root = Path(repo_root).resolve(strict=True)
    project, project_rel = _safe_project(root, project_slug)
    _require_project_account(project, account)
    path = _project_file(project, f"receipts/easel-agent-import-{attempt_id}.json")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise AgentResultError("candidate receipt is unreadable") from None
    if (not isinstance(record, dict) or record.get("schema") != "contentops.easel-agent-result-import/v1"
            or record.get("attempt_id") != attempt_id or record.get("account") != account
            or record.get("project") != project_rel or record.get("source") != "UNVERIFIED_RESULT_BYTES"
            or record.get("agent_execution") != "NOT_PROVEN"
            or record.get("execution_authorized") is not False
            or record.get("production_ready") is not False or record.get("publish_authorized") is not False):
        raise AgentResultError("candidate receipt binding or status is invalid")
    draft = record.get("draft")
    content = None
    if record.get("status") == "IMPORTED_UNVERIFIED":
        expected = f"drafts/easel-agent-unverified-{attempt_id}.md"
        if not isinstance(draft, dict) or draft.get("path") != expected:
            raise AgentResultError("candidate draft binding is invalid")
        data = _project_file(project, expected).read_bytes()
        if len(data) > MAX_RESULT_BYTES or hashlib.sha256(data).hexdigest() != draft.get("sha256"):
            raise AgentResultError("candidate draft is changed or too large")
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            raise AgentResultError("candidate draft is not UTF-8") from None
    elif record.get("status") != "FAILED" or draft is not None:
        raise AgentResultError("candidate result status is invalid")
    return {"receipt": record, "draft": content}


def collect_workspace_result(*, repo_root: Path, account: str, project_slug: str,
                             run_id: str, exit_code: int) -> dict[str, Any]:
    """Collect fixed project output bytes; neither exit code nor origin is proof."""
    if type(exit_code) is not int:
        raise AgentResultError("exit code must be an integer")
    try:
        if not isinstance(run_id, str) or str(uuid.UUID(run_id)) != run_id:
            raise ValueError("invalid run")
    except ValueError:
        raise AgentResultError("run ID must be a canonical UUID") from None
    root = Path(repo_root).resolve(strict=True)
    project, project_rel = _safe_project(root, project_slug)
    _require_project_account(project, account)
    lock = project / ".easel-offline-task.lock"
    if _linklike(lock):
        raise AgentResultError("project lock is linked")
    fd = _acquire_project_lock(lock)
    try:
        base = f"work/easel-agent-workspaces/{run_id}/output"
        path = _project_file(project, f"{base}/agent-result.json")
        if path.stat().st_size > MAX_RESULT_BYTES:
            raise AgentResultError("candidate result exceeds size limit")
        data = path.read_bytes()
        if len(data) > MAX_RESULT_BYTES:
            raise AgentResultError("candidate result exceeds size limit")
        capture_path = project / base / "capture.json"
        if _linklike(capture_path):
            raise AgentResultError("capture record is linked")
        capture_digest = None
        if capture_path.exists():
            capture = _project_file(project, f"{base}/capture.json").read_bytes()
            if len(capture) > 32768:
                raise AgentResultError("capture record exceeds size limit")
            try:
                record = json.loads(capture.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                raise AgentResultError("capture record is unreadable") from None
            if (not isinstance(record, dict) or record.get("schema") != "contentops.easel-agent-output-capture/v1"
                    or record.get("run_id") != run_id or record.get("account") != account
                    or record.get("project") != project_rel or record.get("exit_code") != exit_code
                    or record.get("result_sha256") != hashlib.sha256(data).hexdigest()
                    or record.get("origin") != "UNVERIFIED" or record.get("execution") != "NOT_PROVEN"
                    or record.get("execution_authorized") is not False):
                raise AgentResultError("capture record does not match result or exit code")
            capture_digest = hashlib.sha256(capture).hexdigest()
        return _record_unverified_result(repo_root=root, account=account, project_slug=project_slug,
                                         run_id=run_id, stdout=data, exit_code=exit_code,
                                         capture_record_sha256=capture_digest)
    finally:
        _release_project_lock(fd)


def capture_workspace_output(*, repo_root: Path, account: str, project_slug: str,
                             run_id: str, stdout: bytes, exit_code: int) -> dict[str, Any]:
    """Persist one bounded output for later collection, without claiming origin.

    This is a storage primitive, not an executor or an authorization check.
    A future supervisor must independently prove isolation and consume the
    existing execution grant before supplying output here.
    """
    if not isinstance(stdout, bytes) or len(stdout) > MAX_RESULT_BYTES or type(exit_code) is not int:
        raise AgentResultError("invalid or oversized process output")
    root = Path(repo_root).resolve(strict=True)
    project, project_rel = _safe_project(root, project_slug)
    _require_project_account(project, account)
    lock = project / ".easel-offline-task.lock"
    if _linklike(lock):
        raise AgentResultError("project lock is linked")
    fd = _acquire_project_lock(lock)
    try:
        from .agent_workspace import read_agent_workspace
        state = read_agent_workspace(repo_root=root, account=account, project_slug=project_slug, run_id=run_id)
        if state["input_state"] != "CURRENT" or state["preparation"] != "PREPARED":
            raise AgentResultError("workspace is stale or cancelled")
        output = project / state["workspace"] / "output"
        if _linklike(output) or not output.is_dir() or output.resolve(strict=True).parent != (project / state["workspace"]).resolve(strict=True):
            raise AgentResultError("workspace output path is unsafe")
        target = output / "agent-result.json"
        receipt_path = output / "capture.json"
        if _linklike(target) or _linklike(receipt_path):
            raise AgentResultError("output or capture record is linked")
        digest = hashlib.sha256(stdout).hexdigest()
        record = {"schema": "contentops.easel-agent-output-capture/v1", "run_id": run_id,
                  "account": account, "project": project_rel, "result_sha256": digest,
                  "exit_code": exit_code, "origin": "UNVERIFIED", "execution": "NOT_PROVEN",
                  "execution_authorized": False, "production_ready": False,
                  "publish_authorized": False}
        if target.exists():
            if not target.is_file() or target.read_bytes() != stdout:
                raise AgentResultError("existing output differs from candidate output")
        else:
            with target.open("xb") as stream:
                stream.write(stdout)
        if receipt_path.exists():
            try:
                existing = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, ValueError):
                raise AgentResultError("capture record is unreadable") from None
            if existing != record:
                raise AgentResultError("existing capture record differs")
        else:
            with receipt_path.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(record, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        return record
    finally:
        _release_project_lock(fd)
