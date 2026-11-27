#!/usr/bin/env python3
"""Offline regression suite for the ContentOps Harness Governance overhaul (T01-T10).

Covers:
- Task Contract parsing, 6-tier priority conflict detection, and progressive Context Pack
- L2 deterministic instruction-adherence verification
- 9-state Skill Governance Audit & host context-budget overflow detection
- Content Value & Information Gain gate (including ungrounded first-person refusal)
- Editorial AI-slop / humanizer diagnostics in copy_quality
- Executable Visual Design System & anti-slop HTML linter
- 6 Graphic Templates & platform-native article pack (including Xiaohongshu graphic refusal)
- Director-grade multi-role video planner (9:16 & 16:9, FI zero-recording gate)
- Layered L1-L4 creative review contract (never self-approving or claiming Owner acceptance)
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.graphic.design_system import account_tokens, lint_html_design  # noqa: E402
from contentops.graphic.templates import render_native_article_pack, render_template_html  # noqa: E402
from contentops.media.video_director import DirectorError, build_director_plan  # noqa: E402
from contentops.skills.governance import audit_skills  # noqa: E402
from contentops.workflow import copy_quality  # noqa: E402
from contentops.workflow.content_value import evaluate_value_brief  # noqa: E402
from contentops.workflow.creative_review import build_layered_review  # noqa: E402
from contentops.workflow.task_harness import (  # noqa: E402
    build_context_pack,
    build_task_contract,
    verify_instruction_adherence,
)


def test_task_contract_fi_video_light_palette():
    c = build_task_contract("使用 ContentOps，给未来智能制作一期讲解 Agent Runtime 的技术原理视频。", root=ROOT)
    assert c["account_slug"] == "x-superplay-future-intelligence"
    assert c["content_format"] == "VIDEO"
    assert c["status"] == "READY_FOR_WORKFLOW"
    assert c["palette"]["scene_bg"] == "#E9EDEF"
    assert c["palette"]["surface"] == "#F9FBFA"
    assert c["palette"]["brand_intro_only_bg"] == "#0F1117"
    assert c["palette"]["dark_body_cards_forbidden"] is True
    assert c["production_ready"] is False and c["publish_authorized"] is False
    pack = build_context_pack(c, root=ROOT)
    assert pack["schema"] == "contentops.context-pack/v1"
    assert len(pack["applicable_skills"]) <= 6
    assert any(s["step"] == "3_director_plan" for s in pack["workflow_steps"])


def test_task_contract_hard_conflicts_blocked():
    c = build_task_contract(
        "给未来智能（FI）账号制作一期 Easel 实测视频：全程录制电脑桌面录屏和鼠标点击，并用 AI 生成一张性能对比柱状图作为实测证据。",
        root=ROOT,
    )
    assert c["status"] == "CONFLICT_BLOCKED"
    codes = {row["code"] for row in c["conflicts"] if row["severity"] == "HARD_BLOCK"}
    assert "ACCOUNT_RECORDING_FORBIDDEN" in codes
    assert "GENERATED_AS_EVIDENCE_FORBIDDEN" in codes


def test_task_contract_xhs_graphic_refused():
    c = build_task_contract("给 1024 账号做一篇小红书图文卡片笔记", root=ROOT)
    assert c["status"] == "CONFLICT_BLOCKED"
    codes = {row["code"] for row in c["conflicts"] if row["severity"] == "HARD_BLOCK"}
    assert "PLATFORM_XHS_VIDEO_ONLY" in codes


def test_task_contract_partial_edit_and_preserve_facts():
    c = build_task_contract(
        "把 projects/e2e-p2-fi-video 的第 3 个镜头（fi03）改成暖白底色，其他镜头保持不变，保留原始事实只改表达。",
        root=ROOT,
        account="fi",
    )
    assert c["constraints"]["preserve_facts"] is True
    assert c["constraints"]["lock_other_shots"] is True
    assert "fi03" in c["constraints"]["edit_scope"]
    ok_res = verify_instruction_adherence(
        c,
        actual_account="x-superplay-future-intelligence",
        used_entry_point="scripts/make_content.py",
        rendered_bg_colors=["#F4F2ED"],
        changed_shots=["fi03"],
        modified_claims=[],
    )
    assert ok_res["passed"] is True
    bad_res = verify_instruction_adherence(
        c,
        actual_account="x-superplay-future-intelligence",
        used_entry_point="scripts/run_v1.py",
        rendered_bg_colors=["#0B0F14"],
        changed_shots=["fi03", "fi05"],
        modified_claims=["easel_frozen"],
    )
    assert bad_res["passed"] is False
    failed_ids = {r["id"] for r in bad_res["checks"] if not r["ok"]}
    assert {"PRODUCTION_ENTRY", "LIGHT_PALETTE_COMPLIANCE", "PARTIAL_EDIT_SCOPE", "PRESERVE_FACTS"}.issubset(failed_ids)


def test_skill_governance_audit():
    with tempfile.TemporaryDirectory() as tmp:
        fake_shared = Path(tmp)
        for i in range(65):
            d = fake_shared / f"skill-{i:02d}"
            d.mkdir()
            (d / "SKILL.md").write_text(f"---\nname: skill-{i:02d}\ndescription: Valid test skill description for item {i}\n---\nBody\n", encoding="utf-8")
        report = audit_skills(ROOT, shared_root=fake_shared)
        assert report["schema"] == "contentops.skill-governance-audit/v1"
        assert report["host_store"]["budget_overflow_risk"] is True
        assert report["execution_authorized"] is False
        assert report["summary"]["declared_capabilities"] >= 4


def test_content_value_blocks_ungrounded_first_person():
    bad = evaluate_value_brief(
        {
            "viewer_problem": "开发者不知道怎么选 Agent 底座",
            "info_delta": "基于官方文档梳理架构差异与版本边界",
            "creator_judgment": "我用了三天实测下来我发现它很稳",
            "applicability_and_limits": "仅覆盖 CLI 路径，不包含 Web 工作台",
            "actionable_takeaway": "上线前先锁 commit 再做哈希校验",
            "evidence_basis": "verified_official_docs",
            "real_findings": [
                {"observation": "runtime/easel-pins.json 锁定 bb3c8ff", "source_ref": "runtime/easel-pins.json"},
                {"observation": "doctor 报 7 项 FAIL", "source_ref": "projects/easel-review/script/master.md"},
            ],
        }
    )
    assert bad["ok"] is False
    assert any(i["code"] == "UNGROUNDED_FIRST_PERSON" for i in bad["issues"])

    good = evaluate_value_brief(
        {
            "viewer_problem": "开源 Agent 框架一升级就破坏现有脚本目录结构",
            "info_delta": "给出 bb3c8ff 锁版、1071 文件哈希校验与 7 项实测失败清单",
            "creator_judgment": "CLI 线可用但 Web 路径 6 项未就绪，不能当成开箱即用 SaaS",
            "applicability_and_limits": "适用于愿意配置本机环境的工程师，不适用于零配置新手",
            "actionable_takeaway": "运行 python scripts/easel_engine.py verify v0.3.0 校验底座",
            "evidence_basis": "first_hand_execution",
            "real_findings": [
                {"observation": "easel doctor 12 项 OK、7 项 FAIL", "source_ref": "projects/easel-review/script/master.md"},
                {"observation": "ping healthz 写死 18789 与 37289 错配", "source_ref": "projects/easel-review/sources/screenshots/11-easel-ping.png"},
            ],
        }
    )
    assert good["ok"] is True


def test_copy_quality_ai_slop_detection():
    slop = copy_quality.diagnose([
        "在人工智能飞速发展的今天，这不仅是一次技术创新，更为行业带来无限可能。",
        "不是简单的工具，而是打造全新的智能生态，从而实现真正的价值闭环。",
        "一方面提升了效率，另一方面让我们拭目以待，未来可期。",
    ], format="video")
    audit = slop["editorial_audit"]
    assert len(audit["ai_slop_hits"]) >= 4
    assert audit["mechanical_symmetry_count"] >= 3


def test_design_system_and_six_templates():
    fi = account_tokens(ROOT, "x-superplay-future-intelligence")
    t1024 = account_tokens(ROOT, "x-superplay-1024")
    assert fi["colors"]["bg"] == "#E9EDEF"
    assert t1024["colors"]["bg"] == "#F4F2ED"

    dark_html = "<style>#film { background: #0B0F14; } .card { backdrop-filter: blur(12px); }</style>"
    lint = lint_html_design(dark_html)
    assert lint["ok"] is False
    codes = {f["code"] for f in lint["findings"]}
    assert "FORBIDDEN_DARK_BODY_BG" in codes and "GLASSMORPHISM" in codes

    for tid, data in (
        ("tech_cover", {"title": "测试封面", "subtitle": "副标题"}),
        ("mechanism_architecture", {"title": "架构图", "nodes": [{"label": "A", "detail": "1"}, {"label": "B", "detail": "2"}, {"label": "C", "detail": "3"}]}),
        ("code_annotated", {"title": "代码", "code_lines": ["x = 1", "y = 2"], "highlight_lines": [1], "callouts": [{"title": "点", "detail": "说明"}]}),
        ("measured_comparison", {"title": "对比", "metrics": [{"label": "OK", "value": "12"}], "rows": [{"item": "CLI", "measured": "PASS", "status": "PASS", "boundary": "ok"}]}),
        ("step_workflow_timeline", {"title": "步骤", "steps": [{"title": "第一步", "detail": "校验", "command": "python scripts/doctor.py"}]}),
    ):
        res = render_template_html(ROOT, template_id=tid, account_slug="x-superplay-future-intelligence", data=data)
        assert res["design_lint"]["ok"] is True, f"{tid} failed lint: {res['design_lint']}"

    native = render_native_article_pack(fi, {
        "title": "Easel 工程拆解",
        "lead": "锁死版本与实测边界。",
        "sections": [{"heading": "核验", "paragraphs": ["逐文件比对哈希。"], "code": "python scripts/doctor.py"}],
        "sources": ["runtime/easel-pins.json"],
        "tags": ["AI工程", "Agent"],
    })
    assert "<section" in native["wechat_article"] and "<span leaf=" in native["wechat_article"]
    assert "```bash" in native["csdn"]
    assert "结论先行" in native["zhihu"]

    try:
        render_native_article_pack(fi, {"title": "t"}, platforms=["xiaohongshu_image"])
        raise AssertionError("expected Xiaohongshu graphic refusal")
    except ValueError:
        pass


def test_video_director_dual_aspect_and_fi_redline():
    scenes = [
        {"scene_id": "s01", "role": "hook_conflict", "duration_s": 3.0, "headline": "开场冲突"},
        {"scene_id": "s02", "role": "mechanism_flow", "duration_s": 4.0, "headline": "机制", "nodes": [{"label": "A", "detail": "1"}, {"label": "B", "detail": "2"}]},
        {"scene_id": "s03", "role": "verdict_cta", "duration_s": 3.0, "headline": "收尾"},
    ]
    p_v = build_director_plan(root=ROOT, account_slug="x-superplay-future-intelligence", title="FI V", aspect="9:16", scenes=scenes)
    p_h = build_director_plan(root=ROOT, account_slug="x-superplay-future-intelligence", title="FI H", aspect="16:9", scenes=scenes)
    assert (p_v["width"], p_v["height"]) == (1080, 1920)
    assert (p_h["width"], p_h["height"]) == (1920, 1080)
    assert p_v["colors"]["bg"] == "#E9EDEF"

    # FI refuses manual recording scenes
    try:
        build_director_plan(
            root=ROOT,
            account_slug="x-superplay-future-intelligence",
            title="Bad FI",
            scenes=[{"role": "real_evidence", "duration_s": 3.0, "is_manual_recording": True}],
        )
        raise AssertionError("FI must refuse manual recording")
    except DirectorError as exc:
        assert exc.code == "RECORDING_FORBIDDEN"


def test_layered_review_never_self_approves():
    rev = build_layered_review(
        artifact_id="fi-9x16-formal.mp4",
        artifact_kind="video",
        l1_technical={"passed": True},
        l2_instruction={"passed": True},
        l3_independent_review={"verdict": "PASS_CANDIDATE", "notes": "Clean light palette and clear mechanism."},
        inspection_scope="sampled_frames_plus_ffprobe",
        reviewer_is_independent=True,
    )
    assert rev["stage_status"] == "PENDING_HUMAN_ACCEPTANCE"
    assert rev["owner_accepted"] is False
    assert rev["production_ready"] is False
    assert any("INSPECTION_SCOPE_LIMITED" in w for w in rev["warnings"])


def test_compound_three_way_conflict_and_no_silent_xhs():
    c = build_task_contract(
        "给未来智能做 Easel 视频：我要一段桌面录屏演示，再让 AI 生成一张性能对比柱状图当实测证据，同时发小红书图文版本",
        root=ROOT,
    )
    assert c["status"] == "CONFLICT_BLOCKED"
    codes = {row["code"] for row in c["conflicts"] if row["severity"] == "HARD_BLOCK"}
    assert codes == {
        "ACCOUNT_RECORDING_FORBIDDEN",
        "GENERATED_AS_EVIDENCE_FORBIDDEN",
        "PLATFORM_XHS_VIDEO_ONLY",
    }
    assert "xiaohongshu_video" not in c["platforms"], "must never silently convert Xiaohongshu graphic into video"
    pack = build_context_pack(c, root=ROOT)
    assert [s["step"] for s in pack["workflow_steps"]] == ["0_resolve_conflicts"]


def test_multi_template_and_style_override_single_attr():
    c = build_task_contract(
        "给未来智能做一篇公众号技术长文章，同时同步知乎和 CSDN 原生版，用仓库里已有的技术封面和架构图模板出图。",
        root=ROOT,
    )
    assert "tech_cover" in c["template_ids"]
    assert "mechanism_architecture" in c["template_ids"]
    assert any(a["id"] == "A9_TEMPLATE_LOCK" for a in c["assertions"])

    from contentops.media.video_director import _scene_markup

    markup = _scene_markup(
        {
            "scene_id": "s02",
            "role": "verdict_cta",
            "kicker": "TEST",
            "headline": "暖色覆写",
            "subtext": "单镜头暖色",
            "style_override": "warm-amber",
        },
        1,
        horizontal=False,
        copied_img=None,
        img_dims=None,
        account_label="1024",
    )
    first_tag = markup.splitlines()[0]
    assert first_tag.count("style=") == 1, f"duplicate style attr breaks browser parsing: {first_tag}"
    assert "--bg:#F7EFE4" in first_tag


TESTS = [
    test_task_contract_fi_video_light_palette,
    test_task_contract_hard_conflicts_blocked,
    test_task_contract_xhs_graphic_refused,
    test_task_contract_partial_edit_and_preserve_facts,
    test_compound_three_way_conflict_and_no_silent_xhs,
    test_multi_template_and_style_override_single_attr,
    test_skill_governance_audit,
    test_content_value_blocks_ungrounded_first_person,
    test_copy_quality_ai_slop_detection,
    test_design_system_and_six_templates,
    test_video_director_dual_aspect_and_fi_redline,
    test_layered_review_never_self_approves,
]


def main() -> int:
    for fn in TESTS:
        fn()
        print(f"[ok] {fn.__name__}")
    print(f"\nAll {len(TESTS)} harness governance tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
