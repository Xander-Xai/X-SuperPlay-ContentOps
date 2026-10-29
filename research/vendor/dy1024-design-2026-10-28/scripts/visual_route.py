#!/usr/bin/env python3
"""Route a video script to the safest visual representation.

This is a deterministic, explainable planning layer.  It does not generate or
download media.  It reads the approved script/storyboard and emits a per-scene
visual contract before the assets gate.  Exact claims always win over
decorative generation; editable diagrams and typeset formulas win over raster
image models.
"""

from __future__ import annotations

import argparse
from runtime_context import IDENTITY_ACCOUNT, require_account
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from console_encoding import configure_utf8_stdio
except ImportError:  # imported as scripts.visual_route
    from scripts.console_encoding import configure_utf8_stdio

configure_utf8_stdio()

from xiaohei_ip import profile_metadata
from branding import IP_NAME
from image_policy_contract import (
    IMAGE_ROUTE,
    TEXT_FREE_POLICY,
    XIAOHEI_IMAGE_ROUTE,
    XIAOHEI_TEXT_POLICY,
)
try:
    from canonical_workflow import SUPPORTED_CONTRACT_IDS
except ImportError:  # imported as scripts.visual_route
    from scripts.canonical_workflow import SUPPORTED_CONTRACT_IDS


SCHEMA_VERSION = 1
DEFAULT_OUTPUT = "04_video/visual-route.json"
DEFAULT_MARKDOWN = "04_video/visual-route.md"
ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "profiles" / "visual-routing-rules.json"

# These are first-class visual authors.  They are intentionally not listed as
# explicit visual owners stay visible in the route
# contract so the skill can be proven and audited downstream.
XIAOHEI_RENDERERS = {
    "ian-xiaohei-illustrations": {
        "route_id": "xiaohei_illustration",
        "label": f"{IP_NAME}手绘正文插画",
        "mode": "illustration",
    },
    "ian-xiaohei-scenes": {
        "route_id": "xiaohei_scene",
        "label": f"{IP_NAME}真实物件场景",
        "mode": "scene",
    },
}
BRIDGE_IMAGE_PROVIDER = IMAGE_ROUTE
APPROVED_IMAGE_PROVIDER = XIAOHEI_IMAGE_ROUTE
BRIDGE_OWNERS = {IMAGE_ROUTE, "chatgpt-bridge", "chatgpt bridge", "bridge"}
XIAOHEI_OWNER_ALIASES = {
    "X•超玩": "ian-xiaohei-illustrations",
    "X•超玩插画": "ian-xiaohei-illustrations",
    "X•超玩手绘": "ian-xiaohei-illustrations",
    "X•超玩场景": "ian-xiaohei-scenes",
    "X•超玩实物": "ian-xiaohei-scenes",
    "小黑": "ian-xiaohei-illustrations",
    "小黑插画": "ian-xiaohei-illustrations",
    "小黑手绘": "ian-xiaohei-illustrations",
    "小黑场景": "ian-xiaohei-scenes",
    "小黑实物": "ian-xiaohei-scenes",
    "ian-xiaohei-illustrations": "ian-xiaohei-illustrations",
    "ian-xiaohei-illustration": "ian-xiaohei-illustrations",
    "xiaohei-illustrations": "ian-xiaohei-illustrations",
    "xiaohei-illustration": "ian-xiaohei-illustrations",
    "X•超玩插画": "ian-xiaohei-illustrations",
    "X•超玩手绘": "ian-xiaohei-illustrations",
    "ian-xiaohei-scenes": "ian-xiaohei-scenes",
    "ian-xiaohei-scene": "ian-xiaohei-scenes",
    "xiaohei-scenes": "ian-xiaohei-scenes",
    "xiaohei-scene": "ian-xiaohei-scenes",
    "X•超玩场景": "ian-xiaohei-scenes",
    "X•超玩实物": "ian-xiaohei-scenes",
}
DIGITAL_HUMAN_OWNERS = {
    "digital-human", "digital_human", "presenter", "avatar", "h3", "minimax-h3",
}


def motion_contract(route_id: str, renderer: str, evidence: bool = False) -> dict[str, Any]:
    """Attach a production owner without changing the factual visual route.

    HyperFrames is an overlay/motion-graphics authoring layer.  Remotion is
    the scene/caption composition layer.  Evidence pixels remain owned by the
    source capture and may only receive a non-destructive overlay.
    """
    overlay_only = bool(evidence or route_id == "evidence_screen_recording")
    hyperframes_owner = route_id in {"formula_derivation", "architecture_diagram", "data_chart", "infographic_summary", "designed_card"} and not overlay_only
    owner = "hyperframes" if hyperframes_owner else "remotion"
    result = {
        "hyperframes": {
            "selected": hyperframes_owner,
            "role": "editable-motion-graphic" if hyperframes_owner else "available-overlay-only",
            "preserve_source_pixels": overlay_only,
            "renderer": "hyperframes-html-gsap",
        },
        "remotion": {
            "selected": owner == "remotion",
            "role": "scene-and-caption-composition" if owner == "remotion" else "available-composition-only",
            "renderer": "remotion-react-composition",
        },
        "owner": owner,
        "graphic_owner": owner,
        "one_owner_per_scene": True,
        "selection_reason": (
            "The selected plugin-native owner may annotate source evidence only within its authored contract; "
            "a failed renderer blocks the scene; no renderer switch is permitted."
            if overlay_only else
            "The selected plugin-native owner owns the scene contract; a failure blocks the scene."
        ),
    }
    return result


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"invalid JSON: {path}: {error}") from error


def read_policy() -> dict[str, Any]:
    policy = read_json(POLICY_PATH, {}) or {}
    if not isinstance(policy, dict):
        raise SystemExit(f"visual routing policy must be an object: {POLICY_PATH}")
    return policy


def is_production_canonical_manifest(manifest: dict[str, Any]) -> bool:
    """Match the workflow gate's canonical-vs-compatibility decision.

    Historical caller-selected packages retain the canonical contract label
    for compatibility, but they still need the legacy fallback fields.  The
    explicit canonical path namespace and artifact-root policy distinguish
    those packages from the production package created by ``content_package
    init``.
    """
    paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
    return (
        manifest.get("workflow_contract") in SUPPORTED_CONTRACT_IDS
        and "canonical_brief" in paths
        and manifest.get("artifact_root_policy") != "caller-selected-explicit-override"
    )


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def contains(text: str, terms: Iterable[str]) -> list[str]:
    return [term for term in terms if term.lower() in text]


def xiaohei_skill_request(text: str, explicit_owner: str) -> str:
    """Return the requested installed X•超玩 skill, if any.

    Explicit owner values are authoritative.  Natural-language markers are
    deliberately narrow so a generic request for an illustration does not
    silently change the account's image policy or evidence precedence.
    """
    owner = normalize(explicit_owner)
    if owner in XIAOHEI_OWNER_ALIASES:
        return XIAOHEI_OWNER_ALIASES[owner]
    if any(marker in text for marker in ("X•超玩实物", "X•超玩 2.0", "X•超玩2.0", "小黑实物", "小黑 2.0", "小黑2.0", "真实物件", "场景图", "长卷故事")):
        return "ian-xiaohei-scenes"
    if any(marker in text for marker in ("X•超玩插画", "X•超玩手绘", "X•超玩正文配图", "小黑插画", "小黑手绘", "怪诞正文配图", "小黑正文配图")):
        return "ian-xiaohei-illustrations"
    return ""


def default_xiaohei_skill(text: str) -> str:
    """Choose the first-class X•超玩 author for an opted-in concept scene."""
    if any(marker in text for marker in ("项目复盘", "处境", "压力", "转折", "产品演化", "成长路径", "真实物件", "场景")):
        return "ian-xiaohei-scenes"
    return "ian-xiaohei-illustrations"


def scene_text(scene: dict[str, Any], row: dict[str, str], script: str = "") -> str:
    values: list[Any] = []
    for key in (
        "scene_id", "script_span", "viewer_job", "visual_owner", "asset_type",
        "source_strategy", "rights_plan", "visual_theme", "claim_ids",
    ):
        values.append(scene.get(key, ""))
    for key in (
        "scene_id", "voice", "subtitle", "overlay_text", "visual", "framing", "motion",
        "transition", "source_or_prompt", "visual_treatment",
    ):
        values.append(row.get(key, ""))
    if script:
        values.append(script)
    return normalize(" ".join(str(value) for value in values))


def ratio_for(manifest: dict[str, Any], scene: dict[str, Any], row: dict[str, str]) -> str:
    explicit = str(scene.get("aspect_ratio") or row.get("aspect_ratio") or "").strip()
    if explicit:
        return explicit
    plan = manifest.get("video", {}) if isinstance(manifest.get("video"), dict) else {}
    explicit = str(plan.get("aspect_ratio", "")).strip()
    return explicit or "9:16"


def evidence_route(text: str, scene: dict[str, Any], row: dict[str, str]) -> bool:
    owner = normalize(scene.get("visual_owner") or row.get("visual_owner"))
    source = normalize(scene.get("source_strategy") or row.get("source_or_prompt"))
    evidence_terms = (
        "screen recording", "screen-recording", "录屏", "截图", "产品演示",
        "官方页面", "官网", "terminal", "命令行", "powershell", "界面",
        "仓库", "github", "真实", "证据", "demo", "dashboard", "product demo",
    )
    evidence_hits = contains(text + " " + source, evidence_terms)
    # X•超玩 scene language intentionally uses words such as “真实物件” and
    # “项目复盘”. An explicit X•超玩 owner is illustrative, not documentary;
    # a real evidence marker still wins when both appear in free text.
    if owner in XIAOHEI_OWNER_ALIASES:
        return False
    if xiaohei_skill_request(text, owner) and not evidence_hits:
        return False
    return owner in {"screen-recording", "evidence", "terminal", "screen", "source"} or bool(evidence_hits)


def formula_route(text: str) -> tuple[bool, list[str]]:
    terms = (
        "公式", "推导", "等式", "证明", "矩阵乘法", "偏导", "梯度", "损失函数",
        "softmax", "attention score", "q/k/v", "q k v", "∑", "∫", "σ", "latex",
        "方程", "变量", "代入", "展开", "求导", "概率分布",
    )
    hits = contains(text, terms)
    qkv_only = [hit for hit in hits if hit in {"q/k/v", "q k v"}]
    math_context = contains(text, ("公式", "推导", "计算", "矩阵", "softmax", "权重", "求导", "代入", "展开", "概率"))
    if qkv_only and not math_context:
        hits = [hit for hit in hits if hit not in qkv_only]
    return bool(hits), hits


def animation_request(text: str) -> bool:
    """Detect an explicit request for motion, not merely a technical topic."""
    return bool(contains(text, ("动画", "动态演示", "逐帧", "三蓝一棕", "3blue1brown", "animate", "animated", "walkthrough")))


def architecture_route(text: str) -> tuple[bool, list[str]]:
    terms = (
        "transformer", "架构图", "架构", "architecture", "architecture diagram", "组件", "节点", "链路", "pipeline",
        "encoder", "decoder", "attention layer", "模块", "依赖", "拓扑",
        "api gateway", "数据流", "调用链", "流程图", "系统边界",
    )
    hits = contains(text, terms)
    return bool(hits), hits


def data_route(text: str) -> tuple[bool, list[str]]:
    terms = (
        "数据", "指标", "data chart", "port map", "百分比", "增长", "趋势", "排行", "对比", "比较",
        "柱状图", "折线图", "散点图", "表格", "均值", "中位数", "样本",
        "benchmark", "latency", "accuracy", "%", "同比", "环比",
    )
    hits = contains(text, terms)
    # A numeric comparison is evidence for a chart, but a lone year or scene
    # timestamp should not trigger it.
    numeric = bool(re.search(r"\d+(?:\.\d+)?\s*%|\d+\s*(?:ms|秒|个|项|倍)\b", text))
    explicit_chart = bool(contains(text, ("data chart", "port map", "bar chart", "line chart")))
    return bool(hits) and (numeric or len(hits) >= 2 or explicit_chart), hits + (["numeric"] if numeric else [])


def choose_architecture_strategy(text: str) -> tuple[str, str, list[str], list[str]]:
    """Return one renderer, format and its required skill paths."""
    technical_terms = contains(text, ("transformer", "encoder", "decoder", "attention", "q/k/v", "多头", "层", "张量"))
    educational_terms = contains(text, ("讲解", "原理", "拆解", "理解", "为什么", "白板", "一步一步"))
    if technical_terms and educational_terms:
        return (
            "cs-board_whiteboard",
            "source-image+annotation+srt→mp4→9:16-safe-frame",
            ["cs-board-whiteboard"],
            ["manim-video", "remotion"],
        )
    if technical_terms:
        return (
            "mermaid_svg",
            "editable-mermaid→svg→png→mp4-frame",
            ["beautiful-mermaid"],
            ["remotion"],
        )
    return (
        "mermaid_svg",
        "editable-mermaid→svg→png→mp4-frame",
        ["beautiful-mermaid"],
        ["remotion"],
    )


def image_policy_enabled(account: str) -> bool:
    """Return whether the target profile explicitly enables raster generation."""
    policy = image_policy(account)
    return policy.get("enabled") is True


def image_policy(account: str) -> dict[str, Any]:
    """Load the account-scoped image policy without widening its allow-list."""
    if account != IDENTITY_ACCOUNT:
        return {}
    profile = read_json(ROOT / "profiles" / "profile.json", {}) or {}
    video = profile.get("video", {}) if isinstance(profile, dict) else {}
    policy = video.get("image_policy", {}) if isinstance(video, dict) else {}
    return policy if isinstance(policy, dict) else {}


def image_policy_allows(account: str, renderer: str, provider: str) -> bool:
    """Require both a registered style route and a registered provider route."""
    policy = image_policy(account)
    if policy.get("enabled") is not True:
        return False
    allowed_routes = {str(item).strip() for item in policy.get("allowed_routes", []) if str(item).strip()}
    allowed_routes.update(str(item).strip() for item in policy.get("english_text_routes", []) if str(item).strip())
    allowed_routes.update(str(item).strip() for item in policy.get("no_text_routes", []) if str(item).strip())
    allowed_providers = {str(item).strip() for item in policy.get("allowed_providers", []) if str(item).strip()}
    if not allowed_providers:
        configured = str(policy.get("provider_route", "")).strip()
        if configured:
            allowed_providers.add(configured)
    route_by_renderer = {
        "ian-xiaohei-illustrations": "xiaohei_illustration",
        "ian-xiaohei-scenes": "xiaohei_scene",
    }
    mapped_provider = (policy.get("provider_by_route", {}) or {}).get(route_by_renderer.get(renderer, ""))
    if mapped_provider and str(mapped_provider).strip() != provider:
        return False
    return renderer in allowed_routes and provider in allowed_providers


def route_skill_available(route: str) -> bool:
    """Resolve only skills that are actually present in the isolated bundle."""
    internal = {
        "account-router", "compile-short-video", "design-direction", "media-delivery",
        "runtime-media", "source-collector", "rights-audit", "delivery-package",
        "publish-feedback", "douyin-sidecar-publish", "douyin-creator-sidecar", "creator-ops-sidecar",
        "visual-route",
    }
    if route in internal:
        return True
    root = ROOT / "skills" / route
    return root.is_dir() and any(root.rglob("SKILL.md"))


def resolve_skill_chain(skills: list[str], blocked_routes: list[str]) -> tuple[list[str], list[str], bool]:
    """Keep the authored route stable and report unavailable skills as blocked."""
    primary = [str(item).strip() for item in skills if str(item).strip()]
    available_primary = [item for item in primary if route_skill_available(item)]
    return available_primary or primary, [str(item).strip() for item in blocked_routes if str(item).strip()], available_primary != primary


def route_scene(
    account: str,
    title: str,
    scene: dict[str, Any],
    row: dict[str, str],
    script: str = "",
    index: int = 0,
    manifest: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = scene_text(scene, row, script)
    scene_id = str(scene.get("scene_id") or row.get("scene_id") or f"scene-{index:02d}")
    delivery_ratio = ratio_for(manifest or {}, scene, row) or "9:16"
    evidence = evidence_route(text, scene, row)
    explicit_evidence = normalize(scene.get("visual_owner") or row.get("visual_owner")) in {
        "screen-recording", "evidence", "terminal", "screen", "source",
    }
    formula, formula_hits = formula_route(text)
    architecture, architecture_hits = architecture_route(text)
    data, data_hits = data_route(text)
    explicit_owner = normalize(scene.get("visual_owner") or row.get("visual_owner"))
    explicit_broll_route = normalize(scene.get("broll_route") or row.get("broll_route"))
    xiaohei_renderer = xiaohei_skill_request(text, explicit_owner)
    explicit_cs_board = explicit_owner in {
        "cs-board-whiteboard", "cs-board", "csboard", "srt-whiteboard-animation", "whiteboard-animation",
    }
    image_enabled = image_policy_enabled(account)
    # Generic illustration/concept language uses the Bridge. Xiaohei is
    # opt-in only via an explicit Xiaohei owner or the narrow Xiaohei markers
    # above; never promote a normal concept request to the Xiaohei route.
    default_xiaohei = False
    decision: list[str] = []
    bridge_preflight: dict[str, Any] | None = None

    # Precedence is deliberate: a visual that carries a factual claim may not
    # be replaced by a plausible-looking generated image.
    if explicit_owner in DIGITAL_HUMAN_OWNERS:
        # The presenter is a first-class moving-media route.  It is not an
        # image-generation request, so it must not be handed to the Bridge
        # prompt planner as a raster slot.
        route_id = "digital_human"
        renderer = "minimax-h3"
        preferred = "mp4-with-canonical-narration"
        skills = ["clean-talking-video", "runtime-media"]
        decision.append("explicit-digital-human-owner:minimax-h3")
        text_policy = "spoken-narration-only; no generated text or factual evidence"
        requires_generation = False
        claim_mode = "explanation"
        label = "MiniMax H3 数字人"
    elif explicit_broll_route == "product-ui" or explicit_evidence:
        route_id = "evidence_screen_recording"
        renderer = "source-capture"
        preferred = "png-or-mp4-screen-capture"
        skills = ["media-use", "media-delivery"]
        decision.append(f"explicit-director-broll-route:{explicit_broll_route or 'evidence-owner'}")
        text_policy = "preserve-source-pixels; redact-secrets; no generated replacement for a factual claim"
        requires_generation = False
        claim_mode = "evidence"
        label = "证据录屏/截图"
    elif explicit_broll_route == "concept-motion" and not explicit_evidence:
        route_id = "designed_card"
        renderer = "html-svg-card"
        preferred = "svg-or-png→mp4-frame"
        skills = ["remotion", "design-direction"]
        decision.append("explicit-director-broll-route:concept-motion")
        text_policy = "copy must remain editable; use card only when it carries one short claim"
        requires_generation = False
        claim_mode = "exact-or-illustrative"
        label = "可编辑信息卡"
    elif explicit_cs_board and not explicit_evidence:
        route_id = "cs_board_whiteboard"
        renderer = "cs-board-stream"
        preferred = "source-image+annotation+srt→mp4→9:16-safe-frame"
        skills = ["cs-board-whiteboard"]
        decision.append("explicit-cs-board-owner")
        text_policy = "human-authored-source-and-annotation; exact labels remain editable in source; no model-generated evidence"
        requires_generation = False
        claim_mode = "exact-or-illustrative"
        label = "CS Board 白板动画"
    elif formula and not explicit_evidence:
        route_id = "formula_derivation"
        if animation_request(text):
            renderer = "manim-video"
            preferred = "mp4-technical-animation→9:16-safe-frame"
            skills = ["manim-video", "latex-formatting"]
            decision.append("explicit-animation-request")
            text_policy = "exact-formula-only; MathTex/LaTeX; reserve two-second holds after each reveal"
        else:
            renderer = "manim-video"
            preferred = "mp4-technical-animation→9:16-safe-frame"
            skills = ["manim-video", "latex-formatting"]
            text_policy = "exact-formula-only; MathTex/LaTeX; preserve source script and render receipt"
        decision += [f"formula-marker:{hit}" for hit in formula_hits]
        requires_generation = False
        claim_mode = "exact"
        label = "公式推导白板"
    elif explicit_evidence:
        route_id = "evidence_screen_recording"
        renderer = "source-capture"
        preferred = "png-or-mp4-screen-capture"
        skills = ["media-use", "media-delivery"]
        decision.append("explicit-evidence-owner")
        text_policy = "preserve-source-pixels; redact-secrets; no generated replacement for a factual claim"
        requires_generation = False
        claim_mode = "evidence"
        label = "证据录屏/截图"
    elif evidence:
        route_id = "evidence_screen_recording"
        renderer = "source-capture"
        preferred = "png-or-mp4-screen-capture"
        skills = ["media-use", "media-delivery"]
        decision.append("evidence-or-screen-owner")
        text_policy = "preserve-source-pixels; redact-secrets; no generated replacement for a factual claim"
        requires_generation = False
        claim_mode = "evidence"
        label = "证据录屏/截图"
    elif architecture:
        route_id = "architecture_diagram"
        renderer, preferred, skills, _ = choose_architecture_strategy(text)
        decision += [f"architecture-marker:{hit}" for hit in architecture_hits]
        text_policy = "exact-labels-required; keep editable source; never use raster AI for nodes, code, ports or numbers"
        requires_generation = False
        claim_mode = "exact-or-evidence"
        label = "架构/流程图"
    elif data:
        route_id = "data_chart"
        renderer = "deterministic-chart"
        preferred = "svg-or-png-chart→mp4-frame"
        skills = ["baoyu-infographic", "beautiful-mermaid"]
        decision += [f"data-marker:{hit}" for hit in data_hits]
        text_policy = "numbers-must-be-data-bound; render exact values with SVG/HTML; no hallucinated labels"
        requires_generation = False
        claim_mode = "exact"
        label = "数据图表/对比"
    elif any(marker in text for marker in ("清单", "步骤", "要点", "总结", "路线图", "对照表", "checklist")):
        route_id = "infographic_summary"
        renderer = "html-infographic"
        preferred = "html→png→mp4-frame"
        skills = ["baoyu-infographic"]
        decision.append("summary-or-checklist-marker")
        text_policy = "all copy remains editable HTML/SVG; no tiny text; one core argument per frame"
        requires_generation = False
        claim_mode = "exact"
        label = "信息图摘要"
    elif xiaohei_renderer:
        xiaohei_contract = XIAOHEI_RENDERERS[xiaohei_renderer]
        route_id = str(xiaohei_contract["route_id"])
        renderer = xiaohei_renderer
        preferred = "png→mp4-frame"
        skills = [xiaohei_renderer]
        # This is a policy block.  The route remains the
        # selected primary skill and the assets gate will stop execution until
        # an approved image provider is explicitly enabled.
        decision.append(f"explicit-{IP_NAME}-skill:{xiaohei_renderer}")
        if default_xiaohei:
            decision.append(f"profile-image-policy-default-{IP_NAME}:{xiaohei_renderer}")
        if not image_enabled:
            decision.append("image-policy-disabled-primary-route-blocked")
        elif not image_policy_allows(account, xiaohei_renderer, APPROVED_IMAGE_PROVIDER):
            decision.append("image-policy-route-or-provider-not-allowed")
        text_policy = XIAOHEI_TEXT_POLICY
        requires_generation = True
        claim_mode = "illustrative"
        label = str(xiaohei_contract["label"])
    elif image_enabled and image_policy_allows(account, BRIDGE_IMAGE_PROVIDER, BRIDGE_IMAGE_PROVIDER) and (explicit_owner in BRIDGE_OWNERS or explicit_owner in {"cover", "thumbnail", "hook", "illustration", "generated"} or any(marker in text for marker in ("封面", "概念图", "氛围", "隐喻", "插画", "场景"))):
        route_id = "concept_illustration"
        renderer = BRIDGE_IMAGE_PROVIDER
        preferred = "png"
        skills = [BRIDGE_IMAGE_PROVIDER]
        # pageAssets is a Codex host capability, so runtime checks happen at
        # dispatch. Planning keeps the selected Bridge route visible and never
        # silently downgrades to another provider.
        bridge_preflight = {}
        decision.append("non-factual-concept-or-cover")
        text_policy = TEXT_FREE_POLICY
        requires_generation = True
        claim_mode = "illustrative"
        label = "概念插画/氛围图"
    else:
        route_id = "designed_card"
        renderer = "html-svg-card"
        preferred = "svg-or-png→mp4-frame"
        skills = ["remotion", "design-direction"]
        if explicit_owner in {"cover", "thumbnail", "hook", "illustration", "generated"} or any(marker in text for marker in ("封面", "概念图", "氛围", "隐喻", "插画", "场景")):
            decision.append("image-policy-disabled" if not image_enabled else "image-policy-route-or-provider-not-allowed")
        else:
            decision.append("no-specialized-semantic-marker")
        text_policy = "copy must remain editable; use card only when it carries one short claim"
        requires_generation = False
        claim_mode = "exact"
        label = "可编辑信息卡"

    if route_id == "concept_illustration" and evidence:
        # Explicit evidence always overrides a loosely worded illustration
        # request, which prevents a generated fake screenshot.
        route_id = "evidence_screen_recording"
        renderer = "source-capture"
        preferred = "png-or-mp4-screen-capture"
        skills = ["media-use", "media-delivery"]
        requires_generation = False
        claim_mode = "evidence"
        text_policy = "preserve-source-pixels; redact-secrets; no generated replacement for a factual claim"
        label = "证据录屏/截图"
        decision.append("evidence-overrides-illustration")

    # Render dense deterministic material on a readable source canvas, then
    # reframe it into the platform canvas.  The two ratios are intentionally
    # separate so a vertical video does not force tiny architecture labels or
    # cramped equations.
    source_ratio = delivery_ratio
    source_ratios = ((policy or {}).get("defaults", {}) or {}).get("source_ratios", {})
    if isinstance(source_ratios, dict) and str(source_ratios.get(route_id, "")).strip():
        source_ratio = str(source_ratios[route_id]).strip()
    elif route_id == "architecture_diagram":
        source_ratio = "16:9"
    elif route_id in {"formula_derivation", "data_chart"}:
        source_ratio = "4:3"
    elif route_id == "evidence_screen_recording":
        # Preserve a readable source canvas; the delivery compositor reframes
        # it into the vertical 9:16 safe area later.
        source_ratio = "4:3"
    elif route_id in {"xiaohei_illustration", "xiaohei_scene"}:
        source_ratio = "9:16"
    elif route_id == "cs_board_whiteboard":
        source_ratio = "16:9"

    result = {
        "scene_id": scene_id,
        "label": label,
        "route_id": route_id,
        "renderer": renderer,
        "preferred_format": preferred,
        "aspect_ratio": source_ratio,
        "delivery_aspect_ratio": delivery_ratio,
        "reframe": {
            "mode": "cover",
            "focal_point": [0.5, 0.5],
            "safe_area": "center-column" if source_ratio != delivery_ratio else "full-frame",
        },
        "skill_routes": skills,
        "primary_skill": skills[0] if skills else renderer,
        "requires_generation": requires_generation,
        "generation_provider": (
            str((image_policy(account).get("provider_by_route", {}) or {}).get(route_id) or (
            APPROVED_IMAGE_PROVIDER if renderer in XIAOHEI_RENDERERS else BRIDGE_IMAGE_PROVIDER
            ))
            if requires_generation else ""
        ),
        "provider": "minimax-h3" if route_id == "digital_human" else (
            str((image_policy(account).get("provider_by_route", {}) or {}).get(route_id) or "")
            if requires_generation else ""
        ),
        "generation_mode": "talking-video" if route_id == "digital_human" else "",
        "claim_mode": claim_mode,
        "text_policy": text_policy,
        "text_required": False,
        "generation_route": (
            "bridge-xiaohei" if route_id in {"xiaohei_illustration", "xiaohei_scene"}
            else "bridge-concept" if route_id == "concept_illustration" else ""
        ),
        "provider_preflight": bridge_preflight or {},
        "xiaohei_ip": ({key: value for key, value in profile_metadata().items() if key != "ip_profile_path"}
                       if route_id in {"xiaohei_illustration", "xiaohei_scene"} else {}),
        "decision_trace": decision,
        "claim_ids": scene.get("claim_ids", []) if isinstance(scene.get("claim_ids"), list) else [],
        "asset_id": str(scene.get("asset_id") or row.get("asset_id") or ""),
        "status": "blocked" if bridge_preflight and not bridge_preflight.get("available") else "planned",
        "blocked_by": list(bridge_preflight.get("missing", [])) if bridge_preflight and not bridge_preflight.get("available") else [],
        "execution_contract": {
            "input": "approved scene copy + director material plan + claim/source references",
            "output": preferred,
            "provenance_required": True,
            "human_review_required": True,
        },
        "motion": motion_contract(route_id, renderer, evidence=explicit_evidence or evidence),
        "account": account,
        "title": title,
    }
    # Historical fixtures can still be inspected outside production.  A
    # canonical package receives no alternative-route fields at all.
    if not isinstance(manifest, dict) or not is_production_canonical_manifest(manifest):
        # Compatibility packages still carry a required fallback contract.
        # Preserve an explicit director fallback when it is safe to do so;
        # evidence and generated routes remain fail-closed and may only name
        # their blocking state, never a synthetic substitute.
        explicit_fallbacks = [
            str(value).strip()
            for value in (scene.get("fallback_routes") if isinstance(scene.get("fallback_routes"), list) else [])
            if str(value).strip()
        ]
        explicit_fallback = str(scene.get("fallback", "")).strip()
        if explicit_fallback and explicit_fallback not in explicit_fallbacks:
            explicit_fallbacks.append(explicit_fallback)
        if route_id == "evidence_screen_recording":
            result["fallback_routes"] = ["blocked-awaiting-real-capture"]
        elif requires_generation:
            result["fallback_routes"] = ["blocked-awaiting-human-decision"]
        else:
            result["fallback_routes"] = explicit_fallbacks or ["designed-card"]
    return result


def script_scene_text(script: str) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^###\s*(scene-[^|\s]+)(?:\s*\|[^\n]*)?\s*$", script))
    output: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(script)
        output[match.group(1).strip()] = script[match.start():end]
    return output


def load_scenes(project: Path, manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]], str]:
    paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
    if is_production_canonical_manifest(manifest):
        # Canonical packages store the authoritative scene beats in the JSON
        # Visual Plan rather than the historical markdown/video-script tree.
        # Derive a read-only routing view so the planners cannot silently see
        # zero scenes and report a false "no generation required" result.
        visual_path = project / str(paths.get("canonical_visual_plan", "04_visual/visual-plan.json"))
        visual = read_json(visual_path, {}) or {}
        beats = visual.get("beats", []) if isinstance(visual, dict) else []
        scenes: list[dict[str, Any]] = []
        owner_by_visual = {
            "generated_image": "generated",
            "generated_broll": "generated",
            "generated_i2v": "generated",
            "real_screen_recording": "screen-recording",
            "real_source": "source",
            "information_motion": "concept-motion",
        }
        for beat in beats if isinstance(beats, list) else []:
            if not isinstance(beat, dict) or not str(beat.get("beat_id") or "").strip():
                continue
            primary = str(beat.get("primary_visual") or "").strip()
            scenes.append({
                "scene_id": str(beat.get("beat_id")),
                "viewer_job": str(beat.get("viewer_intent") or "Make the spoken point visible"),
                "visual_owner": owner_by_visual.get(primary, primary),
                "asset_type": primary,
                "asset_id": str(beat.get("asset_id") or beat.get("evidence_asset_id") or ""),
                "claim_ids": beat.get("claim_ids", []) if isinstance(beat.get("claim_ids"), list) else [],
            })
        if scenes:
            return scenes, {}, ""
    script_path = project / str(paths.get("video_script", "04_video/video-script.md"))
    script = script_path.read_text(encoding="utf-8") if script_path.is_file() else ""
    script_parts = script_scene_text(script)
    storyboard_path = project / str(paths.get("storyboard", "04_video/storyboard.csv"))
    rows: dict[str, dict[str, str]] = {}
    if storyboard_path.is_file():
        with storyboard_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = {str(row.get("scene_id", "")): row for row in csv.DictReader(handle) if row.get("scene_id")}
    director_path = project / str(paths.get("director_plan", "04_video/director-material-plan.json"))
    director = read_json(director_path, {}) or {}
    raw_scenes = director.get("scenes", []) if isinstance(director, dict) else []
    scenes = [scene for scene in raw_scenes if isinstance(scene, dict)]
    if not scenes:
        scenes = [{"scene_id": scene_id} for scene_id in rows]
    if not scenes and script_parts:
        scenes = [{"scene_id": scene_id} for scene_id in script_parts]
    return scenes, rows, script


def markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 视觉路由：{report.get('content_id', '')}",
        "",
        "这份文件只决定‘用什么视觉形式’，不会自动生成或下载素材。必须先通过导演计划与素材门禁。",
        "",
        f"- 账号：`{report.get('account', '')}`",
        f"- 状态：`{report.get('status', '')}`",
        f"- 生成时间：`{report.get('generated_at', '')}`",
        f"- 规则版本：`{report.get('rule_version', '')}`",
        "",
        "| 场景 | 路由 | 执行器 | 输出 | 生图 | 选择依据 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in report.get("routes", []):
        lines.append(
            f"| {item.get('scene_id', '')} | {item.get('label', item.get('route_id', ''))} | "
            f"`{item.get('renderer', '')}` | `{item.get('preferred_format', '')}` | "
            f"{'是' if item.get('requires_generation') else '否'} | "
            f"{'；'.join(item.get('decision_trace', [])) or '—'} |"
        )
    lines.extend([
        "",
        "## 硬规则",
        "",
        "- 架构、代码、UI、端口、接口字段和数字不能用栅格 AI 图冒充事实；保留 Mermaid/cs-board/HTML 的可编辑或可追溯源。",
        "- 公式推导默认白板路线，公式用 LaTeX/SVG 精确排版，不能让生图模型绘制公式。",
        "- 证据场景优先使用真实录屏、官方页面或用户素材；概念插画必须标记 illustrative。",
        "- 每个场景必须先取得对应来源或生成资产；缺失时阻断，不替换为其他路线。",
        "- 单篇视频最多使用两套主要视觉系统，连续卡片不超过设计方向设定，防止视觉疲劳。",
        "",
    ])
    return "\n".join(lines)


def build_report(project: Path, manifest: dict[str, Any], text_override: str | None = None) -> dict[str, Any]:
    policy = read_policy()
    scenes, rows, script = load_scenes(project, manifest)
    if text_override:
        scenes = [{"scene_id": "sample", "viewer_job": text_override, "visual_owner": ""}]
        rows = {}
        script = text_override
    title = str(manifest.get("title", ""))
    parts = script_scene_text(script)
    routes = []
    for index, scene in enumerate(scenes, 1):
        scene_id = str(scene.get("scene_id", ""))
        routes.append(
            route_scene(
                str(manifest.get("account", "")),
                title,
                scene,
                rows.get(scene_id, {}),
                parts.get(scene_id, ""),
                index,
                manifest,
                policy,
            )
        )
    contracts = policy.get("routes", {}) if isinstance(policy.get("routes"), dict) else {}
    for item in routes:
        contract = contracts.get(item.get("route_id"), {})
        if isinstance(contract, dict):
            item["policy_contract"] = contract
        route_id = str(item.get("route_id", ""))
        item["audio_binding"] = {
            "owner": "workflow-final-narration",
            "role": "timing-and-caption-only" if route_id in {"xiaohei_illustration", "xiaohei_scene", "concept_illustration", "cs_board_whiteboard"} else "scene-timing",
            "narration": "bound-after-audio-gate",
            "captions": "bound-to-final-audio-asr",
        }
    generated = [item for item in routes if item["requires_generation"]]
    route_ids = sorted({item["route_id"] for item in routes})
    execution_routes = sorted({skill for item in routes for skill in item.get("skill_routes", [])})
    route_blockers = [
        str(item.get("scene_id", ""))
        for item in routes
        if str(item.get("status", "")) == "blocked"
    ]
    audio_handoff_value = str(manifest.get("paths", {}).get("audio_handoff", "04_video/audio-handoff.json"))
    audio_handoff_path = project / audio_handoff_value
    audio_handoff = read_json(audio_handoff_path, {}) if audio_handoff_path.is_file() else {}
    audio_hash = str(audio_handoff.get("audio_sha256", "")).strip()
    for item in routes:
        binding = item.get("audio_binding") if isinstance(item.get("audio_binding"), dict) else {}
        binding["narration"] = audio_handoff_value
        if audio_hash:
            binding["audio_sha256"] = audio_hash
        binding["captions"] = audio_handoff.get("captions") or "bound-to-final-audio-asr"
        item["audio_binding"] = binding
    return {
        "schema_version": SCHEMA_VERSION,
        # Keep the package contract on the route hand-off so canonical gates
        # do not have to infer whether this is a v2 decision or a legacy
        # readable report.
        "contract": str(manifest.get("workflow_contract") or ""),
        "rule_version": str(policy.get("rule_version", "visual-route-1.0")),
        "content_id": str(manifest.get("content_id", "")),
        "account": str(manifest.get("account", "")),
        "platform": "douyin",
        # Legacy packages retain the historical ``ready`` value.  Production
        # canonical packages expose the stage hand-off as ``ready_for_review``
        # while the CLI accepts both values for backwards compatibility.
        "status": (
            "blocked"
            if not routes or route_blockers
            else "ready_for_review" if is_production_canonical_manifest(manifest) else "ready"
        ),
        "generated_at": now(),
        "routes": routes,
        "route_ids": route_ids,
        "generation_required": bool(generated),
        "generation_routes": sorted({item["renderer"] for item in generated}),
        "execution_routes": execution_routes,
        "precedence": policy.get("precedence", []),
        "routing_defaults": policy.get("defaults", {}),
        "hard_bans": policy.get("hard_bans", []),
        "notes": "This report is a plan. Execute only after director-material-plan and assets gate approval.",
        "blocked_by": ["agnes-unavailable-awaiting-human-decision"] if route_blockers else [],
        "audio_binding": {
            "owner": "workflow-final-narration",
            "narration": audio_handoff_value,
            "audio_sha256": audio_hash,
            "duration_seconds": float(audio_handoff.get("duration_seconds") or 0),
            "role": "visual routes consume timing/captions; they never own narration",
        },
    }


def write_project_report(project: Path, manifest: dict[str, Any], report: dict[str, Any], output_value: str | None = None) -> tuple[Path, Path]:
    """Persist the route plan without executing renderers or mutating media.

    Planning is intentionally side-effect free.  Native rendering and its
    provenance must happen in the production stage after the assets gate, so
    a route report can never manufacture ``success`` records for a renderer.
    """
    selected_output = output_value or manifest.get("paths", {}).get("visual_route", DEFAULT_OUTPUT)
    output = Path(selected_output)
    if not output.is_absolute():
        output = project / output
    write_json(output, report)
    markdown_path = output.with_suffix(".md") if output_value else project / str(manifest.get("paths", {}).get("visual_route_review", DEFAULT_MARKDOWN))
    markdown_path.write_text(markdown(report), encoding="utf-8")
    execution_value = manifest.get("paths", {}).get("execution_plan", "00_brief/execution-plan.json")
    execution_path = project / str(execution_value)
    execution = read_json(execution_path, {}) or {}
    execution["visual_routing"] = {
        "status": report["status"],
        "rule_version": report["rule_version"],
        "route_file": str(output.relative_to(project)).replace("\\", "/") if output.is_relative_to(project) else str(output),
        "route_ids": report["route_ids"],
        "generation_required": report["generation_required"],
        "generation_routes": report["generation_routes"],
    }
    # These are the actual selected skill routes for this package.
    # The provenance gate will therefore require evidence only for capabilities
    # that this script chose for this package.
    execution["visual_routes"] = report.get("execution_routes", [])
    if execution_path.is_file():
        write_json(execution_path, execution)

    return output, markdown_path


def run(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve() if args.project else Path.cwd()
    manifest_path = project / "content.json"
    loaded_manifest = read_json(manifest_path, {})
    if args.project and not loaded_manifest:
        raise SystemExit(f"missing content.json: {manifest_path}")
    manifest = loaded_manifest or {
        "content_id": "standalone-sample",
        "account": args.account or IDENTITY_ACCOUNT,
        "title": "standalone visual routing sample",
        "paths": {},
    }
    manifest["account"] = require_account(str(manifest.get("account", args.account or IDENTITY_ACCOUNT)))
    report = build_report(project, manifest, args.text)
    if args.text and not args.project:
        print(json.dumps(report, ensure_ascii=True, indent=2))
        return 0 if report["status"] in {"ready", "ready_for_review", "approved"} else 1
    output, _ = write_project_report(project, manifest, report, args.output)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["status"] in {"ready", "ready_for_review", "approved"} else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Choose deterministic visual routes from an approved video script.")
    root.add_argument("--project")
    root.add_argument("--output")
    root.add_argument("--text", help="Classify one text sample without reading a project.")
    root.add_argument("--account", default=IDENTITY_ACCOUNT)
    root.set_defaults(handler=run)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    if not arguments.project and not arguments.text:
        parser().error("--project is required unless --text is supplied")
    raise SystemExit(arguments.handler(arguments))
