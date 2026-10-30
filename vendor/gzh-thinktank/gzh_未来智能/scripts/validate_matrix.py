#!/usr/bin/env python3
"""Static checks for the two-account WeChat matrix.

This validator intentionally performs no network calls and never reads secret
values from ignored files.  It is safe to run in CI or before a draft publish.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Single-account workflow: the required skill set depends on the fixed
# workflow identity (see workflow-identity.yaml).  The entry skill is
# account-specific; the gzh-* canonical family is shared by both.
try:
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "scripts"))
    from account_context import ACCOUNT_ID  # noqa: E402
    from workspace_hygiene import manifest_errors, workspace_errors  # noqa: E402
except Exception as exc:  # pragma: no cover - fail closed if identity is missing
    raise RuntimeError("workflow identity unavailable; validation is blocked") from exc

_ENTRY_SKILL = "ai-sentinel-workflow" if ACCOUNT_ID == "sentinel" else "ai-thinktank-workflow"
REQUIRED_DIRS = (
    _ENTRY_SKILL,
    "gzh-article-orchestrator",
    "gzh-topic-research",
    "gzh-title-seo",
    "wechat-seo-optimizer",
    "gzh-article-writing",
    "gzh-editorial-review",
    "gzh-article-format",
    "gzh-visual-assets",
    "gzh-visual-director",
    "gzh-draft-publisher",
    "gzh-article-assets",
    "gzh-design-skill",
    "source-evidence-layer",
)
REQUIRED_FILES = (
    "profiles/workflow-gates.yaml",
    "profiles/visual-styles.yaml",
    "profiles/visual-model-policy.yaml",
    "skills/vision/SKILL.md",
    "skills/vision/vision.py",
    "profiles/content-checklists.yaml",
    "profiles/thinktank-positioning.yaml",
    "scripts/workflow_gate.py",
    "scripts/workflow_security.py",
    "scripts/receipt_integrity.py",
    "scripts/matrix_init.py",
    "scripts/record_approval.py",
    "scripts/workspace_hygiene.py",
    "scripts/workspace_paths.py",
    "scripts/workspace_audit.py",
    "scripts/migrate_article_workspace.py",
    "scripts/workspace_lifecycle.py",
    "scripts/workspace_isolation_report.py",
    "scripts/test_workspace_paths.py",
    "scripts/update_split_manifest.py",
    "scripts/vision_review.py",
    "scripts/style_lint.py",
    "scripts/test_workflow_hardening.py",
    "scripts/workflow_status.py",
    "scripts/route_content.py",
    "scripts/media_guard.py",
    "scripts/visual_qa.py",
    "scripts/visual_artifact_qa.py",
    "scripts/visual_geometry_qa.py",
    "scripts/visual_aesthetic_qa.py",
    "scripts/visual_reader_test.py",
    "scripts/visual_depth_qa.py",
    "scripts/visual_depth_contract.py",
    "scripts/visual_content_qa.py",
    "scripts/content_truth_qa.py",
    "scripts/check_runtime_dependencies.py",
    "scripts/visual_semantic_qa.py",
    "scripts/visual_semantic_router.py",
    "scripts/build_image_prompt_plan.py",
    "scripts/generate_article_images.py",
    "scripts/render_visual_anchor.py",
    "scripts/render_mobile_preview.py",
    "scripts/record_revision.py",
    "scripts/verify_sources.py",
    "scripts/source_evidence.py",
    "scripts/source_review.py",
    "scripts/cta_contract.py",
    "scripts/validate_handoff.py",
    "scripts/audit_skill_inventory.py",
    "scripts/topic_evidence_isolation.py",
    "scripts/verify_claims.py",
    "scripts/fact_review.py",
    "scripts/sign_approval_events.py",
    "scripts/build_asset_index.py",
    "scripts/checkpoint.py",
    "scripts/import_metrics.py",
    "scripts/reopen_article.py",
    "scripts/test_workflow_gate.py",
    "scripts/test_revision.py",
    "scripts/test_render_mobile_preview.py",
    "scripts/test_routing.py",
    "scripts/test_media_guard.py",
    "scripts/test_publish_guard.py",
    "scripts/test_adversarial_controls_v2.py",
    "scripts/test_visual_qa.py",
    "scripts/test_visual_artifact_qa.py",
    "scripts/test_visual_geometry_qa.py",
    "scripts/test_visual_aesthetic_qa.py",
    "scripts/test_image_prompt_plan.py",
    "scripts/test_agnes_image_provider.py",
    "scripts/test_visual_director.py",
    "skills/gzh-visual-director/SKILL.md",
    "skills/source-evidence-layer/SKILL.md",
    "integrations/diagram_mermaid.py",
    "integrations/x-superplay-strategy.yaml",
    "integrations/x-superplay-strategy-contract.yaml",
    "scripts/test_diagram_adapter.py",
    "scripts/verify_draft_submission.py",
    "scripts/test_draft_verification.py",
    "scripts/bootstrap_article_environment.py",
    "scripts/write_review_evidence.py",
    "scripts/test_review_evidence.py",
    "scripts/test_public_content_safety.py",
    "scripts/test_publish_token_redaction.py",
    "scripts/article_integrity.py",
    "scripts/publish_preflight.py",
    "scripts/test_publish_preflight.py",
    "scripts/test_claim_verifier.py",
    "scripts/test_source_evidence.py",
    "scripts/test_source_review.py",
    "scripts/test_cta_contract.py",
    "scripts/test_handoff_contract.py",
    "scripts/test_post_publish_registry.py",
    "scripts/test_skill_inventory.py",
    "scripts/test_topic_evidence_isolation.py",
    "scripts/test_fact_review.py",
    "scripts/test_signature_events.py",
    "scripts/test_asset_index.py",
    "scripts/test_check_orphan_assets.py",
    "scripts/test_checkpoint.py",
    "scripts/test_metrics_import.py",
    "docs/thinktank-operating-sop.md",
    "docs/article-workspace-governance.md",
    "workspace-contract.yaml",
    "skills/gzh-article-orchestrator/references/presets/structures/AI 项目问题驱动教程结构.md",
)
CORE_SCAN_DIRS = {
    _ENTRY_SKILL,
    "gzh-article-orchestrator",
    "gzh-topic-research",
    "gzh-title-seo",
    "wechat-seo-optimizer",
    "gzh-article-writing",
    "gzh-editorial-review",
    "gzh-article-format",
    "gzh-visual-assets",
    "gzh-draft-publisher",
    "gzh-article-assets",
    "gzh-design-skill",
}

SECRET_PATTERNS = (
    re.compile(r"gho_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]{20,}"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"(?i)\b(?:sk_live_|pk_live_)[A-Za-z0-9]{16,}"),
    re.compile(r"(?:APPSECRET|APP_SECRET)\s*[:=]\s*['\"]?(?!your_|<|\{|\$)[A-Za-z0-9_-]{16,}"),
)

# Public repository files must not expose local installer paths or branding
# from the temporary skill marketplace used during assembly.  Legal notices
# remain the source-of-truth for attribution and are intentionally excluded.
NEUTRALITY_PATTERNS = (
    re.compile(r"(?i)workbuddy"),
    re.compile(r"(?i)aiworkskills"),
    re.compile(r"(?i)origin\.picgo"),
    re.compile(r"摸鱼小李|甲木"),
)
NEUTRALITY_EXCLUDED_NAMES = {"THIRD_PARTY_NOTICES.md", "LICENSE", "NOTICE", "local-self-media-skill-audit.md"}


def check_required_dirs(errors: list[str]) -> None:
    for name in REQUIRED_DIRS:
        path = ROOT / "skills" / name / "SKILL.md"
        if not path.is_file():
            errors.append(f"missing required skill: {path.relative_to(ROOT)}")
    for relative in REQUIRED_FILES:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"missing workflow contract file: {relative}")


def check_markdown_links(errors: list[str]) -> None:
    # Only validate local Markdown links; URLs and fragment-only links are not
    # filesystem references.
    pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for md in ROOT.rglob("*.md"):
        if ".git" in md.parts or "node_modules" in md.parts:
            continue
        if "skills" in md.parts:
            skill_index = md.parts.index("skills")
            if len(md.parts) <= skill_index + 1 or md.parts[skill_index + 1] not in CORE_SCAN_DIRS:
                continue
        try:
            text = md.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for raw in pattern.findall(text):
            target = raw.strip().split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:", "data:", "javascript:")):
                continue
            if target in {"URL", "url", "link", "placeholder", "图片", "图像", "封面图", "公众号二维码"}:
                continue
            if ".aws-article" in target:
                continue
            if not (target.startswith(("./", "../", "skills/")) or "/" in target or Path(target).suffix):
                continue
            if target.startswith("skills/"):
                candidate = ROOT / target
            else:
                candidate = (md.parent / target).resolve()
            if not candidate.exists():
                errors.append(f"broken local link: {md.relative_to(ROOT)} -> {raw}")


def check_profile_contract(errors: list[str]) -> None:
    for name in ("shared.yaml", f"{ACCOUNT_ID}.yaml"):
        path = ROOT / "profiles" / name
        if not path.is_file():
            errors.append(f"missing profile: {path.relative_to(ROOT)}")
    shared = (ROOT / "profiles" / "shared.yaml").read_text(encoding="utf-8")
    for key in ("default_publish_mode: draft", "human_approval_required:", "artifact_contract:"):
        if key not in shared:
            errors.append(f"shared profile missing contract key: {key}")
    visual = (ROOT / "profiles" / "visual-styles.yaml").read_text(encoding="utf-8")
    theme = "sentinel-radar" if ACCOUNT_ID == "sentinel" else "thinktank-atlas"
    for key in (theme, "require_cover_selection_approval"):
        if key not in visual:
            errors.append(f"visual profile missing contract key: {key}")


def check_article_artifact_contract(errors: list[str]) -> None:
    gates = (ROOT / "profiles" / "workflow-gates.yaml").read_text(encoding="utf-8")
    for artifact in (
        "content-brief.yaml",
        "content-revision.json",
        "seo-report.json",
        "sources.json",
        "source-verification.json",
        "source-review.json",
        "evidence-plan.json",
        "source-evidence.json",
        "evidence-provenance.json",
        "evidence-lineage.json",
        "topic-evidence-isolation.json",
        "review-evidence.json",
        "review-checks.json",
        "format-report.json",
        "image-sources.json",
        "final-review.md",
        "ai-disclosure.yaml",
        "publish-preflight.json",
        "publish-attempt.json",
        "preview-capture.json",
    ):
        if artifact not in gates:
            errors.append(f"workflow gate contract missing artifact: {artifact}")


def check_registry_contract(errors: list[str]) -> None:
    path = ROOT / "skills" / "skill-registry.yaml"
    if not path.is_file():
        errors.append("missing skill registry: skills/skill-registry.yaml")
        return
    text = path.read_text(encoding="utf-8")
    for raw in re.findall(r"^\s+path:\s+([^\s#]+)", text, flags=re.M):
        candidate = ROOT / raw
        if not candidate.exists():
            errors.append(f"registry path does not exist: {raw}")
    for key in (
        "content_strategy",
        "content_production",
        "content_humanizer",
        "visual_quality",
        "article_environment",
        "article_gate_contract",
        "content_revision_contract",
        "browser_preview",
    ):
        if f"  {key}:" not in text:
            errors.append(f"registry missing shared supporting capability: {key}")
    if "optional_capabilities:" not in text or "post_publish_adapters:" not in text:
        errors.append("registry must separate optional capabilities and post-publish adapters")
    for adapter in ("analytics", "z5_review", "fallback_publisher", "cross_platform_repurpose"):
        block = re.search(rf"(?ms)^  {re.escape(adapter)}:\s*\n(.*?)(?=^  [A-Za-z0-9_-]+:\s*$|\Z)", text)
        if not block:
            errors.append(f"registry missing post-publish adapter: {adapter}")
            continue
        body = block.group(1)
        for marker in ("activation: opt-in", "requires: final_reviewed", "guard: media_guard"):
            if marker not in body:
                errors.append(f"registry adapter {adapter} missing {marker}")
    try:
        from skill_resolver import validate as validate_skill_registry
        errors.extend(f"skill-resolver: {error}" for error in validate_skill_registry())
    except Exception as exc:
        errors.append(f"skill-resolver unavailable: {exc}")


def _scan_paths() -> list[Path]:
    """Return the files that participate in current-identity scans.

    A8（对抗审查）：优先用 split-manifest.json 的 allowlist 计算扫描范围；
    无 manifest 时回退到全量 rglob，但排除归档/依赖/运行目录——历史归档目录
    （skills/_archive）中的来源品牌字样属于预期留存，不应作为当前身份违规。
    git 仓库存在时仍以 git ls-files 为准（凭证与忽略文件天然不进入输入）。
    """
    import subprocess

    try:
        output = subprocess.check_output(
            ["git", "ls-files"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        )
        return [ROOT / line.strip() for line in output.splitlines() if line.strip()]
    except (OSError, subprocess.CalledProcessError):
        pass

    manifest_path = ROOT / "split-manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            files = manifest.get("files") if isinstance(manifest, dict) else []
            paths = []
            for item in files:
                if isinstance(item, dict) and str(item.get("path", "")).strip():
                    paths.append(ROOT / str(item["path"]).replace("\\", "/"))
            if paths:
                return [p for p in paths if p.is_file()]
        except (OSError, ValueError):
            pass

    excluded_roots = {
        "_archive",
        ".git",
        "node_modules",
        "__pycache__",
        "drafts",
        ".aws-article",
        "posts",
        "outputs",
        "dist",
        "build",
    }
    return [
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and not any(part in excluded_roots for part in p.relative_to(ROOT).parts)
        and p.suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif", ".zip", ".ttf"}
    ]


def check_tracked_text_for_secrets(errors: list[str]) -> None:
    # Use git's tracked-file list when available so ignored credentials never
    # become part of this scan's input or output.
    for path in _scan_paths():
        if not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".zip", ".ttf"}:
            continue
        if path.name.startswith("test_"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"possible secret in tracked file: {path.relative_to(ROOT)}")
                break


def check_public_neutrality(errors: list[str]) -> None:
    """Reject accidental local marketplace/source branding in public files.

    A8：归档目录（skills/_archive）只做 provenance 校验（存在性），不参与
    当前身份品牌扫描——历史留存的来源品牌字样属于预期，不得误报。
    """
    archive = ROOT / "skills" / "_archive"
    archive_exists = archive.is_dir()
    for path in _scan_paths():
        if (
            not path.is_file()
            or path.resolve() == (ROOT / "scripts" / "validate_matrix.py").resolve()
            or path.name in NEUTRALITY_EXCLUDED_NAMES
            or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".zip", ".ttf"}
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in NEUTRALITY_PATTERNS:
            if pattern.search(text):
                errors.append(f"source branding/path remains in tracked file: {path.relative_to(ROOT)}")
                break
    # 归档目录 provenance 校验：存在且包含预期的 aws-wechat-* 子目录时视为受控留存。
    if archive_exists:
        moved = sorted(p.name for p in archive.glob("aws-wechat-*") if p.is_dir())
        if len(moved) != 9:
            errors.append(f"skills/_archive 归档不完整：期望 9 个 aws-wechat-* 目录，实际 {len(moved)} 个")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-links", action="store_true", help="skip local Markdown link checks")
    args = parser.parse_args()
    errors: list[str] = []
    check_required_dirs(errors)
    check_profile_contract(errors)
    check_article_artifact_contract(errors)
    check_registry_contract(errors)
    errors.extend(f"workspace hygiene: {item}" for item in workspace_errors(ROOT))
    errors.extend(f"manifest integrity: {item}" for item in manifest_errors(ROOT))
    if not args.no_links:
        check_markdown_links(errors)
    check_tracked_text_for_secrets(errors)
    check_public_neutrality(errors)
    if errors:
        print("MATRIX VALIDATION FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("MATRIX VALIDATION PASSED")
    print(f"root={ROOT}")
    print(f"required_skills={len(REQUIRED_DIRS)}")
    print(f"required_workflow_files={len(REQUIRED_FILES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
