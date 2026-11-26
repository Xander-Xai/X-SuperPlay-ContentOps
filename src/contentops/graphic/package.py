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
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from contentops.content_kernel.handoff import (
    GRAPHIC_TEXT,
    HANDOFF_SCHEMA,
    HandoffError,
    verify_bundle_unchanged,
)
from contentops.media.rights_gate import RightsError, validate_request_rights
from contentops.publish.x_image import UndecodableImage, image_facts
from contentops.workflow.contract import (
    GRAPHIC_CONTRACT_ID,
    WorkflowError,
    artifact_path,
    is_current,
    load_workflow,
    new_workflow,
    save_workflow,
)
from contentops.graphic.image_methods import (
    CODEX_METHODS,
    GENERATION_RECEIPT_SCHEMA,
    IAN_SKILL_ID,
    IMAGE_METHODS,
    MINIMAX_METHOD,
    REMOTE_GENERATED_LICENSE,
    RETIRED_IMAGE_METHODS,
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


def _generation_record(project: Path, item: Dict[str, Any], method: str,
                       image_path: Path, image_scope: str, image_sha: str,
                       facts: Dict[str, Any], repo_root: Optional[Path],
                       article_path: str, article_sha256: str) -> Dict[str, Any]:
    reference = item.get("generation")
    if not isinstance(reference, dict) or not reference.get("receipt"):
        raise GraphicPackageError(
            "IMAGE_GENERATION_RECEIPT_REQUIRED",
            f"{item.get('asset_id')} needs a project-local generation receipt",
        )
    if image_scope != "project":
        raise GraphicPackageError(
            "IMAGE_GENERATION_PATH_INVALID", "generated image must be inside the project")
    receipt_path, scope = _inside(
        project, reference.get("receipt"), "image generation receipt", repo_root)
    if scope != "project" or receipt_path.is_symlink():
        raise GraphicPackageError(
            "IMAGE_GENERATION_RECEIPT_INVALID", "generation receipt must be a regular project file")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise GraphicPackageError(
            "IMAGE_GENERATION_RECEIPT_INVALID", "generation receipt is unreadable") from None
    if not isinstance(receipt, dict) or receipt.get("schema") != GENERATION_RECEIPT_SCHEMA:
        raise GraphicPackageError("IMAGE_GENERATION_RECEIPT_INVALID", "receipt schema mismatch")
    expected_provider = "openai-codex" if method in CODEX_METHODS else "minimax"
    terms_url = str(receipt.get("terms_url") or "")
    expected_terms = (
        "https://openai.com/policies/terms-of-use/" if method in CODEX_METHODS
        else "https://platform.minimax.io/protocol/terms-of-service"
    )
    logical_image = image_path.relative_to(project).as_posix()
    checks = (
        (receipt.get("generation_id") == reference.get("generation_id"), "generation id"),
        (receipt.get("method") == method, "method"),
        (receipt.get("provider") == expected_provider, "provider"),
        (receipt.get("terms_url") == expected_terms, "terms URL"),
        (receipt.get("output_path") == logical_image, "image path"),
        (receipt.get("output_sha256") == image_sha, "image digest"),
        (receipt.get("width") == facts.get("width"), "image width"),
        (receipt.get("height") == facts.get("height"), "image height"),
        (receipt.get("format") == facts.get("format"), "image format"),
        (receipt.get("generated") is True, "generated flag"),
        (receipt.get("evidence_capable") is False, "evidence capability"),
        (bool(re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("prompt_sha256") or ""))),
         "prompt digest"),
        (bool(str(receipt.get("model") or "").strip()), "model"),
    )
    for ok, label in checks:
        if not ok:
            raise GraphicPackageError(
                "IMAGE_GENERATION_RECEIPT_INVALID", f"receipt {label} does not match the asset")
    if method == "ian_xiaohei_codex":
        if receipt.get("skill_id") != IAN_SKILL_ID:
            raise GraphicPackageError(
                "IMAGE_GENERATION_RECEIPT_INVALID", "Ian route receipt is missing its skill identity")
        if (receipt.get("article_path") != article_path
                or receipt.get("article_sha256") != article_sha256
                or not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("article_sha256") or ""))):
            raise GraphicPackageError(
                "IMAGE_GENERATION_RECEIPT_INVALID", "Ian route article path/hash does not match the packaged draft")
    elif receipt.get("skill_id") or receipt.get("article_path") or receipt.get("article_sha256"):
        raise GraphicPackageError(
            "IMAGE_GENERATION_RECEIPT_INVALID", "unexpected illustration skill/article identity")
    provider_receipt_path = None
    provider_receipt_sha256 = None
    if method == MINIMAX_METHOD:
        provider_receipt_path, provider_scope = _inside(
            project, receipt.get("provider_receipt_path"), "MiniMax provider receipt", repo_root)
        if provider_scope != "project" or _sha(provider_receipt_path) != receipt.get("provider_receipt_sha256"):
            raise GraphicPackageError(
                "IMAGE_GENERATION_RECEIPT_INVALID", "MiniMax receipt digest/scope does not match")
        try:
            provider_receipt = json.loads(provider_receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise GraphicPackageError("IMAGE_GENERATION_RECEIPT_INVALID", "MiniMax receipt is unreadable") from None
        minimax_source = Path(str(provider_receipt.get("provider_receipt_source") or ""))
        minimax_checks = (
            (provider_receipt.get("schema") == "contentops.graphic-minimax-provider-observation/v1", "schema"),
            (provider_receipt.get("generation_id") == receipt.get("generation_id"), "generation id"),
            (provider_receipt.get("provider") == "minimax_m_plan", "provider"),
            (provider_receipt.get("model") == "image-01", "model"),
            (provider_receipt.get("billing_mode") == "subscription", "billing mode"),
            (provider_receipt.get("payg_allowed") is False, "PAYG policy"),
            (provider_receipt.get("credit_pack_allowed") is False, "credit-pack policy"),
            (provider_receipt.get("billing_guard_verdict") == "SAFE_INCLUDED_PLAN", "billing verdict"),
            (provider_receipt.get("output_sha256") == image_sha, "output digest"),
            (provider_receipt.get("prompt_sha256") == receipt.get("prompt_sha256"), "prompt digest"),
            (provider_receipt.get("generated") is True, "generated flag"),
            (provider_receipt.get("evidence_capable") is False, "evidence capability"),
            (bool(re.fullmatch(r"[0-9a-f]{64}", str(provider_receipt.get("provider_receipt_sha256") or ""))),
             "source receipt digest"),
            (not minimax_source.is_absolute() and ".." not in minimax_source.parts, "relative source receipt path"),
        )
        for ok, label in minimax_checks:
            if not ok:
                raise GraphicPackageError(
                    "IMAGE_GENERATION_RECEIPT_INVALID", f"MiniMax provider receipt {label} is invalid")
        provider_receipt_sha256 = receipt["provider_receipt_sha256"]
    elif receipt.get("provider_receipt_path") or receipt.get("provider_receipt_sha256"):
        raise GraphicPackageError(
            "IMAGE_GENERATION_RECEIPT_INVALID", "unexpected provider receipt for Codex route")
    result = {
        "receipt": Path(reference["receipt"]).as_posix(),
        "receipt_sha256": _sha(receipt_path),
        **{key: receipt[key] for key in (
            "generation_id", "method", "provider", "model", "prompt_sha256",
            "output_sha256", "width", "height", "format", "terms_url",
            "generated", "evidence_capable",
        )},
        **({"skill_id": receipt["skill_id"]} if receipt.get("skill_id") else {}),
        **({"article_path": receipt["article_path"],
            "article_sha256": receipt["article_sha256"]}
           if receipt.get("article_path") else {}),
    }
    if provider_receipt_path is not None:
        result["provider_receipt_path"] = provider_receipt_path.relative_to(project.resolve()).as_posix()
        result["provider_receipt_sha256"] = provider_receipt_sha256
    return result


def _validate_remote_rights(project: Path, rights: Dict[str, Any], generation: Dict[str, Any],
                            image_sha: str) -> None:
    if rights.get("license_id") != REMOTE_GENERATED_LICENSE or rights.get("synthetic") is not True:
        raise GraphicPackageError(
            "IMAGE_REMOTE_RIGHTS_REQUIRED",
            "remote generated images need a synthetic remote-generation review record",
        )
    evidence, _ = _inside(project, rights.get("review_evidence"), "remote rights evidence")
    try:
        record = json.loads(evidence.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise GraphicPackageError("IMAGE_REMOTE_RIGHTS_INVALID", "rights evidence is unreadable") from None
    if not isinstance(record, dict):
        raise GraphicPackageError("IMAGE_REMOTE_RIGHTS_INVALID", "rights evidence must be an object")
    expected = {
        "generation_id": generation["generation_id"],
        "asset_sha256": image_sha,
        "terms_url": generation["terms_url"],
    }
    for key, value in expected.items():
        if record.get(key) != value:
            raise GraphicPackageError(
                "IMAGE_REMOTE_RIGHTS_INVALID", f"rights evidence {key} does not match the asset")
    try:
        terms_date = date.fromisoformat(str(record.get("terms_effective_date") or ""))
    except ValueError:
        raise GraphicPackageError(
            "IMAGE_REMOTE_RIGHTS_INVALID", "terms_effective_date must be YYYY-MM-DD") from None
    if terms_date > date.today():
        raise GraphicPackageError(
            "IMAGE_REMOTE_RIGHTS_INVALID", "terms_effective_date cannot be in the future")
    if not str(record.get("permitted_use") or "").strip():
        raise GraphicPackageError("IMAGE_REMOTE_RIGHTS_INVALID", "permitted_use is required")
    if not str(record.get("review_scope") or "").strip():
        raise GraphicPackageError("IMAGE_REMOTE_RIGHTS_INVALID", "review_scope is required")


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
    raw_candidate = base / text
    current = base
    for part in Path(text).parts:
        current = current / part
        if current.is_symlink():
            raise GraphicPackageError("PATH_INVALID", f"{label} must not use symlinks")
    candidate = raw_candidate.resolve()
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


def _images(project: Path, raw: Any, image_method: str,
            repo_root: Optional[Path] = None, article_path: str = "",
            article_sha256: str = "") -> List[Dict[str, Any]]:
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
            facts = image_facts(path)
        except (OSError, UndecodableImage) as exc:
            raise GraphicPackageError("IMAGE_UNDECODABLE", f"{asset_id}: {exc}") from None
        image_sha = _sha(path)
        generation = None
        if image_method in IMAGE_METHODS:
            generation = _generation_record(
                project, item, image_method, path, scope, image_sha,
                facts.as_dict(), repo_root, article_path, article_sha256)
        try:
            reviewed = validate_request_rights(
                {"rights": rights}, project,
                allow_remote_generated=image_method in IMAGE_METHODS)
        except RightsError as exc:
            raise GraphicPackageError("IMAGE_RIGHTS_INVALID", f"{asset_id}: {exc}") from None
        if generation is not None:
            _validate_remote_rights(project, rights, generation, image_sha)
        if scope == "repo":
            logical = "repo://" + path.relative_to(Path(repo_root).resolve()).as_posix()
        else:
            logical = path.relative_to(project.resolve()).as_posix()
        image_record = {
            "asset_id": asset_id,
            "path": logical,
            "scope": scope,
            "sha256": image_sha,
            "bytes": path.stat().st_size,
            "facts": facts.as_dict(),
            "alt": alt,
            "rights": reviewed,
        }
        if generation is not None:
            image_record["generation"] = generation
        result.append(image_record)
    return result


def build_package(project_dir: Path, handoff_path: Path, input_path: Path,
                  registry_root: Optional[Path] = None,
                  repo_root: Optional[Path] = None,
                  bundle_root: Optional[Path] = None,
                  image_method: Optional[str] = None,
                  require_copy_review: bool = False) -> Dict[str, Any]:
    project = Path(project_dir).resolve()
    if not project.is_dir():
        raise GraphicPackageError("PROJECT_MISSING", project.as_posix())
    from contentops.workflow import copy_review, topic_package
    shared_consumer = topic_package.is_declared_consumer(project)
    if shared_consumer:
        lineage = topic_package.status_child(
            project, content_format=GRAPHIC_TEXT, projects_root=project.parent)
        if not lineage.get("ok"):
            raise GraphicPackageError(
                str(lineage.get("state") or "TOPIC_PACKAGE_BLOCKED"),
                str(lineage.get("detail") or "shared topic package is not current"))
    handoff = _load_handoff(Path(handoff_path))
    if bundle_root is not None:
        # The digest in a handoff is only a claim until the Bundle is re-read.
        # A stale handoff must not be able to produce a package.
        try:
            verify_bundle_unchanged(handoff, repo_root=bundle_root, project_dir=project)
        except HandoffError as exc:
            raise GraphicPackageError(exc.code, exc.detail) from None
    try:
        data = json.loads(Path(input_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GraphicPackageError("INPUT_UNREADABLE", str(exc)) from None
    if not isinstance(data, dict):
        raise GraphicPackageError("INPUT_INVALID", "input must be an object")
    raw_input = Path(input_path)
    if not raw_input.is_absolute():
        raw_input = Path.cwd() / raw_input
    try:
        input_relative_path = raw_input.absolute().relative_to(project).as_posix()
    except ValueError:
        raise GraphicPackageError("INPUT_PATH_INVALID", "graphic input must be inside the project") from None
    current_input = project
    for segment in Path(input_relative_path).parts:
        current_input = current_input / segment
        if current_input.is_symlink():
            raise GraphicPackageError("INPUT_PATH_INVALID", "graphic input must not use symlinks")
    input_file = raw_input.resolve()
    graphic_input_relative = input_relative_path
    if not input_file.is_file():
        raise GraphicPackageError("INPUT_PATH_INVALID", "graphic input must be a regular project file")
    review_required = require_copy_review or shared_consumer
    if review_required:
        try:
            copy_review.require_approved(
                project, projects_root=project.parent,
                graphic_input_path=input_file)
        except (copy_review.CopyReviewRequired, ValueError) as exc:
            raise GraphicPackageError("FORMAT_COPY_REVIEW_REQUIRED", str(exc)) from None

    configured_method = str(data.get("image_method") or "").strip()
    selected_method = str(image_method or configured_method or "legacy/unspecified").strip()
    if image_method and configured_method and image_method != configured_method:
        raise GraphicPackageError(
            "IMAGE_METHOD_CONFLICT",
            "--image-method does not match graphic-input.json image_method",
        )
    if selected_method in RETIRED_IMAGE_METHODS:
        raise GraphicPackageError(
            "IMAGE_METHOD_RETIRED",
            f"{selected_method} is retired for new packages; historical receipts remain unchanged",
        )
    if selected_method not in (*IMAGE_METHODS, "legacy/unspecified"):
        raise GraphicPackageError(
            "IMAGE_METHOD_UNKNOWN",
            f"image method must be one of {list(IMAGE_METHODS)}",
        )

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
    draft_logical_path = (
        "repo://" + draft.relative_to(Path(repo_root).resolve()).as_posix()
        if draft_scope == "repo" else draft.relative_to(project).as_posix()
    )
    draft_sha256 = _sha(draft)
    images = _images(
        project, data.get("images"), selected_method, repo_root,
        article_path=draft_logical_path, article_sha256=draft_sha256)
    blockers = list(handoff.get("blockers") or [])
    if platform.get("delivery") == "PLACEHOLDER" and "PLATFORM_PLACEHOLDER" not in blockers:
        blockers.append("PLATFORM_PLACEHOLDER")

    return {
        "schema": PACKAGE_SCHEMA,
        "bundle_id": handoff.get("bundle_id"),
        "bundle_sha256": handoff.get("bundle_sha256"),
        "bundle_path": handoff.get("bundle_path"),
        "bundle_scope": handoff.get("bundle_scope"),
        "account": handoff.get("account"),
        "handoff_sha256": hashlib.sha256(
            Path(handoff_path).read_bytes()).hexdigest(),
        "title": title,
        "image_method": selected_method,
        "copy_review_input_path": graphic_input_relative,
        "copy_review_sha256": (copy_review.copy_fingerprint(project, input_file)
                               if review_required else None),
        "platform": platform,
        "draft": {
            "path": draft_logical_path,
            "scope": draft_scope,
            "sha256": draft_sha256,
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


def verify_package_current(package: Dict[str, Any], project_dir: Path,
                           repo_root: Optional[Path] = None) -> None:
    """Refuse delivery if the bound Bundle, draft, images or rights evidence drifted."""
    if package.get("schema") != PACKAGE_SCHEMA:
        raise GraphicPackageError("PACKAGE_SCHEMA_INVALID", f"expected {PACKAGE_SCHEMA}")

    project = Path(project_dir).resolve()
    from contentops.workflow import copy_review, topic_package
    if topic_package.is_declared_consumer(project):
        lineage = topic_package.status_child(
            project, content_format=GRAPHIC_TEXT, projects_root=project.parent)
        if not lineage.get("ok"):
            raise GraphicPackageError(
                str(lineage.get("state") or "TOPIC_PACKAGE_BLOCKED"),
                str(lineage.get("detail") or "shared topic package is not current"))
    reviewed_sha = package.get("copy_review_sha256")
    input_reference = package.get("copy_review_input_path")
    if reviewed_sha is not None and (not isinstance(input_reference, str) or not input_reference):
        raise GraphicPackageError(
            "FORMAT_COPY_REVIEW_REQUIRED", "package is not bound to a reviewed graphic input")
    if reviewed_sha is not None or topic_package.is_declared_consumer(project):
        review_input = project / input_reference if input_reference else None
        try:
            review = copy_review.require_approved(
                project, projects_root=project.parent,
                graphic_input_path=review_input)
        except (copy_review.CopyReviewRequired, ValueError) as exc:
            raise GraphicPackageError("FORMAT_COPY_REVIEW_REQUIRED", str(exc)) from None
        if reviewed_sha is not None and review.get("copy_sha256") != reviewed_sha:
            raise GraphicPackageError(
                "FORMAT_COPY_REVIEW_REQUIRED", "reviewed copy fingerprint differs from package")
    handoff = {
        "bundle_path": package.get("bundle_path"),
        "bundle_scope": package.get("bundle_scope"),
        "bundle_sha256": package.get("bundle_sha256"),
    }
    try:
        verify_bundle_unchanged(handoff, repo_root=repo_root, project_dir=project)
    except HandoffError as exc:
        raise GraphicPackageError(exc.code, exc.detail) from None

    records = [(package.get("draft") or {}, "draft")]
    records.extend((item, f"images[{index}]")
                   for index, item in enumerate(package.get("images") or []))
    for record, label in records:
        try:
            path, scope = _inside(project, record.get("path"), label, repo_root)
        except GraphicPackageError:
            raise
        expected_scope = record.get("scope")
        if expected_scope and scope != expected_scope:
            raise GraphicPackageError("PACKAGE_INPUT_CHANGED",
                                      f"{label} scope changed from {expected_scope} to {scope}")
        if _sha(path) != record.get("sha256"):
            raise GraphicPackageError("PACKAGE_INPUT_CHANGED",
                                      f"{label} bytes changed after packaging")

        if label.startswith("images["):
            rights = record.get("rights") or {}
            evidence = rights.get("review_evidence")
            evidence_sha = rights.get("review_evidence_sha256")
            if evidence:
                if not evidence_sha:
                    raise GraphicPackageError("RIGHTS_EVIDENCE_UNBOUND",
                                              f"{label} rights evidence has no recorded digest")
                try:
                    evidence_path, _ = _inside(project, evidence,
                                               f"{label}.rights.review_evidence", repo_root)
                except GraphicPackageError:
                    raise
                if _sha(evidence_path) != evidence_sha:
                    raise GraphicPackageError("PACKAGE_INPUT_CHANGED",
                                              f"{label} rights evidence changed after packaging")
            generation = record.get("generation")
            method = package.get("image_method")
            if method in IMAGE_METHODS and not isinstance(generation, dict):
                raise GraphicPackageError(
                    "IMAGE_GENERATION_RECEIPT_REQUIRED",
                    f"{label} requires a generation receipt for {method}",
                )
            if generation:
                if not isinstance(generation, dict):
                    raise GraphicPackageError(
                        "IMAGE_GENERATION_RECEIPT_INVALID",
                        f"{label} generation record must be an object",
                    )
                receipt_path, _ = _inside(
                    project, generation.get("receipt"),
                    f"{label}.generation.receipt", repo_root)
                if _sha(receipt_path) != generation.get("receipt_sha256"):
                    raise GraphicPackageError(
                        "PACKAGE_INPUT_CHANGED",
                        f"{label} generation receipt changed after packaging",
                    )
                provider_receipt = generation.get("provider_receipt_path")
                if provider_receipt:
                    provider_path, _ = _inside(
                        project, provider_receipt,
                        f"{label}.generation.provider_receipt", repo_root)
                    if _sha(provider_path) != generation.get("provider_receipt_sha256"):
                        raise GraphicPackageError(
                            "PACKAGE_INPUT_CHANGED",
                            f"{label} provider receipt changed after packaging",
                        )
            if method in IMAGE_METHODS:
                if generation.get("method") != method:
                    raise GraphicPackageError(
                        "IMAGE_GENERATION_RECEIPT_INVALID",
                        f"{label} generation method does not match the package",
                    )
                try:
                    validate_request_rights(
                        {"rights": rights}, project, allow_remote_generated=True)
                except RightsError as exc:
                    raise GraphicPackageError(
                        "IMAGE_RIGHTS_INVALID", f"{label}: {exc}") from None
                _validate_remote_rights(project, rights, generation, record.get("sha256"))


def verify_graphic_review(project_dir: Path,
                          package: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Require one current copy decision and passing machine quality checks."""
    project = Path(project_dir).resolve()
    workflow_path = project / "workflow.json"
    if not workflow_path.is_file():
        raise GraphicPackageError("GRAPHIC_REVIEW_REQUIRED",
                                  "workflow.json is missing; automated graphic checks have not run")
    try:
        document = load_workflow(workflow_path)
    except WorkflowError as exc:
        raise GraphicPackageError("GRAPHIC_REVIEW_INVALID", str(exc)) from None
    if document.get("contract") != GRAPHIC_CONTRACT_ID:
        raise GraphicPackageError("GRAPHIC_REVIEW_INVALID",
                                  "workflow.json is not a graphic workflow")

    from contentops.workflow import copy_review
    input_ref = (package or {}).get("copy_review_input_path") or "graphic-input.json"
    try:
        review = copy_review.require_approved(
            project, projects_root=project.parent,
            graphic_input_path=project / input_ref)
    except (copy_review.CopyReviewRequired, ValueError) as exc:
        raise GraphicPackageError("FORMAT_COPY_REVIEW_REQUIRED", str(exc)) from None

    quality = next((item for item in document["stages"] if item.get("id") == "quality"), None)
    if not isinstance(quality, dict) or quality.get("status") not in ("checked", "approved"):
        raise GraphicPackageError("GRAPHIC_QC_REQUIRED",
                                  "graphic quality checks have not passed")
    current, reason = is_current(project, document, "quality")
    if not current:
        raise GraphicPackageError("GRAPHIC_QC_STALE", reason)

    try:
        report = json.loads(artifact_path(project, document, "quality").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise GraphicPackageError("GRAPHIC_QC_INVALID",
                                  "graphic quality report is missing or unreadable") from None
    if not isinstance(report, dict) or report.get("overall") != "PASS":
        raise GraphicPackageError("GRAPHIC_QC_BLOCKED", "graphic quality report is not PASS")
    if report.get("blockers"):
        raise GraphicPackageError("GRAPHIC_QC_BLOCKED",
                                  "graphic quality report still contains blockers")
    return {"reviewer": review["reviewer"],
            "copy_sha256": review["copy_sha256"],
            "artifact_sha256": quality.get("check", {}).get("artifact_sha256")}


def _artifact(document: Dict[str, Any], stage_id: str) -> Path:
    for item in document["stages"]:
        if item["id"] == stage_id:
            return Path(item["artifact"])
    raise GraphicPackageError("WORKFLOW_STAGE_MISSING", stage_id)


def write_workflow(project_dir: Path, package: Dict[str, Any],
                   draft_text: str) -> Path:
    """Materialise artifacts and record routine machine checks without approvals."""
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

    brief_path = project / _artifact(document, "brief")
    legacy_router_brief = project / "00_brief" / "brief.json"
    if brief_path.resolve() == legacy_router_brief.resolve() and brief_path.is_file():
        try:
            existing_brief = json.loads(brief_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise GraphicPackageError(
                "BRIEF_PATH_CONFLICT",
                "legacy graphic workflow brief is unreadable; refusing to overwrite it",
            ) from None
        if not isinstance(existing_brief, dict) or existing_brief.get("schema") != "contentops.graphic-brief/v1":
            raise GraphicPackageError(
                "BRIEF_PATH_CONFLICT",
                "legacy graphic workflow points at 00_brief/brief.json, which is not a graphic brief; "
                "refusing to overwrite router-owned or unknown content",
            )

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
        "image_method": package.get("image_method", "legacy/unspecified"),
        "image_role": "support_visual_only",
        "claim_evidence": False,
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
    from contentops.workflow.gate import check_stage

    def validate_quality(path: Path) -> List[str]:
        try:
            report = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ["graphic quality report is unreadable"]
        if not isinstance(report, dict) or report.get("overall") != "PASS":
            return ["graphic quality report is not PASS"]
        if report.get("blockers"):
            return ["graphic quality report contains blockers"]
        checks = report.get("checks") or []
        if any(not isinstance(check, dict) or check.get("ok") is not True for check in checks):
            return ["one or more graphic quality checks failed"]
        return []

    for stage in document.get("stages", []):
        validators = [validate_quality] if stage.get("id") == "quality" else []
        result = check_stage(project, document, stage["id"], validators=validators)
        if not result["ok"]:
            break
    save_workflow(target, document)
    return target


def write_package(project_dir: Path, package: Dict[str, Any],
                  repo_root: Optional[Path] = None) -> Dict[str, Path]:
    project = Path(project_dir).resolve()
    if package.get("schema") != PACKAGE_SCHEMA:
        raise GraphicPackageError("PACKAGE_SCHEMA_INVALID", f"expected {PACKAGE_SCHEMA}")
    draft_path = package["draft"]["path"]
    if draft_path.startswith("repo://"):
        if repo_root is None:
            raise GraphicPackageError("PATH_INVALID",
                                      "package references repo:// without a repository root")
        draft_file = Path(repo_root).resolve() / draft_path[len("repo://"):]
    else:
        draft_file = project / draft_path
    draft = draft_file.read_text(encoding="utf-8")
    workflow_path = write_workflow(project, package, draft)

    receipts = project / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    package_path = receipts / "graphic-package.json"
    package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")

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
    return {"package": package_path, "preview": preview_path, "workflow": workflow_path}


def load_and_build(project_dir: Path, handoff_path: Path, input_path: Path,
                   registry_root: Optional[Path] = None) -> Dict[str, Any]:
    return build_package(project_dir, handoff_path, input_path, registry_root)
