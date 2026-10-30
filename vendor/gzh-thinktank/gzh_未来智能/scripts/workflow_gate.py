#!/usr/bin/env python3
"""Deterministic, sequential gates for a WeChat article workspace.

The content workflow is deliberately treated as a state machine.  A gate can
only be advanced after every earlier gate passes, and ``--advance`` writes the
new state only after all checks have succeeded.  The script performs no
network calls; the final gate validates the already-created draft receipt.

Examples:
    python scripts/workflow_gate.py --article <external-active/THK-...> \
        --stage environment_ready --env D:/secrets/aws.env --advance
    python scripts/workflow_gate.py --article <external-active/THK-...> \
        --stage draft_submitted --env D:/secrets/aws.env
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Windows consoles commonly default to GBK. Gate diagnostics are evidence for
# operators, so do not let a non-GBK label turn a failed gate into a traceback.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from article_integrity import (  # noqa: E402
    canonical_html_digest,
    canonical_text_sha256_file,
    is_sha256,
    is_text_evidence_path,
    public_content_findings,
    sha256_file,
    stable_sha256_file,
)
from receipt_integrity import verify as verify_receipt_integrity  # noqa: E402
from workflow_security import (  # noqa: E402
    StateConflict,
    content_snapshot,
    ensure_article_path,
    load_json as strict_load_json,
    load_yaml as strict_load_yaml,
    state_lock,
)
from skill_resolver import resolve as resolve_skill  # noqa: E402
from route_content import load_route, route_digest, validate_route_document  # noqa: E402
from visual_backend_registry import validate_record  # noqa: E402
from formula_pipeline import find_unrendered_math_literals  # noqa: E402
from stage_contract import validate_stage_contract  # noqa: E402
from source_evidence import MARKDOWN_START, MARKDOWN_END, _validate_plan as validate_hybrid_evidence  # noqa: E402
from source_review import validate as validate_source_review  # noqa: E402
from topic_evidence_isolation import validate as validate_topic_evidence  # noqa: E402
from topic_integrity import validate_contract as validate_topic_contract, check_alignment as check_topic_alignment  # noqa: E402
from record_approval import approval_event_map  # noqa: E402
from cta_contract import validate as validate_cta_contract  # noqa: E402
from validate_handoff import validate as validate_handoff_card  # noqa: E402
from account_context import (  # noqa: E402
    ACCOUNT_ID, ACCOUNT_IDS, DISPLAY_NAME, PUBLISH_SLOT, FORMATTER_THEME,
    IMAGE_THEME, check_identity_consistency,
)


VALIDATOR = ROOT / "skills" / "gzh-design-skill" / "scripts" / "validate_gzh_html.py"
def _runtime_script(name: str) -> Path:
    """Resolve a gate helper through the v2 registry; fail closed on drift."""

    return resolve_skill(name, section="runtime_scripts").entrypoint


VISUAL_QA = _runtime_script("visual_qa")
VISUAL_SEMANTIC_QA = _runtime_script("visual_semantic_qa")
VISUAL_DEPTH_QA = _runtime_script("visual_depth_qa")
VISUAL_AESTHETIC_QA = _runtime_script("visual_aesthetic_qa")
VISUAL_TASTE_REVIEW = _runtime_script("visual_taste_review")
VISUAL_ROUTE_CONSISTENCY = _runtime_script("visual_route_consistency")
VISION_REVIEW = _runtime_script("vision_review")
# Content-level diagram QA is intentionally a local hard gate.  It validates
# visible topology/compare/code/checklist structure instead of trusting labels
# or geometry metadata alone.
VISUAL_CONTENT_QA = ROOT / "scripts" / "visual_content_qa.py"
CONTENT_TRUTH_QA = ROOT / "scripts" / "content_truth_qa.py"
VISUAL_READER_TEST = ROOT / "scripts" / "visual_reader_test.py"
STYLE_LINT = _runtime_script("style_lint")
FORMULA_SOURCE_CHECK = _runtime_script("formula_source_check")
FORMULA_PIPELINE = ROOT / "scripts" / "formula_pipeline.py"
PROFILES = ROOT / "profiles"
REFERENCE_PRESETS = ROOT / "skills" / "gzh-article-orchestrator" / "references" / "presets"

REQUIRED_PRESET_DIRS = (
    "structures",
    "closing-blocks",
    "title-styles",
    "formatting",
    "cover-styles",
    "image-styles",
    "sticker-styles",
)
REVIEW_CHECKS = ("content", "facts", "sensitivity", "spelling", "humanizer")
REVIEWER_TYPES = {"agent", "human"}
RISK_LEVELS = {"low", "medium", "high", "critical"}


@dataclass(frozen=True)
class Gate:
    key: str
    label: str


GATES = (
    Gate("environment_ready", "环境与账号就绪"),
    Gate("topic_selected", "选题确认"),
    Gate("research_complete", "调研与实测完成"),
    Gate("research_reviewed", "研究来源审查通过"),
    Gate("draft_complete", "初稿完成"),
    Gate("content_reviewed", "内容审稿通过"),
    Gate("formatted", "微信排版通过"),
    Gate("illustrated", "配图与素材通过"),
    Gate("final_reviewed", "终审通过"),
    Gate("draft_submitted", "草稿提交并回读"),
)
GATE_KEYS = tuple(g.key for g in GATES)
STATUS_TO_GATE = {
    "selected": "none",
    "researched": "research_complete",
    "research_reviewed": "research_reviewed",
    "drafted": "draft_complete",
    "reviewed": "content_reviewed",
    "formatted": "formatted",
    "illustrated": "illustrated",
    "final_reviewed": "final_reviewed",
    "draft_submitted": "draft_submitted",
}

# 增强 4：human-in-the-loop 抽样频率——正文图达到该数量后，每批随机抽 1 张
# 要求人工二审（final-review.md 记录 sampled_image_reviewed: true）。
HUMAN_SAMPLE_EVERY = 3


def _read_yaml(path: Path) -> dict[str, Any]:
    """Read YAML with duplicate-key rejection; malformed input fails closed."""

    value = strict_load_yaml(path, default={})
    return value if isinstance(value, dict) else {}


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _refresh_pending_reader_packet(article_dir: Path) -> list[str]:
    """Rebind an unanswered reader packet after deterministic contract checks.

    A pending packet contains no human judgement, so rebuilding its article,
    visual-contract and visual-depth hashes is safe and prevents routine QA
    reruns from leaving a stale receipt.  A packet with any response, or a
    passed/failed decision, is evidence and is never rewritten automatically.
    """

    path = article_dir / "visual-reader-test.json"
    doc = _json(path)
    if (
        doc.get("contract") != "visual-reader-test-v1"
        or doc.get("status") != "pending-human"
        or (isinstance(doc.get("responses"), list) and doc.get("responses"))
    ):
        return []
    expected = {
        "article_sha256": sha256_file(article_dir / "article.md") if (article_dir / "article.md").is_file() else "",
        "visual_contract_sha256": sha256_file(article_dir / "visual-contract.json") if (article_dir / "visual-contract.json").is_file() else "",
        "visual_depth_review_sha256": sha256_file(article_dir / "visual-depth-review.json") if (article_dir / "visual-depth-review.json").is_file() else "",
    }
    if all(str(doc.get(key) or "") == value for key, value in expected.items()):
        return []
    if not VISUAL_READER_TEST.is_file():
        return [f"读者测试包刷新器缺失：{VISUAL_READER_TEST}"]
    reviewer_id = str(doc.get("reviewer_id") or "unassigned-human-reader").strip()
    result = subprocess.run(
        [
            sys.executable,
            str(VISUAL_READER_TEST),
            "--article",
            str(article_dir),
            "--reviewer-id",
            reviewer_id,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode:
        detail = (result.stdout + result.stderr).strip().splitlines()
        return ["visual-reader-test pending 包自动重绑失败：" + (detail[-1] if detail else "无输出")]
    return []


def _reader_receipt_errors(article_dir: Path, reader_doc: dict[str, Any]) -> list[str]:
    """A passed reader test must carry an independent human approval proof."""

    if reader_doc.get("status") != "passed":
        return []
    errors: list[str] = []
    approval = reader_doc.get("approval")
    if not isinstance(approval, dict):
        return ["visual-reader-test.json status=passed 但缺少独立 approval 对象"]
    for key in ("approval_event_id", "reviewer_id", "signed_by", "signed_at"):
        if not str(approval.get(key) or "").strip():
            errors.append(f"visual-reader-test.json approval 缺少 {key}")
    if str(approval.get("contract") or "") != "visual-reader-approval-v1":
        errors.append("visual-reader-test.json approval contract 必须是 visual-reader-approval-v1")
    if approval.get("errors"):
        errors.append("visual-reader-test.json approval.errors 非空；真人测试证明无效")
    # A local answers file is not an independent identity boundary.  Reuse the
    # external approval-event policy required for other high-risk reviews.
    if not os.environ.get("APPROVAL_SIGNATURE_POLICY_PATH", "").strip() or not os.environ.get("APPROVAL_SIGNATURE_KEY_PATH", "").strip():
        errors.append("reader passed receipt 必须配置外部 APPROVAL_SIGNATURE_POLICY_PATH/APPROVAL_SIGNATURE_KEY_PATH")
    return errors


def _public_content_errors(text: str, artifact: str) -> list[str]:
    errors: list[str] = []
    for finding in public_content_findings(text):
        errors.append(
            f"{artifact} 包含不应公开的 {finding['rule']} 标记（第 {finding['line']} 行）；"
            "请改用脱敏占位符后重新审稿"
        )
    return errors


def _requires_structured_review(article_dir: Path) -> bool:
    state = _json(article_dir / "matrix-state.json")
    try:
        return int(state.get("schema_version", 0)) >= 3
    except (TypeError, ValueError):
        return False


def _structured_review_errors(article_dir: Path) -> list[str]:
    path = article_dir / "review-checks.json"
    data = _json(path)
    errors: list[str] = []
    if not path.is_file():
        return ["缺少 review-checks.json；新版本流程必须结构化记录审稿人和检查项"]
    if data.get("status") != "passed":
        errors.append("review-checks.json 的 status 必须是 passed")
    reviewer_type = str(data.get("reviewer_type", "")).strip().lower()
    if reviewer_type not in REVIEWER_TYPES:
        errors.append("review-checks.json 的 reviewer_type 必须是 agent 或 human")
    if not str(data.get("reviewer", "")).strip():
        errors.append("review-checks.json 缺少 reviewer")
    if not _parse_iso_date(data.get("reviewed_at")):
        errors.append("review-checks.json 缺少有效 reviewed_at")
    article_path = article_dir / "article.md"
    report_path = article_dir / "review-report.md"
    digest_fn = stable_sha256_file if data.get("digest_mode") == "stable-text-v1" else sha256_file
    if data.get("article_digest") and data.get("article_digest") != digest_fn(article_path):
        errors.append("review-checks.json 的 article_digest 与当前 article.md 不一致")
    if data.get("report_digest") and data.get("report_digest") != digest_fn(report_path):
        errors.append("review-checks.json 的 report_digest 与当前 review-report.md 不一致")
    checks = data.get("checks")
    if not isinstance(checks, dict):
        errors.append("review-checks.json 缺少 checks 对象")
    else:
        for key in REVIEW_CHECKS:
            if checks.get(key) != "passed":
                errors.append(f"review-checks.json 未通过 {key} 检查")
    if not isinstance(data.get("findings", []), list):
        errors.append("review-checks.json 的 findings 必须是列表")
    return errors


def _errors_for_revision(article_dir: Path, require_final: bool = False) -> list[str]:
    """Validate explicit new/reused content provenance and freshness hashes."""

    errors: list[str] = []
    path = article_dir / "content-revision.json"
    revision = _json(path)
    if not path.is_file():
        return ["缺少 content-revision.json；必须明确本篇是新稿还是复用稿"]
    if revision.get("status") != "passed":
        errors.append("content-revision.json 的 status 必须是 passed")
    mode = str(revision.get("mode", "")).strip().lower()
    if mode not in {"new", "reused"}:
        errors.append("content-revision.json 的 mode 必须是 new 或 reused")
    if not str(revision.get("operator", "")).strip():
        errors.append("content-revision.json 缺少 operator")
    if not str(revision.get("change_summary", "")).strip():
        errors.append("content-revision.json 缺少 change_summary；必须说明本次内容变化")
    if not _parse_iso_date(revision.get("created_at")):
        errors.append("content-revision.json 缺少有效 created_at")

    draft_path = article_dir / "draft.md"
    draft_digest = str(revision.get("draft_digest", "")).strip().lower()
    if not draft_path.is_file():
        errors.append("缺少 draft.md；无法验证内容新鲜度")
    elif not is_sha256(draft_digest) or draft_digest != stable_sha256_file(draft_path):
        errors.append("content-revision.json 的 draft_digest 与当前 draft.md 不一致；请重新记录 revision")

    source = revision.get("source")
    if not isinstance(source, dict):
        errors.append("content-revision.json 缺少 source 对象")
    elif mode == "reused":
        if revision.get("reuse_approved") is not True:
            errors.append("复用稿必须记录 reuse_approved: true")
        source_path = str(source.get("path", "")).strip()
        source_digest = str(source.get("sha256", "")).strip().lower()
        if not source_path:
            errors.append("复用稿 source 缺少 path")
        else:
            candidate = Path(source_path).expanduser()
            if not candidate.is_absolute():
                candidates = (article_dir / candidate, ROOT / candidate)
                candidate = next((item for item in candidates if item.is_file()), candidates[0])
            if not candidate.is_file():
                errors.append(f"复用来源不存在：{source_path}")
            elif not is_sha256(source_digest) or source_digest != stable_sha256_file(candidate):
                errors.append(f"复用来源 SHA-256 不匹配：{source_path}")
    elif mode == "new" and revision.get("reuse_approved") is True:
        errors.append("new 模式不能标记 reuse_approved: true")

    article_path = article_dir / "article.md"
    final_digest = str(revision.get("final_digest", "")).strip().lower()
    if require_final:
        if not article_path.is_file():
            errors.append("缺少 article.md；无法绑定最终稿新鲜度")
        elif not is_sha256(final_digest) or final_digest != stable_sha256_file(article_path):
            errors.append("content-revision.json 的 final_digest 与当前 article.md 不一致；请重新执行 record_revision.py --finalize")
        if not _parse_iso_date(revision.get("finalized_at")):
            errors.append("content-revision.json 缺少有效 finalized_at")
    elif final_digest and article_path.is_file() and final_digest != stable_sha256_file(article_path):
        errors.append("article.md 已变化但 content-revision.json 未重新 finalize")
    return errors


def _json(path: Path) -> dict[str, Any]:
    value = strict_load_json(path, default={})
    return value if isinstance(value, dict) else {}


def _hybrid_evidence_paths(article_dir: Path) -> set[str]:
    """Return image paths owned by the source-evidence appendix."""
    document = _json(article_dir / "source-evidence.json")
    result: set[str] = set()
    for source in document.get("sources", []) if isinstance(document, dict) else []:
        if not isinstance(source, dict):
            continue
        for unit in source.get("evidence", []) if isinstance(source.get("evidence"), list) else []:
            if isinstance(unit, dict) and str(unit.get("kind", "")).lower() in {"screenshot", "diagram", "code", "pdf"}:
                raw = str(unit.get("path", "")).strip().replace("\\", "/")
                if raw:
                    result.add(raw)
    return result


def _account(article_dir: Path) -> str:
    # Single-account workflow: account is fixed by workflow-identity.yaml.
    # The article_dir argument is kept for call compatibility; the returned
    # value is always the unique legal account of this target.
    return ACCOUNT_ID


def _profile_limits(article_dir: Path) -> tuple[int, int]:
    """Return account-specific minimum and maximum content lengths."""
    account = _account(article_dir)
    profile = _read_yaml(PROFILES / f"{account}.yaml")
    raw = str(profile.get("content_length", "2500-5000"))
    match = re.search(r"(\d+)\s*[-~]\s*(\d+)", raw)
    if not match:
        return (2500, 5000)
    return (int(match.group(1)), int(match.group(2)))


def _chars(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def _preset_dirs() -> list[Path]:
    """Return only preset roots owned by this split target."""
    return [
        ROOT / ".aws-article" / "presets",
        REFERENCE_PRESETS,
    ]


def _preset_name_list(value: Any) -> tuple[list[str], bool]:
    """Normalize a preset candidate list and report scalar misuse."""
    if value is None:
        return [], False
    if not isinstance(value, list):
        return [], True
    return [str(item).strip() for item in value if str(item).strip()], False


def _preset_exists(subdir: str, name: str, extensions: tuple[str, ...]) -> bool:
    for root in _preset_dirs():
        for extension in extensions:
            if (root / subdir / f"{name}{extension}").is_file():
                return True
    return False


def _parse_iso_date(value: Any) -> bool:
    if not str(value or "").strip():
        return False
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _external_env_value(args: argparse.Namespace | None) -> str:
    """Resolve an explicitly supplied, repository-external credential file."""

    cli_value = getattr(args, "env", None) if args is not None else None
    return str(
        cli_value
        or os.environ.get("CONTENT_ENV_PATH")
        or os.environ.get("WECHAT_ENV_PATH")
        or ""
    ).strip()


def _external_env_path(args: argparse.Namespace | None) -> Path | None:
    value = _external_env_value(args)
    return Path(value).expanduser().resolve() if value else None


def _publish_env_path(args: argparse.Namespace | None) -> Path | None:
    cli_value = getattr(args, "env", None) if args is not None else None
    value = str(cli_value or os.environ.get("WECHAT_ENV_PATH") or "").strip()
    return Path(value).expanduser().resolve() if value else None


def _path_is_inside_repository(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _errors_for_environment(article_dir: Path, args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    config_path = ROOT / ".aws-article" / "config.yaml"
    if not config_path.is_file():
        errors.append("缺少 .aws-article/config.yaml；不能开始内容生产")
        return errors
    config = _read_yaml(config_path)
    article_meta_path = article_dir / "article.yaml"
    article_meta = _read_yaml(article_meta_path) if article_meta_path.is_file() else {}
    if not article_meta_path.is_file():
        errors.append("本篇缺少 article.yaml；必须先锁定标题、作者和账号")
    account = str(article_meta.get("account", "")).strip().lower()
    if account != ACCOUNT_ID:
        errors.append(f"article.yaml 的 account 必须是 {ACCOUNT_ID}（本工作流唯一账号，收到 {account!r}）")
    identity_problems = check_identity_consistency()
    if identity_problems:
        errors.extend(f"workflow 身份不一致: {problem}" for problem in identity_problems)
    route_path = article_dir / "routing.yaml"
    if not route_path.is_file():
        errors.append("缺少 routing.yaml；必须先完成选题路由和账号路由")
    else:
        route = load_route(route_path)
        errors.extend(validate_route_document(route, expected_account=account or None))
        state = _json(article_dir / "matrix-state.json")
        try:
            state_schema = int(state.get("schema_version", 0) or 0)
        except (TypeError, ValueError):
            state_schema = 0
        if state_schema < 4:
            errors.append("工作区必须使用带 routing.yaml 的 schema v4；请通过 matrix_init.py --route 重建或迁移")
        if str(article_meta.get("content_medium", "")).strip().lower() != "wechat_article":
            errors.append("article.yaml 的 content_medium 必须是 wechat_article")
        if not article_meta.get("route_digest"):
            errors.append("article.yaml 缺少 route_digest；不能确认路由未被替换")
        elif str(article_meta.get("route_digest")).lower() != route_digest(route_path):
            errors.append("article.yaml 的 route_digest 与 routing.yaml 不一致")
        if not state.get("routing_digest"):
            errors.append("matrix-state.json 缺少 routing_digest；不能确认路由未被替换")
        elif str(state.get("routing_digest")).lower() != route_digest(route_path):
            errors.append("matrix-state.json 的 routing_digest 与 routing.yaml 不一致")
        if str(state.get("content_medium", "")).strip().lower() != "wechat_article":
            errors.append("matrix-state.json 的 content_medium 必须是 wechat_article")
    for key in ("article_category", "target_reader", "default_author"):
        if not str(config.get(key, "")).strip():
            errors.append(f".aws-article/config.yaml 缺少全局账号字段：{key}")
    aws_root = ROOT / ".aws-article"
    for name in REQUIRED_PRESET_DIRS:
        if not (aws_root / "presets" / name).is_dir():
            errors.append(f"缺少本地预设目录：.aws-article/presets/{name}；请先运行 bootstrap_article_environment.py")
    if not (aws_root / "tmp").is_dir():
        errors.append("缺少 .aws-article/tmp；请先运行 bootstrap_article_environment.py")
    merged_preset_source = dict(config)
    merged_preset_source.update(article_meta)
    for field, subdir, extensions in (
        ("default_structure", "structures", (".md",)),
        ("default_closing_block", "closing-blocks", (".md",)),
    ):
        names, scalar = _preset_name_list(merged_preset_source.get(field))
        if scalar:
            errors.append(f"{field} 须为 YAML 列表，不能使用字符串")
        for name in names:
            if not _preset_exists(subdir, name, extensions):
                errors.append(f"{field} 指向的预设不存在：{name}")
    if config.get("publish_method", "draft") not in {"draft", "none", "published"}:
        errors.append("publish_method 必须是 draft、none 或 published")
    if config.get("publish_method", "draft") != "none":
        try:
            slot = int(config.get("wechat_publish_slot", 1) or 1)
        except (TypeError, ValueError):
            slot = 1
            errors.append("config.yaml 中 wechat_publish_slot 必须是整数")
        if slot != int(PUBLISH_SLOT):
            errors.append(
                f"config.yaml 的 wechat_publish_slot 必须与固定工作流槽位 {PUBLISH_SLOT} 一致（当前 {slot}）"
            )
        try:
            account_count = int(config.get("wechat_accounts", 0) or 0)
        except (TypeError, ValueError):
            account_count = 0
            errors.append("config.yaml 中 wechat_accounts 必须是整数")
        if account_count < int(PUBLISH_SLOT):
            errors.append(f"config.yaml 的 wechat_accounts 未覆盖固定槽位 {PUBLISH_SLOT}")
    # A7：外部图像能力必须由本篇 capability profile 显式声明。纯
    # deterministic SVG/HTML 或用户供图文章不应被 Agnes 凭证耦合阻断；
    # 但缺少 profile 时仍 fail-closed，避免静默绕过外部依赖策略。
    capability_path = article_dir / "capability-profile.json"
    capability = _json(capability_path)
    if not capability_path.is_file():
        errors.append("缺少 capability-profile.json；必须显式声明外部图像 API 与离线策略")
        external_image_required = True
    else:
        if capability.get("contract") != "capability-profile-v1":
            errors.append("capability-profile.json 的 contract 必须是 capability-profile-v1")
        if not isinstance(capability.get("external_image_api_required"), bool):
            errors.append("capability-profile.json 的 external_image_api_required 必须是布尔值")
        if not isinstance(capability.get("selected_backends"), list) or not capability.get("selected_backends"):
            errors.append("capability-profile.json 必须声明至少一个 selected_backends")
        external_image_required = capability.get("external_image_api_required") is True
    if external_image_required:
        image = config.get("image_model") or {}
        if not (
            isinstance(image, dict)
            and str(image.get("provider", "")).strip().lower() == "agnes"
            and str(image.get("model", "")).strip() == "agnes-image-2.1-flash"
            and str(image.get("base_url", "")).strip().rstrip("/") == "https://apihub.agnes-ai.com/v1/images/generations"
        ):
            errors.append("图片模型必须固定为 Agnes Image 2.1 Flash")
        env_path = _external_env_path(args)
        if env_path is None or not env_path.is_file():
            errors.append(
                "当前能力配置需要 Agnes，但缺少显式仓库外内容凭证文件；"
                "请通过 --env 或 CONTENT_ENV_PATH 指定"
            )
        elif _path_is_inside_repository(env_path):
            errors.append("外部内容凭证文件不能位于仓库内；请移出 aws.env/.env")
        else:
            env_names = {
                line.split("=", 1)[0].strip()
                for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines()
                if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", line.strip())
            }
            if "AGNES_API_KEY" not in env_names:
                errors.append("外部凭证缺少 AGNES_API_KEY")
    return errors


def _errors_for_topic(article_dir: Path) -> list[str]:
    errors: list[str] = []
    errors.extend(f"主题合同：{error}" for error in validate_topic_contract(article_dir))
    card = _text(article_dir / "topic-card.md")
    metadata = _read_yaml(article_dir / "article.yaml") if (article_dir / "article.yaml").is_file() else {}
    route_doc = _read_yaml(article_dir / "routing.yaml") if (article_dir / "routing.yaml").is_file() else {}
    topic_route = route_doc.get("topic_route") if isinstance(route_doc.get("topic_route"), dict) else {}
    reference = str(topic_route.get("reference") or "").strip()
    if str(topic_route.get("mode") or "").strip().lower() == "user_material" and reference.lower().replace("\\", "/").endswith("handoff-card.md"):
        handoff_path = Path(reference).expanduser()
        if not handoff_path.is_absolute():
            handoff_path = ROOT / handoff_path
        errors.extend(f"handoff 合同：{error}" for error in validate_handoff_card(handoff_path.resolve()))
    brief_path = article_dir / "content-brief.yaml"
    brief = _read_yaml(brief_path) if brief_path.is_file() else {}
    if len(card.strip()) < 80:
        errors.append("topic-card.md 太短，必须填写问题、读者、判断和来源")
    for marker in ("账号：", "目标读者：", "核心判断：", "主要来源：", "可搜索关键词：", "可分享角度："):
        if marker not in card:
            errors.append(f"选题卡缺少字段：{marker}")
    if re.search(r"(?i)\b(pending|todo|待补|待定)\b", card):
        errors.append("选题卡仍有 pending/TODO/待补字段")
    for key in ("title", "author", "digest"):
        if not str(metadata.get(key, "")).strip():
            errors.append(f"article.yaml 缺少 {key}")
    if not brief_path.is_file():
        errors.append("缺少 content-brief.yaml；选题必须先锁定内容策略简报")
    else:
        if str(brief.get("account", "")).strip().lower() != str(metadata.get("account", "")).strip().lower():
            errors.append("content-brief.yaml 的 account 与 article.yaml 不一致")
        for key in ("audience", "primary_keyword", "shareable_angle", "primary_claim", "cta"):
            if not str(brief.get(key, "")).strip():
                errors.append(f"content-brief.yaml 缺少 {key}")
        risk_level = str(brief.get("risk_level", "")).strip().lower()
        if risk_level not in RISK_LEVELS:
            errors.append("content-brief.yaml 的 risk_level 必须是 low、medium、high 或 critical")
        if not isinstance(brief.get("human_review_required"), bool):
            errors.append("content-brief.yaml 的 human_review_required 必须是布尔值")
        elif risk_level in {"high", "critical"} and brief.get("human_review_required") is not True:
            errors.append("high/critical 风险内容必须设置 human_review_required: true")
        if str(brief.get("status", "")).strip().lower() in {"pending", "draft", ""}:
            errors.append("content-brief.yaml 尚未完成确认，status 不能是 pending/draft")
    seo_path = article_dir / "seo-report.json"
    seo = _json(seo_path)
    if not seo_path.is_file():
        errors.append("缺少 seo-report.json；标题与搜一搜诊断必须结构化留痕")
    else:
        if seo.get("status") != "passed":
            errors.append("seo-report.json 的 status 必须是 passed")
        try:
            seo_score = float(seo.get("score"))
            if seo_score < 70:
                errors.append(f"SEO 综合分 {seo_score:g} 低于门禁最低分 70")
        except (TypeError, ValueError):
            errors.append("seo-report.json 缺少数值 score")
        if not isinstance(seo.get("keywords"), list) or not seo.get("keywords"):
            errors.append("seo-report.json 必须记录至少一个关键词")
        if _account(article_dir) == "sentinel":
            try:
                if float(seo.get("title_score")) < 85:
                    errors.append("AI哨兵标题评分低于 85，不能进入正文写作")
            except (TypeError, ValueError):
                errors.append("AI哨兵 seo-report.json 缺少 title_score")
    config = _read_yaml(ROOT / ".aws-article" / "config.yaml")
    title_max = config.get("title_max_length")
    if title_max is not None:
        try:
            limit = int(title_max)
            title = str(metadata.get("title", "")).strip()
            if len(title) > limit:
                errors.append(f"标题长度 {len(title)} 超过 config.yaml 的 title_max_length={limit}")
        except (TypeError, ValueError):
            errors.append("config.yaml 的 title_max_length 必须是整数")
    return errors


def _errors_for_research(article_dir: Path) -> list[str]:
    errors: list[str] = []
    research = _text(article_dir / "research.md")
    if _chars(research) < 180:
        errors.append("research.md 证据不足，至少需要来源、版本/环境、复现命令和限制说明")
    required_evidence = {
        "来源": ("来源", "官方", "证据"),
        "版本": ("版本", "环境"),
        "可复现": ("可复现", "命令", "运行"),
        "限制": ("限制", "风险", "边界"),
    }
    for label, markers in required_evidence.items():
        if not any(marker in research for marker in markers):
            errors.append(f"调研记录缺少字段：{label}")
    if re.search(r"(?i)\b(pending|todo|待补|待定)\b", research):
        errors.append("调研记录仍有 pending/TODO/待补字段")
    source_path = article_dir / "sources.json"
    sources_doc = _json(source_path)
    sources = sources_doc.get("sources")
    if not source_path.is_file():
        errors.append("缺少 sources.json；来源必须结构化留痕")
    elif not isinstance(sources, list) or not sources:
        errors.append("sources.json 必须包含至少 1 条来源记录")
    else:
        source_ids: set[str] = set()
        for index, source in enumerate(sources, 1):
            if not isinstance(source, dict):
                errors.append(f"sources.json 第 {index} 条不是对象")
                continue
            source_id = str(source.get("id", "")).strip()
            if not source_id:
                errors.append(f"sources.json 第 {index} 条缺少稳定 id")
            elif source_id in source_ids:
                errors.append(f"sources.json 第 {index} 条 id 重复：{source_id}")
            else:
                source_ids.add(source_id)
            if not str(source.get("title", "")).strip():
                errors.append(f"sources.json 第 {index} 条缺少 title")
            if not _parse_iso_date(source.get("retrieved_at")):
                errors.append(f"sources.json 第 {index} 条 retrieved_at 不是有效 ISO 日期")
            if source.get("published_at") and not _parse_iso_date(source.get("published_at")):
                errors.append(f"sources.json 第 {index} 条 published_at 不是有效 ISO 日期")
            kind = str(source.get("kind", "external")).strip().lower()
            url = str(source.get("url", "")).strip()
            local_path = str(source.get("path", "")).strip()
            if kind in {"local_artifact", "reproduction", "test-fixture"}:
                if not local_path:
                    errors.append(f"sources.json 第 {index} 条本地证据缺少 path")
                else:
                    artifact_path = Path(local_path).expanduser()
                    if not artifact_path.is_absolute():
                        artifact_path = article_dir / artifact_path
                    if not artifact_path.is_file():
                        errors.append(f"sources.json 第 {index} 条本地证据文件不存在：{local_path}")
                    else:
                        recorded_hash = str(source.get("sha256", "")).strip().lower()
                        hash_mode = str(source.get("hash_mode", "raw")).strip().lower()
                        if hash_mode not in {"raw", "canonical-text"}:
                            errors.append(
                                f"sources.json 第 {index} 条本地证据 hash_mode 无效：{hash_mode}"
                            )
                        elif is_text_evidence_path(artifact_path) and hash_mode == "canonical-text":
                            try:
                                expected_hash = canonical_text_sha256_file(artifact_path)
                            except UnicodeDecodeError:
                                errors.append(
                                    f"sources.json 第 {index} 条本地证据声明 canonical-text，但不是 UTF-8 文本：{local_path}"
                                )
                            else:
                                if not is_sha256(recorded_hash) or recorded_hash != expected_hash:
                                    errors.append(f"sources.json 第 {index} 条本地证据 sha256 不匹配：{local_path}")
                        elif not is_sha256(recorded_hash) or recorded_hash != sha256_file(artifact_path):
                            errors.append(f"sources.json 第 {index} 条本地证据 sha256 不匹配：{local_path}")
            elif not re.match(r"^https?://[^\s]+$", url):
                errors.append(f"sources.json 第 {index} 条缺少有效 HTTP(S) URL")
            if not str(source.get("evidence_level", "")).strip():
                errors.append(f"sources.json 第 {index} 条缺少 evidence_level")
            if kind not in {"local_artifact", "reproduction", "test-fixture"}:
                try:
                    freshness_days = int(source.get("freshness_days"))
                    if freshness_days < 1 or freshness_days > 365:
                        raise ValueError
                except (TypeError, ValueError):
                    errors.append(f"sources.json 第 {index} 条缺少有效 freshness_days（1-365）")
                if not str(source.get("official_source") or "").strip():
                    errors.append(f"sources.json 第 {index} 条缺少 official_source 说明")
            if _requires_structured_review(article_dir) and kind not in {"local_artifact", "reproduction", "test-fixture"}:
                if source.get("retrieval_status") != "passed":
                    errors.append(f"sources.json 第 {index} 条外部来源未通过实际抓取验证")
                try:
                    int(source.get("http_status"))
                except (TypeError, ValueError):
                    errors.append(f"sources.json 第 {index} 条缺少 http_status")
                if not is_sha256(source.get("content_sha256")):
                    errors.append(f"sources.json 第 {index} 条缺少 content_sha256")
        claims = sources_doc.get("claims")
        if not isinstance(claims, list) or not claims:
            errors.append("sources.json 必须包含 claims；每条事实/结果都要映射到来源")
        else:
            claim_ids: set[str] = set()
            for index, claim in enumerate(claims, 1):
                if not isinstance(claim, dict):
                    errors.append(f"sources.json 第 {index} 条 claim 不是对象")
                    continue
                claim_id = str(claim.get("id", "")).strip()
                if not claim_id:
                    errors.append(f"sources.json 第 {index} 条 claim 缺少 id")
                elif claim_id in claim_ids:
                    errors.append(f"sources.json claim id 重复：{claim_id}")
                else:
                    claim_ids.add(claim_id)
                if not str(claim.get("statement", "")).strip():
                    errors.append(f"sources.json 第 {index} 条 claim 缺少 statement")
                claim_refs = claim.get("source_ids") if isinstance(claim.get("source_ids"), list) else []
                referenced_external = any(
                    isinstance(s, dict)
                    and str(s.get("id", "")).strip() in {str(ref).strip() for ref in claim_refs}
                    and str(s.get("kind", "external")).strip().lower() not in {"local_artifact", "reproduction", "test-fixture"}
                    for s in sources_doc.get("sources", [])
                )
                if referenced_external and not _parse_iso_date(claim.get("as_of")):
                    errors.append(f"sources.json 第 {index} 条 claim 缺少有效 as_of（主张有效时间）")
                # A10（对抗审查）：claim 必须声明类型；若带定位器则必须是
                # 结构对象或对象列表。多来源 claim 需要逐一覆盖来源，和
                # verify_claims.py 的 locator contract 保持一致。
                if not str(claim.get("claim_type", "")).strip():
                    errors.append(f"sources.json 第 {index} 条 claim 缺少 claim_type（benchmark/mechanism/paper-fact/test-result/...）")
                evidence_locator = claim.get("evidence_locator")
                if evidence_locator is not None:
                    valid_locator = isinstance(evidence_locator, dict) or (
                        isinstance(evidence_locator, list)
                        and bool(evidence_locator)
                        and all(isinstance(item, dict) for item in evidence_locator)
                    )
                    if not valid_locator:
                        errors.append(
                            f"sources.json 第 {index} 条 claim 的 evidence_locator 必须是对象或对象列表（kind/页码/commit/run_id 等）"
                        )
                refs = claim.get("source_ids")
                if not isinstance(refs, list) or not refs:
                    errors.append(f"sources.json 第 {index} 条 claim 缺少 source_ids")
                else:
                    for ref in refs:
                        if str(ref).strip() not in source_ids:
                            errors.append(f"sources.json claim {claim_id or index} 引用了不存在的来源：{ref}")
                claim_type = str(claim.get("claim_type", "")).strip().lower()
                if claim_type in {"mechanism", "implementation", "api", "benchmark", "test-result"} and refs:
                    for ref in refs:
                        source_entry = next((s for s in sources_doc.get("sources", []) if isinstance(s, dict) and str(s.get("id", "")).strip() == str(ref).strip()), {})
                        if str(source_entry.get("kind", "external")).strip().lower() not in {"local_artifact", "reproduction", "test-fixture"} and not str(source_entry.get("version_scope") or source_entry.get("package_version") or "").strip():
                            errors.append(f"claim {claim_id or index} 的来源 {ref} 缺少 version_scope/package_version")

    # ── A1（对抗审查）：外部来源必须由验证器指纹化，禁止自填哈希 ──────────
    # sources.json 的 content_sha256 必须是验证器回执的产物，且回执声称的
    # 快照文件必须存在、哈希可复核。任何“只填 64 位十六进制、无快照”的来源
    # 都无法通过 research_complete。
    external_ids = {
        str(source.get("id", "")).strip()
        for source in sources_doc.get("sources", [])
        if isinstance(source, dict)
        and str(source.get("kind", "external")).strip().lower() not in {"local_artifact", "reproduction", "test-fixture"}
        and str(source.get("id", "")).strip()
    }
    if external_ids:
        verification_path = article_dir / "source-verification.json"
        verification = _json(verification_path)
        if not verification_path.is_file():
            errors.append("存在外部来源但缺少 source-verification.json；请运行 scripts/verify_sources.py 指纹化后重试")
        else:
            if verification.get("contract") != "source-verification-v1":
                errors.append("source-verification.json 的 contract 必须是 source-verification-v1")
            if not _parse_iso_date(verification.get("verified_at")):
                errors.append("source-verification.json 缺少有效 verified_at")
            verified_records = verification.get("sources")
            if not isinstance(verified_records, list):
                errors.append("source-verification.json 缺少 sources 回执列表")
                verified_records = []
            verified_by_id = {
                str(record.get("id", "")).strip(): record
                for record in verified_records
                if isinstance(record, dict) and str(record.get("id", "")).strip()
            }
            for source_id in sorted(external_ids):
                record = verified_by_id.get(source_id)
                if record is None:
                    errors.append(f"外部来源 {source_id} 没有验证器回执")
                    continue
                source_entry = next(
                    (s for s in sources_doc.get("sources", []) if isinstance(s, dict) and str(s.get("id", "")).strip() == source_id),
                    {},
                )
                if str(source_entry.get("content_sha256", "")).strip().lower() != str(record.get("content_sha256", "")).strip().lower():
                    errors.append(f"来源 {source_id} 的 content_sha256 与验证器回执不一致")
                snapshot_raw = str(record.get("snapshot", "")).strip()
                if not snapshot_raw:
                    errors.append(f"来源 {source_id} 回执缺少快照文件记录")
                    continue
                snapshot_path = article_dir / snapshot_raw
                if not snapshot_path.is_file():
                    errors.append(f"来源 {source_id} 的回执快照文件不存在：{snapshot_raw}")
                elif not is_sha256(record.get("snapshot_sha256")) or str(record.get("snapshot_sha256", "")).lower() != sha256_file(snapshot_path):
                    errors.append(f"来源 {source_id} 的回执快照哈希与文件不一致：{snapshot_raw}")
                if not str(record.get("url_normalized", "")).strip():
                    errors.append(f"来源 {source_id} 回执缺少 url_normalized")
    # New workspaces opt into the hybrid evidence layer via matrix_init.  Keep
    # older historical fixtures readable, but make every new article prove
    # source tiering, a real evidence unit, attribution and content hashes.
    if (article_dir / "evidence-plan.json").is_file():
        evidence_errors, _ = validate_hybrid_evidence(article_dir, require_appendix=False, require_provenance=True)
        errors.extend(f"hybrid-evidence: {error}" for error in evidence_errors)
        isolation_errors, _ = validate_topic_evidence(article_dir)
        errors.extend(f"topic-evidence-isolation: {error}" for error in isolation_errors)
        lineage_path = article_dir / "evidence-lineage.json"
        lineage = _json(lineage_path) if lineage_path.is_file() else None
        if not isinstance(lineage, dict):
            errors.append("hybrid-evidence: 缺少 evidence-lineage.json；请重新运行 source_evidence.py audit")
        else:
            if lineage.get("contract") != "evidence-lineage-v1":
                errors.append("hybrid-evidence: evidence-lineage.json contract 无效")
            if lineage.get("status") != "passed":
                errors.append("hybrid-evidence: evidence-lineage.json 的 status 必须是 passed")
            if lineage.get("identity_authenticated") is not False:
                errors.append("hybrid-evidence: evidence-lineage.json 必须明确 identity_authenticated: false")
            run = lineage.get("run")
            job = lineage.get("job")
            if not isinstance(run, dict) or not str(run.get("run_id", "")).strip():
                errors.append("hybrid-evidence: evidence-lineage.json 缺少 run.run_id")
            if not isinstance(job, dict) or not str(job.get("name", "")).strip():
                errors.append("hybrid-evidence: evidence-lineage.json 缺少 job.name")
    return errors


def _section_count(text: str) -> int:
    return len(re.findall(r"^##\s+", text, flags=re.M))


def _image_marker_count(text: str) -> int:
    return len(re.findall(r"!\[[^\]]*\]\([^)]*\)", text))


def _errors_for_research_review(article_dir: Path) -> list[str]:
    """Require an explicit relevance/scope review before source reuse.

    ``research_complete`` proves retrieval, provenance and evidence integrity;
    this separate gate proves that every declared source was actually read at
    a bounded level, compared with the topic, and either included conditionally
    or excluded with a reason.  It intentionally does not replace semantic
    fact review for high-consequence claims.
    """

    return [f"source-review: {error}" for error in validate_source_review(article_dir)]


def _errors_for_draft(article_dir: Path) -> list[str]:
    errors: list[str] = []
    errors.extend(_errors_for_revision(article_dir))
    errors.extend(check_topic_alignment(article_dir, "draft.md"))
    draft = _text(article_dir / "draft.md")
    minimum, maximum = _profile_limits(article_dir)
    length = _chars(draft)
    if length < minimum:
        errors.append(f"初稿有效字数 {length}，当前账号至少 {minimum}")
    if length > maximum * 1.25:
        errors.append(f"初稿有效字数 {length}，超过当前账号建议上限 {maximum} 的 125%")
    if not re.search(r"^#\s+", draft, flags=re.M):
        errors.append("初稿缺少一级标题")
    sections = _section_count(draft)
    images = _image_marker_count(draft)
    if sections < 3:
        errors.append("初稿至少需要 3 个二级章节")
    if images < sections + 1:
        errors.append(f"初稿图片占位不足：需要封面 + 每个章节 1 张，当前 {images} 个、章节 {sections} 个")
    # Image placeholders are required at this stage.  Only unresolved TODO or
    # 待补 markers are blocking; prose explaining the placeholder contract is
    # allowed and is checked again after illustration.
    draft_without_image_markers = re.sub(r"!\[[^\]]*\]\(placeholder\)", "", draft, flags=re.I)
    if re.search(r"(?i)\bTODO\b|待补", draft_without_image_markers):
        errors.append("初稿残留 TODO/待补内容")
    account = _account(article_dir)
    if account == "sentinel" and not re.search(r"结论|判断|值得|不值得|评分|建议", draft):
        errors.append("AI哨兵初稿必须出现明确的结论、价值判断或建议")
    if account == "thinktank" and not re.search(r"步骤|部署|教程|实践|代码|常见问题|原理|拆解", draft):
        errors.append("X超玩•未来智能初稿必须出现教程、原理、步骤、代码或常见问题结构")
    return errors


def _cta_errors(article_dir: Path, text: str | None = None) -> list[str]:
    """Require a useful, auditable follow/lead action for v2 Thinktank work."""
    brief_path = article_dir / "content-brief.yaml"
    if not brief_path.is_file():
        return []
    brief = _read_yaml(brief_path)
    account = str(brief.get("account") or _account(article_dir)).strip().lower()
    if account != "thinktank":
        return []
    # Backward-compatible for legacy fixtures; matrix_init now writes schema 2
    # so every new article receives the stronger contract automatically.
    if not (brief.get("public_brand") or brief.get("primary_cta") or int(brief.get("schema_version", 1) or 1) >= 2):
        return []
    errors: list[str] = []
    errors.extend(f"CTA 合同：{error}" for error in validate_cta_contract(article_dir))
    brand = str(brief.get("public_brand") or "").strip()
    primary = str(brief.get("primary_cta") or brief.get("cta") or "").strip()
    secondary = str(brief.get("secondary_cta") or "").strip()
    magnet = str(brief.get("lead_magnet") or "").strip()
    keyword = str(brief.get("reply_keyword") or "").strip()
    primary_keyword = str(brief.get("primary_keyword") or "").strip()
    canonical_topic = str(brief.get("canonical_topic") or "").strip()
    if not canonical_topic:
        topic_contract = _read_yaml(article_dir / "topic-contract.yaml") if (article_dir / "topic-contract.yaml").is_file() else {}
        canonical_topic = str(topic_contract.get("canonical_topic") or "").strip()
    offer = str(brief.get("commercial_offer") or "").strip()
    for field, value in (("public_brand", brand), ("primary_cta", primary), ("secondary_cta", secondary), ("lead_magnet", magnet), ("reply_keyword", keyword), ("commercial_offer", offer)):
        if not value:
            errors.append(f"content-brief.yaml 缺少转化字段 {field}")
    body = text if text is not None else _text(article_dir / "article.md")
    # The reference appendix is an evidence/audit block, not a second CTA.
    # Remove it while checking the “last substantive paragraph” invariant so
    # the article can keep references at the physical end without making the
    # call-to-action look duplicated or misplaced.
    body_for_cta = re.sub(
        re.escape(MARKDOWN_START) + r"[\s\S]*?" + re.escape(MARKDOWN_END),
        "",
        body,
        flags=re.M,
    ) if MARKDOWN_START in body else body
    if brand and brand not in body_for_cta:
        errors.append(f"正文缺少公开品牌署名：{brand}")
    if keyword and keyword not in body_for_cta:
        errors.append(f"正文缺少回复关键词引导：{keyword}")
    if primary and primary not in body_for_cta:
        errors.append("正文缺少 primary_cta 的完整关注引导")
    if primary and body_for_cta.count(primary) != 1:
        errors.append("正文必须恰好出现一次 primary_cta，禁止重复或模板拼接")
    if secondary and body_for_cta.count(secondary) != 1:
        errors.append("正文必须恰好出现一次 secondary_cta，禁止重复或模板拼接")
    substantive = [
        line.strip().strip("`*_ ")
        for line in body_for_cta.splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "!", "```", ">"))
    ]
    if primary and substantive and primary not in substantive[-1]:
        errors.append("primary_cta 必须位于正文最后一个实质段落")
    if secondary and substantive and secondary not in substantive[-1]:
        errors.append("secondary_cta 必须与 primary_cta 一起位于正文最后一个实质段落")
    # Anti-template guard: a CTA must name the current article's subject.  A
    # brand name and a generic keyword such as "资料/架构" are not enough.
    topic_terms = [term for term in (primary_keyword, canonical_topic) if term]
    if topic_terms and primary and not any(term.lower() in primary.lower() for term in topic_terms):
        errors.append("primary_cta 未包含当前主题关键词；禁止沿用上一主题的固定文案")
    # Do not promise formulas when the article has no formula source or
    # rendered formula asset.  This catches the exact class of generic ending
    # shown in the old draft screenshot.
    article_text = body_for_cta
    if re.search(r"公式", magnet + " " + primary) and not re.search(r"\$\$|(?<!\\$)\$(?!\\$)|formula|KaTeX|公式图", article_text, flags=re.I):
        errors.append("CTA/lead_magnet 声称包含公式，但当前文章没有公式源或公式图")
    return errors


def _claim_verification_errors(article_dir: Path) -> list[str]:
    """Require deterministic claim-to-source provenance before content review.

    This checker deliberately does not call an LLM or declare semantic truth;
    it verifies that the claim ledger was processed, every claim has a
    locator, and the verifier receipt is bound to the current sources.json.
    """
    path = article_dir / "claim-verification.json"
    errors: list[str] = []
    if not path.is_file():
        return ["缺少 claim-verification.json；请运行 scripts/verify_claims.py"]
    document = _json(path)
    if document.get("contract") != "claim-verification-v1":
        errors.append("claim-verification.json 的 contract 必须是 claim-verification-v1")
    if document.get("status") != "passed":
        errors.append("claim-verification.json 的 status 必须是 passed")
    if not _parse_iso_date(document.get("verified_at")):
        errors.append("claim-verification.json 缺少有效 verified_at")
    sources_path = article_dir / "sources.json"
    if not sources_path.is_file():
        errors.append("claim-verification.json 绑定的 sources.json 不存在")
    elif document.get("sources_digest") != sha256_file(sources_path):
        errors.append("claim-verification.json 的 sources_digest 与当前 sources.json 不一致")
    source_doc = _json(sources_path)
    claims = source_doc.get("claims", []) if isinstance(source_doc, dict) else []
    if isinstance(claims, list):
        claims_payload = json.dumps(claims, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        expected_claim_digest = hashlib.sha256(claims_payload.encode("utf-8")).hexdigest()
        if document.get("claims_digest") != expected_claim_digest:
            errors.append("claim-verification.json 的 claims_digest 与当前 claim ledger 不一致")
        expected_ids = {str(item.get("id", "")).strip() for item in claims if isinstance(item, dict)}
    else:
        expected_ids = set()
        errors.append("sources.json 的 claims 必须是列表")
    records = document.get("records")
    if not isinstance(records, list):
        return errors + ["claim-verification.json 缺少 records 列表"]
    record_map = {
        str(item.get("claim_id", "")).strip(): item
        for item in records
        if isinstance(item, dict) and str(item.get("claim_id", "")).strip()
    }
    missing = sorted(expected_ids - set(record_map))
    if missing:
        errors.append("claim-verification.json 缺少 claim 回执：" + ", ".join(missing))
    for claim_id, record in record_map.items():
        if record.get("status") != "passed":
            errors.append(f"claim {claim_id} 的 provenance verifier 未通过")
        if record.get("errors") not in ([], None):
            errors.append(f"claim {claim_id} 的 verifier 仍有错误")
    return errors


def _semantic_fact_review_errors(article_dir: Path) -> list[str]:
    """Require an independent semantic receipt for high-consequence claims.

    Provenance alone cannot tell whether wording overstates a paper or a
    benchmark.  The strict subset is deliberately limited to benchmark,
    paper-fact, regulated-domain, or explicitly human-required content so
    low-risk local test fixtures remain deterministic and network-free.
    """
    source_doc = _json(article_dir / "sources.json")
    claims = source_doc.get("claims", []) if isinstance(source_doc, dict) else []
    claim_types = {
        str(item.get("claim_type", "")).strip().lower()
        for item in claims
        if isinstance(item, dict)
    }
    # A generator must not evade independent fact review by relabelling a
    # paper/benchmark claim as a generic ``reference``.  The source evidence
    # level is the stronger signal because it is controlled by the research
    # ledger, not by the prose generator.
    source_doc = _json(article_dir / "sources.json")
    source_map = {
        str(item.get("id", "")).strip(): item
        for item in (source_doc.get("sources", []) if isinstance(source_doc, dict) else [])
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }
    research_levels = {"primary-research", "paper", "benchmark", "standard"}
    source_requires_review = False
    for claim in claims if isinstance(claims, list) else []:
        if not isinstance(claim, dict):
            continue
        for source_id in claim.get("source_ids", []) if isinstance(claim.get("source_ids"), list) else []:
            source = source_map.get(str(source_id).strip(), {})
            level = str(source.get("evidence_level", "")).strip().lower()
            title = str(source.get("title", "")).strip().lower()
            if level in research_levels or any(token in title for token in ("arxiv", "paper", "benchmark", "neurips", "eacl")):
                source_requires_review = True
                break
        if source_requires_review:
            break
    brief = _read_yaml(article_dir / "content-brief.yaml")
    risk = str(brief.get("risk_level", "")).strip().lower()
    required = bool(claim_types & {"benchmark", "paper-fact", "paper_fact", "medical", "legal", "financial"})
    required = required or source_requires_review or risk in {"high", "critical"} or brief.get("human_review_required") is True
    if not required:
        return []
    try:
        from fact_review import validate as validate_fact_review
    except ImportError:
        return ["严格事实主张需要 fact_review.py，但验证器不可用"]
    return validate_fact_review(article_dir, require=True)


def _approval_signature_errors(article_dir: Path) -> list[str]:
    """Verify optional external HMAC chain when the workflow requires it.

    The policy and key are intentionally process inputs, never article
    artifacts.  HMAC is an integrity check only; it must not be interpreted as
    proof that ``reviewer`` or ``signed_by`` is a human identity.
    """
    profile = _json(article_dir / "capability-profile.json")
    brief = _read_yaml(article_dir / "content-brief.yaml")
    risk = str(brief.get("risk_level", "")).strip().lower()
    required = bool(isinstance(profile, dict) and profile.get("approval_signature_required") is True)
    required = required or risk in {"high", "critical"} or brief.get("human_review_required") is True
    policy_path = os.environ.get("APPROVAL_SIGNATURE_POLICY_PATH", "").strip()
    key_path = os.environ.get("APPROVAL_SIGNATURE_KEY_PATH", "").strip()
    if not required and not policy_path:
        return []
    if not policy_path or not key_path:
        return ["需要外部批准事件签名，但未提供 APPROVAL_SIGNATURE_POLICY_PATH/APPROVAL_SIGNATURE_KEY_PATH"]
    try:
        from sign_approval_events import verify_events
    except ImportError:
        return ["批准事件签名验证器不可用"]
    return [f"approval-signature: {error}" for error in verify_events(article_dir, policy_path, key_path)]


def _approval_scope_matches(article_dir: Path, event: dict[str, Any], required: set[str]) -> bool:
    """Require an approval event to cover current bytes, not just a subject."""

    scopes = event.get("scope")
    hashes = event.get("scope_sha256")
    if not isinstance(scopes, list) or not isinstance(hashes, dict):
        return False
    scope_names = {str(item).strip().replace("\\", "/") for item in scopes if str(item).strip()}
    if not required.issubset(scope_names):
        return False
    for raw in scope_names:
        candidate = (article_dir / raw).resolve()
        try:
            candidate.relative_to(article_dir.resolve())
        except ValueError:
            return False
        if not candidate.is_file() or str(hashes.get(raw, "")).lower() != sha256_file(candidate):
            return False
    return True


def _article_local_file(article_dir: Path, raw: Any) -> tuple[Path | None, str]:
    """Resolve a receipt-owned artifact without allowing workspace escape.

    Preview/metrics receipts are editable JSON/Markdown inputs.  Treat every
    recorded path as untrusted: absolute paths and ``..``/symlink escapes must
    not let a gate attest to an arbitrary file elsewhere on the workstation.
    """

    value = str(raw or "").strip()
    if not value:
        return None, "路径为空"
    supplied = Path(value)
    if supplied.is_absolute():
        return None, "不允许绝对路径"
    root = article_dir.resolve()
    candidate = (root / supplied).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None, "路径越出当前文章工作区"
    if not candidate.is_file():
        return None, "文件不存在"
    return candidate, ""


def _conversion_metric_errors(article_dir: Path) -> list[str]:
    brief = _read_yaml(article_dir / "content-brief.yaml") if (article_dir / "content-brief.yaml").is_file() else {}
    try:
        schema = int(brief.get("schema_version", 1) or 1)
    except (TypeError, ValueError):
        schema = 1
    if schema < 3:
        return []
    metrics = _json(article_dir / "metrics.json")
    errors: list[str] = []
    if not metrics:
        return ["schema v3 内容简报必须有 metrics.json 转化复盘结构"]
    try:
        metrics_schema = int(metrics.get("schema_version", 1) or 1)
    except (TypeError, ValueError):
        metrics_schema = 0
    if metrics_schema < 2:
        errors.append("metrics.json schema_version 必须至少为 2")
    conversion = metrics.get("conversion")
    if not isinstance(conversion, dict):
        errors.append("metrics.json 缺少 conversion 指标对象")
    else:
        for key in ("follows", "keyword_replies", "lead_magnet_claims", "consultation_requests", "qualified_leads"):
            if key not in conversion:
                errors.append(f"metrics.json conversion 缺少 {key}")
    attribution = metrics.get("attribution")
    if not isinstance(attribution, dict):
        errors.append("metrics.json 缺少 attribution 归因对象")
    else:
        for key in ("primary_cta", "reply_keyword", "lead_magnet"):
            if not str(attribution.get(key, "")).strip():
                errors.append(f"metrics.json attribution 缺少 {key}")
    # T+1/T+7 是观测窗口，不是可以由脚本填充的默认数字。只要窗口
    # 被填写，就必须带原始数据来源、采集时间、导出哈希和非负指标。
    for window in ("t1", "t7"):
        observed = metrics.get(window)
        if observed in (None, {}, []):
            continue
        if not isinstance(observed, dict):
            errors.append(f"metrics.json {window} 必须是对象")
            continue
        if str(observed.get("status", "")).strip().lower() != "observed":
            errors.append(f"metrics.json {window} 必须明确标记为 observed")
        for key in ("source", "source_path", "source_sha256", "captured_at", "imported_at", "values"):
            if key not in observed or (isinstance(observed.get(key), str) and not observed.get(key).strip()):
                errors.append(f"metrics.json {window} 缺少 {key}")
        source_hash = str(observed.get("source_sha256", "")).strip().lower()
        if source_hash and not re.fullmatch(r"[0-9a-f]{64}", source_hash):
            errors.append(f"metrics.json {window}.source_sha256 不是 SHA-256")
        source_path, path_error = _article_local_file(article_dir, observed.get("source_path"))
        if path_error:
            errors.append(f"metrics.json {window}.source_path {path_error}")
        elif source_hash and source_path is not None and source_hash != sha256_file(source_path):
            errors.append(f"metrics.json {window}.source_sha256 与原始导出文件不一致")
        for timestamp_key in ("captured_at", "imported_at"):
            if observed.get(timestamp_key) and not _parse_iso_date(observed.get(timestamp_key)):
                errors.append(f"metrics.json {window}.{timestamp_key} 必须是有效 ISO 时间")
        values = observed.get("values")
        if not isinstance(values, dict) or not values:
            errors.append(f"metrics.json {window}.values 必须是非空对象")
        elif any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in values.values()):
            errors.append(f"metrics.json {window}.values 只能包含非负整数")
    return errors


def _errors_for_review(article_dir: Path) -> list[str]:
    errors: list[str] = []
    errors.extend(_errors_for_revision(article_dir, require_final=True))
    report = _text(article_dir / "review-report.md")
    article = _text(article_dir / "article.md")
    if (article_dir / "evidence-plan.json").is_file():
        evidence_errors, _ = validate_hybrid_evidence(article_dir, require_appendix=False, require_provenance=True)
        errors.extend(f"hybrid-evidence: {error}" for error in evidence_errors)
        isolation_errors, _ = validate_topic_evidence(article_dir)
        errors.extend(f"topic-evidence-isolation: {error}" for error in isolation_errors)
        if MARKDOWN_START not in article or MARKDOWN_END not in article:
            errors.append("hybrid-evidence: article.md 缺少篇尾原始证据与参考资料区块")
    errors.extend(check_topic_alignment(article_dir, "article.md"))
    if not CONTENT_TRUTH_QA.is_file():
        errors.append(f"内容真实性检查器缺失：{CONTENT_TRUTH_QA}")
    else:
        result = subprocess.run(
            [sys.executable, str(CONTENT_TRUTH_QA), "--article", str(article_dir)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode:
            detail = (result.stdout + result.stderr).strip().splitlines()
            errors.append("内容真实性检查失败：" + (detail[-1] if detail else "无输出"))
    errors.extend(_public_content_errors(article, "article.md"))
    for finding in find_unrendered_math_literals(article):
        errors.append(f"数学表达仍以行内代码存在：{finding['value']}；请改为 $...$ LaTeX")
    errors.extend(_cta_errors(article_dir, article))
    if _chars(article) < 1000 or "占位文件" in article:
        errors.append("article.md 不是可发布定稿，或仍为占位文件")
    if _chars(report) < 300:
        errors.append("review-report.md 缺少完整审核记录")
    if not any(marker in report for marker in ("内容审", "事实", "合规")):
        errors.append("审核报告缺少内容/事实/合规检查记录")
    if re.search(r"(?im)^\s*[-*]\s*(?:🔴|阻断|BLOCKING)", report):
        errors.append("审核报告存在阻断级问题")
    if re.search(
        r"(?im)^\s*(?:[-*]\s*)?(?:status|状态|内容审|事实核验|合规|敏感|错别字|校对|AI\s*味)\s*[:：]\s*(?:pending|todo|待审核|待处理)\s*$",
        report,
    ):
        errors.append("审核报告的显式状态仍为 pending/TODO/待审核")
    # 方案 E：thinktank 文章若含数学公式，必须至少配 1 个 fenced 代码块
    # （PyTorch / NumPy / Shell 实现）。公式驱动代码上下文，与公式渲染管线
    # 联动，确保理论与实战结合。仅在含公式时检查，无公式不强制。
    article_meta = _read_yaml(article_dir / "article.yaml") if (article_dir / "article.yaml").is_file() else {}
    if str(article_meta.get("account", "")).strip().lower() == "thinktank":
        has_fenced_code = bool(re.search(r"```[A-Za-z0-9_+-]*\n[\s\S]*?```", article))
        has_formula = bool(re.search(r"(?<!\\)\$\$?.+?\$\$?", article, flags=re.S))
        if has_formula and not has_fenced_code:
            errors.append("thinktank 文章包含数学公式但没有任何 fenced 代码块：按 SOP 要求补 PyTorch / NumPy / Shell 实现")
    if _image_marker_count(article) == 0:
        errors.append("定稿缺少图片占位，不能进入配图")
    evidence_path = article_dir / "review-evidence.json"
    evidence = _json(evidence_path)
    if not evidence_path.is_file():
        errors.append("缺少 review-evidence.json；审稿技能必须留下结构化回执")
    else:
        if evidence.get("status") != "passed":
            errors.append("review-evidence.json 的 status 必须是 passed")
        checks = evidence.get("checks")
        if not isinstance(checks, dict):
            errors.append("review-evidence.json 缺少 checks 对象")
        else:
            for key in REVIEW_CHECKS:
                if checks.get(key) != "passed":
                    errors.append(f"review-evidence.json 未通过 {key} 检查")
        digest_fn = stable_sha256_file if evidence.get("digest_mode") == "stable-text-v1" else sha256_file
        article_digest = digest_fn(article_dir / "article.md") if (article_dir / "article.md").is_file() else ""
        if evidence.get("article_digest") != article_digest:
            errors.append("review-evidence.json 的 article_digest 与当前 article.md 不一致")
        report_digest = digest_fn(article_dir / "review-report.md") if (article_dir / "review-report.md").is_file() else ""
        if evidence.get("report_digest") != report_digest:
            errors.append("review-evidence.json 的 report_digest 与当前 review-report.md 不一致")
    disclosure_path = article_dir / "ai-disclosure.yaml"
    disclosure = _read_yaml(disclosure_path) if disclosure_path.is_file() else {}
    if not disclosure_path.is_file():
        errors.append("缺少 ai-disclosure.yaml；必须记录文字/图片是否由 AI 生成及公开标识")
    else:
        if disclosure.get("status") != "passed":
            errors.append("ai-disclosure.yaml 的 status 必须是 passed")
        if disclosure.get("metadata_preserved") is not True:
            errors.append("ai-disclosure.yaml 必须记录 metadata_preserved: true")
        if not isinstance(disclosure.get("contains_ai_generated"), bool):
            errors.append("ai-disclosure.yaml 的 contains_ai_generated 必须是布尔值")
        for key in ("contains_ai_generated", "text_generation", "image_generation", "disclosure_text"):
            if key != "contains_ai_generated" and (key not in disclosure or not str(disclosure.get(key, "")).strip()):
                errors.append(f"ai-disclosure.yaml 缺少 {key}")
    if _requires_structured_review(article_dir):
        errors.extend(_structured_review_errors(article_dir))
        errors.extend(_claim_verification_errors(article_dir))
        errors.extend(_semantic_fact_review_errors(article_dir))
        errors.extend(_approval_signature_errors(article_dir))
        # A3（对抗审查）：review-checks 若自报 reviewer_type=human，必须有对应
        # 的 human 批准事件（signed_by 非空），防止“自填人审”冒充。
        review_checks = _json(article_dir / "review-checks.json")
        if str(review_checks.get("reviewer_type", "")).strip().lower() == "human":
            factual_events = [
                event
                for event in approval_event_map(article_dir).get("factual_review", [])
                if str(event.get("reviewer_type", "")).strip().lower() == "human"
                and str(event.get("signed_by", "")).strip()
                and _approval_scope_matches(article_dir, event, {"review-checks.json"})
            ]
            if not factual_events:
                errors.append(
                    "review-checks.json 声明 human 审稿，但 approval-events.json 缺少 "
                    "绑定当前 review-checks.json 的 factual_review human 批准事件；禁止使用旧 scope 自报人审"
                )
    return errors


def _errors_for_formatted(article_dir: Path) -> list[str]:
    errors: list[str] = []
    if (article_dir / "evidence-plan.json").is_file():
        evidence_errors, _ = validate_hybrid_evidence(article_dir, require_appendix=True, require_provenance=True)
        errors.extend(f"hybrid-evidence: {error}" for error in evidence_errors)
        isolation_errors, _ = validate_topic_evidence(article_dir)
        errors.extend(f"topic-evidence-isolation: {error}" for error in isolation_errors)
    html_path = article_dir / "article.html"
    article_path = article_dir / "article.md"
    html = _text(html_path)
    errors.extend(_public_content_errors(html, "article.html"))
    if not html_path.is_file() or _chars(html) < 1000 or "占位文件" in html:
        errors.append("article.html 缺失或仍为占位文件")
    # Freshness is content-addressed below by source_digest/html_digest.
    # Filesystem mtimes are not an integrity signal: idempotent evidence
    # append, checkout and backup tools may touch Markdown without changing
    # the canonical bytes that were formatted.
    if 'src="placeholder"' in html or "src='placeholder'" in html:
        errors.append("HTML 残留 placeholder 图片源")
    if not VALIDATOR.is_file():
        errors.append(f"严格 HTML 校验器缺失：{VALIDATOR}")
    elif html_path.is_file():
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), "--strict", str(html_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode:
            detail = (result.stdout + result.stderr).strip().splitlines()
            errors.append("公众号 HTML 严格校验失败：" + (detail[-1] if detail else "无输出"))
    format_report_path = article_dir / "format-report.json"
    format_report = _json(format_report_path)
    if not format_report_path.is_file():
        errors.append("缺少 format-report.json；排版必须留下 HTML 校验回执")
    else:
        if format_report.get("status") != "passed":
            errors.append("format-report.json 的 status 必须是 passed")
        if format_report.get("validator") != "passed":
            errors.append("format-report.json 的 validator 必须是 passed")
        source_name = str(format_report.get("source") or article_path.name)
        render_source = article_dir / source_name
        source_digest = sha256_file(render_source) if render_source.is_file() else (sha256_file(article_path) if article_path.is_file() else "")
        html_digest = sha256_file(html_path) if html_path.is_file() else ""
        if format_report.get("source_digest") != source_digest:
            errors.append("format-report.json 的 source_digest 与实际排版输入不一致")
        canonical_digest = format_report.get("canonical_source_digest")
        if canonical_digest and article_path.is_file() and canonical_digest != sha256_file(article_path):
            errors.append("format-report.json 的 canonical_source_digest 与当前 article.md 不一致")
    if format_report.get("html_digest") != html_digest:
            errors.append("format-report.json 的 html_digest 与当前 article.html 不一致")
    if not STYLE_LINT.is_file():
        errors.append(f"样式 lint 缺失：{STYLE_LINT}")
    else:
        style_result = subprocess.run(
            [sys.executable, str(STYLE_LINT), "--article", str(article_dir)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if style_result.returncode:
            detail = (style_result.stdout + style_result.stderr).strip().splitlines()
            errors.append("微信代码样式检查失败：" + (detail[-1] if detail else "无输出"))
    formula_manifest = article_dir / "formula-manifest.json"
    formula_source = article_dir / "article.md"
    if formula_manifest.is_file() or re.search(r"(?<!\\)\$\$?.+?\$\$?", _text(formula_source), flags=re.S):
        if not FORMULA_SOURCE_CHECK.is_file():
            errors.append(f"公式源检查器缺失：{FORMULA_SOURCE_CHECK}")
        else:
            source_result = subprocess.run(
                [sys.executable, str(FORMULA_SOURCE_CHECK), str(article_dir)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if source_result.returncode:
                detail = (source_result.stdout + source_result.stderr).strip().splitlines()
                errors.append("公式源检查失败：" + (detail[-1] if detail else "无输出"))
        if not formula_manifest.is_file():
            errors.append("检测到 LaTeX 公式但缺少 formula-manifest.json")
        elif not FORMULA_PIPELINE.is_file():
            errors.append("公式渲染器缺失：scripts/formula_pipeline.py")
        else:
            result = subprocess.run(
                [sys.executable, str(FORMULA_PIPELINE), "check", "--article", str(article_dir)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode:
                detail = (result.stdout + result.stderr).strip().splitlines()
                errors.append("公式渲染检查失败：" + (detail[-1] if detail else "无输出"))
    return errors


def _image_paths(html: str) -> list[str]:
    return re.findall(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", html, flags=re.I)


def _errors_for_illustrated(article_dir: Path) -> list[str]:
    errors: list[str] = []
    # 若已有通过的人工语义审核记录，后续 visual_qa check / semantic_qa
    # 重跑时透传 human reviewer，避免 Agnes 封面/概念图在 agent 模式被误判。
    semantic_report = _json(article_dir / "visual-semantic-review.json")
    imgs = article_dir / "imgs"
    if not imgs.is_dir():
        return ["缺少 imgs/ 素材目录"]
    cover = next((p for p in imgs.glob("cover.*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}), None)
    if cover is None:
        errors.append("缺少真实封面文件 imgs/cover.*")
    html = _text(article_dir / "article.html")
    references = _image_paths(html)
    if not references:
        errors.append("article.html 未包含正文图片")
    missing = []
    for raw in references:
        if raw.startswith(("http://", "https://", "data:")):
            continue
        candidate = (article_dir / raw).resolve()
        if not candidate.is_file():
            missing.append(raw)
    if missing:
        errors.append("HTML 引用的图片不存在：" + ", ".join(missing[:5]))
    brief_path = article_dir / "visual-brief.yaml"
    if not brief_path.is_file():
        errors.append("缺少 visual-brief.yaml；必须先完成视觉简报和封面确认")
    else:
        # A3（对抗审查）：封面批准必须落在 approval-events.json 事件账本，
        # 不能只靠 visual-brief.yaml 内自报的 reviewer_type 字段。
        brief = _read_yaml(brief_path)
        brief_approval = brief.get("approval", {}) if isinstance(brief, dict) else {}
        cover_events = approval_event_map(article_dir).get("cover_selection", [])
        current_cover_events = [
            event for event in cover_events
            if _approval_scope_matches(article_dir, event, {"visual-brief.yaml"})
        ]
        if not cover_events:
            errors.append("封面批准缺少 approval-events.json 事件；请通过 visual_qa.py approve 或 record_approval.py 记录")
        elif not current_cover_events:
            errors.append("封面批准事件的 scope_sha256 与当前 visual-brief.yaml 不一致；必须重新审批")
        elif str(brief_approval.get("reviewer_type", "")).strip().lower() == "human":
            if not any(
                str(event.get("reviewer_type", "")).strip().lower() == "human" and str(event.get("signed_by", "")).strip()
                for event in current_cover_events
            ):
                errors.append("visual-brief 声明 human 封面审批，但 approval-events.json 没有对应 human 事件（signed_by 非空）")
    if not (article_dir / "image-plan.md").is_file() or _chars(_text(article_dir / "image-plan.md")) < 80:
        errors.append("缺少 image-plan.md 或图片计划过短")
    routing_path = article_dir / "visual-routing.json"
    routing_doc = _json(routing_path)
    if not routing_path.is_file():
        errors.append("缺少 visual-routing.json；必须记录导演主/备后端与路由原因")
    elif routing_doc.get("contract") != "visual-semantic-routing-v1" or routing_doc.get("status") not in {"passed", "generated"}:
        errors.append("visual-routing.json 必须是 visual-semantic-routing-v1 且 status=passed/generated")
    elif not isinstance(routing_doc.get("routes"), list) or not routing_doc.get("routes"):
        errors.append("visual-routing.json 必须包含 routes")
    if not VISUAL_ROUTE_CONSISTENCY.is_file():
        errors.append(f"视觉路由一致性检查器缺失：{VISUAL_ROUTE_CONSISTENCY}")
    else:
        route_result = subprocess.run(
            [sys.executable, str(VISUAL_ROUTE_CONSISTENCY), "--article", str(article_dir)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if route_result.returncode:
            detail = (route_result.stdout + route_result.stderr).strip().splitlines()
            errors.append("视觉路由一致性检查失败：" + (detail[-1] if detail else "无输出"))
    evaluation_path = article_dir / "skill-evaluation.json"
    evaluation_doc = _json(evaluation_path)
    if not evaluation_path.is_file():
        errors.append("缺少 skill-evaluation.json；必须记录候选 Skill 的适配、评分与拒绝原因")
    elif evaluation_doc.get("contract") != "visual-skill-evaluation-v1" or evaluation_doc.get("status") not in {"passed", "generated", "planned"}:
        errors.append("skill-evaluation.json contract/status 无效")
    elif not isinstance(evaluation_doc.get("routes"), list) or not evaluation_doc.get("routes"):
        errors.append("skill-evaluation.json 必须包含 routes")
    director_path = article_dir / "visual-director-plan.json"
    director_doc = _json(director_path)
    if not director_path.is_file():
        errors.append("缺少 visual-director-plan.json；必须先完成视觉导演计划")
    elif director_doc.get("contract") != "visual-director-v1" or director_doc.get("status") not in {"ready", "approved", "generated"}:
        errors.append("visual-director-plan.json 必须是 visual-director-v1 且 status=ready/approved/generated")
    else:
        director_records = director_doc.get("records")
        if not isinstance(director_records, list) or not director_records:
            errors.append("visual-director-plan.json 必须包含素材记录")
        else:
            for record in director_records:
                if not isinstance(record, dict):
                    errors.append("visual-director-plan.json 含有无法解析的素材记录")
                    continue
                for field in ("id", "asset", "viewer_job", "visual_owner", "generation_mode", "source_strategy", "rights_status", "fallback", "continuity_group", "safe_area", "expected_elements", "forbidden_elements", "source_excerpt_sha256", "render_backend", "skill_evaluation"):
                    if not str(record.get(field, "")).strip():
                        errors.append(f"visual-director-plan.json 素材缺少 {field}: {record.get('id', '')}")
                if str(record.get("requested_backend") or "").strip():
                    errors.extend(validate_record(record))
    generation_path = article_dir / "image-generation-plan.json"
    generation_doc = _json(generation_path)
    if not generation_path.is_file():
        errors.append("缺少 image-generation-plan.json；必须先编译提示词与执行计划")
    elif generation_doc.get("generation_contract") != "prompt-v2":
        errors.append("image-generation-plan.json 必须使用 generation_contract=prompt-v2")
    else:
        prompt_records = generation_doc.get("prompt_files")
        if not isinstance(prompt_records, list) or not prompt_records:
            errors.append("image-generation-plan.json 必须包含 prompt_files")
        else:
            max_streak = int((generation_doc.get("generation_policy") or {}).get("max_consecutive_generated_cards", 2) or 2)
            streak = 0
            for record in prompt_records:
                if not isinstance(record, dict):
                    errors.append("image-generation-plan.json 含有无法解析的 prompt 记录")
                    continue
                for field in ("id", "asset", "kind", "generation_mode", "size", "ratio", "visual_owner", "viewer_job", "fallback", "sha256", "expected_elements", "forbidden_elements", "source_excerpt_sha256", "render_backend", "skill_evaluation"):
                    if not str(record.get(field, "")).strip():
                        errors.append(f"image-generation-plan.json 素材缺少 {field}: {record.get('id', '')}")
                if str(record.get("requested_backend") or "").strip():
                    errors.extend(validate_record(record))
                if str(record.get("generation_mode", "")).strip().lower() == "agnes":
                    streak += 1
                    if streak > max_streak:
                        errors.append(f"连续 Agnes 生图超过反疲劳上限 {max_streak}: {record.get('id', '')}")
                else:
                    streak = 0
                if str(record.get("id")) != "cover":
                    if not str(record.get("execution_provider", "")).strip():
                        errors.append(f"image-generation-plan.json 缺少实际 execution_provider: {record.get('id', '')}")
                    if not str(record.get("requested_provider", "")).strip():
                        errors.append(f"image-generation-plan.json 缺少 requested_provider: {record.get('id', '')}")
                    technical_kind = str(record.get("kind", "")).strip().lower()
                    backend = str(record.get("render_backend", "")).strip().lower()
                    if technical_kind in {"qkv", "shape", "attention", "numeric"} and not backend.startswith("katex-"):
                        errors.append(f"精确数学图必须使用 KaTeX 确定性后端：{record.get('id', '')}")
                    if technical_kind in {"multihead", "kv-cache"} and backend not in {"deterministic-svg", "beautiful-mermaid", "excalidraw"}:
                        errors.append(f"关系/时序技术图必须使用 SVG、Mermaid 或 Excalidraw 后端：{record.get('id', '')}")
                    requested = str(record.get("requested_provider", "")).strip().lower()
                    actual = str(record.get("execution_provider", "")).strip().lower()
                    if requested and actual and requested != actual and actual not in {"local-deterministic", "local-fallback", "local"}:
                        errors.append(f"requested_provider 与 execution_provider 不一致：{record.get('id', '')}")
                    if str(record.get("requested_backend") or "").strip() and not str(record.get("execution_backend") or "").strip():
                        errors.append(f"image-generation-plan.json 缺少 execution_backend: {record.get('id', '')}")
            if generation_doc.get("status") not in {"generated", "partial"}:
                errors.append("image-generation-plan.json 尚未记录实际执行结果")
    image_analysis = _text(article_dir / "img_analysis.md")
    if _chars(image_analysis) < 100 or not re.search(r"错误：\s*0", image_analysis):
        errors.append("img_analysis.md 缺少图片质量通过回执")
    source_path = article_dir / "image-sources.json"
    source_doc = _json(source_path)
    assets = source_doc.get("assets")
    if not source_path.is_file():
        errors.append("缺少 image-sources.json；图片来源和授权必须留痕")
    elif not isinstance(assets, list) or not assets:
        errors.append("image-sources.json 必须包含至少 1 个素材记录")
    else:
        if source_doc.get("status") != "passed":
            errors.append("image-sources.json 的 status 必须是 passed")
        asset_paths = set()
        for item in assets:
            if isinstance(item, str):
                errors.append(f"image-sources.json 素材缺少 source/license 元数据：{item}")
                asset_paths.add(item)
            elif isinstance(item, dict):
                path_value = str(item.get("path", "")).strip()
                asset_paths.add(path_value)
                if not str(item.get("source", "")).strip() or not str(item.get("license", "")).strip():
                    errors.append(f"image-sources.json 素材缺少 source/license 元数据：{path_value}")
                origin = str(item.get("origin", "")).strip().lower()
                if origin not in {"generated", "reused", "user_provided", "external"}:
                    errors.append(f"image-sources.json 素材缺少有效 origin：{path_value}")
                if origin == "reused":
                    if item.get("reuse_approved") is not True:
                        errors.append(f"复用图片必须记录 reuse_approved: true：{path_value}")
                    if not str(item.get("source_ref", "") or item.get("source_article", "")).strip():
                        errors.append(f"复用图片缺少来源稿件 source_ref：{path_value}")
                    if not str(item.get("reuse_reason", "")).strip():
                        errors.append(f"复用图片缺少 reuse_reason：{path_value}")
                elif item.get("reuse_approved") is True:
                    errors.append(f"非 reused 图片不能标记 reuse_approved: true：{path_value}")
                try:
                    source_schema = int(source_doc.get("schema_version", 1) or 1)
                except (TypeError, ValueError):
                    source_schema = 1
                if source_schema >= 2 and origin == "generated":
                    generation = item.get("generation")
                    if not isinstance(generation, dict):
                        errors.append(f"生成图片缺少 generation provenance：{path_value}")
                    else:
                        for field in ("provider", "model", "method", "prompt_file", "prompt_sha256", "request_sha256", "visual_owner", "viewer_job", "fallback"):
                            if not str(generation.get(field, "")).strip():
                                errors.append(f"生成图片缺少 generation.{field}：{path_value}")
                if path_value and not path_value.startswith(("http://", "https://", "data:")):
                    local_asset = (article_dir / path_value).resolve()
                    digest = str(item.get("sha256", "")).strip().lower()
                    if not local_asset.is_file():
                        errors.append(f"image-sources.json 素材文件不存在：{path_value}")
                    elif not is_sha256(digest) or digest != sha256_file(local_asset):
                        errors.append(f"image-sources.json 素材 sha256 不匹配：{path_value}")
                elif path_value and not str(item.get("sha256", "")).strip():
                    errors.append(f"image-sources.json 远程素材缺少 sha256 或内容指纹：{path_value}")
            else:
                errors.append("image-sources.json 含有无法解析的素材记录")
        formula_refs: set[str] = set()
        formula_manifest = article_dir / "formula-manifest.json"
        if formula_manifest.is_file():
            formula_doc = _json(formula_manifest)
            formula_refs = {
                str(item.get("output", "")).strip()
                for item in formula_doc.get("formulas", [])
                if isinstance(item, dict) and str(item.get("output", "")).strip()
            }
        evidence_refs = _hybrid_evidence_paths(article_dir)
        for raw in references:
            # formula-manifest.json is the authoritative source/license/hash
            # ledger for generated formula PNGs; image-sources.json remains
            # responsible for cover and cognitive-anchor artwork.
            if not raw.startswith(("http://", "https://", "data:")) and raw not in asset_paths and raw not in formula_refs and raw not in evidence_refs:
                errors.append(f"image-sources.json 未记录 HTML 图片：{raw}")
        if cover is not None and "imgs/" + cover.name not in asset_paths:
            errors.append(f"image-sources.json 未记录封面：imgs/{cover.name}")
    if not VISUAL_QA.is_file():
        errors.append(f"视觉质量检查器缺失：{VISUAL_QA}")
    else:
        # 若已有通过的人工语义审核记录，则透传 human reviewer，避免
        # Agnes 封面/概念图在 agent 模式被误判为"未人工确认"。
        semantic_report = _json(article_dir / "visual-semantic-review.json")
        qa_args = ["check", "--article", str(article_dir)]
        if semantic_report.get("status") == "passed" and str(semantic_report.get("reviewer_type", "")).strip().lower() == "human":
            qa_args += ["--reviewer-type", "human", "--reviewer", str(semantic_report.get("reviewer") or "human-review")]
        result = subprocess.run(
            [sys.executable, str(VISUAL_QA), *qa_args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode:
            detail = (result.stdout + result.stderr).strip().splitlines()
            errors.append("图片质量检查失败：" + (detail[-1] if detail else "无输出"))
    if not VISUAL_SEMANTIC_QA.is_file():
        errors.append(f"视觉语义检查器缺失：{VISUAL_SEMANTIC_QA}")
    else:
        # Do not trust a stale visual-semantic-review.json.  Re-run the
        # contract checker at the illustrated gate so a backend that was only
        # planned (or a footer/placeholder that reappeared) cannot pass by
        # leaving an old report in the article directory.  A previously
        # recorded human semantic review is honoured by re-running the checker
        # in the same human mode instead of silently accepting the old file.
        semantic_args = ["--article", str(article_dir)]
        if semantic_report.get("status") == "passed" and str(semantic_report.get("reviewer_type", "")).strip().lower() == "human":
            semantic_args += ["--reviewer-type", "human", "--reviewer", str(semantic_report.get("reviewer") or "human-review")]
        result = subprocess.run(
            [sys.executable, str(VISUAL_SEMANTIC_QA), *semantic_args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode:
            detail = (result.stdout + result.stderr).strip().splitlines()
            errors.append("图片语义检查失败：" + (detail[-1] if detail else "无输出"))
    if not VISUAL_CONTENT_QA.is_file():
        errors.append(f"视觉内容检查器缺失：{VISUAL_CONTENT_QA}")
    else:
        result = subprocess.run(
            [sys.executable, str(VISUAL_CONTENT_QA), "--article", str(article_dir)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode:
            detail = (result.stdout + result.stderr).strip().splitlines()
            errors.append("视觉内容语义检查失败：" + (detail[-1] if detail else "无输出"))
    # The visual brief defines the exact cognitive-anchor image set.  Extra or
    # missing images make the plan and the published HTML diverge.
    if brief_path.is_file():
        brief = _read_yaml(brief_path)
        visuals = brief.get("body_visuals", [])
        expected_refs = {
            str(item.get("asset", "")).strip()
            for item in visuals
            if isinstance(item, dict) and str(item.get("asset", "")).strip()
        }
        cover_data = brief.get("cover", {}) if isinstance(brief, dict) else {}
        cover_asset = str(
            cover_data.get("selected") or cover_data.get("asset") or ""
        ).strip() if isinstance(cover_data, dict) else ""
        formula_refs: set[str] = set()
        formula_manifest = article_dir / "formula-manifest.json"
        if formula_manifest.is_file():
            formula_doc = _json(formula_manifest)
            formula_refs = {
                str(item.get("output", "")).strip()
                for item in formula_doc.get("formulas", [])
                if isinstance(item, dict) and str(item.get("output", "")).strip()
            }
        # The cover is a separately uploaded WeChat thumbnail. It may be
        # embedded by some formatters, but it is not a body-anchor image.
        evidence_refs = _hybrid_evidence_paths(article_dir)
        actual_refs = {
            raw for raw in references
            if not raw.startswith(("http://", "https://", "data:")) and raw != cover_asset and raw not in formula_refs and raw not in evidence_refs
        }
        if expected_refs and actual_refs != expected_refs:
            missing = sorted(expected_refs - actual_refs)
            extra = sorted(actual_refs - expected_refs)
            details = []
            if missing:
                details.append("缺少 " + ", ".join(missing))
            if extra:
                details.append("多出 " + ", ".join(extra))
            errors.append("HTML 图片与视觉简报未一一对应：" + "；".join(details))
        for item in visuals if isinstance(visuals, list) else []:
            if isinstance(item, dict) and str(item.get("id")) != "cover" and str(item.get("status", "planned")) not in {"generated", "deterministic", "fallback"}:
                errors.append(f"visual-brief.yaml 素材状态未闭环：{item.get('id', '')}")
    contract_path = article_dir / "visual-contract.json"
    semantic_path = article_dir / "visual-semantic-review.json"
    if not contract_path.is_file():
        errors.append("缺少 visual-contract.json；illustrated 必须有正文语义合同")
    else:
        contract_doc = _json(contract_path)
        if contract_doc.get("contract") != "visual-contract-v1":
            errors.append("visual-contract.json contract 必须为 visual-contract-v1")
        units = contract_doc.get("units")
        if not isinstance(units, list) or not units:
            errors.append("visual-contract.json 必须包含 units")
        else:
            for unit in units:
                if not isinstance(unit, dict):
                    errors.append("visual-contract.json 含有无法解析的 unit")
                    continue
                for field in ("id", "viewer_job", "expected_elements", "forbidden_elements", "render_backend", "output"):
                    if not str(unit.get(field, "")).strip() and field not in {"expected_elements", "forbidden_elements"}:
                        errors.append(f"visual-contract.json 素材缺少 {field}: {unit.get('id', '')}")
    semantic_doc = _json(semantic_path)
    if not semantic_path.is_file() or semantic_doc.get("status") != "passed":
        errors.append("visual-semantic-review.json 必须是 status=passed")
    elif not isinstance(semantic_doc.get("records"), list) or not semantic_doc.get("records"):
        errors.append("visual-semantic-review.json 必须包含逐图 records")
    vision_skill = semantic_doc.get("vision_skill") if isinstance(semantic_doc, dict) else None
    if not isinstance(vision_skill, dict) or vision_skill.get("contract") != "vision-skill-v1":
        errors.append("visual-semantic-review.json 必须记录 vision skill 路由（vision-skill-v1）")
    elif vision_skill.get("status") != "available" or vision_skill.get("routing_command_status") != "passed":
        errors.append("vision skill 不可用或路由探测未通过；不能跳过图片理解责任")
    if not VISION_REVIEW.is_file():
        errors.append(f"逐图 vision review 检查器缺失：{VISION_REVIEW}")
    else:
        vision_result = subprocess.run(
            [sys.executable, str(VISION_REVIEW), "--article", str(article_dir), "check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if vision_result.returncode:
            detail = (vision_result.stdout + vision_result.stderr).strip().splitlines()
            errors.append("逐图视觉审查回执失败：" + (detail[-1] if detail else "无输出"))
    if re.search(r"(?m)^!\[[^\]]*\]\(placeholder\)\s*$", _text(article_dir / "article.md"), flags=re.I):
        errors.append("定稿仍有未替换的图片占位")
    if re.search(r"\bsrc=[\"']placeholder[\"']", html, flags=re.I):
        errors.append("素材或 HTML 中残留 placeholder 图片源")
    for match in re.finditer(r"<img\b([^>]*)>", html, flags=re.I):
        if not re.search(r"\balt=[\"'][^\"']+[\"']", match.group(1), flags=re.I):
            errors.append("HTML 图片缺少非空 alt 替代文本")
            break
    # Depth QA is additive to pixel/label QA.  It is required when the visual
    # contract opts into visual-depth-contract-v1; legacy contracts remain
    # backward compatible until their units are upgraded.
    # Every non-cover technical visual must carry the depth contract.  An
    # opt-in flag allowed a renderer to omit reader questions, typed
    # relations, evidence and fallback semantics while still reaching
    # ``illustrated``; that is exactly the label-list failure this gate is
    # meant to prevent.
    depth_required = False
    if contract_path.is_file():
        depth_required = any(
            isinstance(unit, dict) and str(unit.get("id") or "") != "cover"
            for unit in (_json(contract_path).get("units") or [])
        )
    if depth_required:
        if not VISUAL_DEPTH_QA.is_file():
            errors.append(f"视觉深度检查器缺失：{VISUAL_DEPTH_QA}")
        else:
            depth_result = subprocess.run(
                [sys.executable, str(VISUAL_DEPTH_QA), "--article", str(article_dir), "check"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if depth_result.returncode:
                detail = (depth_result.stdout + depth_result.stderr).strip().splitlines()
                errors.append("视觉深度检查失败：" + (detail[-1] if detail else "无输出"))
        errors.extend(_refresh_pending_reader_packet(article_dir))
        reader_doc = _json(article_dir / "visual-reader-test.json")
        if reader_doc.get("contract") != "visual-reader-test-v1":
            errors.append("视觉深度合同必须有 visual-reader-test-v1 读者理解测试包")
        elif reader_doc.get("status") not in {"pending-human", "passed"}:
            errors.append("visual-reader-test.json 状态无效；失败的读者测试不能进入 illustrated")
        else:
            errors.extend(_reader_receipt_errors(article_dir, reader_doc))
            # Reader/depth receipts are products of the current article and
            # contract.  A stale pending packet must not silently survive a
            # later edit just because its status is still syntactically valid.
            expected_article_sha = sha256_file(article_dir / "article.md") if (article_dir / "article.md").is_file() else ""
            expected_contract_sha = sha256_file(article_dir / "visual-contract.json") if (article_dir / "visual-contract.json").is_file() else ""
            if reader_doc.get("article_sha256") != expected_article_sha:
                errors.append("visual-reader-test.json 的 article_sha256 与当前 article.md 不一致")
            if reader_doc.get("visual_contract_sha256") != expected_contract_sha:
                errors.append(
                    "visual-reader-test.json 的 visual_contract_sha256 与当前 visual-contract.json 不一致"
                    f"（receipt={reader_doc.get('visual_contract_sha256')}, current={expected_contract_sha}）"
                )
            depth_doc = _json(article_dir / "visual-depth-review.json")
            expected_depth_sha = sha256_file(article_dir / "visual-depth-review.json") if (article_dir / "visual-depth-review.json").is_file() else ""
            if depth_doc.get("article_sha256") != expected_article_sha:
                errors.append("visual-depth-review.json 的 article_sha256 与当前 article.md 不一致")
            if depth_doc.get("visual_contract_sha256") != expected_contract_sha:
                errors.append("visual-depth-review.json 的 visual_contract_sha256 与当前 visual-contract.json 不一致")
    if not VISUAL_AESTHETIC_QA.is_file():
        errors.append(f"视觉美学卫生检查器缺失：{VISUAL_AESTHETIC_QA}")
    else:
        aesthetic_result = subprocess.run(
            [sys.executable, str(VISUAL_AESTHETIC_QA), "--article", str(article_dir)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if aesthetic_result.returncode:
            detail = (aesthetic_result.stdout + aesthetic_result.stderr).strip().splitlines()
            errors.append("视觉美学卫生检查失败：" + (detail[-1] if detail else "无输出"))
    taste_doc = _json(article_dir / "visual-taste-review.json")
    if not VISUAL_TASTE_REVIEW.is_file():
        errors.append(f"视觉审美检查器缺失：{VISUAL_TASTE_REVIEW}")
    elif taste_doc.get("status") != "passed" or (taste_doc.get("rubric") or {}).get("human_review_status") != "passed":
        errors.append("视觉审美检查未通过：必须有 status=passed 且 human_review_status=passed 的逐图人眼复核")
    return errors


def _errors_for_final(article_dir: Path) -> list[str]:
    report = _text(article_dir / "review-report.md")
    errors: list[str] = []
    errors.extend(check_topic_alignment(article_dir, "article.md"))
    errors.extend(_cta_errors(article_dir, _text(article_dir / "article.md")))
    errors.extend(_conversion_metric_errors(article_dir))
    visual_contract_path = article_dir / "visual-contract.json"
    if visual_contract_path.is_file():
        depth_doc = _json(article_dir / "visual-depth-review.json")
        depth_required = any(
            isinstance(unit, dict) and str(unit.get("id") or "") != "cover"
            for unit in (_json(visual_contract_path).get("units") or [])
        )
        if VISUAL_CONTENT_QA.is_file():
            result = subprocess.run(
                [sys.executable, str(VISUAL_CONTENT_QA), "--article", str(article_dir)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode:
                detail = (result.stdout + result.stderr).strip().splitlines()
                errors.append("终审视觉内容语义检查失败：" + (detail[-1] if detail else "无输出"))
        if depth_required and VISUAL_DEPTH_QA.is_file():
            depth_result = subprocess.run(
                [sys.executable, str(VISUAL_DEPTH_QA), "--article", str(article_dir), "check"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if depth_result.returncode:
                detail = (depth_result.stdout + depth_result.stderr).strip().splitlines()
                errors.append("终审视觉深度检查失败：" + (detail[-1] if detail else "无输出"))
        errors.extend(_refresh_pending_reader_packet(article_dir))
        depth_doc = _json(article_dir / "visual-depth-review.json")
        if depth_required and depth_doc.get("status") != "passed":
            errors.append("终审前必须有 status=passed 的 visual-depth-review.json（结构深度合同）")
        reader_doc = _json(article_dir / "visual-reader-test.json")
        if reader_doc.get("contract") != "visual-reader-test-v1" or reader_doc.get("status") not in {"pending-human", "passed"}:
            errors.append("终审前必须有有效的 visual-reader-test.json；pending-human 只能表示尚未完成真人测试")
        else:
            errors.extend(_reader_receipt_errors(article_dir, reader_doc))
            expected_article_sha = sha256_file(article_dir / "article.md") if (article_dir / "article.md").is_file() else ""
            expected_contract_sha = sha256_file(article_dir / "visual-contract.json") if (article_dir / "visual-contract.json").is_file() else ""
            if reader_doc.get("article_sha256") != expected_article_sha:
                errors.append("visual-reader-test.json 的 article_sha256 与当前 article.md 不一致")
            if reader_doc.get("visual_contract_sha256") != expected_contract_sha:
                errors.append("visual-reader-test.json 的 visual_contract_sha256 与当前 visual-contract.json 不一致")
            depth_doc = _json(article_dir / "visual-depth-review.json")
            expected_depth_sha = sha256_file(article_dir / "visual-depth-review.json") if (article_dir / "visual-depth-review.json").is_file() else ""
            if depth_doc.get("article_sha256") != expected_article_sha:
                errors.append("visual-depth-review.json 的 article_sha256 与当前 article.md 不一致")
            if depth_doc.get("visual_contract_sha256") != expected_contract_sha:
                errors.append("visual-depth-review.json 的 visual_contract_sha256 与当前 visual-contract.json 不一致")
        aesthetic_doc = _json(article_dir / "visual-aesthetic-review.json")
        if aesthetic_doc.get("contract") != "visual-aesthetic-contract-v1" or aesthetic_doc.get("status") != "passed":
            errors.append("终审前必须有 status=passed 的 visual-aesthetic-review.json（客观美学卫生合同）")
        semantic_doc = _json(article_dir / "visual-semantic-review.json")
        if semantic_doc.get("status") != "passed":
            errors.append("终审前必须有 status=passed 的 visual-semantic-review.json")
        vision_skill = semantic_doc.get("vision_skill") if isinstance(semantic_doc, dict) else None
        if not isinstance(vision_skill, dict) or vision_skill.get("contract") != "vision-skill-v1" or vision_skill.get("status") != "available":
            errors.append("终审前必须确认 vision skill 已接入且可用")
        vision_review_doc = _json(article_dir / "vision-review.json")
        if vision_review_doc.get("contract") != "vision-review-v1" or vision_review_doc.get("status") not in {"passed", "deterministic-only"}:
            errors.append("终审前必须有 status=passed 或 deterministic-only 的 vision-review.json")
        elif str(vision_review_doc.get("reviewer_mode") or "").strip().lower() not in {"native", "external", "human", "deterministic"}:
            errors.append("vision-review.json 必须记录 native/external/human/deterministic 的实际审查模式")
        elif not str(vision_review_doc.get("capability_evidence") or "").strip():
            errors.append("vision-review.json 缺少 capability_evidence，禁止审批自证")
        if not re.search(r"(?im)^\s*-\s*visual_semantic_status:\s*passed\s*$", _text(article_dir / "final-review.md")):
            errors.append("final-review.md 必须记录 visual_semantic_status: passed")
        for field in ("requested_provider", "execution_provider"):
            if not re.search(rf"(?im)^\s*-\s*{field}:\s*\S+\s*$", _text(article_dir / "final-review.md")):
                errors.append(f"final-review.md 必须区分 {field}")
    formula_manifest_path = article_dir / "formula-manifest.json"
    if formula_manifest_path.is_file():
        formula_doc = _json(formula_manifest_path)
        if formula_doc.get("check", {}).get("status") != "passed":
            errors.append("终审前必须有 status=passed 的 formula-manifest.json check")
        if not re.search(r"(?im)^\s*-\s*formula_status:\s*passed\s*$", _text(article_dir / "final-review.md")):
            errors.append("final-review.md 必须记录 formula_status: passed")
    if "终审门禁" not in report:
        errors.append("审核报告缺少“终审门禁”清单")
    if not re.search(r"(?m)^\s*\|.*\|\s*✅", report):
        errors.append("终审报告没有逐项 ✅ 结果")
    preview = article_dir / "article_预览.html"
    if not preview.is_file() or _chars(_text(preview)) < 500:
        errors.append("缺少手机预览文件 article_预览.html")
    if not (article_dir / "img_analysis.md").is_file():
        errors.append("缺少 img_analysis.md 图片质量报告")
    if not (article_dir / "content-brief.yaml").is_file():
        errors.append("缺少 content-brief.yaml 内容策略简报")
    final_review_path = article_dir / "final-review.md"
    final_review = _text(final_review_path)
    if not final_review_path.is_file():
        errors.append("缺少 final-review.md；终审必须独立记录")
    else:
        if not re.search(r"(?im)^\s*-\s*status:\s*approved\s*$", final_review):
            errors.append("final-review.md 的 status 必须是 approved")
        human_match = re.search(r"(?im)^\s*-\s*human_review:\s*(true|false)\s*$", final_review)
        reviewer_type_match = re.search(r"(?im)^\s*-\s*reviewer_type:\s*(agent|human)\s*$", final_review)
        reviewer_match = re.search(r"(?im)^\s*-\s*reviewer:\s*(\S+)\s*$", final_review)
        reviewed_at_match = re.search(r"(?im)^\s*-\s*reviewed_at:\s*(\S+)\s*$", final_review)
        brief = _read_yaml(article_dir / "content-brief.yaml")
        risk_level = str(brief.get("risk_level", "")).strip().lower()
        human_required = brief.get("human_review_required") is True
        if risk_level in {"high", "critical"} or human_required:
            if not human_match or human_match.group(1).lower() != "true":
                errors.append("高风险内容必须在 final-review.md 明确记录 human_review: true")
            if not reviewer_type_match or reviewer_type_match.group(1) != "human":
                errors.append("高风险内容必须由 reviewer_type: human 确认，不能由 Agent 自审")
        if _requires_structured_review(article_dir):
            if not human_match:
                errors.append("final-review.md 缺少 human_review 布尔值")
            if not reviewer_type_match:
                errors.append("final-review.md 缺少 reviewer_type（agent/human）")
            if not reviewer_match:
                errors.append("final-review.md 缺少 reviewer")
            if not reviewed_at_match or not _parse_iso_date(reviewed_at_match.group(1)):
                errors.append("final-review.md 缺少有效 reviewed_at")
            if human_match and human_match.group(1).lower() == "true" and reviewer_type_match and reviewer_type_match.group(1) != "human":
                errors.append("human_review: true 时 reviewer_type 必须是 human，不能把 Agent 自审标成人审")
        if not re.search(r"(?im)^\s*-\s*mobile_width:\s*390(?:px)?\s*$", final_review):
            errors.append("final-review.md 必须记录 390px 手机预览检查")
        preview_match = re.search(r"(?im)^\s*-\s*preview_file:\s*(\S+)\s*$", final_review)
        if not preview_match:
            errors.append("final-review.md 必须记录 preview_file")
        else:
            preview_path, preview_path_error = _article_local_file(article_dir, preview_match.group(1))
            if preview_path_error or preview_path is None:
                errors.append(f"终审记录的预览文件无效：{preview_match.group(1)}（{preview_path_error}）")
            else:
                try:
                    from PIL import Image  # type: ignore

                    with Image.open(preview_path) as image:
                        if image.width not in {390, 780} or image.height < 300:
                            errors.append(f"手机预览截图尺寸不符合 390px 契约：{image.width}x{image.height}")
                except ImportError:
                    errors.append("缺少 Pillow，无法验证手机预览截图尺寸")
                except OSError:
                    errors.append(f"无法读取手机预览截图：{preview_match.group(1)}")
                expected_preview_digest = sha256_file(preview_path)
                preview_digest_match = re.search(r"(?im)^\s*-\s*preview_digest:\s*([0-9a-f]{64})\s*$", final_review)
                if not preview_digest_match or preview_digest_match.group(1).lower() != expected_preview_digest:
                    errors.append("final-review.md 的 preview_digest 与当前预览文件不一致")
                fullpage_path = article_dir / "preview-fullpage.png"
                fullpage_digest = sha256_file(fullpage_path) if fullpage_path.is_file() else ""
                fullpage_match = re.search(r"(?im)^\s*-\s*fullpage_digest:\s*([0-9a-f]{64})\s*$", final_review)
                if not fullpage_digest or not fullpage_match or fullpage_match.group(1).lower() != fullpage_digest:
                    errors.append("final-review.md 的 fullpage_digest 与全页预览不一致")
                capture_doc = _json(article_dir / "preview-capture.json")
                slice_count = int(capture_doc.get("scroll_slice_count", 0) or 0) if capture_doc else 0
                if slice_count < 1 or not re.search(rf"(?im)^\s*-\s*scroll_slice_count:\s*{slice_count}\s*$", final_review):
                    errors.append("final-review.md 必须记录 scroll_slice_count 并与 preview-capture.json 一致")
        # 增强 4 + A5（对抗审查）：human-in-the-loop 抽样升级为风险加权。
        # 样本数 = ceil(n/3)（不再是固定 1 张）；封面、Agnes/外部生成、复用素材
        # 等高风险图必审，确定性技术图用稳定种子随机补齐。
        if _requires_structured_review(article_dir):
            body_imgs = sorted(
                p for p in (article_dir / "imgs").glob("section-*.png")
                if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            )
            if len(body_imgs) >= HUMAN_SAMPLE_EVERY:
                generation_plan = _json(article_dir / "image-generation-plan.json")
                prompt_by_asset = {
                    str(item.get("asset", "")).strip(): item
                    for item in generation_plan.get("prompt_files", [])
                    if isinstance(item, dict)
                }
                must_review: list[str] = []
                for img in body_imgs:
                    asset = f"imgs/{img.name}"
                    record = prompt_by_asset.get(asset)
                    provider = str((record or {}).get("execution_provider") or "").strip().lower()
                    generation_mode = str((record or {}).get("generation_mode") or "").strip().lower()
                    source_strategy = str((record or {}).get("source_strategy") or "").strip().lower()
                    if provider in {"agnes", "local-fallback"} or generation_mode == "agnes" or "reuse" in source_strategy:
                        must_review.append(img.name)
                required_samples = max(len(must_review), -(-len(body_imgs) // HUMAN_SAMPLE_EVERY))
                # Bind the deterministic sample to the actual candidate bytes,
                # not to a relative/absolute workspace spelling.  The same
                # images must yield the same human-review packet everywhere;
                # changing any image intentionally selects a fresh sample.
                sample_seed = json.dumps(
                    [(img.name, sha256_file(img)) for img in body_imgs],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                rng = random.Random(hashlib.sha256(sample_seed).digest())
                sampled = list(must_review)
                candidates = [img.name for img in body_imgs if img.name not in sampled]
                rng.shuffle(candidates)
                sampled.extend(candidates[: max(0, required_samples - len(sampled))])
                sampled = sorted(set(sampled))
                missing = []
                for name in sampled:
                    if not re.search(
                        rf"(?im)^\s*-\s*sampled_image_reviewed:\s*true\s*[^\n]*{re.escape(name)}",
                        final_review,
                    ):
                        missing.append(name)
                if missing:
                    errors.append(
                        f"抽样人工二审未完成，需 {len(sampled)} 张（每 {HUMAN_SAMPLE_EVERY} 张至少 1 张，高风险图必审）："
                        + "；".join(missing)
                        + "；请在 final-review.md 逐张记录 `- sampled_image_reviewed: true (<图名>)`"
                    )
        if _requires_structured_review(article_dir):
            capture_path = article_dir / "preview-capture.json"
            capture = _json(capture_path)
            if not capture_path.is_file():
                errors.append("缺少 preview-capture.json；终审必须来自真实浏览器渲染")
            else:
                if capture.get("status") != "passed":
                    errors.append("preview-capture.json 的 status 必须是 passed")
                allowed_renderers = {"chrome-headless", "edge-headless"}
                if os.environ.get("WORKFLOW_TEST_MODE") == "1":
                    allowed_renderers.add("test-fixture")
                if capture.get("renderer") not in allowed_renderers:
                    errors.append("preview-capture.json 必须记录 Chrome/Edge headless 渲染器")
                if capture.get("target_kind", "local_preview") not in {"local_preview", "wechat_editor"}:
                    errors.append("preview-capture.json 的 target_kind 必须是 local_preview 或 wechat_editor")
                if not is_sha256(capture.get("dom_sha256")):
                    errors.append("preview-capture.json 缺少有效 dom_sha256")
                dom_check = capture.get("dom_check")
                if not isinstance(dom_check, dict) or dom_check.get("status") != "passed":
                    errors.append("preview-capture.json 必须包含通过的 dom_check 浏览器运行时检查")
                else:
                    if dom_check.get("title_present") is not True:
                        errors.append("浏览器 DOM 检查未发现文章标题")
                    try:
                        if int(dom_check.get("body_text_chars", 0) or 0) < 80:
                            errors.append("浏览器 DOM 检查发现正文过短")
                    except (TypeError, ValueError):
                        errors.append("浏览器 DOM 检查缺少 body_text_chars")
                    try:
                        if int(dom_check.get("image_count", 0) or 0) < 1:
                            errors.append("浏览器 DOM 检查未发现正文图片")
                    except (TypeError, ValueError):
                        errors.append("浏览器 DOM 检查缺少 image_count")
                    try:
                        if int(dom_check.get("placeholder_count", 0) or 0) != 0:
                            errors.append("浏览器 DOM 检查发现 placeholder 素材")
                    except (TypeError, ValueError):
                        errors.append("浏览器 DOM 检查缺少 placeholder_count")
                viewport = capture.get("viewport")
                viewport_width = 0
                if isinstance(viewport, dict):
                    try:
                        viewport_width = int(viewport.get("width", 0) or 0)
                    except (TypeError, ValueError):
                        viewport_width = 0
                if viewport_width != 390:
                    errors.append("preview-capture.json 的 viewport.width 必须是 390")
                source_name = str(capture.get("source", "article_预览.html"))
                source_path, source_path_error = _article_local_file(article_dir, source_name)
                if source_path_error or source_path is None or capture.get("source_sha256") != sha256_file(source_path):
                    errors.append("preview-capture.json 的 source_sha256 与预览 HTML 不一致")
                screenshot_name = str(capture.get("screenshot", "preview_screenshot.png"))
                screenshot_path, screenshot_path_error = _article_local_file(article_dir, screenshot_name)
                if screenshot_path_error or screenshot_path is None or capture.get("screenshot_sha256") != sha256_file(screenshot_path):
                    errors.append("preview-capture.json 的 screenshot_sha256 与截图不一致")
                fullpage_name = str(capture.get("fullpage_screenshot", "preview-fullpage.png"))
                fullpage_path, fullpage_path_error = _article_local_file(article_dir, fullpage_name)
                if fullpage_path_error or fullpage_path is None or capture.get("fullpage_screenshot_sha256") != sha256_file(fullpage_path):
                    errors.append("preview-capture.json 的 fullpage_screenshot_sha256 与全页截图不一致")
                slices = capture.get("scroll_slices")
                if not isinstance(slices, list) or not slices:
                    errors.append("preview-capture.json 必须包含 scroll_slices 分段截图")
                else:
                    for slice_item in slices:
                        if not isinstance(slice_item, dict):
                            errors.append("preview-capture.json 含有无法解析的 scroll slice")
                            continue
                        slice_name = str(slice_item.get("path", "")).strip()
                        slice_path, slice_path_error = _article_local_file(article_dir, slice_name)
                        if slice_path_error or slice_path is None or slice_item.get("sha256") != sha256_file(slice_path):
                            errors.append(f"scroll slice 缺失或 hash 不一致：{slice_name}")
        expected_article_digest = sha256_file(article_dir / "article.md") if (article_dir / "article.md").is_file() else ""
        expected_html_digest = sha256_file(article_dir / "article.html") if (article_dir / "article.html").is_file() else ""
        article_digest_match = re.search(r"(?im)^\s*-\s*article_digest:\s*([0-9a-f]{64})\s*$", final_review)
        html_digest_match = re.search(r"(?im)^\s*-\s*html_digest:\s*([0-9a-f]{64})\s*$", final_review)
        if not article_digest_match or article_digest_match.group(1).lower() != expected_article_digest:
            errors.append("final-review.md 的 article_digest 与当前 article.md 不一致")
        if not html_digest_match or html_digest_match.group(1).lower() != expected_html_digest:
            errors.append("final-review.md 的 html_digest 与当前 article.html 不一致")
    # ── A9（对抗审查）：回执隐私扫描 ──────────────────────────────────────
    # 本阶段所属回执若被上传、分享或进入知识库，不得携带
    # 本机绝对路径、凭证文件名或密钥变量名（复用 article_integrity 规则）。
    # publish-* 回执属于后续 draft_submitted 阶段；其 pending/失败内容
    # 不得反向使已完成的 final_reviewed 过期。
    for artifact in ("preview-capture.json", "source-verification.json"):
        raw_text = _text(article_dir / artifact)
        if not raw_text:
            continue
        scan_text = raw_text
        if artifact.endswith(".json"):
            try:
                doc = json.loads(raw_text)
                if isinstance(doc, dict):
                    for key in ("appid_key", "appsecret_key", "credential_names_found"):
                        doc.pop(key, None)
                    scan_text = json.dumps(doc, ensure_ascii=False, indent=2)
            except (json.JSONDecodeError, OSError):
                pass
        for finding in public_content_findings(scan_text):
            errors.append(
                f"{artifact} 包含不应公开的 {finding['rule']} 标记（第 {finding['line']} 行）；"
                "请去除本机路径/凭证线索后重新生成回执"
            )
    return errors


def _publish_preflight_errors(article_dir: Path, args: argparse.Namespace | None) -> list[str]:
    """Validate publish-only credentials and the signed token-probe receipt."""

    errors: list[str] = []
    config = _read_yaml(ROOT / ".aws-article" / "config.yaml")
    if str(config.get("publish_method", "draft")).strip().lower() == "none":
        errors.append("publish_method=none；当前配置禁止提交微信草稿")
    try:
        configured_slot = int(config.get("wechat_publish_slot", 0) or 0)
    except (TypeError, ValueError):
        configured_slot = 0
    expected_slot = int(PUBLISH_SLOT)
    if configured_slot != expected_slot:
        errors.append(
            f"config.yaml 的 wechat_publish_slot={configured_slot or 'invalid'} "
            f"与工作流固定槽位 {expected_slot} 不一致"
        )

    env_path = _publish_env_path(args)
    if env_path is None or not env_path.is_file():
        errors.append(
            "缺少显式仓库外微信凭证文件；请通过 --env 或 WECHAT_ENV_PATH 指定"
        )
        env_path_for_receipt = None
    elif _path_is_inside_repository(env_path):
        errors.append("外部微信凭证文件不能位于仓库内；请移出 aws.env/.env")
        env_path_for_receipt = None
    else:
        env_path_for_receipt = env_path
        env_names = {
            line.split("=", 1)[0].strip()
            for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", line.strip())
        }
        for suffix in ("APPID", "APPSECRET"):
            if f"WECHAT_{expected_slot}_{suffix}" not in env_names:
                errors.append(f"外部凭证缺少 WECHAT_{expected_slot}_{suffix}")

    preflight_path = article_dir / "publish-preflight.json"
    preflight = _json(preflight_path)
    if not preflight_path.is_file():
        return errors + ["缺少 publish-preflight.json；发布权限和 IP 白名单必须先完成预检"]
    if preflight.get("status") != "passed":
        errors.append("publish-preflight.json 的 status 必须是 passed")
    if not _parse_iso_date(preflight.get("checked_at")):
        errors.append("publish-preflight.json 缺少有效 checked_at")
    try:
        if int(preflight.get("account_slot")) != expected_slot:
            errors.append("publish-preflight.json 的 account_slot 与固定发布槽位不一致")
    except (TypeError, ValueError):
        errors.append("publish-preflight.json 缺少数值 account_slot")
    if preflight.get("draft_permission") is not True:
        errors.append("publish-preflight.json 必须明确记录 draft_permission: true")
    if preflight.get("ip_whitelist_checked") is not True:
        errors.append("publish-preflight.json 必须明确记录 ip_whitelist_checked: true")
    if str(preflight.get("appid_key", "")).strip() != f"WECHAT_{expected_slot}_APPID":
        errors.append("publish-preflight.json 的 appid_key 与固定发布槽位不一致")
    if str(preflight.get("appsecret_key", "")).strip() != f"WECHAT_{expected_slot}_APPSECRET":
        errors.append("publish-preflight.json 的 appsecret_key 与固定发布槽位不一致")
    if _requires_structured_review(article_dir):
        probe = preflight.get("probe")
        if not isinstance(probe, dict) or probe.get("status") != "passed":
            errors.append("publish-preflight.json 必须包含 status=passed 的实际 token probe")
    errors.extend(
        f"publish-preflight 完整性：{error}"
        for error in verify_receipt_integrity(
            preflight,
            article_dir,
            receipt_kind="publish-preflight",
            account_slot=expected_slot,
            env_path=env_path_for_receipt,
        )
    )
    return errors


def _errors_for_submission(article_dir: Path, args: argparse.Namespace | None = None) -> list[str]:
    errors = _publish_preflight_errors(article_dir, args)
    receipt_path = article_dir / "publish-receipt.json"
    receipt = _json(receipt_path)
    if not receipt:
        return errors + ["publish-receipt.json 缺失或不是合法 JSON"]
    meta_for_slot = _read_yaml(article_dir / "article.yaml")
    try:
        expected_slot = int(PUBLISH_SLOT)
    except (TypeError, ValueError):
        expected_slot = None
    env_path_for_receipt = _publish_env_path(args)
    if env_path_for_receipt is not None and _path_is_inside_repository(env_path_for_receipt):
        env_path_for_receipt = None
    errors.extend(
        f"publish-receipt 完整性：{error}"
        for error in verify_receipt_integrity(
            receipt,
            article_dir,
            receipt_kind="publish-receipt",
            account_slot=expected_slot,
            env_path=env_path_for_receipt,
        )
    )
    if receipt.get("status") != "draft_created_and_verified":
        errors.append("草稿回执状态必须是 draft_created_and_verified")
    if receipt.get("mode") != "draft":
        errors.append("当前工作流只允许以 draft 模式进入草稿箱")
    if _requires_structured_review(article_dir):
        meta = _read_yaml(article_dir / "article.yaml")
        if meta.get("draft_submitted") is not True:
            errors.append("article.yaml 的 draft_submitted 必须是 true")
        if meta.get("draft_verified") is not True:
            errors.append("article.yaml 的 draft_verified 必须是 true")
        if meta.get("public_published") is not False:
            errors.append("draft 模式下 article.yaml 的 public_published 必须是 false")
    if not receipt.get("media_id"):
        errors.append("草稿回执缺少 media_id")
    readback = receipt.get("readback")
    if not isinstance(readback, dict):
        errors.append("草稿回执缺少 readback 回读结果")
    else:
        for key in ("title_matches", "author_matches"):
            if readback.get(key) is not True:
                errors.append(f"草稿回读 {key} 未通过")
        if readback.get("literal_unicode_escapes", 0) != 0:
            errors.append("草稿正文残留字面量 \\uXXXX 转义")
        if readback.get("replacement_characters", 0) != 0:
            errors.append("草稿正文残留 Unicode 替换字符")
        if readback.get("content_has_div") is True:
            errors.append("草稿正文回读发现 <div>")
        if readback.get("html_validator") != "passed":
            errors.append("草稿回读的 HTML 校验没有 passed")
        html_path = article_dir / "article.html"
        local_digest = canonical_html_digest(_text(html_path)) if html_path.is_file() else ""
        if readback.get("local_html_digest") != local_digest:
            errors.append("草稿回读缺少当前 HTML 的 local_html_digest")
        if readback.get("html_digest_matches") is not True:
            # WeChat rewrites image URLs and sanitizes HTML during draft/add.
            # Keep the mismatch visible in the receipt, but accept it only
            # when the verifier explicitly classified it as platform
            # normalization and all independent readback checks passed.
            if readback.get("html_normalization_status") != "wechat_draft_normalized":
                errors.append("草稿回读的远端正文指纹与当前 HTML 不一致且未声明微信规范化")
        if int(readback.get("image_count", 0) or 0) < 1:
            errors.append("草稿回读没有正文图片")
        local_image_count = len(_image_paths(_text(html_path))) if html_path.is_file() else 0
        if local_image_count and int(readback.get("image_count", 0) or 0) != local_image_count:
            errors.append(
                f"草稿回读图片数量 {readback.get('image_count')} 与当前 HTML {local_image_count} 不一致；必须重新提交草稿"
            )
        # A6（对抗审查）：图片计数必须分类——公式 PNG 不能充当正文认知锚点，
        # 反之缺一张章节锚点也可能被总 img 数掩盖。回读分别核对两类计数。
        if html_path.is_file():
            html_text = _text(html_path)
            formula_refs = {
                raw
                for raw in _image_paths(html_text)
                if raw.startswith("imgs/formulas/") or "/formulas/" in raw
            }
            body_anchor_refs = {
                raw
                for raw in _image_paths(html_text)
                if raw not in formula_refs and not raw.startswith("imgs/cover")
            }
            formula_manifest = _json(article_dir / "formula-manifest.json")
            expected_formula_count = len(formula_manifest.get("formulas", [])) if isinstance(formula_manifest.get("formulas"), list) else 0
            if expected_formula_count and int(readback.get("formula_image_count", -1) or -1) != len(formula_refs):
                errors.append(
                    f"草稿回读公式图片数 {readback.get('formula_image_count')} 与本地 HTML {len(formula_refs)} 不一致（formula-manifest 应渲染 {expected_formula_count} 个公式）"
                )
            brief = _read_yaml(article_dir / "visual-brief.yaml")
            brief_anchors = [
                str(item.get("asset", "")).strip()
                for item in brief.get("body_visuals", [])
                if isinstance(item, dict)
            ]
            if brief_anchors and int(readback.get("body_anchor_count", -1) or -1) != len(body_anchor_refs):
                errors.append(
                    f"草稿回读正文认知锚点数 {readback.get('body_anchor_count')} 与本地 HTML {len(body_anchor_refs)} 不一致；公式图不计入认知锚点"
                )
    submitted_at = receipt.get("submitted_at") or receipt.get("created_at")
    html_path = article_dir / "article.html"
    if not submitted_at:
        errors.append("草稿回执缺少 submitted_at")
    elif html_path.is_file():
        try:
            stamp = datetime.fromisoformat(str(submitted_at).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            # Parseability matters for transaction ordering, but filesystem
            # mtime does not.  The exact html_digest below is the freshness
            # proof and survives harmless touch/copy operations.
        except (TypeError, ValueError, OSError):
            errors.append("草稿回执 submitted_at 无法解析，不能确认其对应当前 HTML")
    if html_path.is_file() and receipt.get("html_digest") != sha256_file(html_path):
        errors.append("草稿回执 html_digest 与当前 article.html 不一致")

    # ── A4（对抗审查）：attempt/receipt 必须构成可复核的幂等事务 ──────────
    # prepare → preflight → submit(operation_id) → readback → reconcile → receipt。
    # attempt 未 passed、或 attempt 与 receipt 的 media_id/html_digest 不一致、
    # 或回执早于 attempt，都说明提交记录被人为拼接过，必须阻断。
    attempt_path = article_dir / "publish-attempt.json"
    attempt = _json(attempt_path)
    if not attempt_path.is_file():
        errors.append("缺少 publish-attempt.json；提交必须是 attempt→receipt 的幂等事务")
    else:
        errors.extend(
            f"publish-attempt 完整性：{error}"
            for error in verify_receipt_integrity(
                attempt,
                article_dir,
                receipt_kind="publish-attempt",
                account_slot=expected_slot,
                env_path=env_path_for_receipt,
            )
        )
        if attempt.get("status") != "passed":
            errors.append("publish-attempt.json 的 status 必须是 passed（attempt 未成功，receipt 不可信）")
        for field in ("media_id", "html_digest"):
            attempt_value = attempt.get(field)
            receipt_value = receipt.get(field)
            if attempt_value and receipt_value and str(attempt_value) != str(receipt_value):
                errors.append(f"publish-attempt 与 receipt 的 {field} 不一致：attempt={attempt_value} receipt={receipt_value}")
        if attempt.get("operation_id") and receipt.get("operation_id") and attempt.get("operation_id") != receipt.get("operation_id"):
            errors.append("publish-attempt 与 receipt 的 operation_id 不一致")
        if attempt.get("created_at") and submitted_at:
            try:
                stamp_attempt = datetime.fromisoformat(str(attempt["created_at"]).replace("Z", "+00:00"))
                stamp_receipt = datetime.fromisoformat(str(submitted_at).replace("Z", "+00:00"))
                if stamp_attempt.tzinfo is None:
                    stamp_attempt = stamp_attempt.replace(tzinfo=timezone.utc)
                if stamp_receipt.tzinfo is None:
                    stamp_receipt = stamp_receipt.replace(tzinfo=timezone.utc)
                if stamp_receipt.timestamp() + 1 < stamp_attempt.timestamp():
                    errors.append("草稿回执早于 attempt；事务顺序错误，可能为陈旧回执")
            except (TypeError, ValueError):
                errors.append("publish-attempt 的 created_at 无法解析")
    # mock/生产隔离：回执必须显式声明 target_kind；mock 只允许在测试夹具中推进。
    target_kind = str(receipt.get("target_kind") or "").strip().lower()
    if target_kind not in {"wechat", "mock"}:
        errors.append("草稿回执必须显式声明 target_kind=mock|wechat")
    if target_kind == "mock" and os.environ.get("WORKFLOW_TEST_MODE") != "1":
        errors.append("mock 回执只能用于测试夹具，禁止推进生产 draft_submitted；请使用真实微信凭证重新提交")
    return errors


CHECKERS = {
    "environment_ready": _errors_for_environment,
    "topic_selected": _errors_for_topic,
    "research_complete": _errors_for_research,
    "research_reviewed": _errors_for_research_review,
    "draft_complete": _errors_for_draft,
    "content_reviewed": _errors_for_review,
    "formatted": _errors_for_formatted,
    "illustrated": _errors_for_illustrated,
    "final_reviewed": _errors_for_final,
    "draft_submitted": _errors_for_submission,
}


def gate_index(key: str) -> int:
    if key == "none":
        return -1
    try:
        return GATE_KEYS.index(key)
    except ValueError as exc:
        raise ValueError(f"未知工作流阶段：{key}") from exc


def current_stage(state: dict[str, Any]) -> str:
    stage = state.get("current_stage")
    if isinstance(stage, str) and (stage == "none" or stage in GATE_KEYS):
        return stage
    return STATUS_TO_GATE.get(str(state.get("status", "selected")), "none")


def validate_transition(state: dict[str, Any], target: str) -> list[str]:
    errors: list[str] = []
    current = current_stage(state)
    current_idx = gate_index(current)
    target_idx = gate_index(target)
    if target_idx > current_idx + 1:
        next_key = GATE_KEYS[current_idx + 1]
        errors.append(f"不能跳过阶段：当前是 {current}，下一阶段只能是 {next_key}")
    if target_idx <= current_idx:
        errors.append(f"阶段 {target} 已经通过或早于当前状态 {current}，如需复核请不要使用 --advance")
    return errors


def evaluate_stage(article_dir: Path, stage: str, args: argparse.Namespace) -> list[str]:
    visual_contract_path = article_dir / "visual-contract.json"
    contract_before = sha256_file(visual_contract_path) if visual_contract_path.is_file() else ""
    errors = CHECKERS[stage](article_dir, args) if stage in {"environment_ready", "draft_submitted"} else CHECKERS[stage](article_dir)
    contract_after = sha256_file(visual_contract_path) if visual_contract_path.is_file() else ""
    if contract_before and contract_after and contract_before != contract_after:
        errors = list(errors) + [f"阶段检查改写了 visual-contract.json（before={contract_before}, after={contract_after}）；检查必须无副作用"]
    # RC6: run the declarative stage contract as an additive layer.  The prose
    # in workflow-gates.yaml is now backed by executable data; a stage passes
    # only when both the rich semantic checks and the structural contract agree.
    contract_errors = validate_stage_contract(article_dir, stage)
    if contract_errors:
        errors = list(errors) + [f"[契约] {e}" for e in contract_errors]
    return errors


def load_state(article_dir: Path) -> dict[str, Any]:
    path = article_dir / "matrix-state.json"
    state = _json(path)
    if not state:
        raise ValueError(f"缺少或无法解析 {path.relative_to(ROOT)}")
    return state


def _prepare_readonly_workspace(article_dir: Path, temp_root: Path) -> Path:
    """Copy an article into a valid ephemeral artifact root for gate checks.

    Several semantic checkers intentionally validate the production workspace
    contract before writing their derived reports.  A plain temp copy outside
    ``production/`` therefore looked invalid and made ``--all`` fail even when
    the real registered workspace was valid.  Mirror the artifact-root layout
    and registry so subprocesses keep the same security checks while all
    checker writes remain isolated from the real article.
    """

    evaluation_dir = temp_root / "active" / article_dir.name
    evaluation_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(article_dir, evaluation_dir)
    state = _json(evaluation_dir / "matrix-state.json")
    workspace_id = str(state.get("workspace_id") or "-").strip()
    if not re.fullmatch(r"THK-\d{8}-\d{3}", workspace_id):
        workspace_id = "-".join(article_dir.name.split("-", 3)[:3])
    registry_dir = temp_root / "registry"
    registry_dir.mkdir(parents=True, exist_ok=True)
    (registry_dir / "workspace-index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "contract": "workspace-index-v1",
                "workspaces": [{
                    "workspace_id": workspace_id,
                    "relative_path": f"active/{article_dir.name}",
                }],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return evaluation_dir


def save_state(
    article_dir: Path,
    state: dict[str, Any],
    *,
    expected_state_sha256: str = "",
    expected_content_snapshot: str = "",
) -> None:
    """Persist a stage transition under a lock with last-moment CAS checks."""

    path = article_dir / "matrix-state.json"
    with state_lock(article_dir):
        if expected_state_sha256:
            actual = sha256_file(path) if path.is_file() else ""
            if actual != expected_state_sha256:
                raise StateConflict("matrix-state.json changed during gate evaluation")
        if expected_content_snapshot and content_snapshot(article_dir) != expected_content_snapshot:
            raise StateConflict("article inputs changed during gate evaluation")
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
        # Keep visual-contract.json immutable after visual generation.  Gate
        # progress belongs to matrix-state/workflow-status; embedding it here
        # changes the contract hash and invalidates reader/vision receipts after
        # every otherwise-valid --advance.
        # workflow-status is a derived view, never an independently stale writer.
        # Generate it in the same state transition and promote atomically.
        try:
            from workflow_status import build as build_workflow_status

            status_path = article_dir / "workflow-status.json"
            status_tmp = status_path.with_suffix(".json.tmp")
            status_tmp.write_text(
                json.dumps(build_workflow_status(article_dir), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            status_tmp.replace(status_path)
        except (ImportError, OSError, TypeError, ValueError):
            # A state transition must still be visible; the next explicit status
            # command can rebuild the view if the optional renderer is unavailable.
            pass


def run(args: argparse.Namespace) -> int:
    try:
        article_dir = ensure_article_path(args.article, allow_test_fixture=True)
    except ValueError as exc:
        print(f"GATE BLOCKED: {exc}")
        return 1
    if not article_dir.is_dir():
        print(f"GATE BLOCKED: 文章目录不存在：{args.article}")
        return 1
    try:
        state = load_state(article_dir)
        target_idx = gate_index(args.stage)
    except ValueError as exc:
        print(f"GATE BLOCKED: {exc}")
        return 1

    expected_state_sha256 = sha256_file(article_dir / "matrix-state.json") if args.advance else ""
    expected_content_snapshot = content_snapshot(article_dir) if args.advance else ""

    if args.advance:
        transition_errors = validate_transition(state, args.stage)
        if transition_errors:
            print("GATE BLOCKED: 顺序门禁未通过")
            for error in transition_errors:
                print(f"- {error}")
            return 1
        stages_to_check = GATE_KEYS[: target_idx + 1]
    elif args.all or args.stage in {"final_reviewed", "draft_submitted"}:
        # High-stakes read-only checks must re-evaluate the complete chain.
        # Otherwise a stale matrix-state.json can say final_reviewed even when
        # an earlier illustrated/content gate has since become invalid.
        stages_to_check = GATE_KEYS[: target_idx + 1]
    else:
        stages_to_check = (args.stage,)

    # Checker scripts produce useful reports, but a plain `check` must not
    # mutate the evidence being checked.  Evaluate a complete temporary copy
    # unless this invocation is the explicit state-changing `--advance`.
    temp_workspace: tempfile.TemporaryDirectory[str] | None = None
    evaluation_dir = article_dir
    previous_gate_check_mode = os.environ.get("WORKFLOW_GATE_CHECK")
    previous_artifact_root = os.environ.get("GZH_ARTIFACT_ROOT")
    if not args.advance:
        temp_workspace = tempfile.TemporaryDirectory(prefix="workflow-gate-check-")
        temp_root = Path(temp_workspace.name)
        evaluation_dir = _prepare_readonly_workspace(article_dir, temp_root)
        os.environ["WORKFLOW_GATE_CHECK"] = "1"
        os.environ["GZH_ARTIFACT_ROOT"] = str(temp_root)

    failures: dict[str, list[str]] = {}
    try:
        for stage in stages_to_check:
            errors = evaluate_stage(evaluation_dir, stage, args)
            label = next(g.label for g in GATES if g.key == stage)
            if errors:
                failures[stage] = errors
                print(f"[BLOCKED] {stage}｜{label}")
                for error in errors:
                    print(f"  - {error}")
            else:
                print(f"[PASS]    {stage}｜{label}")
    finally:
        if temp_workspace is not None:
            temp_workspace.cleanup()
        if previous_gate_check_mode is None:
            os.environ.pop("WORKFLOW_GATE_CHECK", None)
        else:
            os.environ["WORKFLOW_GATE_CHECK"] = previous_gate_check_mode
        if previous_artifact_root is None:
            os.environ.pop("GZH_ARTIFACT_ROOT", None)
        else:
            os.environ["GZH_ARTIFACT_ROOT"] = previous_artifact_root
    if failures:
        print(f"GATE BLOCKED: {len(failures)} 个阶段未通过，未写入状态")
        return 1

    if args.advance:
        history = state.setdefault("gate_history", [])
        if not isinstance(history, list):
            history = []
            state["gate_history"] = history
        state["current_stage"] = args.stage
        state["status"] = args.stage
        history.append({
            "stage": args.stage,
            "passed_at": datetime.now(timezone.utc).isoformat(),
            "checks": "strict",
        })
        try:
            save_state(
                article_dir,
                state,
                expected_state_sha256=expected_state_sha256,
                expected_content_snapshot=expected_content_snapshot,
            )
        except (StateConflict, TimeoutError) as exc:
            print(f"GATE BLOCKED: 并发/时序冲突，未写入状态：{exc}")
            return 1
        print(f"GATE ADVANCED: {args.stage}")
    else:
        print(f"GATE CHECKED: {args.stage}")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, help="文章工作区目录")
    parser.add_argument("--stage", choices=GATE_KEYS, required=True)
    parser.add_argument("--advance", action="store_true", help="通过后推进 current_stage；默认只检查不写入")
    parser.add_argument("--all", action="store_true", help="连同目标之前的所有阶段一起检查")
    parser.add_argument("--env", help="仓库外的 aws.env 路径；不会读取或打印密钥值")
    args = parser.parse_args()
    if args.advance and args.all:
        parser.error("--advance 与 --all 不能同时使用")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
