#!/usr/bin/env python3
"""Structured strategy card for X•超玩1024 copy.

This is an editorial contract, not a script generator.  It keeps opportunity
triage, angle selection, thesis/argument structure, hook packaging and the
teaching contract visible before the canonical spoken script is written.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from console_encoding import configure_utf8_stdio
except ImportError:  # imported as scripts.copy_strategy
    from scripts.console_encoding import configure_utf8_stdio

configure_utf8_stdio()

try:
    from runtime_context import ACCOUNT
except ImportError:  # imported as scripts.copy_strategy
    from scripts.runtime_context import ACCOUNT

try:
    from adaptive_copy_router import CANONICAL_ARGUMENT_STRUCTURE, CANONICAL_PACKAGING_STRUCTURE, VIEWER_JOBS, contract_values, pillar_for_content_type, viewer_job_for_content_type
except ImportError:  # imported as scripts.copy_strategy
    from scripts.adaptive_copy_router import CANONICAL_ARGUMENT_STRUCTURE, CANONICAL_PACKAGING_STRUCTURE, VIEWER_JOBS, contract_values, pillar_for_content_type, viewer_job_for_content_type

try:
    from audience_insight import VIEWER_PROGRESS_STRUCTURE, build_scaffold as build_audience_scaffold, lens_projection, validate_lens_projection
except ImportError:  # imported as scripts.copy_strategy
    from scripts.audience_insight import VIEWER_PROGRESS_STRUCTURE, build_scaffold as build_audience_scaffold, lens_projection, validate_lens_projection

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 3
# The complete angle catalog lives in this active module so candidate IDs stay
# deterministic and cannot drift through an untracked external source.
ANGLE_LIBRARY_SOURCE = "scripts/copy_strategy.py#ANGLE_LIBRARY_CATALOG"

ANGLE_FAMILIES: dict[str, list[dict[str, str]]] = {
    "AI 新能力实测": [
        {"id": "ai-traitor", "family": "AI叛徒", "label": "反向验证", "why": "拆穿能力边界，要求可展示的失败或限制证据"},
        {"id": "ai-vs-ai", "family": "AI对抗AI", "label": "对照实验", "why": "固定变量比较模型、配置或流程差异"},
        {"id": "live-verification", "family": "现场验证", "label": "现场验证", "why": "把抽象能力落到一个可复现的输入和结果"},
        {"id": "limit-challenge", "family": "限制挑战", "label": "限制挑战", "why": "先固定资源、时间或权限，再观察能力边界"},
        {"id": "authority-compare", "family": "权威对照", "label": "权威对照", "why": "把官方描述与本地测试结果分开对照"},
    ],
    "AI × 现实任务实验": [
        {"id": "ai-tutor", "family": "AI调教师", "label": "失败复盘", "why": "公开代价、错误和修正，而不是只展示成功"},
        {"id": "job-challenge", "family": "岗位挑战", "label": "职业代入", "why": "判断 AI 能否接管具体职业任务的一步"},
        {"id": "failure-review", "family": "错误纠正", "label": "错误纠正", "why": "把失败原因和修复动作讲清楚"},
        {"id": "role-swap", "family": "角色互换", "label": "角色互换", "why": "让观众看到 AI、人工和用户之间的责任变化"},
        {"id": "process-reveal", "family": "过程揭秘", "label": "过程揭秘", "why": "展示输入、检查点和人工介入位置"},
    ],
    "AI 生意实验室": [
        {"id": "cost-breakdown", "family": "成本拆解", "label": "成本拆解", "why": "把时间、工具、人工和失败成本放到同一张表"},
        {"id": "user-test", "family": "用户测试", "label": "用户测试", "why": "用真实行为而不是口头兴趣判断需求"},
        {"id": "payment-signal", "family": "借钱测试", "label": "付费信号", "why": "寻找预约、付费或持续使用等可验证信号"},
        {"id": "counterfactual", "family": "后果推演", "label": "后果推演", "why": "比较采用和不采用 AI 时的责任、成本和边界"},
        {"id": "audience-cocreation", "family": "观众共创", "label": "观众共创", "why": "把评论区具体任务变成下一轮实验输入"},
    ],
}

# The source registry contains the full user-provided angle inventory.  A
# package selects a small, explainable candidate set from this catalog; it does
# not blindly apply every angle to every topic.
ANGLE_LIBRARY_CATALOG: list[dict[str, str]] = [
    {"id": "survival-anxiety", "family": "痛点/焦虑", "label": "生存焦虑"},
    {"id": "lazy-result", "family": "痛点/焦虑", "label": "懒人结果"},
    {"id": "counterintuitive", "family": "痛点/焦虑", "label": "反常识"},
    {"id": "identity-mismatch", "family": "痛点/焦虑", "label": "身份错位"},
    {"id": "ai-judge", "family": "痛点/焦虑", "label": "AI判官"},
    {"id": "job-challenge", "family": "痛点/焦虑", "label": "岗位挑战"},
    {"id": "misuse-risk", "family": "痛点/焦虑", "label": "误用风险"},
    {"id": "resource-analysis", "family": "痛点/焦虑", "label": "资源分析"},
    {"id": "cyber-fortune", "family": "痛点/焦虑", "label": "赛博算命"},
    {"id": "replacement", "family": "痛点/焦虑", "label": "平替"},
    {"id": "sharp-tongue", "family": "痛点/焦虑", "label": "毒舌"},
    {"id": "reverse-ppu", "family": "痛点/焦虑", "label": "反向PUA"},
    {"id": "cost-breakdown", "family": "痛点/焦虑", "label": "成本拆解"},
    {"id": "public-data", "family": "痛点/焦虑", "label": "公开数据"},
    {"id": "jargon-translation", "family": "痛点/焦虑", "label": "黑话翻译"},
    {"id": "cyber-revival", "family": "情感/自我解构", "label": "赛博还魂"},
    {"id": "digital-double-judgment", "family": "情感/自我解构", "label": "数字分身审判"},
    {"id": "digital-childhood", "family": "情感/自我解构", "label": "数字童年"},
    {"id": "cyber-legacy", "family": "情感/自我解构", "label": "赛博遗产"},
    {"id": "divorce-simulation", "family": "情感/自我解构", "label": "离婚模拟"},
    {"id": "ai-empathy", "family": "情感/自我解构", "label": "AI共情"},
    {"id": "time-capsule", "family": "情感/自我解构", "label": "时间胶囊"},
    {"id": "last-lesson", "family": "情感/自我解构", "label": "最后一课"},
    {"id": "ai-substitute", "family": "情感/自我解构", "label": "AI替身"},
    {"id": "beggar-mode", "family": "社会实验", "label": "乞丐模式"},
    {"id": "borrow-money-test", "family": "社会实验", "label": "借钱测试"},
    {"id": "help-letter-compare", "family": "社会实验", "label": "求助信对比"},
    {"id": "all-day-ai-decision", "family": "社会实验", "label": "全天决策交给AI"},
    {"id": "historical-defense", "family": "历史/经典重审", "label": "历史人物辩护"},
    {"id": "classic-new-evidence", "family": "历史/经典重审", "label": "经典文本新证据"},
    {"id": "time-travel-career", "family": "历史/经典重审", "label": "时空穿越职业化"},
    {"id": "new-career", "family": "未来/创造", "label": "新职业"},
    {"id": "doomsday-survival", "family": "未来/创造", "label": "末日生存"},
    {"id": "forecast-backtest", "family": "未来/创造", "label": "预测与回测"},
    {"id": "redefine", "family": "认知/运营/系列", "label": "重新定义"},
    {"id": "destiny-judgment", "family": "认知/运营/系列", "label": "命盘审判"},
    {"id": "traffic-mechanism", "family": "认知/运营/系列", "label": "流量机制公开"},
    {"id": "double-agent", "family": "认知/运营/系列", "label": "无间道"},
    {"id": "ethics-question", "family": "认知/运营/系列", "label": "伦理问题"},
    {"id": "twin-comparison", "family": "认知/运营/系列", "label": "双胞胎对照"},
    {"id": "new-career-launch", "family": "认知/运营/系列", "label": "新职业发布会"},
    {"id": "fan-letter", "family": "认知/运营/系列", "label": "粉丝来信"},
    {"id": "virtual-country-daily", "family": "认知/运营/系列", "label": "虚拟国家日报"},
    {"id": "classic-review", "family": "认知/运营/系列", "label": "经典重审"},
    {"id": "classic-review-series", "family": "认知/运营/系列", "label": "经典重审系列"},
]
REGISTERED_ANGLE_IDS = {
    item["id"] for item in ANGLE_LIBRARY_CATALOG
}.union(
    item["id"] for values in ANGLE_FAMILIES.values() for item in values
).union({"hot-consequence"})


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def profile() -> dict[str, Any]:
    return load_json(ROOT / "profiles" / "profile.json")


def hotspot_eligible(route: dict[str, Any]) -> bool:
    snapshot = route.get("hotspot_snapshot") if isinstance(route.get("hotspot_snapshot"), dict) else {}
    items = snapshot.get("items")
    return (
        route.get("topic_mode") == "hotspot"
        and snapshot.get("passed") is True
        and snapshot.get("freshness_verified") is True
        and isinstance(items, list)
        and bool(items)
    )


def opportunity_type(route: dict[str, Any]) -> str:
    mode = str(route.get("topic_mode", "")).strip()
    return {"hotspot": "hotspot", "user-document": "user_document", "user-topic": "user_question"}.get(mode, "user_question")


def content_type_for_route(route: dict[str, Any]) -> str:
    return "newsjacking" if hotspot_eligible(route) else ""


def default_pillar(strategy: dict[str, Any]) -> str:
    pillars = strategy.get("pillars") if isinstance(strategy.get("pillars"), list) else []
    return str(pillars[0]) if pillars else "AI 新能力实测"


def angle_candidates(pillar: str, opportunity: str) -> list[dict[str, str]]:
    candidates = [dict(item) for item in ANGLE_FAMILIES.get(pillar, ANGLE_FAMILIES["AI 新能力实测"])]
    if opportunity == "hotspot":
        candidates.insert(0, {
            "id": "hot-consequence",
            "family": "热点后果",
            "label": "热点后果",
            "why": "把热点事实转成一个与 AI 任务直接相关的现实影响问题",
        })
    return candidates[:8]


def build_seed(
    manifest: dict[str, Any],
    route: dict[str, Any] | None = None,
    copy_plan: dict[str, Any] | None = None,
    audience_insight: dict[str, Any] | None = None,
    audience_insight_sha256: str = "",
) -> dict[str, Any]:
    route = route if isinstance(route, dict) else {}
    copy_plan = copy_plan if isinstance(copy_plan, dict) else {}
    canonical = profile()
    strategy = canonical.get("strategy", {}) if isinstance(canonical.get("strategy"), dict) else {}
    opportunity = opportunity_type(route)
    route_hotspot = hotspot_eligible(route)
    topic = str(route.get("topic", manifest.get("title", ""))).strip()
    content_type = content_type_for_route(route) if route.get("topic_mode") == "hotspot" else str(copy_plan.get("content_type") or manifest.get("content_type", "")).strip()
    if route.get("topic_mode") == "hotspot" and not route_hotspot:
        content_type = ""
    pillar = str(copy_plan.get("pillar", "")).strip() or pillar_for_content_type(content_type) or default_pillar(strategy)
    # An unclassified user-topic scaffold must remain visibly incomplete.  Do
    # not silently inject the default viewer job until the editor/router has
    # selected a content type; ready tool_test packages still receive the
    # content-type default through this same path.
    viewer_job = str(copy_plan.get("viewer_job", "")).strip() or (
        viewer_job_for_content_type(content_type) if content_type else ""
    )
    insight = audience_insight if isinstance(audience_insight, dict) else build_audience_scaffold(
        str(manifest.get("content_id", "")),
        topic,
        account=str(manifest.get("account", ACCOUNT)),
        content_type=content_type,
        pillar=pillar,
    )
    insight_path = str((manifest.get("paths") or {}).get("audience_insight", "01_research/audience-insight.json")) if isinstance(manifest.get("paths"), dict) else "01_research/audience-insight.json"
    audience_lens = lens_projection(insight, source_path=insight_path, source_sha256=audience_insight_sha256)
    audience = str(audience_lens.get("primary_segment_label", "")).strip()
    viewer_intent = str(audience_lens.get("functional_job", "")).strip()
    value_contract = dict(insight.get("value_contract", {})) if isinstance(insight.get("value_contract"), dict) else {}
    emotional_arc = dict(insight.get("emotional_arc", {})) if isinstance(insight.get("emotional_arc"), dict) else {}
    classification = {
        "content_type": content_type,
        "topic": str(copy_plan.get("topic", topic)).strip(),
        "evidence_level": str(copy_plan.get("evidence_level", "")).strip(),
        "pillar": pillar,
        "viewer_job": viewer_job,
        "pillar_selection": copy_plan.get("pillar_selection", {}),
        "audience": audience,
        "viewer_intent": viewer_intent,
        "structure": str(copy_plan.get("structure", "")).strip(),
        "cta": str(copy_plan.get("cta", "")).strip(),
        "cta_mode": str(copy_plan.get("cta_mode", "")).strip(),
        "duration_tier": str(copy_plan.get("duration_tier", "")).strip(),
        "target_seconds": copy_plan.get("target_seconds"),
        "duration_range": copy_plan.get("duration_range", []),
        "duration_selection_reason": str(copy_plan.get("duration_selection_reason", "")).strip(),
        "source": str(copy_plan.get("classification_source", "route-hotspot" if route.get("topic_mode") == "hotspot" else "pending-editor")),
        "reason": str(copy_plan.get("classification_reason", "")).strip(),
        "hot_topic": bool(copy_plan.get("hot_topic", route_hotspot)),
        "hot_topic_verified": copy_plan.get("hot_topic_verified", route_hotspot),
    }
    hotspot_snapshot = route.get("hotspot_snapshot") if isinstance(route.get("hotspot_snapshot"), dict) else {}
    hotspot_items = hotspot_snapshot.get("items") if isinstance(hotspot_snapshot.get("items"), list) else []
    hotspot_contract = {
        "why_now": str(copy_plan.get("why_now", "")).strip(),
        "ai_relevance": str(copy_plan.get("ai_relevance", "")).strip(),
        "viewer_problem": str(copy_plan.get("viewer_problem", "")).strip(),
        "evidence_floor": str(copy_plan.get("evidence_floor", "")).strip(),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "pending",
        "content_id": str(manifest.get("content_id", "")),
        "account": str(manifest.get("account", ACCOUNT)),
        "title": str(manifest.get("title", "")),
        "topic": topic,
        "structure_contract": {
            "argument_structure": CANONICAL_ARGUMENT_STRUCTURE,
            "packaging_structure": CANONICAL_PACKAGING_STRUCTURE,
            "viewer_progress_structure": VIEWER_PROGRESS_STRUCTURE,
            "beat_preset": str(classification.get("structure", "")).strip(),
        },
        "positioning": {
            "account_role": str(strategy.get("account_role", "Explore")),
            "north_star": str(strategy.get("north_star", "")),
            "pillar": pillar,
            "viewer_job": viewer_job,
            "audience": audience,
            "audience_segment_id": str(audience_lens.get("primary_segment_id", "")),
            "audience_lens": audience_lens,
            "boundary": "没有可回溯证据时只允许明确标记为假设，不得写成实测",
        },
        "classification": classification,
        "opportunity": {
            "type": opportunity,
            "content_type": content_type,
            # The canonical route owns a package-local hotspot receipt.  Keep
                # the external report path only as provenance when no
            # package artifact has been materialized yet.
            "source_snapshot": str(route.get("hotspot_snapshot_artifact") or route.get("hotspot_report", "")),
            "route_id": str(route.get("route_id", "")),
            "why_now": hotspot_contract["why_now"],
            "ai_relevance": hotspot_contract["ai_relevance"],
            "viewer_problem": hotspot_contract["viewer_problem"],
            "evidence_floor": hotspot_contract["evidence_floor"],
            "stop_rule": "放弃热点或选题，不把未经验证的观察写成事实",
            "freshness_verified": route_hotspot,
            "hotspot_gate": {
                "passed": hotspot_snapshot.get("passed") is True,
                "freshness_verified": hotspot_snapshot.get("freshness_verified") is True,
                # Upstream collectors use either verified_at or retrieved_at;
                # preserve the timestamp instead of silently losing the
                # verification receipt at the strategy boundary.
                "verified_at": str(hotspot_snapshot.get("verified_at") or hotspot_snapshot.get("retrieved_at") or "").strip(),
                "item_count": len(hotspot_items),
                "source_urls": [
                    str(item.get("source_url", "")).strip()
                    for item in hotspot_items
                    if isinstance(item, dict) and str(item.get("source_url", "")).strip()
                ],
                "status": "blocked" if route.get("topic_mode") == "hotspot" and not route_hotspot else "ready",
            },
        },
        "angle_board": {
            "library_source": ANGLE_LIBRARY_SOURCE,
            "library_catalog": ANGLE_LIBRARY_CATALOG,
            "candidate_angles": angle_candidates(pillar, opportunity),
            "selected_angle_id": "",
            "secondary_angle_id": "",
            "selection_rationale": "",
            "rejected_angles": [],
        },
        "thesis_card": {
            "question": "",
            "hypothesis": "",
            "method": "",
            "conditions": "",
            "concrete_example": "",
            "evidence_needed": [],
            "expected_result": "",
            "counterview": "",
            "limitation": "",
            "verdict": "",
            "next_action": "",
        },
        "hook_packaging": {
            "variants": [],
            "selected_variant_id": "",
            "selection_rationale": "",
        },
        "audience_lens": audience_lens,
        "value_contract": value_contract,
        "emotional_arc": emotional_arc,
        "viewer_progress_card": {
            "recognition": "",
            "tension": "",
            "promise": "",
            "discovery": "",
            "proof": "",
            "meaning": "",
            "action": "",
        },
        "teaching_contract": {
            "learning_objective": "",
            "practical_value": "",
            "value_contract": value_contract,
            "theory_streak_max_seconds": 8,
            "evidence_interval_seconds": 20,
            "calibration": "ab-test+comprehension-test",
        },
        "method_usage": {
            "audience_research": False,
            "newsjacking_eligible": content_type == "newsjacking",
            "newsjacking": False,
            "angle_library": False,
            "thesis_structure": False,
            "hook_packaging": False,
            "evidence_map": False,
        },
        "method_receipt": {
            "audience_research": {"status": "pending", "evidence": ""},
            "angle_library": {"status": "pending", "evidence": "", "selected_angle_id": ""},
            "thesis_structure": {"status": "pending", "evidence": ""},
            "hook_packaging": {"status": "pending", "evidence": "", "selected_hook_id": ""},
            "evidence_map": {"status": "pending", "evidence": ""},
            "newsjacking": {"status": "not_applicable" if content_type != "newsjacking" else "pending", "evidence": ""},
        },
        "hotspot_contract": hotspot_contract,
        "notes": [
            "这是策略卡，不是最终口播；先完成受众研究，再完成定位、价值、角度、thesis 和 hook 选择。",
            "内容支柱与受众分群是正交轴；候选受众不能按支柱自动升级为已选受众。",
            "热点路线必须同时满足 passed、freshness_verified 和非空 items，才允许 content_type=newsjacking。",
        ],
    }


def validate_strategy(
    payload: dict[str, Any],
    *,
    require_ready: bool = True,
    claim_ids: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    for field in ("content_id", "account", "positioning", "classification", "opportunity", "angle_board", "thesis_card", "hook_packaging", "teaching_contract"):
        if not payload.get(field):
            errors.append(f"missing copy strategy field: {field}")
    if payload.get("account") != ACCOUNT:
        errors.append(f"copy strategy account must be {ACCOUNT}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"copy strategy schema_version must be {SCHEMA_VERSION}")
    structure_contract = payload.get("structure_contract") if isinstance(payload.get("structure_contract"), dict) else {}
    if structure_contract.get("argument_structure") != CANONICAL_ARGUMENT_STRUCTURE:
        errors.append("structure_contract.argument_structure must use the canonical thesis spine")
    if structure_contract.get("packaging_structure") != CANONICAL_PACKAGING_STRUCTURE:
        errors.append("structure_contract.packaging_structure must be hook-body-close")
    if structure_contract.get("viewer_progress_structure") != VIEWER_PROGRESS_STRUCTURE:
        errors.append("structure_contract.viewer_progress_structure must use the Audience Lens v3 progression spine")
    if require_ready and not str(structure_contract.get("beat_preset", "")).strip():
        errors.append("structure_contract.beat_preset is required as a content-type adaptation label")
    errors.extend(validate_lens_projection(payload, required=True))
    positioning = payload.get("positioning") if isinstance(payload.get("positioning"), dict) else {}
    profile_values = contract_values()
    positioning_required = ("pillar", "viewer_job", "audience", "boundary", "audience_segment_id")
    for field in positioning_required:
        if not str(positioning.get(field, "")).strip():
            errors.append(f"positioning.{field} is required")
    top_lens = payload.get("audience_lens")
    positioned_lens = positioning.get("audience_lens")
    if top_lens != positioned_lens:
        errors.append("positioning.audience_lens must match top-level audience_lens")
    if isinstance(top_lens, dict):
        if positioning.get("audience_segment_id") != top_lens.get("primary_segment_id"):
            errors.append("positioning.audience_segment_id must match audience_lens.primary_segment_id")
        if positioning.get("audience") != top_lens.get("primary_segment_label"):
            errors.append("positioning.audience must match audience_lens.primary_segment_label")
    if str(positioning.get("pillar", "")).strip() and positioning.get("pillar") not in profile_values["pillars"]:
        errors.append("positioning.pillar is not declared by the account profile")
    if str(positioning.get("viewer_job", "")).strip() and positioning.get("viewer_job") not in profile_values["viewer_jobs"]:
        errors.append("positioning.viewer_job is not declared by the account profile")
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if require_ready:
        for field in ("content_type", "pillar", "viewer_job", "structure", "cta", "cta_mode", "source"):
            if not str(classification.get(field, "")).strip():
                errors.append(f"classification.{field} is required")
        if classification.get("content_type") not in {
            "newsjacking", "comparison", "tool_test", "technical_explainer", "career_experiment", "business_experiment",
            "github_project", "monetization_case", "tutorial", "failure_review", "opinion",
        }:
            errors.append("classification.content_type is not a supported taxonomy type")
        if str(classification.get("pillar", "")).strip() and classification.get("pillar") not in profile_values["pillars"]:
            errors.append("classification.pillar is not declared by the account profile")
        if str(classification.get("viewer_job", "")).strip() and classification.get("viewer_job") not in profile_values["viewer_jobs"]:
            errors.append("classification.viewer_job is not declared by the account profile")
        # The adaptive router owns the default content-type -> account-fit
        # mapping.  An editor may override it, but the override must be
        # explicit in the selection receipt; otherwise a manually edited
        # strategy can silently turn a career/business topic into the default
        # capability-test pillar and viewer job.
        content_type = str(classification.get("content_type", "")).strip()
        expected_pillar = pillar_for_content_type(content_type)
        expected_viewer_job = viewer_job_for_content_type(content_type)
        selection = classification.get("pillar_selection") if isinstance(classification.get("pillar_selection"), dict) else {}
        selection_source = str(selection.get("source", "")).strip()
        actual_pillar = str(classification.get("pillar", "")).strip()
        actual_viewer_job = str(classification.get("viewer_job", "")).strip()
        allowed_selection_sources = {"content_type_default", "hotspot_topic_hint", "editor_override"}
        if selection_source and selection_source not in allowed_selection_sources:
            errors.append("classification.pillar_selection.source is not a registered selection source")
        if selection_source == "hotspot_topic_hint" and content_type != "newsjacking":
            errors.append("classification.pillar_selection.source=hotspot_topic_hint requires newsjacking")
        if actual_pillar != expected_pillar and selection_source in {"", "content_type_default"}:
            errors.append("classification.pillar conflicts with content_type without an editor override receipt")
        if actual_viewer_job != expected_viewer_job and selection_source in {"", "content_type_default"}:
            errors.append("classification.viewer_job conflicts with content_type without an editor override receipt")
        if selection_source and selection_source != "content_type_default" and not str(selection.get("reason", "")).strip():
            errors.append("classification.pillar_selection.reason is required for non-default selection")
        if classification.get("hot_topic") is True and classification.get("hot_topic_verified") is not True:
            errors.append("classification.hot_topic requires hot_topic_verified=true")
        if classification.get("hot_topic_verified") is True and classification.get("hot_topic") is not True:
            errors.append("classification.hot_topic_verified requires hot_topic=true")
        if classification.get("hot_topic") is True and classification.get("content_type") != "newsjacking":
            errors.append("classification.hot_topic requires content_type=newsjacking")
        if str(classification.get("pillar", "")).strip() and str(classification.get("pillar", "")).strip() != str(positioning.get("pillar", "")).strip():
            errors.append("classification.pillar must match positioning.pillar")
        if str(classification.get("viewer_job", "")).strip() and str(classification.get("viewer_job", "")).strip() != str(positioning.get("viewer_job", "")).strip():
            errors.append("classification.viewer_job must match positioning.viewer_job")
    opportunity = payload.get("opportunity") if isinstance(payload.get("opportunity"), dict) else {}
    if require_ready and opportunity.get("type") not in {"hotspot", "user_question", "user_document"}:
        errors.append("opportunity.type is not a supported route type")
    opportunity_content_type = str(opportunity.get("content_type", "")).strip()
    classification_content_type = str(classification.get("content_type", "")).strip()
    if require_ready and opportunity_content_type and classification_content_type and opportunity_content_type != classification_content_type:
        errors.append("opportunity.content_type must match classification.content_type")
    if opportunity.get("type") == "hotspot":
        if opportunity.get("content_type") != "newsjacking":
            errors.append("hotspot opportunity must declare content_type=newsjacking")
        if opportunity.get("freshness_verified") is not True:
            errors.append("hotspot opportunity requires freshness_verified=true")
        gate = opportunity.get("hotspot_gate") if isinstance(opportunity.get("hotspot_gate"), dict) else {}
        if gate.get("passed") is not True or gate.get("freshness_verified") is not True:
            errors.append("hotspot opportunity must carry a passed hotspot_gate receipt")
        item_count = gate.get("item_count")
        if isinstance(item_count, bool) or not isinstance(item_count, int) or item_count < 1:
            errors.append("hotspot_gate.item_count must be a positive integer")
        if not str(gate.get("verified_at", "")).strip():
            errors.append("hotspot_gate.verified_at is required")
        if not isinstance(gate.get("source_urls"), list) or not any(str(item).strip() for item in gate.get("source_urls", [])):
            errors.append("hotspot_gate.source_urls must contain at least one source URL")
    if require_ready and classification.get("content_type") == "newsjacking":
        if opportunity.get("type") != "hotspot" or opportunity.get("freshness_verified") is not True:
            errors.append("newsjacking classification requires a fresh hotspot opportunity")
        for field in ("why_now", "ai_relevance", "viewer_problem", "evidence_floor"):
            if not str(opportunity.get(field, "")).strip():
                contract = payload.get("hotspot_contract") if isinstance(payload.get("hotspot_contract"), dict) else {}
                if not str(contract.get(field, "")).strip():
                    errors.append(f"newsjacking opportunity requires {field}")
    board = payload.get("angle_board") if isinstance(payload.get("angle_board"), dict) else {}
    candidates = board.get("candidate_angles")
    if not isinstance(candidates, list) or not 3 <= len(candidates) <= 8:
        errors.append("angle_board must contain 3-8 candidates")
    elif any(not isinstance(item, dict) or not all(str(item.get(field, "")).strip() for field in ("id", "family", "why")) for item in candidates):
        errors.append("angle_board candidates must include id, family and why")
    selected = str(board.get("selected_angle_id", "")).strip()
    candidate_ids = {str(item.get("id", "")) for item in candidates if isinstance(item, dict)} if isinstance(candidates, list) else set()
    if not selected or selected not in candidate_ids:
        errors.append("angle_board.selected_angle_id must select one candidate")
    if require_ready and isinstance(candidates, list) and any(str(item.get("id", "")).strip() not in REGISTERED_ANGLE_IDS for item in candidates if isinstance(item, dict)):
        errors.append("angle_board candidates must come from the registered angle catalog")
    if not str(board.get("selection_rationale", "")).strip():
        errors.append("angle_board.selection_rationale is required")
    thesis = payload.get("thesis_card") if isinstance(payload.get("thesis_card"), dict) else {}
    thesis_required = ("question", "hypothesis", "method", "conditions", "concrete_example", "limitation", "verdict", "next_action")
    for field in thesis_required:
        if not str(thesis.get(field, "")).strip():
            errors.append(f"thesis_card.{field} is required")
    evidence_needed = thesis.get("evidence_needed")
    if not isinstance(evidence_needed, list) or not evidence_needed:
        errors.append("thesis_card.evidence_needed must contain at least one item")
    elif claim_ids is not None:
        missing_claims = sorted({str(item).strip() for item in evidence_needed if str(item).strip()} - claim_ids)
        if missing_claims:
            errors.append("thesis_card.evidence_needed references unknown claim IDs: " + ", ".join(missing_claims))
    hooks = payload.get("hook_packaging") if isinstance(payload.get("hook_packaging"), dict) else {}
    variants = hooks.get("variants")
    if not isinstance(variants, list) or not 3 <= len(variants) <= 8:
        errors.append("hook_packaging.variants must contain 3-8 variants")
    elif any(not isinstance(item, dict) or not all(str(item.get(field, "")).strip() for field in ("id", "hook_text", "proof_point", "risk_notes", "score", "rationale")) for item in variants):
        errors.append("hook_packaging variants must include id, hook_text, proof_point, risk_notes, score and rationale")
    hook_ids = {str(item.get("id", "")) for item in variants if isinstance(item, dict)} if isinstance(variants, list) else set()
    if str(hooks.get("selected_variant_id", "")).strip() not in hook_ids:
        errors.append("hook_packaging.selected_variant_id must select one variant")
    if not str(hooks.get("selection_rationale", "")).strip():
        errors.append("hook_packaging.selection_rationale is required")
    progress_card = payload.get("viewer_progress_card") if isinstance(payload.get("viewer_progress_card"), dict) else {}
    for field in ("recognition", "tension", "promise", "discovery", "proof", "meaning", "action"):
        if not str(progress_card.get(field, "")).strip():
            errors.append(f"viewer_progress_card.{field} is required")
    value = payload.get("value_contract") if isinstance(payload.get("value_contract"), dict) else {}
    for field in ("primary_dimension", "primary_promise", "meaning_for_viewer"):
        if not str(value.get(field, "")).strip():
            errors.append(f"value_contract.{field} is required")
    arc = payload.get("emotional_arc") if isinstance(payload.get("emotional_arc"), dict) else {}
    for field in ("start_state", "recognition_cue", "turning_evidence", "end_state"):
        if not str(arc.get(field, "")).strip():
            errors.append(f"emotional_arc.{field} is required")
    usage = payload.get("method_usage") if isinstance(payload.get("method_usage"), dict) else {}
    if require_ready:
        required_methods = ["audience_research", "angle_library", "thesis_structure", "hook_packaging", "evidence_map"]
        for field in required_methods:
            if usage.get(field) is not True:
                errors.append(f"method_usage.{field} must be true before strategy approval")
        expected_news = classification.get("content_type") == "newsjacking"
        if usage.get("newsjacking_eligible") is not expected_news:
            errors.append("method_usage.newsjacking_eligible must match classification.content_type")
        if usage.get("newsjacking") is not expected_news:
            errors.append("method_usage.newsjacking must match classification.content_type")
        receipt = payload.get("method_receipt") if isinstance(payload.get("method_receipt"), dict) else {}
        angle_receipt = receipt.get("angle_library") if isinstance(receipt.get("angle_library"), dict) else {}
        hook_receipt = receipt.get("hook_packaging") if isinstance(receipt.get("hook_packaging"), dict) else {}
        if str(angle_receipt.get("selected_angle_id", "")).strip() != selected:
            errors.append("method_receipt.angle_library.selected_angle_id must match angle_board.selected_angle_id")
        if str(hook_receipt.get("selected_hook_id", "")).strip() != str(hooks.get("selected_variant_id", "")).strip():
            errors.append("method_receipt.hook_packaging.selected_hook_id must match hook_packaging.selected_variant_id")
        receipt_fields = ["audience_research", "angle_library", "thesis_structure", "hook_packaging", "evidence_map", "newsjacking"]
        for field in receipt_fields:
            item = receipt.get(field) if isinstance(receipt.get(field), dict) else {}
            status = str(item.get("status", "")).strip()
            if field == "newsjacking" and not expected_news:
                if status != "not_applicable":
                    errors.append("method_receipt.newsjacking must be not_applicable for non-news content")
            elif status != "applied":
                errors.append(f"method_receipt.{field}.status must be applied")
            if field != "newsjacking" and not str(item.get("evidence", "")).strip():
                errors.append(f"method_receipt.{field}.evidence is required")
    teaching = payload.get("teaching_contract") if isinstance(payload.get("teaching_contract"), dict) else {}
    teaching_required = ("learning_objective", "practical_value", "theory_streak_max_seconds", "evidence_interval_seconds", "calibration")
    for field in teaching_required:
        if teaching.get(field) in (None, "", []):
            errors.append(f"teaching_contract.{field} is required")
    if require_ready and payload.get("status") != "ready":
        errors.append("copy strategy status must be ready")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the X•超玩1024 structured copy strategy card.")
    parser.add_argument("command", choices=("seed", "check"))
    parser.add_argument("--input")
    parser.add_argument("--manifest")
    parser.add_argument("--route")
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-pending", action="store_true")
    args = parser.parse_args()
    if args.command == "seed":
        if not args.manifest:
            parser.error("seed requires --manifest")
        manifest = load_json(Path(args.manifest))
        route = load_json(Path(args.route)) if args.route else {}
        result = build_seed(manifest, route)
    else:
        if not args.input:
            parser.error("check requires --input")
        result = load_json(Path(args.input))
    errors = validate_strategy(result, require_ready=not args.allow_pending)
    result["errors"] = errors
    result["passed"] = not errors
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(Path(args.output).resolve()), "passed": result["passed"], "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
