"""Review-only adapter for existing huashu-motion clips; Easel stays the compositor.

The external skill creates the clip. ContentOps verifies bytes, technical
properties, pin and rights, but never triggers creation or grants publication.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict

from contentops.media.motion_sample import check_motion_sample
from contentops.media.rights_gate import RightsError, validate_request_rights

SCHEMA = "contentops.huashu-motion-request/v1"
HANDOFF_SCHEMA = "contentops.huashu-motion-handoff/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class HuashuMotionError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _need(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise HuashuMotionError(code, detail)


def _project_file(project: Path, ref: Any, suffix: str) -> Path:
    text = str(ref or "")
    _need(text.startswith("project://"), "HUASHU_PATH_SCHEME", "use project:// paths")
    relative = text[len("project://"):].replace("\\", "/")
    _need(bool(relative) and not relative.startswith("/")
          and not re.match(r"^[A-Za-z]:", relative)
          and ".." not in relative.split("/"),
          "HUASHU_PATH_ESCAPE", text)
    root = project.resolve()
    result = (root / relative).resolve()
    _need(result.is_relative_to(root), "HUASHU_PATH_ESCAPE", text)
    _need(result.suffix.lower() == suffix, "HUASHU_FILE_TYPE", text)
    _need(result.is_file(), "HUASHU_FILE_MISSING", text)
    return result


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def verify_runtime(*, runtime: Path, lock: Dict[str, Any],
                   observed_commit: str) -> Dict[str, str]:
    """Verify the externally installed checkout without executing its scripts."""
    _need(lock.get("schema") == "contentops.huashu-motion-lock/v1",
          "HUASHU_LOCK_SCHEMA", "unexpected runtime lock")
    _need(lock.get("repository") == "https://github.com/alchaincyf/huashu-motion",
          "HUASHU_LOCK_REPO", "runtime repository mismatch")
    _need(bool(_COMMIT.fullmatch(str(lock.get("commit") or ""))),
          "HUASHU_LOCK_COMMIT", "expected full 40-character git commit")
    _need(observed_commit == lock["commit"], "HUASHU_RUNTIME_UNPINNED",
          "checkout commit differs from lock")
    root = runtime.resolve()
    for name in ("package.json", "cli/om.js", "skills/huashu-motion/SKILL.md",
                 "THIRD_PARTY.md", "LICENSE"):
        _need((root / name).is_file(), "HUASHU_RUNTIME_MISSING", name)
    try:
        package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HuashuMotionError("HUASHU_RUNTIME_INVALID", "invalid package.json") from exc
    _need(package.get("name") == "huashu-motion"
          and package.get("version") == lock.get("version"),
          "HUASHU_RUNTIME_VERSION", "package version mismatch")
    return {"repository": lock["repository"], "commit": observed_commit,
            "version": package["version"]}


def make_handoff(*, project: Path, repo_root: Path, request: Dict[str, Any],
                 runtime_identity: Dict[str, str], probe: Dict[str, Any],
                 sample_checker: Callable[..., Dict[str, Any]] = check_motion_sample
                 ) -> Dict[str, Any]:
    """Check an exported MP4 and return a candidate for explicit M5 selection."""
    _need(isinstance(request, dict) and request.get("schema") == SCHEMA,
          "HUASHU_REQUEST_SCHEMA", SCHEMA)
    for field in ("asset_id", "placement_id"):
        value = request.get(field)
        _need(isinstance(value, str) and bool(re.fullmatch(
              r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value)),
              "HUASHU_ID_INVALID", field)
    _need(runtime_identity.get("repository") ==
          "https://github.com/alchaincyf/huashu-motion"
          and bool(_COMMIT.fullmatch(str(runtime_identity.get("commit") or ""))),
          "HUASHU_RUNTIME_UNVERIFIED", "runtime identity not pinned")
    project, repo_root = project.resolve(), repo_root.resolve()
    _need(project.is_relative_to(repo_root), "HUASHU_PROJECT_OUTSIDE_REPO",
          str(project))
    source = _project_file(project, request.get("film_source"), ".html")
    _need(source.name == "index.html", "HUASHU_SOURCE",
          "film must have an index.html")
    video = _project_file(project, request.get("output"), ".mp4")
    _need(bool(_SHA256.fullmatch(str(request.get("output_sha256") or ""))),
          "HUASHU_EXPECTED_HASH_REQUIRED", "output_sha256 must be provided")
    check = sample_checker(video, probe=probe,
                           expected_sha256=request["output_sha256"])
    _need(check.get("state") == "TECHNICALLY_CHECKED",
          "HUASHU_SAMPLE_BLOCKED",
          str(check.get("reason") or "sample did not pass technical QC"))
    rights = request.get("rights")
    _need(isinstance(rights, dict), "HUASHU_RIGHTS_REQUIRED",
          "rights mapping is required")
    try:
        reviewed = validate_request_rights(
            {"rights": rights, "license": rights.get("license_id")}, project)
    except RightsError as exc:
        raise HuashuMotionError("HUASHU_RIGHTS_BLOCKED", str(exc)) from exc
    _need(reviewed.get("evidence_capable") is False, "HUASHU_EVIDENCE",
          "motion is support-only")
    _need(request.get("restricted_character_review") is True,
          "HUASHU_RESTRICTED_CHARACTER_REVIEW",
          "operator must review use of excluded demo character")
    _need(request.get("asset_usage") == "VISUAL_SUPPORT_ONLY", "HUASHU_EVIDENCE",
          "motion cannot prove a fact")
    _need(request.get("publish_authorized") is False,
          "HUASHU_PUBLISH_FLAG", "handoff does not authorize publishing")
    digest = _digest(video)
    _need(digest == request["output_sha256"], "HUASHU_HASH_MISMATCH",
          "video bytes changed since request")
    candidate = {
        "id": request["asset_id"],
        "repo_path": video.relative_to(repo_root).as_posix(),
        "type": "motion",
        "sha256": digest,
        "permission": "CREATED_BY_OWNER",
        "license": rights["license_id"],
        "rights": rights,
        "generated": True,
        "evidence_capable": False,
        "evidence_use": "VISUAL_SUPPORT",
    }
    return {
        "schema": HANDOFF_SCHEMA,
        "state": "TECHNICALLY_CHECKED_AWAITING_MANUAL_REVIEW",
        "runtime": dict(runtime_identity),
        "asset_id": request["asset_id"],
        "placement_id": request["placement_id"],
        "film_source": request["film_source"],
        "film_source_sha256": _digest(source),
        "output": request["output"],
        "output_sha256": digest,
        "duration_s": check["duration_s"],
        "technical_check": "TECHNICALLY_CHECKED",
        "upstream_om_check": "NOT_VERIFIED_BY_THIS_ADAPTER",
        "upstream_om_qa": "NOT_VERIFIED_BY_THIS_ADAPTER",
        "rights_review_record_sha256": reviewed["review_evidence_sha256"],
        "third_party_dependency_rights": "REQUIRES_PROJECT_REVIEW",
        "asset_kind": "GENERATED_VIDEO",
        "generated": True,
        "evidence_capable": False,
        "evidence_use": "VISUAL_SUPPORT",
        "human_review": "PENDING_FOUNDER_REVIEW",
        "production_ready": False,
        "publish_authorized": False,
        "m5_asset_candidate": candidate,
        "note": "Not automatically active in M5/Manifest; requires explicit selection.",
    }
