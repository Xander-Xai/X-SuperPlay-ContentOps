"""Deterministic, offline-only Easel draft scaffold executor.

This module does not call an Agent, model, gateway, network, shell, or the
upstream workbench. It writes a clearly labelled scaffold and a project-local
receipt so the request/output/receipt path can be exercised before any real
execution grant exists.
"""

from __future__ import annotations

import hashlib
from html import escape
import importlib.util
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict

from .path_safety import is_linklike as _linklike

MAX_BRIEF_CHARS = 8_000
PROJECT_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class OfflineTaskError(ValueError):
    def __init__(self, code: str, detail: str, status: int = 400) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail
        self.status = status
        self.failure_receipt = None
        self.failure_record = None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def _safe_project(repo_root: Path, slug: str) -> tuple[Path, str]:
    if not isinstance(slug, str):
        raise OfflineTaskError("PROJECT_INVALID", "project must be a lowercase project slug")
    local = slug.startswith("_local/")
    name = slug[7:] if local else slug
    if not PROJECT_SLUG.fullmatch(name):
        raise OfflineTaskError("PROJECT_INVALID", "project must be a lowercase project slug or _local/<slug>")
    root = Path(repo_root).resolve(strict=True)
    projects = root / "projects"
    parent = projects / "_local" if local else projects
    project = parent / name
    if _linklike(projects) or (local and _linklike(parent)) or _linklike(project):
        raise OfflineTaskError("PROJECT_UNSAFE", "project path may not contain a symlink or junction", 403)
    if not projects.is_dir() or not parent.is_dir() or not project.is_dir():
        raise OfflineTaskError("PROJECT_MISSING", "the selected project must already exist", 404)
    resolved_parent = parent.resolve(strict=True)
    resolved_project = project.resolve(strict=True)
    if (local and resolved_parent.parent != projects.resolve(strict=True)) or resolved_project.parent != resolved_parent:
        raise OfflineTaskError("PROJECT_UNSAFE", "project resolves outside the projects directory", 403)
    return resolved_project, resolved_project.relative_to(root).as_posix()


def _ensure_child_dir(project: Path, name: str) -> Path:
    path = project / name
    if _linklike(path):
        raise OfflineTaskError("PROJECT_UNSAFE", f"{name} may not be a symlink or junction", 403)
    path.mkdir(exist_ok=True)
    if not path.is_dir() or path.resolve(strict=True).parent != project.resolve(strict=True):
        raise OfflineTaskError("PROJECT_UNSAFE", f"{name} must stay directly under the project", 403)
    return path


def _require_project_account(project: Path, account: str) -> None:
    """Bind task access to the account declared by the existing project."""
    config = project / "project.yaml"
    if (_linklike(config) or not config.is_file()
            or config.resolve(strict=True).parent != project):
        raise OfflineTaskError("PROJECT_ACCOUNT_MISSING", "project.yaml with an account_slug is required", 409)
    try:
        text = config.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise OfflineTaskError("PROJECT_ACCOUNT_INVALID", "project account declaration is unreadable", 409) from None
    try:
        import yaml
    except ImportError:
        raise OfflineTaskError("PROJECT_ACCOUNT_INVALID", "YAML support is unavailable", 409) from None
    try:
        node = yaml.compose(text, Loader=yaml.SafeLoader)
        if not isinstance(node, yaml.MappingNode):
            raise ValueError("project config must be a mapping")
        matches = [(key, value) for key, value in node.value
                   if isinstance(key, yaml.ScalarNode) and key.value == "account_slug"]
        # YAML merges could supply or override the account outside this mapping.
        if any(isinstance(key, yaml.ScalarNode) and key.tag == "tag:yaml.org,2002:merge"
               for key, _ in node.value):
            raise ValueError("merged project mappings are not supported")
        if len(matches) != 1 or not isinstance(matches[0][1], yaml.ScalarNode):
            raise ValueError("project must declare exactly one account_slug")
        value = matches[0][1].value
    except (ValueError, yaml.YAMLError):
        raise OfflineTaskError("PROJECT_ACCOUNT_INVALID", "project account declaration is invalid", 409) from None
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", value):
        raise OfflineTaskError("PROJECT_ACCOUNT_INVALID", "project account_slug is invalid", 409)
    if value != account:
        raise OfflineTaskError("PROJECT_ACCOUNT_MISMATCH", "selected account does not match the project", 403)


def list_account_projects(*, repo_root: Path, account: str) -> Dict[str, Any]:
    """List direct and repository-local projects bound to this account."""
    repo = Path(repo_root).resolve(strict=True)
    _load_dna(account, repo)
    projects = repo / "projects"
    if _linklike(projects) or not projects.is_dir():
        raise OfflineTaskError("PROJECT_DIRECTORY_UNSAFE", "projects directory is unavailable", 403)
    selected = []
    paths = [(path, path.name) for path in projects.iterdir()]
    local = projects / "_local"
    if not _linklike(local) and local.is_dir():
        paths.extend((path, f"_local/{path.name}") for path in local.iterdir())
    for path, identifier in sorted(paths, key=lambda item: item[1]):
        if not PROJECT_SLUG.fullmatch(path.name) or _linklike(path) or not path.is_dir():
            continue
        try:
            project, _ = _safe_project(repo, identifier)
            config = project / "project.yaml"
            if not config.is_file() or config.stat().st_size > 1_048_576:
                continue
            _require_project_account(project, account)
        except (OfflineTaskError, OSError):
            continue
        selected.append(identifier)
    return {"account": account, "projects": selected}


def _atomic_write(path: Path, data: bytes) -> None:
    temp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(temp, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _acquire_project_lock(path: Path) -> int:
    """Acquire a kernel-released nonblocking project lock.

    The lock file intentionally remains after release. The OS lock itself is
    dropped if the process exits unexpectedly, so a retry can resume the
    persisted idempotency state without guessing whether an old PID is alive.
    """
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"0")
            os.fsync(fd)
        os.lseek(fd, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except OSError:
        os.close(fd)
        raise OfflineTaskError("TASK_BUSY", "another offline task is active for this project", 409) from None
    except Exception:
        os.close(fd)
        raise


def _release_project_lock(fd: int) -> None:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _load_dna(slug: str, repo_root: Path) -> Dict[str, Any]:
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        raise OfflineTaskError("ACCOUNT_INVALID", "account must be a lowercase account slug")
    directory = Path(repo_root) / "config" / "accounts"
    path = directory / f"{slug}.json"
    if (_linklike(directory) or _linklike(directory.parent)
            or _linklike(directory.parent.parent) or _linklike(path)
            or not directory.is_dir() or not path.is_file()
            or path.resolve(strict=True).parent != directory.resolve(strict=True)):
        raise OfflineTaskError("ACCOUNT_MISSING", "selected account DNA is unavailable", 404)
    try:
        dna = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, TypeError):
        raise OfflineTaskError("ACCOUNT_DNA_INVALID", "selected account DNA is unreadable") from None
    profile_script = Path(repo_root) / "scripts" / "easel_profile.py"
    if (_linklike(profile_script) or not profile_script.is_file()
            or profile_script.resolve(strict=True).parent != profile_script.parent.resolve(strict=True)):
        raise OfflineTaskError("PROFILE_PROJECTOR_UNAVAILABLE", "Easel profile projector is unavailable", 500)
    spec = importlib.util.spec_from_file_location(
        "contentops_easel_profile_projector", profile_script)
    if spec is None or spec.loader is None:
        raise OfflineTaskError("PROFILE_PROJECTOR_UNAVAILABLE", "Easel profile projector is unavailable", 500)
    easel_profile = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(easel_profile)
    except Exception:  # noqa: BLE001 - projector failure must stop the entire selector
        raise OfflineTaskError("PROFILE_PROJECTOR_UNAVAILABLE", "Easel profile projector failed", 500) from None
    try:
        easel_profile.validate_profile_dna(slug, dna)
        profile = easel_profile.build_profile(slug, dna)
    except (ValueError, TypeError, AttributeError) as exc:
        raise OfflineTaskError("ACCOUNT_DNA_INVALID", str(exc)) from None
    return {"dna": dna, "profile": profile, "dna_sha256": _sha(_canonical(dna)),
            "profile_sha256": {name: _sha(text.encode("utf-8"))
                               for name, text in profile.items()}}


def _frontend_proof(repo: Path, expected_commit: str | None) -> Dict[str, Any]:
    """Read the local build receipt and verify its bytes without network access."""
    manifest = repo / "runtime" / "easel-workbench-frontend-build.json"
    manifest_sha = None
    if manifest.is_file() and not _linklike(manifest):
        try:
            manifest_sha = _sha(manifest.read_bytes())
        except OSError:
            pass
    verifier_path = repo / "scripts" / "verify_easel_runtime.py"
    overlay_path = repo / "runtime" / "easel-workbench-overlay.json"
    if (_linklike(verifier_path) or not verifier_path.is_file()
            or _linklike(overlay_path) or not overlay_path.is_file()):
        return {"status": "UNVERIFIED", "manifest_sha256": manifest_sha,
                "dist_tree_sha256": None, "file_count": None}
    scripts_dir = str(verifier_path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        spec = importlib.util.spec_from_file_location(
            "contentops_frontend_build_verifier", verifier_path)
        if spec is None or spec.loader is None:
            raise ValueError("verifier unavailable")
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        overlay = verifier.load_overlay(overlay_path)
        if not overlay.get("readable"):
            raise ValueError("overlay unreadable")
        frontend = verifier.workbench_path(overlay) / "web" / "frontend"
        result = verifier.verify_frontend_build(frontend, manifest,
                                                expected_commit or "")
    except Exception:  # noqa: BLE001 - provenance errors remain unverified
        return {"status": "UNVERIFIED", "manifest_sha256": manifest_sha,
                "dist_tree_sha256": None, "file_count": None}
    return {"status": result.get("status", "UNVERIFIED"),
            "manifest_sha256": manifest_sha,
            "dist_tree_sha256": result.get("tree_sha256")
            if result.get("status") == "VERIFIED" else None,
            "file_count": result.get("file_count")
            if result.get("status") == "VERIFIED" else None}


def list_profile_summaries(repo_root: Path) -> Dict[str, Any]:
    """Return eligible DNA-derived profiles and explicitly list exclusions."""
    repo = Path(repo_root).resolve(strict=True)
    accounts = repo / "config" / "accounts"
    if (_linklike(accounts) or _linklike(accounts.parent) or not accounts.is_dir()):
        raise OfflineTaskError("ACCOUNT_DIRECTORY_UNSAFE", "account DNA directory is unavailable", 403)
    result = []
    excluded = []
    for path in sorted(accounts.glob("*.json")):
        slug = path.stem
        if _linklike(path) or path.resolve(strict=True).parent != accounts.resolve(strict=True):
            raise OfflineTaskError("ACCOUNT_DNA_UNSAFE", "account DNA path may not be linked", 403)
        try:
            loaded = _load_dna(slug, repo)
        except OfflineTaskError as exc:
            if exc.code != "ACCOUNT_DNA_INVALID":
                raise
            excluded.append({"slug": slug, "reason": exc.code})
            continue
        dna = loaded["dna"]
        narrative = dna["narrative"]
        visual = dna["visual"]
        result.append({
            "slug": slug,
            "name": dna["account"],
            "role": dna["role"],
            "promise": dna["promise"],
            "dna_sha256": loaded["dna_sha256"],
            "profile_sha256": loaded["profile_sha256"],
            "narrative": {
                "mode": narrative["mode"],
                "speech_rate_cpm": narrative["speech_rate_cpm"],
                "target_duration_s": narrative["target_duration_s"],
                "template": narrative["template"],
                "cta": narrative["cta"],
            },
            "visual": {
                "composition": visual["composition"]["segments"],
                "caption_style": visual["caption_style"],
            },
        })
    return {"profiles": result, "excluded_accounts": excluded}


def read_profile_detail(repo_root: Path, account: str) -> Dict[str, Any]:
    """Return one DNA-derived profile, without reading the upstream profile store."""
    repo = Path(repo_root).resolve(strict=True)
    loaded = _load_dna(account, repo)
    return {"account": account, "dna_sha256": loaded["dna_sha256"],
            "profile_sha256": loaded["profile_sha256"],
            "files": loaded["profile"],
            "source": "contentops-account-dna",
            "upstream_snapshot_verified": False,
            "agent_context_verified": False,
            "execution_authorized": False}


def _project_file(project: Path, relative: str) -> Path:
    """Resolve a project-local input without following links or hidden paths."""
    parts = relative.replace("\\", "/").split("/")
    if (not parts or any(not p or p in (".", "..") or p.startswith(".")
                         or ":" in p for p in parts)):
        raise OfflineTaskError("PROJECT_INPUT_UNSAFE", "project input path is unsafe", 409)
    current = project
    for part in parts:
        current = current / part
        if _linklike(current):
            raise OfflineTaskError("PROJECT_INPUT_UNSAFE", "linked project input is not permitted", 409)
    if not current.is_file() or project not in current.resolve(strict=True).parents:
        raise OfflineTaskError("PROJECT_INPUT_MISSING", "project input is missing", 409)
    return current


def _driver_plan_summary(project: Path, repo: Path) -> Dict[str, Any]:
    """Read the existing driver's plan without exposing its executable argv."""
    from .driver import DriverError, build_plan

    # The driver reads fixed receipt names and checks the corresponding final
    # video. Refuse linked entries before handing the directory to that reader.
    for name in ("receipts", "final"):
        directory = project / name
        if _linklike(directory):
            raise OfflineTaskError("PROJECT_INPUT_UNSAFE", f"{name} directory is linked", 409)
        if directory.exists():
            if not directory.is_dir() or directory.resolve(strict=True).parent != project:
                raise OfflineTaskError("PROJECT_INPUT_UNSAFE", f"{name} directory is unsafe", 409)
            for child in directory.iterdir():
                if _linklike(child):
                    raise OfflineTaskError("PROJECT_INPUT_UNSAFE", f"{name} contains linked entries", 409)
    try:
        plan = build_plan(project, repo)
    except (DriverError, OSError, ValueError, TypeError):
        return {"state": "BLOCKED", "reason": "DRIVER_PLAN_UNAVAILABLE"}
    return {"state": "AVAILABLE", "format": plan.get("format"),
            "steps": [{"id": item.get("id"), "label": item.get("label"),
                       "authority": item.get("authority"), "requires": item.get("requires"),
                       "receipt_state": ("HUMAN_REQUIRED" if item.get("authority") == "HUMAN_ONLY"
                                         else "NOT_APPLICABLE" if not item.get("receipts")
                                         else "COMPLETE" if item.get("ready") else "NOT_COMPLETE")}
                      for item in plan.get("steps", [])],
            "note": "Receipt-based plan only; no step was executed and no permission was granted."}


def project_readiness(*, repo_root: Path, account: str, project_slug: str) -> Dict[str, Any]:
    """Report existing ContentOps handoff inputs without executing a pipeline."""
    from ..routing import handoff as brief_handoff
    from ..script.evidence import load_pack, sufficiency
    from ..content_kernel.handoff import HANDOFF_SCHEMA, VIDEO, verify_bundle_unchanged

    repo = Path(repo_root).resolve(strict=True)
    project, project_rel = _safe_project(repo, project_slug)
    _require_project_account(project, account)
    _load_dna(account, repo)
    result = {"project": project_rel, "account": account,
              "brief": {"state": "BLOCKED"}, "evidence": {"state": "BLOCKED"},
              "bundle": {"state": "BLOCKED"}, "production_ready": False,
              "publish_authorized": False, "human_review": "PENDING",
              "note": "Read-only input assessment; it does not execute or approve a production step."}
    try:
        path = _project_file(project, "00_brief/brief.json")
        brief = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(brief, dict) or (brief.get("intent") or {}).get("account_id") != account:
            raise ValueError("brief account mismatch")
        verdict = brief_handoff.check(brief)
        result["brief"] = {"state": "READY" if verdict.get("ok") else "BLOCKED",
                           "reason": verdict.get("reason"),
                           "content_digest": verdict.get("content_digest")}
    except OfflineTaskError as exc:
        result["brief"]["reason"] = exc.code
    except (OSError, ValueError, TypeError, AttributeError):
        result["brief"]["reason"] = "BRIEF_MISSING_OR_INVALID"

    try:
        pack = load_pack(_project_file(project, "00_brief/evidence-pack.json"))
        if len(pack.items) > 100:
            raise ValueError("too many evidence items")
        verdict = sufficiency(pack)
        for item in pack.items:
            relative = item.document.replace("\\", "/")
            if relative.startswith("project://"):
                relative = relative[len("project://"):]
            document = _project_file(project, relative)
            if document.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("evidence document too large")
            if not item.sha256 or _sha(document.read_bytes()) != item.sha256:
                raise ValueError("evidence digest mismatch")
        result["evidence"] = {"state": "CHECKED" if verdict.get("ok") else "BLOCKED",
                              "reason": verdict.get("code"),
                              "items": verdict.get("items"),
                              "characters": verdict.get("characters"),
                              "missing": verdict.get("missing")}
    except OfflineTaskError as exc:
        result["evidence"]["reason"] = exc.code
    except (OSError, ValueError, TypeError, AttributeError):
        result["evidence"]["reason"] = "EVIDENCE_MISSING_INVALID_OR_CHANGED"

    try:
        handoff_path = _project_file(project, "receipts/bundle-handoff-video.json")
        record = json.loads(handoff_path.read_text(encoding="utf-8"))
        roles = {"explorer": "x-superplay-1024",
                 "thinktank": "x-superplay-future-intelligence"}
        if (not isinstance(record, dict) or record.get("schema") != HANDOFF_SCHEMA
                or record.get("content_format") != VIDEO
                or record.get("state") != "READY_FOR_PRODUCTION"
                # Bundle handoff stores the directory's slug, while the UI
                # uses _local/<slug> to distinguish repository-local projects.
                or record.get("project_slug") != project.name
                or roles.get(record.get("account")) != account):
            raise ValueError("invalid bundle binding")
        relative = record.get("bundle_path")
        scope = record.get("bundle_scope")
        if not isinstance(relative, str) or not relative.endswith(".json"):
            raise ValueError("invalid bundle path")
        if scope == "project":
            _project_file(project, relative)
        elif scope == "repo" and relative.startswith("projects/"):
            _project_file(repo, relative)
        else:
            raise ValueError("bundle scope is not permitted")
        bundle = verify_bundle_unchanged(record, repo_root=repo, project_dir=project)
        if (bundle.get("bundle_id") != record.get("bundle_id")
                or not isinstance((bundle.get("account_treatments") or {}).get(record["account"]), dict)):
            raise ValueError("bundle treatment mismatch")
        result["bundle"] = {"state": "READY", "bundle_id": record.get("bundle_id"),
                            "bundle_sha256": record.get("bundle_sha256")}
    except OfflineTaskError as exc:
        result["bundle"]["reason"] = exc.code
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        result["bundle"]["reason"] = "BUNDLE_MISSING_INVALID_OR_CHANGED"
    try:
        result["driver"] = _driver_plan_summary(project, repo)
    except (OfflineTaskError, OSError):
        result["driver"] = {"state": "BLOCKED", "reason": "DRIVER_INPUT_UNSAFE"}
    return result


def _render_scaffold(run_id: str, account: str, brief: str, dna: Dict[str, Any]) -> str:
    narrative = dna.get("narrative") or {}
    visual = dna.get("visual") or {}
    duration = narrative.get("target_duration_s", [])
    composition = (visual.get("composition") or {}).get("segments") or []
    composition_text = "、".join(
        f"{item.get('role')} {item.get('pct')}%" for item in composition
        if isinstance(item, dict)
    ) or "DNA 未声明"
    beats = narrative.get("template") or []
    sections = "\n".join(f"## {beat}\n\n待基于真实材料撰写。\n" for beat in beats)
    return (
        "<!-- OFFLINE_SCAFFOLD_ONLY: no model, gateway, or Agent was called. -->\n"
        f"# 离线草稿框架：{dna.get('account', account)}\n\n"
        f"- run_id: `{run_id}`\n- status: `OFFLINE_DRAFT_ONLY`\n"
        f"- production_ready: `false`\n- publish_authorized: `false`\n\n"
        "## 用户任务输入\n\n"
        f"{escape(brief.strip(), quote=False)}\n\n"
        "## 绑定的画像约束\n\n"
        f"- 账号承诺：{dna.get('promise', '未声明')}\n"
        f"- 叙事模式：{narrative.get('mode', '未声明')}\n"
        f"- 语速：{narrative.get('speech_rate_cpm')} 字/分钟\n"
        f"- 时长：{duration} 秒\n- 叙事模板：{' → '.join(map(str, beats)) or '未声明'}\n"
        f"- CTA：{narrative.get('cta', '未声明')}\n- 画面配比：{composition_text}\n\n"
        "## 草稿正文（离线占位）\n\n"
        f"{sections}\n"
        "## 验收边界\n\n"
        "本文件只验证离线请求、画像绑定和回执链路。正文尚未由 Agent 或人工撰写；"
        "不得作为事实证据、生产成片或发布内容。\n"
    )


def _read_supporting_artifact(project: Path, receipt: Dict[str, Any],
                              task_id: str, account: str, project_rel: str) -> Dict[str, Any] | None:
    reference = receipt.get("supporting_artifact")
    if reference is None and receipt.get("status") != "OFFLINE_EVIDENCE_DRAFT":
        return None
    expected_path = f"drafts/easel-offline-{task_id}.artifacts.json"
    if (not isinstance(reference, dict) or set(reference) != {"path", "sha256"}
            or reference.get("path") != expected_path
            or not isinstance(reference.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", reference["sha256"])):
        raise OfflineTaskError("TASK_RECEIPT_INVALID", "supporting artifact binding is invalid", 409)
    path = _project_file(project, expected_path)
    try:
        data = path.read_bytes()
        if _sha(data) != reference["sha256"]:
            raise ValueError("digest mismatch")
        payload = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise OfflineTaskError("TASK_RECEIPT_INVALID", "supporting artifact is unreadable or changed", 409) from None
    if (not isinstance(payload, dict)
            or payload.get("schema") != "contentops.easel-offline-draft-artifacts/v1"
            or payload.get("task_id") != task_id or payload.get("account") != account
            or payload.get("project") != project_rel
            or not all(isinstance(payload.get(key), dict)
                       for key in ("lines", "claim_map", "storyboard", "report"))):
        raise OfflineTaskError("TASK_RECEIPT_INVALID", "supporting artifact contents are invalid", 409)
    return payload


def run_offline_draft_task(*, repo_root: Path, account: str, project_slug: str,
                           brief: str, idempotency_key: str,
                           executor: str = "scaffold") -> Dict[str, Any]:
    """Write one bounded offline scaffold and its receipt under an existing project.

    A repeated key with the same request returns the original receipt. A key
    reused for different input is a conflict. Only one task per project may be
    active at a time; an existing lock fails closed rather than being stolen.
    """
    if executor not in {"scaffold", "evidence"}:
        raise OfflineTaskError("EXECUTOR_INVALID", "unsupported offline executor")
    if not isinstance(brief, str) or not brief.strip() or len(brief) > MAX_BRIEF_CHARS:
        raise OfflineTaskError("INPUT_INVALID", f"brief must contain 1-{MAX_BRIEF_CHARS} characters")
    try:
        brief.encode("utf-8")
    except UnicodeEncodeError:
        raise OfflineTaskError("INPUT_INVALID", "brief must contain valid Unicode text") from None
    if not isinstance(idempotency_key, str) or not IDEMPOTENCY_KEY.fullmatch(idempotency_key):
        raise OfflineTaskError("IDEMPOTENCY_KEY_INVALID", "invalid idempotency key")
    repo = Path(repo_root).resolve(strict=True)
    project, project_rel = _safe_project(repo, project_slug)
    _require_project_account(project, account)
    account_data = _load_dna(account, repo)
    brief = brief.strip()
    request_data = {"account": account, "project": project_rel, "brief": brief}
    if executor != "scaffold":
        request_data["executor"] = executor
    request_sha = _sha(_canonical(request_data))
    key_sha = _sha(idempotency_key.encode("utf-8"))
    receipts = _ensure_child_dir(project, "receipts")
    drafts = _ensure_child_dir(project, "drafts")
    index_path = receipts / f"easel-offline-idempotency-{key_sha}.json"
    lock_path = project / ".easel-offline-task.lock"
    if _linklike(lock_path):
        raise OfflineTaskError("PROJECT_UNSAFE", "project lock may not be a symlink or junction", 403)
    lock_fd = _acquire_project_lock(lock_path)
    task_id = None
    try:
        prior = None
        if _linklike(index_path):
            raise OfflineTaskError("IDEMPOTENCY_STATE_INVALID", "stored idempotency state is unsafe", 409)
        if index_path.exists():
            try:
                prior = json.loads(index_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise OfflineTaskError("IDEMPOTENCY_STATE_INVALID", "stored idempotency receipt is unreadable", 409) from None
            if not isinstance(prior, dict):
                raise OfflineTaskError("IDEMPOTENCY_STATE_INVALID", "stored idempotency state is invalid", 409)
            if prior.get("request_sha256") != request_sha:
                raise OfflineTaskError("IDEMPOTENCY_CONFLICT", "key was already used for different input", 409)
            task_id = prior.get("task_id")
            try:
                if not isinstance(task_id, str) or str(uuid.UUID(task_id)) != task_id:
                    raise ValueError("non-canonical task id")
            except ValueError:
                raise OfflineTaskError("IDEMPOTENCY_STATE_INVALID", "stored task id is invalid", 409) from None
            expected_receipt_rel = f"receipts/easel-offline-{task_id}.json"
            if prior.get("receipt") != expected_receipt_rel:
                raise OfflineTaskError("IDEMPOTENCY_STATE_INVALID", "stored receipt path is invalid", 409)
            if prior.get("status") == "COMPLETE":
                expected_artifact_rel = f"drafts/easel-offline-{task_id}.md"
                if prior.get("artifact") != expected_artifact_rel:
                    raise OfflineTaskError("IDEMPOTENCY_STATE_INVALID", "stored artifact path is invalid", 409)
                receipt_path = project / expected_receipt_rel
                artifact_path = project / expected_artifact_rel
                if (not receipt_path.is_file() or _linklike(receipt_path)
                        or receipt_path.resolve(strict=True).parent != receipts.resolve(strict=True)
                        or not artifact_path.is_file() or _linklike(artifact_path)
                        or artifact_path.resolve(strict=True).parent != drafts.resolve(strict=True)):
                    raise OfflineTaskError("IDEMPOTENCY_STATE_INVALID", "stored receipt is missing or unsafe", 409)
                receipt_bytes = receipt_path.read_bytes()
                artifact_bytes = artifact_path.read_bytes()
                if (_sha(receipt_bytes) != prior.get("receipt_sha256")
                        or _sha(artifact_bytes) != prior.get("artifact_sha256")):
                    raise OfflineTaskError("IDEMPOTENCY_STATE_INVALID", "stored task output changed", 409)
                try:
                    stored_receipt = json.loads(receipt_bytes.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    raise OfflineTaskError("IDEMPOTENCY_STATE_INVALID", "stored receipt is unreadable", 409) from None
                if (not isinstance(stored_receipt, dict)
                        or stored_receipt.get("task_id") != task_id
                        or stored_receipt.get("account") != account
                        or stored_receipt.get("project") != project_rel):
                    raise OfflineTaskError("IDEMPOTENCY_STATE_INVALID", "stored receipt binding is invalid", 409)
                _read_supporting_artifact(project, stored_receipt, task_id, account, project_rel)
                return stored_receipt
            if prior.get("status") != "RUNNING" or not isinstance(prior.get("task_id"), str):
                raise OfflineTaskError("IDEMPOTENCY_STATE_INVALID", "stored task state is invalid", 409)
        else:
            task_id = str(uuid.uuid4())
        draft_rel = f"drafts/easel-offline-{task_id}.md"
        receipt_rel = f"receipts/easel-offline-{task_id}.json"
        draft_path = project / draft_rel
        receipt_path = project / receipt_rel
        if _linklike(draft_path) or _linklike(receipt_path):
            raise OfflineTaskError("PROJECT_UNSAFE", "generated output path may not be a symlink", 403)

        overlay_path = repo / "runtime" / "easel-workbench-overlay.json"
        try:
            overlay_bytes = overlay_path.read_bytes()
            overlay = json.loads(overlay_bytes.decode("utf-8"))
            upstream = overlay.get("upstream") or {}
            easel_commit = upstream.get("commit")
            overlay_record_sha = _sha(overlay_bytes)
            overlay_record_state = "PRESENT_UNVERIFIED"
        except (OSError, ValueError, TypeError):
            easel_commit = None
            overlay_record_sha = None
            overlay_record_state = "UNAVAILABLE"
        evidence_binding = None
        supporting_bytes = None
        if executor == "evidence":
            from ..script.draft import ScriptBlocked, build
            before = project_readiness(repo_root=repo, account=account, project_slug=project_slug)
            if (before["brief"].get("state") != "READY"
                    or before["evidence"].get("state") != "CHECKED"
                    or before["bundle"].get("state") != "READY"):
                raise OfflineTaskError("PROJECT_INPUTS_BLOCKED",
                                       "project Brief, evidence or video Bundle is not ready; inspect project materials", 409)
            pack_path = _project_file(project, "00_brief/evidence-pack.json")
            pack_digest = _sha(pack_path.read_bytes())
            try:
                built = build(project, root=repo)
            except ScriptBlocked as exc:
                raise OfflineTaskError(exc.code, exc.detail, 409) from None
            after = project_readiness(repo_root=repo, account=account, project_slug=project_slug)
            if (before != after or pack_digest != _sha(pack_path.read_bytes())
                    or _load_dna(account, repo)["dna_sha256"] != account_data["dna_sha256"]
                    or built.account_id != account
                    or built.report.get("content_digest") != before["brief"].get("content_digest")):
                raise OfflineTaskError("PROJECT_INPUTS_CHANGED", "project inputs changed during draft generation", 409)
            evidence_binding = {"brief_content_digest": before["brief"]["content_digest"],
                                "evidence_pack_sha256": pack_digest,
                                "bundle_id": before["bundle"]["bundle_id"],
                                "bundle_sha256": before["bundle"]["bundle_sha256"]}
            draft = ("<!-- OFFLINE_EVIDENCE_DRAFT: no Easel Agent or model was called. -->\n"
                     + built.master + "\n")
            report = dict(built.report)
            # These values are host-dependent and would make interrupted-task
            # recovery non-deterministic or disclose an absolute local path.
            report.pop("generated_at", None)
            report["project"] = project_rel
            supporting_bytes = _canonical({
                "schema": "contentops.easel-offline-draft-artifacts/v1",
                "task_id": task_id,
                "account": account,
                "project": project_rel,
                "lines": built.lines,
                "claim_map": built.claim_map,
                "storyboard": built.storyboard,
                "report": report,
            }) + b"\n"
        else:
            draft = _render_scaffold(task_id, account, brief, account_data["dna"])
        draft_bytes = draft.encode("utf-8")
        frontend = _frontend_proof(repo, easel_commit)
        receipt = {
            "schema": "contentops.easel-workbench-task-receipt/v1",
            "task_id": task_id,
            "account": account,
            "project": project_rel,
            "input_sha256": request_sha,
            "dna_sha256": account_data["dna_sha256"],
            "profile_sha256": account_data["profile_sha256"],
            "easel_commit": easel_commit,
            "easel_execution": "NOT_EXECUTED",
            "easel_commit_role": "CANDIDATE_IDENTITY_ONLY",
            "overlay_record_sha256": overlay_record_sha,
            "overlay_verification": overlay_record_state,
            "executor": ("contentops.script.draft" if executor == "evidence"
                         else "deterministic-offline-scaffold"),
            "execution": "OFFLINE_ONLY",
            "status": "OFFLINE_EVIDENCE_DRAFT" if executor == "evidence" else "OFFLINE_DRAFT_ONLY",
            "evidence_binding": evidence_binding,
            "artifact": {"path": draft_rel, "sha256": _sha(draft_bytes)},
            "frontend_build": frontend["status"],
            "frontend_build_manifest_sha256": frontend["manifest_sha256"],
            "frontend_dist_tree_sha256": frontend["dist_tree_sha256"],
            "frontend_file_count": frontend["file_count"],
            "production_ready": False,
            "publish_authorized": False,
            "human_review": "PENDING",
            "failure_reason": None,
            "receipt": receipt_rel,
        }
        supporting_path = None
        if supporting_bytes is not None:
            supporting_rel = f"drafts/easel-offline-{task_id}.artifacts.json"
            supporting_path = project / supporting_rel
            if _linklike(supporting_path):
                raise OfflineTaskError("PROJECT_UNSAFE", "supporting artifact may not be a link", 403)
            receipt["supporting_artifact"] = {"path": supporting_rel,
                                              "sha256": _sha(supporting_bytes)}
        receipt_bytes = _canonical(receipt) + b"\n"
        expected = {"request_sha256": request_sha, "task_id": task_id,
                    "status": "RUNNING", "receipt": receipt_rel,
                    "artifact": draft_rel, "artifact_sha256": _sha(draft_bytes),
                    "receipt_sha256": _sha(receipt_bytes)}
        if supporting_bytes is not None:
            expected["supporting_artifact"] = receipt["supporting_artifact"]
        if prior is not None:
            for field in ("task_id", "receipt", "artifact", "artifact_sha256", "receipt_sha256", "supporting_artifact"):
                if prior.get(field) != expected.get(field):
                    raise OfflineTaskError("IDEMPOTENCY_STATE_INVALID", "pending task does not match its request", 409)
        else:
            _atomic_write(index_path, _canonical(expected) + b"\n")

        outputs = [(draft_path, draft_bytes)]
        if supporting_path is not None:
            outputs.append((supporting_path, supporting_bytes))
        outputs.append((receipt_path, receipt_bytes))
        for output_path, expected_bytes in outputs:
            if output_path.exists():
                if output_path.read_bytes() != expected_bytes:
                    raise OfflineTaskError("OUTPUT_COLLISION", "partial task output does not match its request", 409)
            else:
                _atomic_write(output_path, expected_bytes)
        expected["status"] = "COMPLETE"
        _atomic_write(index_path, _canonical(expected) + b"\n")
        return receipt
    except Exception as exc:
        # Only a validated, project-bound task receives an attempt record.
        # The receipt stores a stable code, never arbitrary exception text or
        # the brief, and does not alter a prior idempotency or success record.
        try:
            valid_task = isinstance(task_id, str) and str(uuid.UUID(task_id)) == task_id
        except ValueError:
            valid_task = False
        if valid_task:
            failure_id = str(uuid.uuid4())
            failure_rel = f"receipts/easel-offline-failure-{failure_id}.json"
            failure_path = project / failure_rel
            code = exc.code if isinstance(exc, OfflineTaskError) else "TASK_INTERNAL_ERROR"
            failure = {"schema": "contentops.easel-workbench-task-failure/v1",
                       "attempt_id": failure_id, "task_id": task_id,
                       "account": account, "project": project_rel,
                       "input_sha256": request_sha, "dna_sha256": account_data["dna_sha256"],
                       "profile_sha256": account_data["profile_sha256"],
                       "easel_commit": locals().get("easel_commit"),
                       "overlay_record_sha256": locals().get("overlay_record_sha"),
                       "frontend_build_manifest_sha256": (locals().get("frontend") or {}).get("manifest_sha256"),
                       "executor": executor, "status": "FAILED", "failure_reason": code,
                       "execution": "OFFLINE_ONLY", "easel_execution": "NOT_EXECUTED",
                       "production_ready": False, "publish_authorized": False,
                       "human_review": "PENDING"}
            try:
                if _linklike(receipts) or receipts.resolve(strict=True).parent != project:
                    raise OSError("unsafe receipt directory")
                with failure_path.open("xb") as output:
                    output.write(_canonical(failure) + b"\n")
                if isinstance(exc, OfflineTaskError):
                    exc.failure_receipt = failure_rel
                    exc.failure_record = failure
                else:
                    wrapped = OfflineTaskError("TASK_INTERNAL_ERROR", "offline task failed", 500)
                    wrapped.failure_receipt = failure_rel
                    wrapped.failure_record = failure
                    raise wrapped from None
            except OSError:
                raise OfflineTaskError("FAILURE_RECEIPT_WRITE_FAILED",
                                       "task failed and its failure receipt could not be written", 500) from None
        raise
    finally:
        _release_project_lock(lock_fd)


def read_offline_failure(*, repo_root: Path, account: str,
                         project_slug: str, attempt_id: str) -> Dict[str, Any]:
    """Read a project-bound failed attempt by its server-generated ID."""
    try:
        if not isinstance(attempt_id, str) or str(uuid.UUID(attempt_id)) != attempt_id:
            raise ValueError("invalid attempt id")
    except ValueError:
        raise OfflineTaskError("TASK_ID_INVALID", "attempt id must be a canonical UUID") from None
    repo = Path(repo_root).resolve(strict=True)
    project, project_rel = _safe_project(repo, project_slug)
    _require_project_account(project, account)
    path = _project_file(project, f"receipts/easel-offline-failure-{attempt_id}.json")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise OfflineTaskError("TASK_RECEIPT_INVALID", "failure receipt is unreadable", 409) from None
    if (not isinstance(record, dict)
            or record.get("schema") != "contentops.easel-workbench-task-failure/v1"
            or record.get("attempt_id") != attempt_id or record.get("account") != account
            or record.get("project") != project_rel or record.get("status") != "FAILED"):
        raise OfflineTaskError("TASK_RECEIPT_INVALID", "failure receipt binding is invalid", 409)
    return record


def read_offline_task_receipt(*, repo_root: Path, account: str,
                              project_slug: str, task_id: str) -> Dict[str, Any]:
    """Read one receipt and its draft, bound to the requested project/account."""
    try:
        if not isinstance(task_id, str) or str(uuid.UUID(task_id)) != task_id:
            raise ValueError("non-canonical task id")
    except ValueError:
        raise OfflineTaskError("TASK_ID_INVALID", "task id must be a canonical UUID") from None
    repo = Path(repo_root).resolve(strict=True)
    project, project_rel = _safe_project(repo, project_slug)
    _require_project_account(project, account)
    _load_dna(account, repo)
    receipts = project / "receipts"
    drafts = project / "drafts"
    if (_linklike(receipts) or _linklike(drafts)
            or not receipts.is_dir() or not drafts.is_dir()):
        raise OfflineTaskError("TASK_NOT_FOUND", "task receipt or draft is unavailable", 404)
    receipt_rel = f"receipts/easel-offline-{task_id}.json"
    artifact_rel = f"drafts/easel-offline-{task_id}.md"
    receipt_path = project / receipt_rel
    artifact_path = project / artifact_rel
    if (_linklike(receipt_path) or _linklike(artifact_path)
            or not receipt_path.is_file() or not artifact_path.is_file()
            or receipt_path.resolve(strict=True).parent != receipts.resolve(strict=True)
            or artifact_path.resolve(strict=True).parent != drafts.resolve(strict=True)):
        raise OfflineTaskError("TASK_NOT_FOUND", "task receipt or draft is unavailable", 404)
    try:
        receipt_bytes = receipt_path.read_bytes()
        receipt = json.loads(receipt_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise OfflineTaskError("TASK_RECEIPT_INVALID", "task receipt is unreadable", 409) from None
    if (not isinstance(receipt, dict)
            or receipt.get("schema") != "contentops.easel-workbench-task-receipt/v1"
            or receipt.get("task_id") != task_id
            or receipt.get("account") != account
            or receipt.get("project") != project_rel
            or receipt.get("receipt") != receipt_rel
            or receipt.get("artifact") != {"path": artifact_rel,
                                            "sha256": _sha(artifact_path.read_bytes())}):
        raise OfflineTaskError("TASK_RECEIPT_INVALID", "task receipt binding or artifact digest is invalid", 409)
    _read_supporting_artifact(project, receipt, task_id, account, project_rel)
    return receipt


def list_offline_tasks(*, repo_root: Path, account: str, project_slug: str) -> Dict[str, Any]:
    """List recent intact offline tasks belonging to the selected project/account."""
    repo = Path(repo_root).resolve(strict=True)
    project, _ = _safe_project(repo, project_slug)
    _require_project_account(project, account)
    _load_dna(account, repo)
    receipts = project / "receipts"
    if _linklike(receipts):
        raise OfflineTaskError("PROJECT_UNSAFE", "receipts directory is linked", 403)
    if not receipts.exists():
        return {"tasks": [], "failures": [], "unavailable_count": 0, "limit": 50}
    if not receipts.is_dir() or receipts.resolve(strict=True).parent != project:
        raise OfflineTaskError("PROJECT_UNSAFE", "receipts directory is unsafe", 403)
    candidates = []
    unavailable = 0
    for path in receipts.glob("easel-offline-*.json"):
        value = path.name.removeprefix("easel-offline-").removesuffix(".json")
        try:
            if str(uuid.UUID(value)) != value:
                continue
            if _linklike(path) or not path.is_file():
                unavailable += 1
                continue
            candidates.append((path.stat().st_mtime_ns, value))
        except (OSError, ValueError):
            continue
    tasks = []
    for _, task_id in sorted(candidates, reverse=True)[:50]:
        try:
            receipt = read_offline_task_receipt(repo_root=repo, account=account,
                                                project_slug=project_slug, task_id=task_id)
        except (OfflineTaskError, OSError):
            unavailable += 1
            continue
        tasks.append({"task_id": task_id, "status": receipt.get("status"),
                      "executor": receipt.get("executor")})
    failures = []
    failure_candidates = []
    for path in receipts.glob("easel-offline-failure-*.json"):
        value = path.name.removeprefix("easel-offline-failure-").removesuffix(".json")
        try:
            if str(uuid.UUID(value)) != value:
                continue
            if _linklike(path) or not path.is_file():
                unavailable += 1
                continue
            failure_candidates.append((path.stat().st_mtime_ns, value))
        except (OSError, ValueError):
            continue
    for _, attempt_id in sorted(failure_candidates, reverse=True)[:50]:
        try:
            record = read_offline_failure(repo_root=repo, account=account,
                                          project_slug=project_slug, attempt_id=attempt_id)
        except (OfflineTaskError, OSError):
            unavailable += 1
            continue
        failures.append({"attempt_id": attempt_id, "reason": record.get("failure_reason")})
    return {"tasks": tasks, "failures": failures, "unavailable_count": unavailable, "limit": 50}


def read_offline_task_artifacts(*, repo_root: Path, account: str,
                                project_slug: str, task_id: str) -> Dict[str, Any]:
    """Return only the checked supporting artifacts for one evidence draft."""
    receipt = read_offline_task_receipt(repo_root=repo_root, account=account,
                                        project_slug=project_slug, task_id=task_id)
    project, project_rel = _safe_project(Path(repo_root).resolve(strict=True), project_slug)
    result = _read_supporting_artifact(project, receipt, task_id, account, project_rel)
    if result is None:
        raise OfflineTaskError("TASK_ARTIFACTS_MISSING", "this task has no supporting artifacts", 404)
    return result


def read_offline_task_draft(*, repo_root: Path, account: str,
                            project_slug: str, task_id: str) -> Dict[str, Any]:
    """Read only the integrity-checked draft belonging to a validated receipt."""
    receipt = read_offline_task_receipt(
        repo_root=repo_root, account=account,
        project_slug=project_slug, task_id=task_id)
    project, _ = _safe_project(Path(repo_root).resolve(strict=True), project_slug)
    artifact_path = project / receipt["artifact"]["path"]
    try:
        content = artifact_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise OfflineTaskError("TASK_DRAFT_INVALID", "task draft is unreadable", 409) from None
    if _sha(content.encode("utf-8")) != receipt["artifact"]["sha256"]:
        raise OfflineTaskError("TASK_DRAFT_INVALID", "task draft digest does not match", 409)
    return {"task_id": task_id, "account": account,
            "project": receipt["project"], "artifact": receipt["artifact"],
            "content": content}
