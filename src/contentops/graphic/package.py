"""Build a manual graphic/text delivery package.

This is not a WeChat or Xiaohongshu publisher. It is the fail-closed step that
turns an approved draft and its real images into a reviewable package: copy,
image facts, rights records, ALT text and explicit pending review state.

Nothing here renders HTML, logs in to a platform, writes a draft box or
publishes. The package is always ``AWAITING_MANUAL_REVIEW``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from contentops.content_kernel.handoff import GRAPHIC_TEXT, HANDOFF_SCHEMA
from contentops.media.rights_gate import RightsError, validate_request_rights
from contentops.publish.x_image import UndecodableImage, image_facts
from contentops.workflow.contract import (
    GRAPHIC_CONTRACT_ID,
    load_workflow,
    new_workflow,
    save_workflow,
)

PACKAGE_SCHEMA = "contentops.graphic-package/v1"
MAX_DRAFT_BYTES = 200 * 1024


class GraphicPackageError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inside(project: Path, relative: Any, label: str,
            repo_root: Optional[Path] = None) -> Tuple[Path, str]:
    text = str(relative or "").strip().replace("\\", "/")
    if text.startswith("repo://"):
        if repo_root is None:
            raise GraphicPackageError("PATH_INVALID",
                                      f"{label} uses repo:// without a repository root")
        text = text[len("repo://"):]
        base = Path(repo_root).resolve()
        scope = "repo"
    else:
        base = project.resolve()
        scope = "project"
    if not text or text.startswith("/") or ".." in text.split("/"):
        raise GraphicPackageError("PATH_INVALID", f"{label} must be a safe relative path")
    candidate = (base / text).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise GraphicPackageError("PATH_ESCAPES_PROJECT", f"{label} resolves outside its root")
    if not candidate.is_file():
        raise GraphicPackageError("FILE_MISSING", f"{label} does not exist: {text}")
    return candidate, scope


def _load_handoff(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GraphicPackageError("HANDOFF_UNREADABLE", str(exc)) from None
    if not isinstance(payload, dict) or payload.get("schema") != HANDOFF_SCHEMA:
        raise GraphicPackageError("HANDOFF_INVALID", f"expected {HANDOFF_SCHEMA}")
    if payload.get("content_format") != GRAPHIC_TEXT:
        raise GraphicPackageError("HANDOFF_FORMAT_MISMATCH",
                                  "graphic package input requires a GRAPHIC_TEXT handoff")
    if payload.get("publish_authorized") is not False:
        raise GraphicPackageError("HANDOFF_PUBLISH_FLAG_INVALID",
                                  "a handoff may never carry publish authorization")
    return payload


def _platform(input_data: Dict[str, Any], handoff: Dict[str, Any],
              registry_root: Optional[Path]) -> Dict[str, Any]:
    platform_id = str(input_data.get("platform_id") or "").strip()
    handoff_platform = (handoff.get("platform") or {}).get("platform_id")
    if handoff_platform and platform_id and platform_id != handoff_platform:
        raise GraphicPackageError("PLATFORM_MISMATCH",
                                  f"input targets {platform_id}, handoff targets {handoff_platform}")
    platform_id = platform_id or handoff_platform
    if not platform_id:
        raise GraphicPackageError("PLATFORM_REQUIRED", "a graphic package needs a target platform")
    if registry_root is None:
        return {"platform_id": platform_id, "status": "UNVERIFIED"}
    from contentops.platforms import RegistryError, load_platforms

    try:
        entries = load_platforms(Path(registry_root))
    except RegistryError as exc:
        raise GraphicPackageError("PLATFORM_REGISTRY_INVALID", exc.detail) from None
    entry = entries.get(platform_id)
    if entry is None:
        raise GraphicPackageError("PLATFORM_UNKNOWN", f"{platform_id!r} is not registered")
    if entry.pipeline == "VIDEO":
        raise GraphicPackageError("PLATFORM_FORMAT_MISMATCH",
                                  f"{platform_id} is a video platform")
    return {
        "platform_id": entry.platform_id,
        "strategy_platform": entry.strategy_platform,
        "pipeline": entry.pipeline,
        "status": entry.status,
        "delivery": "PLACEHOLDER" if entry.status == "PLANNED" else "MANUAL_PACKAGE_ONLY",
    }


def _images(project: Path, raw: Any, repo_root: Optional[Path] = None) -> List[Dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise GraphicPackageError("IMAGES_REQUIRED",
                                  "a graphic package needs at least one real image")
    seen = set()
    result = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise GraphicPackageError("IMAGE_INVALID", f"images[{index}] must be an object")
        asset_id = str(item.get("asset_id") or "").strip()
        if not asset_id or asset_id in seen:
            raise GraphicPackageError("IMAGE_ID_INVALID",
                                      f"images[{index}] needs a unique asset_id")
        seen.add(asset_id)
        path, scope = _inside(project, item.get("path"), f"images[{index}].path", repo_root)
        alt = str(item.get("alt") or "").strip()
        if not alt:
            raise GraphicPackageError("IMAGE_ALT_MISSING", f"{asset_id} needs ALT text")
        rights = item.get("rights")
        if not isinstance(rights, dict) or not rights:
            raise GraphicPackageError("IMAGE_RIGHTS_MISSING",
                                      f"{asset_id} needs a reviewed rights block")
        try:
            reviewed = validate_request_rights({"rights": rights}, project)
        except RightsError as exc:
            raise GraphicPackageError("IMAGE_RIGHTS_INVALID", f"{asset_id}: {exc}") from None
        try:
            facts = image_facts(path)
        except (OSError, UndecodableImage) as exc:
            raise GraphicPackageError("IMAGE_UNDECODABLE", f"{asset_id}: {exc}") from None
        if scope == "repo":
            logical = "repo://" + path.relative_to(Path(repo_root).resolve()).as_posix()
        else:
            logical = path.relative_to(project.resolve()).as_posix()
        result.append({
            "asset_id": asset_id,
            "path": logical,
            "scope": scope,
            "sha256": _sha(path),
            "bytes": path.stat().st_size,
            "facts": facts.as_dict(),
            "alt": alt,
            "rights": reviewed,
        })
    return result


def build_package(project_dir: Path, handoff_path: Path, input_path: Path,
                  registry_root: Optional[Path] = None,
                  repo_root: Optional[Path] = None) -> Dict[str, Any]:
    project = Path(project_dir).resolve()
    if not project.is_dir():
        raise GraphicPackageError("PROJECT_MISSING", project.as_posix())
    handoff = _load_handoff(Path(handoff_path))
    try:
        data = json.loads(Path(input_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GraphicPackageError("INPUT_UNREADABLE", str(exc)) from None
    if not isinstance(data, dict):
        raise GraphicPackageError("INPUT_INVALID", "input must be an object")

    title = str(data.get("title") or "").strip()
    if not title:
        raise GraphicPackageError("TITLE_REQUIRED", "a graphic package needs a title")
    if len(title) > 120:
        raise GraphicPackageError("TITLE_TOO_LONG", "title must be at most 120 characters")
    draft, draft_scope = _inside(project, data.get("draft"), "draft", repo_root)
    if draft.suffix.lower() not in (".md", ".txt"):
        raise GraphicPackageError("DRAFT_FORMAT_INVALID", "draft must be Markdown or text")
    draft_bytes = draft.stat().st_size
    if draft_bytes == 0 or draft_bytes > MAX_DRAFT_BYTES:
        raise GraphicPackageError("DRAFT_SIZE_INVALID",
                                  f"draft must be 1..{MAX_DRAFT_BYTES} bytes, got {draft_bytes}")
    try:
        draft.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise GraphicPackageError("DRAFT_NOT_UTF8", "draft must be UTF-8") from None

    platform = _platform(data, handoff, registry_root)
    images = _images(project, data.get("images"), repo_root)
    blockers = list(handoff.get("blockers") or [])
    if platform.get("delivery") == "PLACEHOLDER" and "PLATFORM_PLACEHOLDER" not in blockers:
        blockers.append("PLATFORM_PLACEHOLDER")

    return {
        "schema": PACKAGE_SCHEMA,
        "bundle_id": handoff.get("bundle_id"),
        "bundle_sha256": handoff.get("bundle_sha256"),
        "account": handoff.get("account"),
        "handoff_sha256": hashlib.sha256(
            Path(handoff_path).read_bytes()).hexdigest(),
        "title": title,
        "platform": platform,
        "draft": {
            "path": ("repo://" + draft.relative_to(Path(repo_root).resolve()).as_posix())
                    if draft_scope == "repo"
                    else draft.relative_to(project).as_posix(),
            "scope": draft_scope,
            "sha256": _sha(draft),
            "bytes": draft_bytes,
        },
        "images": images,
        "aigc_provenance": {
            "required": True,
            "disclosure_review_status": "pending",
        },
        "blockers": sorted(set(blockers)),
        "status": "AWAITING_MANUAL_REVIEW",
        "human_review": "NOT_STARTED",
        "production_ready": False,
        "publish_authorized": False,
        "note": "Manual package only. No platform draft, HTML render or publication was performed.",
    }


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def _artifact(document: Dict[str, Any], stage_id: str) -> Path:
    for item in document["stages"]:
        if item["id"] == stage_id:
            return Path(item["artifact"])
    raise GraphicPackageError("WORKFLOW_STAGE_MISSING", stage_id)


def write_workflow(project_dir: Path, package: Dict[str, Any],
                   draft_text: str) -> Path:
    """Materialise the graphic contract's artifacts and leave every stage pending.

    The files make the gate usable; they do not approve any stage. A human still
    runs `workflow_gate.py check` and `approve` stage by stage.
    """
    project = Path(project_dir).resolve()
    target = project / "workflow.json"
    if target.is_file():
        document = load_workflow(target)
        if document.get("contract") != GRAPHIC_CONTRACT_ID:
            raise GraphicPackageError(
                "WORKFLOW_CONTRACT_MISMATCH",
                f"{target.name} is {document.get('contract')}, not {GRAPHIC_CONTRACT_ID}")
    else:
        document = new_workflow(project.name, str(package.get("account") or ""),
                                GRAPHIC_CONTRACT_ID)

    headings = [line.strip() for line in draft_text.splitlines()
                if line.strip().startswith("#")]
    checks = [
        {"id": "draft_nonempty", "ok": bool(draft_text.strip())},
        {"id": "image_present", "ok": bool(package.get("images"))},
        {"id": "image_alt_present",
         "ok": all(bool(image.get("alt")) for image in package.get("images") or [])},
        {"id": "image_rights_present",
         "ok": all(bool((image.get("rights") or {}).get("license_id"))
                   for image in package.get("images") or [])},
    ]
    _write_json(project / _artifact(document, "brief"), {
        "schema": "contentops.graphic-brief/v1",
        "bundle_id": package.get("bundle_id"),
        "bundle_sha256": package.get("bundle_sha256"),
        "title": package.get("title"),
        "platform": package.get("platform"),
    })
    _write_json(project / _artifact(document, "outline"), {
        "schema": "contentops.graphic-outline/v1",
        "headings": headings,
        "source_draft_sha256": package["draft"]["sha256"],
    })
    draft_target = project / _artifact(document, "draft")
    draft_target.parent.mkdir(parents=True, exist_ok=True)
    draft_target.write_text(draft_text, encoding="utf-8")
    _write_json(project / _artifact(document, "images"), {
        "schema": "contentops.graphic-images/v1",
        "images": package.get("images") or [],
    })
    _write_json(project / _artifact(document, "layout"), {
        "schema": "contentops.graphic-layout/v1",
        "preview": "receipts/graphic-preview.md",
        "image_order": [image["asset_id"] for image in package.get("images") or []],
    })
    _write_json(project / _artifact(document, "quality"), {
        "schema": "contentops.graphic-qc/v1",
        "overall": "PASS" if all(check["ok"] for check in checks) else "FAIL",
        "checks": checks,
        "blockers": package.get("blockers") or [],
        "human_review": package.get("human_review"),
    })
    _write_json(project / _artifact(document, "delivery"), {
        "schema": "contentops.graphic-delivery/v1",
        "package": "receipts/graphic-package.json",
        "preview": "receipts/graphic-preview.md",
        "status": package.get("status"),
        "publish_authorized": False,
        "production_ready": False,
    })
    save_workflow(target, document)
    return target


def write_package(project_dir: Path, package: Dict[str, Any],
                  repo_root: Optional[Path] = None) -> Dict[str, Path]:
    project = Path(project_dir).resolve()
    if package.get("schema") != PACKAGE_SCHEMA:
        raise GraphicPackageError("PACKAGE_SCHEMA_INVALID", f"expected {PACKAGE_SCHEMA}")
    receipts = project / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    package_path = receipts / "graphic-package.json"
    package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")

    draft_path = package["draft"]["path"]
    if draft_path.startswith("repo://"):
        if repo_root is None:
            raise GraphicPackageError("PATH_INVALID",
                                      "package references repo:// without a repository root")
        draft_file = Path(repo_root).resolve() / draft_path[len("repo://"):]
    else:
        draft_file = project / draft_path
    draft = draft_file.read_text(encoding="utf-8")
    lines = [f"# {package['title']}", "", draft.strip(), "", "## Images", ""]
    for image in package.get("images") or []:
        lines.append(f"- `{image['asset_id']}` — {image['facts']['width']}x"
                     f"{image['facts']['height']} {image['facts']['format']}")
        lines.append(f"  ![{image['alt']}]({image['path']})")
    lines.extend([
        "",
        "## Review state",
        "",
        f"- status: `{package['status']}`",
        "- publish authorized: **no**",
        f"- blockers: {', '.join(package.get('blockers') or []) or 'none'}",
    ])
    preview_path = receipts / "graphic-preview.md"
    preview_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    workflow_path = write_workflow(project, package, draft)
    return {"package": package_path, "preview": preview_path, "workflow": workflow_path}


def load_and_build(project_dir: Path, handoff_path: Path, input_path: Path,
                   registry_root: Optional[Path] = None) -> Dict[str, Any]:
    return build_package(project_dir, handoff_path, input_path, registry_root)
