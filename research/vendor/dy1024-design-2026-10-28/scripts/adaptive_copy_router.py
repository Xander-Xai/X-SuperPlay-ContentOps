#!/usr/bin/env python3
"""Adaptive copy router and fail-closed copy contract validator."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

try:
    from console_encoding import configure_utf8_stdio
except ImportError:  # imported as scripts.adaptive_copy_router
    from scripts.console_encoding import configure_utf8_stdio

configure_utf8_stdio()

try:
    from runtime_context import ACCOUNT
except ImportError:  # imported as scripts.adaptive_copy_router
    from scripts.runtime_context import ACCOUNT

try:
    from duration_policy import adjust_for_complexity, policy_from_profile, resolve_tier
except ImportError:  # imported as scripts.adaptive_copy_router in tests
    from scripts.duration_policy import adjust_for_complexity, policy_from_profile, resolve_tier

try:
    from audience_insight import VIEWER_PROGRESS_STRUCTURE, build_scaffold as build_audience_scaffold, lens_projection, validate_lens_projection
except ImportError:  # imported as scripts.adaptive_copy_router in tests
    from scripts.audience_insight import VIEWER_PROGRESS_STRUCTURE, build_scaffold as build_audience_scaffold, lens_projection, validate_lens_projection

ROOT = Path(__file__).resolve().parents[1]
COPY_DIRECTION_ROUTES = ROOT / "configs" / "copy-direction-routes.json"
CANONICAL_ARGUMENT_STRUCTURE = "question-hypothesis-method-evidence-result-limitation-verdict-action"
CANONICAL_PACKAGING_STRUCTURE = "hook-body-close"

PILLARS = (
    "AI 新能力实测",
    "AI × 现实任务实验",
    "AI 生意实验室",
)
VIEWER_JOBS = {
    "判断": "判断一个 AI 能力、项目或方案是否值得投入时间",
    "复现": "按明确条件复现实验并知道关键参数",
    "迁移": "判断 AI 能否接管具体职业任务的一步",
    "参与": "提供真实场景、问题或下一轮实验输入",
    "验证生意": "验证真实用户是否愿意使用、预约或付费",
}
HOOK_TYPES = {"反常识", "结果先看", "职业代入", "失败预警", "参与式实验"}
CTA_MODES = {"problem_signal", "handoff", "reproduction", "source", "judgment"}

# A verified hotspot can still belong to a different account pillar.  These
# hints are deliberately conservative: only strong task/business language
# changes the default; an editor can always make an explicit pillar choice.
HOTSPOT_PILLAR_HINTS = (
    (("职业", "岗位", "从业者", "招聘", "裁员", "工作流", "人工介入", "员工"), "AI × 现实任务实验", "热点明确指向职业任务或人工边界"),
    (("用户", "付费", "订单", "客户", "商业", "生意", "创业", "mvp", "saas", "预约"), "AI 生意实验室", "热点明确指向用户行为、商业验证或付费信号"),
)


def load_profile() -> dict[str, Any]:
    return load_json(ROOT / "profiles" / "profile.json")


def load_copy_direction_routes() -> dict[str, Any]:
    """Load the pillar-to-module registry from the canonical checkout."""
    payload = load_json(COPY_DIRECTION_ROUTES)
    routes = payload.get("routes")
    if not isinstance(routes, dict) or len(routes) != 3:
        raise ValueError("copy direction route registry must declare exactly three pillar routes")
    return payload


def copy_direction_for_pillar(pillar: str) -> dict[str, Any]:
    """Resolve one and only one internal copy module for an account pillar."""
    payload = load_copy_direction_routes()
    route = payload.get("routes", {}).get(str(pillar).strip())
    if not isinstance(route, dict) or not str(route.get("route_id", "")).strip() or not str(route.get("module", "")).strip():
        raise ValueError(f"no copy direction route is registered for pillar: {pillar}")
    module = ROOT / str(route["module"])
    if not module.is_file():
        raise ValueError(f"copy direction module is missing: {route['module']}")
    return {
        "pillar": str(pillar).strip(),
        "route_id": str(route["route_id"]).strip(),
        "module": str(route["module"]).strip(),
        "module_status": str(route.get("module_status", "")).strip(),
        "method": str(route.get("method", "")).strip(),
        "required_beats": list(route.get("required_beats", [])) if isinstance(route.get("required_beats"), list) else [],
        "evidence_floor": list(route.get("evidence_floor", [])) if isinstance(route.get("evidence_floor"), list) else [],
        "research_basis": list(route.get("research_basis", [])) if isinstance(route.get("research_basis"), list) else [],
    }


def copy_direction_for_content(content_type: str, pillar: str) -> dict[str, Any]:
    """Resolve a pillar route plus an explicit content-type specialization.

    The pillar remains the account ownership boundary.  A specialization may
    change the beats/evidence floor when the content type would otherwise be
    forced through a mismatched route (for example, a mechanism explanation
    through a local-benchmark route).
    """
    base = copy_direction_for_pillar(pillar)
    payload = load_copy_direction_routes()
    route = payload.get("routes", {}).get(str(pillar).strip(), {})
    overrides = route.get("content_type_overrides", {}) if isinstance(route, dict) else {}
    override = overrides.get(str(content_type).strip()) if isinstance(overrides, dict) else None
    if not isinstance(override, dict):
        return base
    merged = {**base}
    for field in ("route_id", "module", "module_status", "method"):
        if str(override.get(field, "")).strip():
            merged[field] = str(override[field]).strip()
    for field in ("required_beats", "evidence_floor", "research_basis"):
        if isinstance(override.get(field), list):
            merged[field] = list(override[field])
    return merged


def validate_direction_routing(payload: dict[str, Any]) -> list[str]:
    """Validate explicit route metadata when a copy brief carries it.

    Older standalone fixtures may omit the new metadata. New package briefs
    always include it, so their route cannot silently drift from the pillar.
    """
    route_id = str(payload.get("copy_direction_route", "")).strip()
    module = str(payload.get("copy_direction_module", "")).strip()
    if not route_id and not module:
        direction = payload.get("copy_direction")
        if isinstance(direction, dict):
            route_id = str(direction.get("route_id", "")).strip()
            module = str(direction.get("module", "")).strip()
    if not route_id and not module:
        return []
    errors: list[str] = []
    try:
        expected = copy_direction_for_content(str(payload.get("content_type", "")), str(payload.get("pillar", "")))
    except ValueError as error:
        return [str(error)]
    if route_id != expected["route_id"]:
        errors.append("copy direction route does not match pillar")
    if module != expected["module"]:
        errors.append("copy direction module does not match pillar route")
    return errors


def contract_values(profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read the active copy contract from the canonical profile."""
    profile = profile or load_profile()
    strategy = profile.get("strategy", {}) if isinstance(profile.get("strategy"), dict) else {}
    copy_contract = strategy.get("copy_contract", {}) if isinstance(strategy.get("copy_contract"), dict) else {}
    pillars = tuple(str(item).strip() for item in strategy.get("pillars", []) if str(item).strip())
    viewer_jobs = tuple(str(item).strip() for item in copy_contract.get("viewer_jobs", []) if str(item).strip())
    hook_types = tuple(str(item).strip() for item in copy_contract.get("hook_types", []) if str(item).strip())
    return {
        "pillars": pillars,
        "viewer_jobs": viewer_jobs,
        "hook_types": hook_types,
        "copy_contract": copy_contract,
    }


def validate_contract_metadata(payload: dict[str, Any], *, require_ready_disclosure: bool = True) -> list[str]:
    """Validate the fields that must travel through every active copy route."""
    values = contract_values()
    errors: list[str] = []
    for field in ("pillar", "viewer_job", "hook_type", "narrative_tension", "voice_contract", "cta_mode", "ai_disclosure"):
        if not payload.get(field):
            errors.append(f"missing copy contract field: {field}")
    if payload.get("pillar") not in values["pillars"]:
        errors.append("pillar is not declared by the account profile")
    if payload.get("viewer_job") not in values["viewer_jobs"]:
        errors.append("viewer_job is not declared by the account profile")
    if payload.get("hook_type") not in values["hook_types"]:
        errors.append("hook_type is not declared by the account profile")
    if payload.get("cta_mode") not in CTA_MODES:
        errors.append("cta_mode is invalid")
    voice = payload.get("voice_contract") if isinstance(payload.get("voice_contract"), dict) else {}
    if voice.get("boundary_sentence_required") is not True:
        errors.append("voice_contract must require a boundary sentence")
    disclosure = payload.get("ai_disclosure") if isinstance(payload.get("ai_disclosure"), dict) else {}
    if disclosure.get("required") is not True:
        errors.append("ai_disclosure.required must be true for the fixed digital-human voice-clone route")
    if require_ready_disclosure and disclosure.get("status") != "ready":
        errors.append("ai_disclosure.status must be ready before copy approval")
    if not str(disclosure.get("location", "")).strip():
        errors.append("ai_disclosure.location is required")
    if payload.get("schema_version") != 3:
        errors.append("copy contract schema_version must be 3")
    if voice.get("audience_empathy_required") is not True:
        errors.append("voice_contract must require audience empathy")
    for field in ("empathy_rule", "emotional_turn_rule"):
        if not str(voice.get(field, "")).strip():
            errors.append(f"voice_contract.{field} is required")
    errors.extend(validate_lens_projection(payload, required=True))
    lens = payload.get("audience_lens") if isinstance(payload.get("audience_lens"), dict) else {}
    if str(payload.get("audience", "")).strip() != str(lens.get("primary_segment_label", "")).strip():
        errors.append("audience must match audience_lens.primary_segment_label")
    if str(payload.get("viewer_intent", "")).strip() != str(lens.get("functional_job", "")).strip():
        errors.append("viewer_intent must match audience_lens.functional_job")
    if payload.get("viewer_progress_structure") != VIEWER_PROGRESS_STRUCTURE:
        errors.append("viewer_progress_structure must use the Audience Lens v3 progression spine")
    value = payload.get("value_contract") if isinstance(payload.get("value_contract"), dict) else {}
    for field in ("primary_dimension", "primary_promise", "meaning_for_viewer"):
        if not str(value.get(field, "")).strip():
            errors.append(f"value_contract.{field} is required")
    arc = payload.get("emotional_arc") if isinstance(payload.get("emotional_arc"), dict) else {}
    for field in ("start_state", "recognition_cue", "turning_evidence", "end_state"):
        if not str(arc.get(field, "")).strip():
            errors.append(f"emotional_arc.{field} is required")
    return errors


def validate_copy_lifecycle(payload: dict[str, Any], *, require_ready: bool = True) -> list[str]:
    """Reject an initialized scaffold until its copy brief is approved."""
    if not require_ready:
        return []
    status = str(payload.get("status", "pending")).strip().lower()
    return [] if status in {"ready", "approved"} else ["copy brief status must be ready or approved before execution"]


def pillar_for_content_type(content_type: str) -> str:
    if content_type in {"career_experiment"}:
        return "AI × 现实任务实验"
    if content_type in {"business_experiment", "monetization_case"}:
        return "AI 生意实验室"
    return "AI 新能力实测"


def viewer_job_for_content_type(content_type: str) -> str:
    if content_type in {"career_experiment"}:
        return "迁移"
    if content_type in {"business_experiment", "monetization_case"}:
        return "验证生意"
    if content_type in {"tutorial"}:
        return "复现"
    if content_type in {"newsjacking", "opinion"}:
        return "参与"
    return "判断"


def infer_pillar_selection(content_type: str, topic: str, explicit_pillar: str = "") -> tuple[str, str, str]:
    """Choose a pillar without letting a hot headline erase account fit."""
    if explicit_pillar.strip():
        return explicit_pillar.strip(), "editor_override", "编辑明确指定账号支柱"
    if content_type == "newsjacking":
        text = str(topic).lower()
        for tokens, pillar, reason in HOTSPOT_PILLAR_HINTS:
            if any(token.lower() in text for token in tokens):
                return pillar, "hotspot_topic_hint", reason
    return pillar_for_content_type(content_type), "content_type_default", "按内容类型默认支柱"


def viewer_job_for_selection(content_type: str, pillar: str) -> str:
    if content_type == "newsjacking" and pillar == "AI × 现实任务实验":
        return "迁移"
    if content_type == "newsjacking" and pillar == "AI 生意实验室":
        return "验证生意"
    return viewer_job_for_content_type(content_type)


def cta_for_content_type(content_type: str) -> tuple[str, str]:
    profile = load_profile()
    conversion = profile.get("conversion", {}) if isinstance(profile.get("conversion"), dict) else {}
    mapping = conversion.get("content_type_ctas", {}) if isinstance(conversion.get("content_type_ctas"), dict) else {}
    cta = str(mapping.get(content_type, "") or conversion.get("default_cta", "")).strip()
    mode = str(conversion.get("content_type_cta_modes", {}).get(content_type, "problem_signal")) if isinstance(conversion.get("content_type_cta_modes"), dict) else "problem_signal"
    return cta, mode


def voice_contract() -> dict[str, Any]:
    values = contract_values()
    profile = load_profile()
    brand_voice = load_json(ROOT / "configs" / "brand-voice.json")
    axes = brand_voice.get("adaptive_axes", {}) if isinstance(brand_voice.get("adaptive_axes"), dict) else {}
    rules = values["copy_contract"].get("voice_rules", [])
    return {
        "emotional_temperature": (axes.get("emotional_temperature") or ["冷静实测"])[0],
        "narrative_mode": (axes.get("narrative_mode") or ["结果先看"])[0],
        "first_person_rule": str(rules[0]) if len(rules) > 0 else "第一人称必须绑定具体实验动作、条件或观察",
        "signature_rule": str(rules[1]) if len(rules) > 1 else "先给判断，再交代证据；至少说清一个边界",
        "forbidden_shortcut": "不以夸张承诺、空泛热词或未经验证的第一人称代替证据",
        "boundary_sentence_required": True,
        "audience_empathy_required": True,
        "empathy_rule": "先描述观众可验证的处境，再进入实验；不把假设写成观众原话或作者经历",
        "emotional_turn_rule": "情绪变化服务于理解和掌控感，不用恐惧替代证据或承诺",
    }


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def classify(
    topic: str,
    evidence_level: str = "local_test",
    hot_topic: bool = False,
    forced_content_type: str = "",
    verified_hotspot: bool = False,
) -> tuple[str, str]:
    text = f"{topic} {evidence_level}".lower()
    if forced_content_type:
        taxonomy = load_json(ROOT / "configs" / "content-taxonomy.json")
        if forced_content_type not in taxonomy.get("content_types", {}):
            raise ValueError(f"unknown content type: {forced_content_type}")
        if forced_content_type == "newsjacking" and verified_hotspot is not True:
            raise ValueError("newsjacking override requires verified_hotspot=true")
        return forced_content_type, "content type explicitly selected by the editor."
    # A route may contain a stale/user-supplied hotspot title.  Such a title
    # is a research candidate, not permission to publish newsjacking copy.
    hotspot_signal = hot_topic or any(token in text for token in ("热搜", "榜单", "新闻", "news"))
    # A keyword or a caller-provided hot_topic flag is only a discovery hint.
    # Newsjacking is a publishable route only after the freshness/source gate
    # has explicitly returned True.  The default must therefore be fail-closed
    # for direct library and CLI callers as well as the package initializer.
    if hotspot_signal and verified_hotspot is True:
        return "newsjacking", "存在明确热点信号，先核验事件来源和 AI 相关性。"
    if any(token in text for token in ("github", "开源", "仓库", "部署", "readme")):
        return "github_project", "内容重点是项目能力和最短部署路径。"
    # Specific real-work and business signals outrank the broad word
    # “替代”.  Otherwise a topic such as “AI 能否替代咖啡师完成真实岗位
    # 任务” is misrouted to a generic comparison even though its required
    # evidence is task completion and human intervention.
    if any(token in text for token in ("职业", "岗位", "从业者", "真实任务", "工作流", "人工介入", "完成率", "行业")):
        return "career_experiment", "内容必须把 AI 放进真实职业任务，并记录人工边界与任务结果。"
    if any(token in text for token in ("变现", "收入", "营收", "回款", "订单", "成本回收")):
        return "monetization_case", "内容需要同时交代投入、证据和适用条件。"
    if any(token in text for token in ("生意", "商业实验", "用户测试", "付费", "预约", "mvp", "saas", "客户验证")):
        return "business_experiment", "内容必须用真实用户行为或付费信号验证问题，而不是只讲想法。"
    if any(token in text for token in ("原理", "机制", "为什么", "主要解决", "核心收益", "工作方式", "kv cache", "attention", "分页", "连续批处理")):
        return "technical_explainer", "内容重点是解释技术机制、关键术语和条件性收益，不把概念解释冒充本机实测。"
    if any(token in text for token in ("对比", "比较", "替代", "横评", "benchmark", "同类")):
        return "comparison", "内容需要先固定比较维度，再用同一组证据给出适用场景判断。"
    if any(token in text for token in ("模型", "实测", "实验", "配置", "gpu", "显存", "耗时", "对比")):
        return "tool_test", "内容有本机实验和参数对比，优先结果先看。"
    if any(token in text for token in ("失败", "踩坑", "报错", "bad case")):
        return "failure_review", "内容以失败样本和根因复盘为主。"
    if any(token in text for token in ("教程", "步骤", "怎么用", "安装")):
        return "tutorial", "内容需要逐步可复现，而不是先讲抽象原理。"
    return "opinion", "缺少明确实验或项目信号，先按事实与判断分离处理。"


def plan(
    topic: str,
    title: str,
    evidence_level: str,
    hot_topic: bool = False,
    forced_content_type: str = "",
    evidence_count: int = 0,
    step_count: int = 0,
    comparison_dimensions: int = 0,
    pillar: str = "",
    viewer_job: str = "",
    hook_type: str = "结果先看",
    ai_disclosure_status: str = "pending",
    ai_disclosure_location: str = "发布描述或画面显式标识",
    verified_hotspot: bool = False,
) -> dict[str, Any]:
    taxonomy = load_json(ROOT / "configs" / "content-taxonomy.json")
    profile = load_json(ROOT / "profiles" / "profile.json")
    content_type, reason = classify(topic, evidence_level, hot_topic, forced_content_type, verified_hotspot)
    selected_pillar, pillar_selection_source, pillar_selection_reason = infer_pillar_selection(content_type, topic, pillar)
    selected_viewer_job = viewer_job or viewer_job_for_selection(content_type, selected_pillar)
    values = contract_values(profile)
    if selected_pillar not in values["pillars"]:
        raise ValueError(f"unknown pillar: {selected_pillar}")
    if selected_viewer_job not in values["viewer_jobs"]:
        raise ValueError(f"unknown viewer_job: {selected_viewer_job}")
    if hook_type not in values["hook_types"]:
        raise ValueError(f"unknown hook_type: {hook_type}")
    direction = copy_direction_for_content(content_type, selected_pillar)
    cta, cta_mode = cta_for_content_type(content_type)
    spec = taxonomy.get("content_types", {}).get(content_type, {})
    structures = spec.get("structures", []) if isinstance(spec, dict) else []
    structure = structures[0] if structures else "problem-evidence-verdict-action"
    # Newsjacking has five mandatory beats in the taxonomy.  Its default must
    # therefore be promoted to a two-minute tier unless the editor supplies a
    # higher-confidence complexity calculation; this prevents evidence from
    # being squeezed into the one-minute default merely because counts were
    # not available at initialization time.
    duration_evidence_count = evidence_count
    if content_type == "newsjacking" and isinstance(spec, dict):
        duration_evidence_count = max(evidence_count, len(spec.get("required_beats", [])))
    duration_policy = policy_from_profile(profile)
    duration = adjust_for_complexity(
        duration_policy,
        resolve_tier(duration_policy, content_type=content_type),
        evidence_count=duration_evidence_count,
        step_count=step_count,
        comparison_dimensions=comparison_dimensions,
    )
    # Content type can rank candidates, but it cannot choose a real audience
    # or invent empathy. The package-local audience insight owns that decision.
    audience_scaffold = build_audience_scaffold(
        "pending-content-id",
        topic,
        content_type=content_type,
        pillar=selected_pillar,
    )
    return {
        "schema_version": 3,
        "status": "pending",
        "account": ACCOUNT,
        "title": title,
        "topic": topic,
        "content_type": content_type,
        "classification_source": "explicit_override" if forced_content_type else "adaptive_copy_router",
        "classification_reason": reason,
        # Keep publishable metadata distinct from a caller's discovery hint.
        # An unverified hot flag must not travel downstream as if it were an
        # approved news route.
        "hot_topic": bool(content_type == "newsjacking" and verified_hotspot is True),
        "hot_topic_verified": bool(verified_hotspot),
        "duration_tier": duration["id"],
        "duration_label": duration["label"],
        "target_seconds": duration["target_seconds"],
        "duration_range": duration["allowed_range_seconds"],
        "duration_selection_reason": duration["selection_reason"],
        "complexity": {
            "evidence_count": evidence_count,
            "duration_evidence_floor": duration_evidence_count,
            "step_count": step_count,
            "comparison_dimensions": comparison_dimensions,
        },
        # ``structure`` remains the taxonomy beat preset for compatibility;
        # the actual writing framework is the single canonical argument spine.
        "argument_structure": CANONICAL_ARGUMENT_STRUCTURE,
        "viewer_progress_structure": VIEWER_PROGRESS_STRUCTURE,
        "structure_role": "beat_preset",
        "structure": structure,
        "structure_reason": reason,
        "packaging_contract": {
            "structure": CANONICAL_PACKAGING_STRUCTURE,
            "hook_max_seconds": 6,
            "title_intro_match_required": True,
            "body_must_deliver_promise": True,
            "cta_count": 1,
            "evidence_policy_id": "douyin-copy-evidence-v1",
        },
        "evidence_level": evidence_level,
        "required_beats": spec.get("required_beats", []) if isinstance(spec, dict) else [],
        "pillar": selected_pillar,
        "pillar_selection": {
            "source": pillar_selection_source,
            "reason": pillar_selection_reason,
        },
        "copy_direction_route": direction["route_id"],
        "copy_direction_module": direction["module"],
        "copy_direction": direction,
        "viewer_job": selected_viewer_job,
        "viewer_intent": "",
        "audience": "",
        "audience_candidates": audience_scaffold["candidate_segments"],
        "audience_lens": lens_projection(audience_scaffold),
        "value_contract": audience_scaffold["value_contract"],
        "emotional_arc": audience_scaffold["emotional_arc"],
        "hook_type": hook_type,
        "narrative_tension": "",
        "voice_contract": voice_contract(),
        "cta": cta,
        "cta_mode": cta_mode,
        "cta_policy": "只保留一个与本条观众任务直接相关、可分类的动作",
        "strategy_ref": {
            "path": "00_brief/copy-strategy.json",
            "selected_angle_id": "",
            "selected_hook_id": "",
            "status": "pending",
        },
        "ai_disclosure": {
            "required": True,
            "status": ai_disclosure_status,
            "location": ai_disclosure_location,
            "reason": "当前账号固定使用数字人和授权音色克隆，发布前必须显式披露合成表达。",
        },
        "hotspot_contract": {
            "why_now": "",
            "ai_relevance": "",
            "viewer_problem": "",
            "evidence_floor": "",
        },
    }


def validate_copy(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("content_id", "account", "title", "content_type", "pillar", "viewer_job", "audience", "viewer_intent", "evidence_level", "structure", "hook_type", "narrative_tension", "voice_contract", "cta", "cta_mode", "claims", "duration_tier", "target_seconds", "duration_range", "duration_selection_reason", "ai_disclosure"):
        if not payload.get(field):
            errors.append(f"missing required field: {field}")
    if payload.get("account") != ACCOUNT:
        errors.append(f"account must be {ACCOUNT}")
    if payload.get("argument_structure") != CANONICAL_ARGUMENT_STRUCTURE:
        errors.append("argument_structure must use the canonical thesis spine")
    if payload.get("structure_role") != "beat_preset":
        errors.append("structure_role must identify structure as a beat preset")
    errors.extend(validate_contract_metadata(payload))
    packaging = payload.get("packaging_contract") if isinstance(payload.get("packaging_contract"), dict) else {}
    if packaging:
        if packaging.get("structure") != CANONICAL_PACKAGING_STRUCTURE:
            errors.append("packaging_contract.structure must be hook-body-close")
        if packaging.get("title_intro_match_required") is not True:
            errors.append("packaging_contract.title_intro_match_required must be true")
        if packaging.get("body_must_deliver_promise") is not True:
            errors.append("packaging_contract.body_must_deliver_promise must be true")
        if packaging.get("cta_count") != 1:
            errors.append("packaging_contract.cta_count must be 1")
    strategy_ref = payload.get("strategy_ref")
    if strategy_ref is not None:
        if not isinstance(strategy_ref, dict) or not str(strategy_ref.get("path", "")).strip():
            errors.append("strategy_ref must include path, selected_angle_id and selected_hook_id")
        elif not all(str(strategy_ref.get(field, "")).strip() for field in ("selected_angle_id", "selected_hook_id")):
            if str(payload.get("status", "")).strip() not in {"pending", "draft"} or str(strategy_ref.get("status", "")).strip() not in {"pending", "draft"}:
                errors.append("strategy_ref must include selected_angle_id and selected_hook_id before approval")
    if str(payload.get("evidence_level", "")) not in {"official", "local_test", "user_owned", "hypothesis"}:
        errors.append("invalid evidence_level")
    try:
        duration_policy = policy_from_profile(load_json(ROOT / "profiles" / "profile.json"))
        tier = resolve_tier(duration_policy, content_type=str(payload.get("content_type", "")), requested_tier=str(payload.get("duration_tier", "")))
    except (ValueError, TypeError) as error:
        errors.append(f"invalid duration tier: {error}")
        tier = None
    target = payload.get("target_seconds")
    if isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(float(target)) or float(target) <= 0:
        errors.append("target_seconds must be a positive finite number")
    duration_range = payload.get("duration_range")
    if not isinstance(duration_range, list) or len(duration_range) != 2 or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in duration_range):
        errors.append("duration_range must contain exactly two finite numbers")
    elif float(duration_range[0]) > float(duration_range[1]):
        errors.append("duration_range lower bound must not exceed upper bound")
    if tier is not None and isinstance(target, (int, float)) and not isinstance(target, bool) and isinstance(duration_range, list) and len(duration_range) == 2 and all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) for value in duration_range):
        lower, upper = [float(value) for value in tier["allowed_range_seconds"]]
        if float(target) < lower or float(target) > upper:
            errors.append("target_seconds is outside the selected duration tier")
        if float(duration_range[0]) > float(target) or float(duration_range[1]) < float(target):
            errors.append("duration_range must include target_seconds")
        if float(duration_range[0]) < lower or float(duration_range[1]) > upper:
            errors.append("duration_range exceeds the selected duration tier")
    claims = payload.get("claims") if isinstance(payload.get("claims"), list) else []
    for index, claim in enumerate(claims, 1):
        if not isinstance(claim, dict) or not claim.get("claim") or not claim.get("evidence") or not claim.get("status"):
            errors.append(f"claim {index} lacks claim/evidence/status")
    copy_text = str(payload.get("voiceover", ""))
    if not copy_text.strip():
        errors.append("voiceover is empty")
    forbidden = load_json(ROOT / "configs" / "brand-voice.json").get("banned_or_high_risk_phrases", [])
    found = [phrase for phrase in forbidden if phrase and phrase in copy_text]
    if found:
        errors.append("high-risk phrases present: " + ", ".join(found))
    cta = str(payload.get("cta", "")).strip()
    if copy_text.count(cta) > 1 and cta:
        errors.append("CTA is repeated; keep one action")
    if len(re.findall(r"(?:请|记得|欢迎|评论|收藏|关注|私信|点击|回复)", copy_text)) > 4:
        errors.append("too many CTA-like commands")
    if payload.get("content_type") == "newsjacking":
        if not payload.get("hot_topic"):
            errors.append("newsjacking requires hot_topic metadata")
        if payload.get("hot_topic_verified") is not True:
            errors.append("newsjacking requires hot_topic_verified=true")
        if str(payload.get("status", "")).strip().lower() in {"ready", "approved"}:
            for field in ("why_now", "ai_relevance", "viewer_problem", "evidence_floor"):
                if not str(payload.get(field, "")).strip():
                    contract = payload.get("hotspot_contract") if isinstance(payload.get("hotspot_contract"), dict) else {}
                    if not str(contract.get(field, "")).strip():
                        errors.append(f"newsjacking requires {field}")
    if payload.get("content_type") == "technical_explainer":
        try:
            from technical_explainer_qc import validate_payload as validate_technical_payload
        except ImportError:  # imported as scripts.adaptive_copy_router
            from scripts.technical_explainer_qc import validate_payload as validate_technical_payload
        errors.extend(validate_technical_payload(payload))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Route and validate adaptive Douyin copy.")
    sub = parser.add_subparsers(dest="command", required=True)
    route = sub.add_parser("route")
    route.add_argument("--topic", required=True)
    route.add_argument("--title", required=True)
    route.add_argument("--evidence-level", default="local_test", choices=["official", "local_test", "user_owned", "hypothesis"])
    route.add_argument("--hot-topic", action="store_true")
    route.add_argument("--verified-hotspot", action="store_true", help="confirm that the hotspot snapshot passed freshness verification")
    route.add_argument("--content-type", default="", help="explicit taxonomy override")
    route.add_argument("--evidence-count", type=int, default=0)
    route.add_argument("--step-count", type=int, default=0)
    route.add_argument("--comparison-dimensions", type=int, default=0)
    values = contract_values()
    route.add_argument("--pillar", choices=values["pillars"], default="")
    route.add_argument("--viewer-job", choices=sorted(values["viewer_jobs"]), default="")
    route.add_argument("--hook-type", choices=sorted(values["hook_types"]), default="结果先看")
    route.add_argument("--ai-disclosure-status", choices=["pending", "ready", "not-applicable"], default="pending")
    route.add_argument("--ai-disclosure-location", default="发布描述或画面显式标识")
    route.add_argument("--output")
    check = sub.add_parser("check")
    check.add_argument("--input", required=True)
    args = parser.parse_args()
    if args.command == "route":
        try:
            result = plan(
                args.topic,
                args.title,
                args.evidence_level,
                args.hot_topic,
                args.content_type,
                args.evidence_count,
                args.step_count,
                args.comparison_dimensions,
                args.pillar,
                args.viewer_job,
                args.hook_type,
                args.ai_disclosure_status,
                args.ai_disclosure_location,
                args.verified_hotspot,
            )
        except ValueError as error:
            raise SystemExit(str(error)) from error
    else:
        result = load_json(Path(args.input))
        errors = validate_copy(result)
        print(json.dumps({"status": "passed" if not errors else "blocked", "errors": errors}, ensure_ascii=False, indent=2))
        return 0 if not errors else 1
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
