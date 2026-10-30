#!/usr/bin/env python3
"""Initialize a reviewable article workspace for either matrix account."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from route_content import load_route, route_digest, validate_route_document  # noqa: E402
from workflow_security import load_yaml as strict_load_yaml  # noqa: E402
from workspace_paths import (  # noqa: E402
    allocate_workspace,
    artifact_root,
    resolve_route_path,
    slugify,
    workspace_manifest,
)
from account_context import (  # noqa: E402
    ACCOUNT_ID, ACCOUNT_IDS, DISPLAY_NAME, PUBLIC_BRAND, INTERNAL_ACCOUNT_NAME,
    FORMATTER_THEME, IMAGE_THEME, CONTENT_LENGTH, PUBLISH_SLOT, check_identity_consistency,
)


def _bootstrap_presets() -> None:
    """Create public local preset seeds before initializing an article."""
    try:
        from bootstrap_article_environment import ensure_article_environment
    except ImportError:
        return
    ensure_article_environment()


def write_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", default=ACCOUNT_ID, choices=sorted(ACCOUNT_IDS),
                        help=f"固定为本工作流账号 {ACCOUNT_ID}")
    parser.add_argument("--title", required=True)
    parser.add_argument("--slug", help="optional stable slug; generated from title when omitted")
    parser.add_argument("--date", default=date.today().strftime("%Y%m%d"))
    parser.add_argument(
        "--root",
        default=None,
        help="外部 artifact root 下的新稿父目录；默认 <GZH_ARTIFACT_ROOT>/active，禁止使用仓库 drafts/",
    )
    parser.add_argument(
        "--route",
        required=True,
        type=Path,
        help="已由 route_content.py 确认的选题/账号路由文件；不允许跳过",
    )
    args = parser.parse_args()

    try:
        route_path = resolve_route_path(args.route, allow_test_fixture=True)
    except ValueError as exc:
        print(f"MATRIX INIT BLOCKED: {exc}")
        return 1
    if not route_path.is_file():
        print(f"MATRIX INIT BLOCKED: 路由文件不存在：{route_path}")
        return 1
    route = load_route(route_path)
    route_errors = validate_route_document(route, expected_account=args.account)
    if route_errors:
        print("MATRIX INIT BLOCKED: 选题/账号路由未确认")
        for error in route_errors:
            print(f"- {error}")
        return 1

    _bootstrap_presets()

    account_name = PUBLIC_BRAND
    internal_account_name = INTERNAL_ACCOUNT_NAME
    formatter_theme = FORMATTER_THEME
    image_theme = IMAGE_THEME
    length_hint = CONTENT_LENGTH
    publish_slot = PUBLISH_SLOT
    config_path = ROOT / ".aws-article" / "config.yaml"
    if config_path.is_file():
        try:
            import yaml  # type: ignore

            publish_slot = int((strict_load_yaml(config_path, default={}) or {}).get("wechat_publish_slot", PUBLISH_SLOT) or PUBLISH_SLOT)
        except (ImportError, OSError, TypeError, ValueError):
            publish_slot = PUBLISH_SLOT
    identity_problems = check_identity_consistency()
    if identity_problems:
        print("MATRIX INIT BLOCKED: workflow 身份不一致")
        for problem in identity_problems:
            print(f"- {problem}")
        return 1
    try:
        article_dir, workspace_id, sequence = allocate_workspace(
            args.title,
            date_value=args.date,
            requested_slug=args.slug,
            root=args.root,
        )
    except (OSError, ValueError, TimeoutError) as exc:
        print(f"MATRIX INIT BLOCKED: {exc}")
        return 1
    slug = slugify(args.slug or args.title)
    manifest = workspace_manifest(article_dir, workspace_id, args.title, slug)
    (article_dir / "workspace-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_if_missing(
        article_dir / "article.yaml",
        "\n".join(
            [
                "schema_version: 1",
                f"workspace_id: {workspace_id}",
                f"workspace_relative_path: {manifest['relative_path']}",
                f"account: {args.account}",
                "content_medium: wechat_article",
                f"route_digest: {route_digest(route_path)}",
                f"topic_route_mode: {route['topic_route']['mode']}",
                f"account_route: {args.account}",
                f"title: \"{args.title.replace(chr(34), '')}\"",
                f"author: {account_name}",
                f"public_brand: {account_name}",
                f"internal_account_name: {internal_account_name}",
                f"digest: \"围绕{args.title.replace(chr(34), '')}给出可复现、可审核的公众号内容方案。\"",
                "content_source: article.html",
                "publish_mode: draft",
                f"visual_theme: {formatter_theme}",
                f"image_theme: {image_theme}",
                f"content_length: \"{length_hint}\"",
                f"default_format_preset:\n  - {formatter_theme}",
                "default_structure:",
                "  - AI 项目问题驱动教程结构",
                "default_closing_block:",
                "  - 公众号关注引导",
                "default_cover_image_style: 编辑部视觉系统",
                "default_article_image_style: 认知锚点图",
                "publish_completed: false",
                "draft_submitted: false",
                "draft_verified: false",
                "public_published: false",
                "",
            ]
        ),
    )

    write_if_missing(article_dir / "topic-card.md", f"# 选题卡｜{args.title}\n\n- 账号：{account_name}\n- 状态：selected\n- 目标读者：\n- 核心判断：\n- 主要来源：\n- 可搜索关键词：\n- 可分享角度：\n- 读者下一步动作：\n")
    write_if_missing(article_dir / "topic-contract.yaml", "\n".join([
        "schema_version: 1",
        "status: draft",
        "canonical_topic: \"\"",
        "topic_thesis: \"\"",
        "reader_problem: \"\"",
        "scope:",
        "  in_scope: []",
        "  out_of_scope: []",
        "anchor:",
        "  required_terms: []",
        "  aliases: []",
        "  minimum_total_hits: 3",
        "series:",
        "  mode: cluster",
        "  subtopics: []",
        "drift_rules:",
        "  min_anchor_coverage: 0.6",
        "  max_anchorless_sections: 1",
        "  require_anchor_in_title: true",
        "  require_anchor_in_lead: true",
        "  require_section_return: true",
        "approval:",
        "  reviewer: \"\"",
        "  approved_at: \"\"",
        "  decision_note: \"\"",
        "",
    ]))
    write_if_missing(article_dir / "topic-cluster.md", "\n".join([
        f"# 主题簇｜{args.title}",
        "",
        "> 先填写 topic-contract.yaml，再把同一主题的母题、子题和内容缺口记录在这里。",
        "",
        "## 核心母题",
        "",
        "待填写：这组内容始终要回到的唯一主问题。",
        "",
        "## 相邻选题与内容缺口",
        "",
        "待填写：至少 3 个子题；每个子题必须说明为什么属于主主题。",
        "",
        "## 复用边界",
        "",
        "待填写：哪些内容可以派生，哪些内容不能反向替代主稿事实。",
        "",
    ]))
    write_if_missing(article_dir / "content-calendar.md", "# 内容日历\n\n- 状态：待完成主题合同后安排\n- 选题簇：\n- 发布节奏：\n- 复盘指标：\n")
    write_if_missing(article_dir / "topic-integrity.json", json.dumps({
        "schema_version": 1,
        "contract": "topic-contract.yaml",
        "content": "draft.md",
        "status": "pending",
        "errors": ["topic-contract.yaml 尚未批准"],
    }, ensure_ascii=False, indent=2) + "\n")
    profile = {}
    profile_path = ROOT / "profiles" / f"{ACCOUNT_ID}.yaml"
    if profile_path.is_file():
        try:
            import yaml  # type: ignore
            profile = strict_load_yaml(profile_path, default={}) or {}
        except (ImportError, OSError, ValueError):
            profile = {}
    conversion_stage = str(profile.get("conversion_stage") or "discovery_to_follow")
    # CTA is an article-level promise, not a timeless account slogan.  Seed it
    # from the routed topic so a new subject cannot inherit "公式/架构/资料"
    # wording from a previous article and then pass only because the brand
    # name happens to match.
    routed_topic = str((route.get("topic_route") or {}).get("topic") or "").strip()
    topic_hint = re.sub(r"[\s:：,，。！？!?/\\]+", " ", routed_topic or args.title).strip()
    topic_hint = topic_hint[:24].strip() or "本期主题"
    profile_reply = str(profile.get("reply_keyword") or "").strip()
    reply_keyword = profile_reply if profile_reply and profile_reply.lower() in topic_hint.lower() else topic_hint[:16]
    cta = f"关注 {account_name}，回复‘{reply_keyword}’领取 {topic_hint} 实战图解与检查清单"
    secondary_cta = f"如果你正在把 {topic_hint} 落到项目里，留言你的具体问题，我会继续补充实现与部署细节"
    lead_magnet = f"{topic_hint} 实战图解与检查清单"
    offer = str(profile.get("commercial_offer") or "")
    write_if_missing(article_dir / "content-brief.yaml", f"schema_version: 3\naccount: {args.account}\ntitle: \"{args.title.replace(chr(34), '')}\"\naudience: \"\"\nprimary_keyword: \"\"\nshareable_angle: \"\"\nprimary_claim: \"\"\ncta: \"{cta}\"\npublic_brand: \"{account_name}\"\nconversion_stage: {conversion_stage}\nprimary_cta: \"{cta}\"\nsecondary_cta: \"{secondary_cta}\"\nlead_magnet: \"{lead_magnet}\"\nreply_keyword: {reply_keyword}\ncommercial_offer: \"{offer}\"\nrisk_level: medium\nhuman_review_required: false\nstatus: draft\n")
    try:
        from cta_contract import build as build_cta_contract
        write_if_missing(
            article_dir / "cta-contract.json",
            json.dumps(build_cta_contract(article_dir), ensure_ascii=False, indent=2) + "\n",
        )
    except Exception as exc:  # noqa: BLE001 - contract is advisory until topic gate
        write_if_missing(
            article_dir / "cta-contract.json",
            json.dumps({
                "schema_version": 1,
                "contract": "cta-contract-v1",
                "status": "pending",
                "error": str(exc),
            }, ensure_ascii=False, indent=2) + "\n",
        )
    write_if_missing(article_dir / "seo-report.json", json.dumps({"schema_version": 1, "status": "pending", "score": 0, "title_score": 0, "keywords": []}, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "research.md", "# 调研与实测\n\n- 状态：researched\n- 来源快照：\n- 主张与证据：在 sources.json claims 中逐条映射；每个 evidence_locator 必须包含 source_id、kind、ref（URL 锚点/快照路径/代码行范围）\n- 版本/环境：\n- 可复现命令：\n- 已知限制：\n- 证据等级：\n- 混合证据层：先运行 source_evidence.py init，再为正文采用的可信来源补充摘录/截图并完成 audit\n")
    write_if_missing(article_dir / "sources.json", json.dumps({"schema_version": 1, "sources": [], "claims": []}, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "source-review.json", json.dumps({
        "schema_version": 1,
        "contract": "source-review-v1",
        "status": "pending",
        "review_method": "structured-source-scope-review-v1",
        "reviewer_type": "agent",
        "reviewer": "",
        "reviewed_at": "",
        "sources_digest": "",
        "topic_fingerprint": "",
        "semantic_truth_boundary": "本回执只证明来源相关性、摘要提取和适用范围已审查，不证明主张语义真值。",
        "sources": [],
    }, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "evidence-plan.json", json.dumps({
        "schema_version": 2,
        "contract": "hybrid-evidence-plan-v1",
        "status": "draft",
        "topic_binding": {
            "contract": "topic-evidence-binding-v1",
            "topic_contract_sha256": "",
            "topic_fingerprint": "",
            "canonical_topic": "",
            "topic_terms": [],
            "bound_at": "",
        },
        "policy": {
            "minimum_trusted_sources": 3,
            "minimum_primary_sources": 2,
            "minimum_source_domains": 2,
            "minimum_evidence_units_per_source": 1,
            "maximum_excerpt_chars": 420,
            "require_attribution": True,
            "require_reuse_approval_for_embedded_assets": True,
            "require_claim_evidence": True,
            "require_source_verification": True,
            "require_provenance": True,
        },
        "sources": [],
        "operator_notes": "每个 evidence 单元必须声明 claim_ids；审计会生成 evidence-provenance.json 与 evidence-lineage.json 供离线回放。",
    }, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "source-evidence.json", json.dumps({
        "schema_version": 2,
        "contract": "hybrid-evidence-v1",
        "status": "pending",
        "source_count": 0,
        "trusted_source_count": 0,
        "sources": [],
        "errors": ["尚未运行 scripts/source_evidence.py audit"],
    }, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "evidence-provenance.json", json.dumps({
        "schema_version": 1,
        "contract": "hybrid-evidence-provenance-v1",
        "status": "pending",
        "identity_authenticated": False,
        "errors": ["尚未运行 scripts/source_evidence.py audit"],
    }, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "evidence-lineage.json", json.dumps({
        "schema_version": 1,
        "contract": "evidence-lineage-v1",
        "verifier_version": "1.0.0",
        "status": "pending",
        "identity_authenticated": False,
        "operator_note": "待 source_evidence.py audit 生成 run/job/material/product 血缘回执。",
    }, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "draft.md", f"# {args.title}\n\n<!-- 初稿：完成审核前不得替换为 article.md -->\n")
    write_if_missing(article_dir / "content-revision.json", json.dumps({
        "schema_version": 1,
        "status": "pending",
        "mode": "",
        "operator": "",
        "created_at": "",
        "change_summary": "",
        "reuse_approved": False,
        "source": {},
        "draft_digest": "",
        "final_digest": "",
        "finalized_at": "",
    }, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "review-report.md", "# 审核报告\n\n- SEO：pending\n- 事实核验：pending\n- 合规：pending\n- 人工修改：\n")
    write_if_missing(article_dir / "review-evidence.json", json.dumps({
        "schema_version": 1,
        "status": "pending",
        "checks": {
            "content": "pending",
            "facts": "pending",
            "sensitivity": "pending",
            "spelling": "pending",
            "humanizer": "pending",
        },
    }, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "review-checks.json", json.dumps({
        "schema_version": 1,
        "status": "pending",
        "reviewer_type": "",
        "reviewer": "",
        "reviewed_at": "",
        "checks": {key: "pending" for key in ("content", "facts", "sensitivity", "spelling", "humanizer")},
        "findings": [],
    }, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "ai-disclosure.yaml", "\n".join([
        "schema_version: 1",
        "status: pending",
        "contains_ai_generated: true",
        "text_generation: 待确认本篇文字生成方式",
        "image_generation: 待确认本篇图片生成方式",
        "disclosure_text: 本文部分内容或配图由人工智能生成，已完成人工审核。",
        "metadata_preserved: false",
        "",
    ]))
    write_if_missing(article_dir / "article.md", "<!-- 审核通过后写入定稿；当前仅为占位文件。 -->\n")
    write_if_missing(article_dir / "article.html", "<!-- 排版通过后写入微信 HTML；当前仅为占位文件。 -->\n")
    write_if_missing(article_dir / "format-report.json", json.dumps({"schema_version": 1, "status": "pending", "validator": "pending"}, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "publish-preflight.json", json.dumps({
        "schema_version": 1,
        "status": "pending",
        "account_slot": publish_slot,
        "appid_key": f"WECHAT_{publish_slot}_APPID",
        "appsecret_key": f"WECHAT_{publish_slot}_APPSECRET",
        "draft_permission": False,
        "ip_whitelist_checked": False,
        "checked_at": "",
    }, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "publish-receipt.json", json.dumps({"status": "pending", "mode": "draft", "account": ACCOUNT_ID}, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "metrics.json", json.dumps({"schema_version": 2, "t1": {}, "t7": {}, "handoff_signals": [], "content_reuse": [], "conversion": {"follows": 0, "keyword_replies": 0, "lead_magnet_claims": 0, "consultation_requests": 0, "qualified_leads": 0}, "attribution": {"primary_cta": cta, "reply_keyword": reply_keyword, "lead_magnet": lead_magnet}}, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "visual-brief.yaml", f"schema_version: 1\naccount: {args.account}\nformatter_theme: {formatter_theme}\nimage_theme: {image_theme}\napproval:\n  cover_selection: pending\n  approved_by: \"\"\n  approved_at: \"\"\n  reason: \"\"\n")
    write_if_missing(article_dir / "image-plan.md", "# 图片计划\n\n请在完成定稿后运行：\n\n```powershell\npython scripts/visual_qa.py plan --article <文章目录>\n```\n\n生成候选图并人工确认后，再运行 `visual_qa.py approve` 和 `visual_qa.py check`。\n")
    write_if_missing(article_dir / "img_analysis.md", "# 图片质量报告\n\n- 状态：待生成视觉简报并检查\n")
    write_if_missing(article_dir / "image-sources.json", json.dumps({"schema_version": 1, "assets": []}, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "asset-index.json", json.dumps({"schema_version": 1, "contract": "asset-index-v1", "status": "pending", "assets": []}, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "checkpoint-manifest.json", json.dumps({"schema_version": 1, "contract": "checkpoint-v1", "checkpoints": []}, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "fact-review.json", json.dumps({"schema_version": 1, "contract": "fact-review-v1", "status": "not_prepared", "semantic_truth_check": "pending_independent_human_review"}, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "final-review.md", "# 终审记录\n\n- status: pending\n- human_review: false\n- reviewer_type: agent\n- reviewer: \n- reviewed_at: \n- mobile_width: 390\n- preview_file: preview_screenshot.png\n- preview_digest: \n- fullpage_digest: \n- scroll_slice_count: 0\n- preview_capture: preview-capture.json\n")
    write_if_missing(article_dir / "preview-capture.json", json.dumps({
        "schema_version": 1,
        "status": "pending",
        "renderer": "",
        "source": "article_预览.html",
        "source_sha256": "",
        "viewport": {"width": 390, "height": 1200},
        "screenshot": "preview_screenshot.png",
        "screenshot_sha256": "",
        "fullpage_screenshot": "preview-fullpage.png",
        "fullpage_screenshot_sha256": "",
        "scroll_slices": [],
        "scroll_slice_count": 0,
        "dom_check": {"status": "pending", "title_present": False, "body_text_chars": 0, "image_count": 0, "placeholder_count": 0},
        "captured_at": "",
    }, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "publish-attempt.json", json.dumps({
        "schema_version": 1,
        "status": "pending",
        "mode": "draft",
        "account_slot": publish_slot,
        "media_id": "",
        "thumb_media_id": "",
        "created_at": "",
        "html_digest": "",
    }, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "vision-review.json", json.dumps({
        "schema_version": 1,
        "contract": "vision-review-v1",
        "status": "pending",
        "reviewer_mode": "",
        "reviews": [],
    }, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "workflow-status.json", json.dumps({
        "schema_version": 1,
        "contract": "workflow-status-v1",
        "current_stage": "none",
        "stages": [],
        "external_effects": {"side_effect_completed": False},
    }, ensure_ascii=False, indent=2) + "\n")
    write_if_missing(article_dir / "capability-profile.json", json.dumps({
        "schema_version": 1,
        "contract": "capability-profile-v1",
        "external_image_api_required": True,
        "approval_signature_required": False,
        "selected_backends": ["agnes", "deterministic-svg", "katex-html-composite"],
        "offline_allowed": False,
        "fallback_policy": "blocked-unless-explicitly-switched",
    }, ensure_ascii=False, indent=2) + "\n")
    if ACCOUNT_ID == "sentinel":
        write_if_missing(article_dir / "handoff-card.md", "# X超玩•未来智能转交卡\n\n- 状态：pending-human-confirmation\n- 触发信号：\n- 读者问题样本：\n- 建议深挖方向：\n")

    try:
        state_article_dir = article_dir.relative_to(artifact_root(create=False)).as_posix()
    except ValueError:
        state_article_dir = str(article_dir)
    target_route_path = article_dir / "routing.yaml"
    target_route_path.write_text(route_path.read_text(encoding="utf-8"), encoding="utf-8")
    state = {
        "schema_version": 4,
        "account": args.account,
        "title": args.title,
        "slug": slug,
        "workspace_id": workspace_id,
        "workspace_sequence": sequence,
        "workspace_relative_path": state_article_dir,
        "workspace_lifecycle": "active",
        "process_files_dir": "work",
        "deliverable_dir": "exports",
        "checkpoint_dir": "snapshots",
        "status": "selected",
        "current_stage": "none",
        "gate_history": [],
        "publish_mode": "draft",
        "content_medium": "wechat_article",
        "routing_status": "confirmed",
        "routing_digest": route_digest(target_route_path),
        "article_dir": state_article_dir,
        "artifacts": ["workspace-manifest.json", "routing.yaml", "topic-card.md", "topic-contract.yaml", "topic-cluster.md", "content-calendar.md", "topic-integrity.json", "content-brief.yaml", "cta-contract.json", "seo-report.json", "research.md", "sources.json", "source-verification.json", "source-review.json", "source-snapshots/", "evidence-plan.json", "source-evidence.json", "evidence-provenance.json", "evidence-lineage.json", "topic-evidence-isolation.json", "evidence/", "draft.md", "content-revision.json", "review-report.md", "review-checks.json", "review-evidence.json", "content-truth-qa.json", "claim-verification.json", "fact-review.json", "ai-disclosure.yaml", "article.md", "article.html", "format-report.json", "visual-brief.yaml", "visual-routing.json", "skill-evaluation.json", "image-plan.md", "visual-director-plan.json", "visual-director-plan.md", "image-generation-plan.json", "img_analysis.md", "image-sources.json", "asset-index.json", "visual-semantic-review.json", "visual-content-qa.json", "visual-depth-review.json", "visual-reader-test.json", "vision-review.json", "workflow-status.json", "checkpoint-manifest.json", "final-review.md", "article_预览.html", "preview-capture.json", "preview_screenshot.png", "preview-fullpage.png", "preview-slices/", "publish-preflight.json", "publish-attempt.json", "publish-receipt.json", "publish-result.json", "metrics.json", "work/", "exports/", "snapshots/"],
    }
    (article_dir / "matrix-state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(str(article_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
