"""Task Contract, Rule Priority Conflict Engine, and Progressive Context Pack.

Why this module exists
----------------------
Coding agents entering X-SuperPlay-ContentOps previously had to manually guess
which of 30+ docs, 300+ host skills, and 20+ CLI scripts applied to a simple
user instruction such as "make a technical video for FI" or "write a WeChat
article". On hosts with >100 installed skills, Codex strips skill descriptions
due to context-budget overflow, leaving the agent blind to both account DNA and
the fail-closed production gates.

This module turns one natural-language request (or explicit CLI arguments) into:

1. ``contentops.task-contract/v1`` — structured intent, explicit constraints,
   partial-edit scope, fact-preservation lock, and deterministic conflict
   detection across the six-tier priority hierarchy.
2. ``contentops.context-pack/v1`` — minimal-sufficient, progressive context
   scoped to *this* task: active account DNA, exact light/brand visual tokens,
   platform native rules, filtered applicable skills (with exact local paths),
   honest local runtime availability, ordered production commands, and
   machine-checkable L2 instruction-adherence assertions.

What this module does NOT do
----------------------------
It never signs copy review, never authorizes paid spend or publication, never
modifies frozen upstream Easel, and never silently resolves a Tier 1–3 hard
conflict. Conflicts are surfaced explicitly for human resolution.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

CONTRACT_SCHEMA = "contentops.task-contract/v1"
CONTEXT_PACK_SCHEMA = "contentops.context-pack/v1"
ADHERENCE_SCHEMA = "contentops.instruction-adherence/v1"

CONTRACT_FILE = Path("receipts") / "task-contract.json"
CONTEXT_PACK_FILE = Path("receipts") / "context-pack.json"

PRIORITY_TIERS: Sequence[Dict[str, Any]] = (
    {"tier": 1, "id": "IMMUTABLE_BOUNDARY", "overridable": False,
     "scope": "Safety, truth boundary, generated != evidence, rights, no auto-publish, no unauthorized paid spend, frozen Easel v0.3.0 pin"},
    {"tier": 2, "id": "ACCOUNT_HARD_POLICY", "overridable": False,
     "scope": "Account red lines (FI manual_recording=FORBIDDEN; 1024 formal video requires cropped real recording)"},
    {"tier": 3, "id": "PLATFORM_POLICY", "overridable": False,
     "scope": "Platform scope (Xiaohongshu VIDEO-only; Zhihu/CSDN/WeChat GRAPHIC_TEXT native; aspect ratio & duration limits)"},
    {"tier": 4, "id": "OWNER_TASK_EXPLICIT", "overridable": True,
     "scope": "Explicit task overrides within Tiers 1-3: visual style tweak, template choice, partial shot edit scope, fact preservation"},
    {"tier": 5, "id": "ACCOUNT_DEFAULTS", "overridable": True,
     "scope": "Default light palette, narrative template, speech rate, benchmark accounts, voice persona"},
    {"tier": 6, "id": "DEFAULT_SUGGESTION", "overridable": True,
     "scope": "Fallback layout/workflow recommendations"},
)

ACCOUNT_MAP = {
    "fi": "x-superplay-future-intelligence",
    "future-intelligence": "x-superplay-future-intelligence",
    "future_intelligence": "x-superplay-future-intelligence",
    "thinktank": "x-superplay-future-intelligence",
    "未来智能": "x-superplay-future-intelligence",
    "x-superplay-future-intelligence": "x-superplay-future-intelligence",
    "1024": "x-superplay-1024",
    "explorer": "x-superplay-1024",
    "x-superplay-1024": "x-superplay-1024",
    "en": "x-superplay-english",
    "english": "x-superplay-english",
    "x-superplay-english": "x-superplay-english",
}

PLATFORM_ALIASES = {
    "抖音": "douyin",
    "douyin": "douyin",
    "b站": "bilibili",
    "bilibili": "bilibili",
    "视频号": "shipinhao",
    "shipinhao": "shipinhao",
    "小红书": "xiaohongshu_video",
    "xhs": "xiaohongshu_video",
    "xiaohongshu": "xiaohongshu_video",
    "xiaohongshu_video": "xiaohongshu_video",
    "公众号": "wechat_article",
    "微信公众号": "wechat_article",
    "gzh": "wechat_article",
    "wechat": "wechat_article",
    "wechat_article": "wechat_article",
    "知乎": "zhihu",
    "zhihu": "zhihu",
    "csdn": "csdn",
    "x": "x",
    "twitter": "x",
    "youtube": "youtube",
}

VIDEO_PLATFORMS = {"douyin", "bilibili", "xiaohongshu_video", "shipinhao", "youtube"}
GRAPHIC_PLATFORMS = {"wechat_article", "zhihu", "csdn", "x"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_obj(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _detect_account(request: str, explicit: Optional[str]) -> Optional[str]:
    if explicit:
        key = explicit.strip().casefold()
        return ACCOUNT_MAP.get(key, explicit.strip())
    low = request.casefold()
    if any(tok in low for tok in ("未来智能", "x-superplay-future-intelligence", "thinktank")) or re.search(r"\bfi\b", low):
        return "x-superplay-future-intelligence"
    if any(tok in low for tok in ("1024", "x-superplay-1024", "explorer")):
        return "x-superplay-1024"
    if any(tok in low for tok in ("english", "x-superplay-english", "英文账号")):
        return "x-superplay-english"
    return None


def _detect_platforms(request: str, explicit: Sequence[str] = (), *, wants_xhs_graphic: bool = False) -> List[str]:
    found: List[str] = []
    for raw in explicit:
        for part in str(raw).split(","):
            norm = PLATFORM_ALIASES.get(part.strip().casefold(), part.strip().casefold())
            if norm and norm not in found:
                found.append(norm)
    if found:
        return found
    low = request.casefold()
    checks = (
        ("公众号", "wechat_article"),
        ("微信公众号", "wechat_article"),
        ("wechat_article", "wechat_article"),
        ("知乎", "zhihu"),
        ("zhihu", "zhihu"),
        ("csdn", "csdn"),
        ("小红书", "xiaohongshu_video"),
        ("xiaohongshu", "xiaohongshu_video"),
        ("b站", "bilibili"),
        ("bilibili", "bilibili"),
        ("视频号", "shipinhao"),
        ("抖音", "douyin"),
        ("douyin", "douyin"),
        ("youtube", "youtube"),
    )
    for token, plat in checks:
        if plat == "xiaohongshu_video" and wants_xhs_graphic:
            continue  # Never silently convert a Xiaohongshu graphic ask into xiaohongshu_video
        if token in low and plat not in found:
            found.append(plat)
    if re.search(r"(?<![a-z0-9])x(?:\s*平台|\s*短帖|\s*图文|\s*长帖|\s*post|\s*thread)", low):
        if "x" not in found:
            found.append("x")
    return found


def _detect_format(request: str, explicit: Optional[str], platforms: Sequence[str]) -> str:
    if explicit:
        val = explicit.strip().upper()
        if val in ("VIDEO", "GRAPHIC_TEXT", "TOPIC"):
            return val
    low = request.casefold()
    wants_video = any(k in low for k in ("视频", "video", "分镜", "镜头", "口播", "9:16", "16:9", "剪辑", "动效"))
    wants_graphic = any(k in low for k in ("图文", "文章", "长文", "公众号", "知乎", "csdn", "卡片", "封面", "排版", "模板", "graphic", "article"))
    if wants_video and wants_graphic:
        return "TOPIC"
    if wants_graphic and not wants_video:
        return "GRAPHIC_TEXT"
    if wants_video and not wants_graphic:
        return "VIDEO"
    if platforms:
        has_v = any(p in VIDEO_PLATFORMS for p in platforms)
        has_g = any(p in GRAPHIC_PLATFORMS for p in platforms)
        if has_v and has_g:
            return "TOPIC"
        if has_g:
            return "GRAPHIC_TEXT"
        if has_v:
            return "VIDEO"
    return "VIDEO"


def _detect_intent_flags(request: str) -> Dict[str, Any]:
    low = request.casefold()
    wants_xhs_graphic = bool(
        re.search(r"(?:小红书|xiaohongshu|xhs)[^，。,.；;\n]{0,12}(?:图文|卡片|笔记图|graphic|image-text)", low)
        or re.search(r"(?:图文|卡片|笔记图|graphic|image-text)[^，。,.；;\n]{0,12}(?:小红书|xiaohongshu|xhs)", low)
    )
    wants_desktop_recording = any(
        k in low for k in (
            "桌面录屏", "全程录制", "鼠标点击", "鼠标操作", "操作 vs code",
            "操作vscode", "手动录屏", "录屏过程", "整屏录屏",
        )
    )
    wants_ai_as_evidence = (
        any(k in low for k in ("ai 生成", "ai生成", "生成图片", "生成一张", "生成柱状图", "生成截图", "生成图表"))
        and any(
            k in low for k in (
                "作为证据", "作为实测证据", "当成证据", "当成实测证据", "当实测证据", "当证据",
                "作证据", "做实测证据", "做证据", "充当证据", "冒充证据", "证明实测",
            )
        )
        and not any(k in low for k in ("禁止生成图片冒充", "禁止用ai", "不能冒充证据", "不要冒充证据", "禁止ai冒充"))
    )
    forbid_ai_evidence = any(
        k in low for k in ("禁止生成图片冒充", "真实素材", "禁止ai冒充", "禁止伪造", "不得冒充证据")
    )
    preserve_facts = any(
        k in low for k in ("保留原始事实", "只改表达", "不改事实", "保留事实", "不要改事实", "原始事实也不要改动")
    )
    lock_other_shots = any(
        k in low for k in ("其他镜头保持不变", "其他镜头不变", "只改第", "仅修改", "局部修改")
    )
    wants_auto_publish = any(k in low for k in ("自动发布", "直接发布到", "帮我发布上线"))
    wants_fabricated_experience = any(k in low for k in ("假装我用了", "写我用了三天", "编造实测"))

    # Extract explicit shot IDs (e.g. fi03, P-03, S-02, 第3个镜头)
    shot_ids: List[str] = []
    for match in re.findall(r"\b(fi\d{2}|s-\d{2}|p-\d{2}|u\d{2}|shot[-_]?\d{1,2})\b", request, re.I):
        norm = match.lower()
        if norm not in shot_ids:
            shot_ids.append(norm)
    for num in re.findall(r"第\s*(\d{1,2})\s*个?镜头", request):
        tag = f"s{int(num):02d}"
        if tag not in shot_ids:
            shot_ids.append(tag)

    # Extract explicit aspect ratio
    aspect = None
    if "16:9" in low or "横屏" in low or "横版" in low:
        aspect = "16:9"
    elif "9:16" in low or "竖屏" in low or "竖版" in low:
        aspect = "9:16"
    elif "3:4" in low:
        aspect = "3:4"

    # Extract visual style override hint
    style_override = None
    if any(k in request for k in ("暖白", "暖色", "换暖色", "暖色调")):
        style_override = "warm-editorial (#F4F2ED / #FFFFFF)"
    elif "石墨纸" in request:
        style_override = "graphite-paper (#DBE1E2 / #F3F6F5)"
    elif "柔和工程灰" in request:
        style_override = "soft-engineering (#E9EDEF / #F9FBFA)"
    elif "深色" in request or "暗色" in request:
        style_override = "dark-requested"

    # Extract natural-language template hints
    template_hints: List[str] = []
    tmpl_rules = (
        (("技术封面", "封面模板", "tech_cover"), "tech_cover"),
        (("架构图", "原理图", "机制图", "mechanism_architecture"), "mechanism_architecture"),
        (("代码注释", "代码图", "代码卡", "code_annotated"), "code_annotated"),
        (("对比图", "评测对比", "实测对比", "measured_comparison"), "measured_comparison"),
        (("步骤图", "时间线", "流程图", "step_workflow_timeline"), "step_workflow_timeline"),
        (("长文章", "长文模板", "case_teardown_article"), "case_teardown_article"),
    )
    for kws, tid in tmpl_rules:
        if any(k in low for k in kws) and tid not in template_hints:
            template_hints.append(tid)

    return {
        "wants_xhs_graphic": wants_xhs_graphic,
        "wants_desktop_recording": wants_desktop_recording,
        "wants_ai_as_evidence": wants_ai_as_evidence,
        "forbid_ai_evidence": forbid_ai_evidence,
        "preserve_facts": preserve_facts,
        "lock_other_shots": lock_other_shots,
        "edit_scope_shots": shot_ids,
        "wants_auto_publish": wants_auto_publish,
        "wants_fabricated_experience": wants_fabricated_experience,
        "aspect_ratio": aspect,
        "style_override": style_override,
        "template_hints": template_hints,
    }


def _load_account_dna(root: Path, slug: Optional[str]) -> Optional[Dict[str, Any]]:
    if not slug:
        return None
    return _read_json(root / "config" / "accounts" / f"{slug}.json")


def resolve_active_palette(dna: Optional[Dict[str, Any]], style_override: Optional[str] = None) -> Dict[str, Any]:
    """Return the exact visual tokens that renderers and templates MUST consume.

    Root-cause fix (T06): account DNA contains ``brand.palette.base = #0F1117``
    (reserved strictly for intro/outro brand marks) alongside
    ``visual.motion.motion_profile.palette`` (light canvas: ``#E9EDEF`` for FI,
    ``#F4F2ED`` for 1024). Historical templates wrongly read ``brand.palette.base``
    or hardcoded ``#0B0F14`` for body frames. This resolver separates brand mark
    tokens from active scene/card tokens explicitly.
    """
    if not dna:
        return {
            "variant": "soft-engineering-default",
            "scene_bg": "#E9EDEF",
            "surface": "#F9FBFA",
            "ink": "#202B31",
            "sub": "#65747A",
            "accent": "#157F8B",
            "accent2": "#AABDC1",
            "problem": "#BD5149",
            "brand_intro_only_bg": "#0F1117",
            "brand_highlight": "#38BDF8",
            "dark_body_cards_forbidden": True,
        }
    brand_p = (dna.get("brand") or {}).get("palette") or {}
    motion_p = ((dna.get("visual") or {}).get("motion") or {}).get("motion_profile") or {}
    variants = motion_p.get("style_variants") or {}
    rec_variant = str(motion_p.get("recommended_variant") or "default")

    chosen = dict(variants.get(rec_variant) or motion_p.get("palette") or {})
    chosen_variant = rec_variant
    override_applied = False

    if style_override:
        if "warm-editorial" in style_override:
            chosen = {
                "bg": "#F4F2ED", "surface": "#FFFFFF", "ink": "#18232B",
                "sub": "#5C6970", "accent": "#087FA6", "accent2": "#C4DCE3",
            }
            chosen_variant = "warm-editorial (task-override)"
            override_applied = True
        elif "graphite-paper" in style_override and "graphite-paper" in variants:
            chosen = dict(variants["graphite-paper"])
            chosen_variant = "graphite-paper (task-override)"
            override_applied = True

    return {
        "variant": chosen_variant,
        "override_applied": override_applied,
        "scene_bg": chosen.get("bg") or brand_p.get("surface") or "#F9FBFA",
        "surface": chosen.get("surface") or brand_p.get("surface") or "#FFFFFF",
        "ink": chosen.get("ink") or brand_p.get("ink") or "#202B31",
        "sub": chosen.get("sub") or brand_p.get("muted") or "#65747A",
        "accent": chosen.get("accent") or "#157F8B",
        "accent2": chosen.get("accent2") or "#AABDC1",
        "problem": brand_p.get("problem") or "#BD5149",
        "brand_intro_only_bg": brand_p.get("base") or "#0F1117",
        "brand_highlight": brand_p.get("accent") or "#38BDF8",
        "code_theme": brand_p.get("code_theme") or "github-light",
        "dark_body_cards_forbidden": True,
        "rule": (
            "Body scenes, cards, and infographics MUST use light scene_bg/surface tokens. "
            "brand_intro_only_bg (#0F1117) is restricted strictly to intro/outro brand marks "
            "and never copied onto every body frame."
        ),
    }


def evaluate_conflicts(
    *,
    account_slug: Optional[str],
    dna: Optional[Dict[str, Any]],
    platforms: Sequence[str],
    content_format: str,
    flags: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Detect conflicts against Tiers 1-3 and classify allowed Tier 4 overrides."""
    conflicts: List[Dict[str, Any]] = []

    if flags.get("wants_ai_as_evidence"):
        conflicts.append({
            "severity": "HARD_BLOCK",
            "tier": 1,
            "code": "GENERATED_AS_EVIDENCE_FORBIDDEN",
            "rule": "AGENTS.md §1.2-3 & QUALITY-STANDARD: Generated visuals are support only and may NEVER serve as factual/test evidence.",
            "requested": "AI-generated chart/image as measured evidence",
            "resolution": "REFUSE using AI image as evidence. Replace with real measured data/chart rendered deterministically from verified numbers, or mark the claim unsupported.",
        })

    if flags.get("wants_auto_publish"):
        conflicts.append({
            "severity": "HARD_BLOCK",
            "tier": 1,
            "code": "AUTO_PUBLISH_FORBIDDEN",
            "rule": "ADR-005 & README: ContentOps produces reviewable packages/drafts only; auto-publish is out of scope.",
            "requested": "automatic publication",
            "resolution": "STOP at offline package / draft-only handoff with publish_authorized=false.",
        })

    if flags.get("wants_fabricated_experience"):
        conflicts.append({
            "severity": "HARD_BLOCK",
            "tier": 1,
            "code": "FABRICATED_EXPERIENCE_FORBIDDEN",
            "rule": "AGENTS.md §3 Content Truth Boundary: First-person test claims require real session/artifact evidence.",
            "requested": "unverified first-person test claim",
            "resolution": "REFUSE first-person fabrication; attribute facts strictly to verified sources or run a real test first.",
        })

    manual_policy = str(((dna or {}).get("evidence") or {}).get("manual_recording") or "")
    if manual_policy == "FORBIDDEN" and flags.get("wants_desktop_recording"):
        conflicts.append({
            "severity": "HARD_BLOCK",
            "tier": 2,
            "code": "ACCOUNT_RECORDING_FORBIDDEN",
            "rule": f"Account {account_slug} declares evidence.manual_recording=FORBIDDEN (no desktop recording, no mouse clicks, no full-screen IDE).",
            "requested": "desktop screen recording",
            "resolution": (
                "REFUSE desktop recording on Future Intelligence. Either (A) keep FI and replace with "
                "vector architecture animation + cropped static key-line code excerpts (zero cursor/IDE chrome), "
                "or (B) switch account to x-superplay-1024 (ALLOWED_CROPPED, cropped terminal/log output only)."
            ),
        })

    if flags.get("wants_xhs_graphic"):
        conflicts.append({
            "severity": "HARD_BLOCK",
            "tier": 3,
            "code": "PLATFORM_XHS_VIDEO_ONLY",
            "rule": "AGENTS.md Xiaohongshu Workflow Boundary: Xiaohongshu is VIDEO-only (xiaohongshu_video) in ContentOps; graphic/image-text route is unsupported.",
            "requested": "Xiaohongshu graphic/image-text note",
            "resolution": "Explicitly state Xiaohongshu graphic is unsupported; do NOT silently convert it to video without user confirmation.",
        })

    if flags.get("style_override") == "dark-requested":
        conflicts.append({
            "severity": "WARN_NEEDS_CONFIRMATION",
            "tier": 4,
            "code": "DARK_STYLE_VS_ACCOUNT_LIGHT_DNA",
            "rule": "Both FI and 1024 DNAs prohibit copying dark #0F1117 backgrounds onto body frames.",
            "requested": "dark visual style",
            "resolution": "Confirm explicitly whether the user intends a one-off task override on specific frames only, or keep the account light palette.",
        })
    elif flags.get("style_override") and account_slug == "x-superplay-future-intelligence" and "warm-editorial" in str(flags.get("style_override")):
        conflicts.append({
            "severity": "ALLOWED_OVERRIDE",
            "tier": 4,
            "code": "PARTIAL_PALETTE_OVERRIDE_ALLOWED",
            "rule": "Tier 4 task-specific palette override may override Tier 5 default soft-engineering palette on the explicitly scoped shot(s) while respecting Tiers 1-3.",
            "requested": str(flags.get("style_override")),
            "resolution": "Apply warm-editorial palette ONLY to the scoped shot(s); keep all other shots unchanged.",
        })

    return conflicts


def build_task_contract(
    request: str,
    *,
    root: Path,
    project: Optional[Path] = None,
    account: Optional[str] = None,
    platforms: Sequence[str] = (),
    content_format: Optional[str] = None,
    topic: Optional[str] = None,
    template_id: Optional[str] = None,
    edit_scope: Sequence[str] = (),
    preserve_facts: Optional[bool] = None,
    style_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Compile a user request + optional flags into a verifiable Task Contract."""
    root = Path(root).resolve()
    flags = _detect_intent_flags(request)
    account_slug = _detect_account(request, account)
    dna = _load_account_dna(root, account_slug)
    resolved_platforms = _detect_platforms(request, platforms, wants_xhs_graphic=flags["wants_xhs_graphic"])
    if not resolved_platforms and dna:
        default_plats = list(dna.get("platforms") or [])
        if default_plats:
            resolved_platforms = [PLATFORM_ALIASES.get(p.casefold(), p) for p in default_plats[:2]]
    resolved_format = _detect_format(request, content_format, resolved_platforms)
    if resolved_format == "GRAPHIC_TEXT" and not resolved_platforms:
        resolved_platforms = ["wechat_article"]

    merged_edit_scope = list(dict.fromkeys([*edit_scope, *flags["edit_scope_shots"]]))
    effective_preserve_facts = flags["preserve_facts"] if preserve_facts is None else bool(preserve_facts)
    effective_style = style_override or flags["style_override"]

    conflicts = evaluate_conflicts(
        account_slug=account_slug,
        dna=dna,
        platforms=resolved_platforms,
        content_format=resolved_format,
        flags={**flags, "style_override": effective_style},
    )
    palette = resolve_active_palette(dna, style_override=effective_style)

    missing_required: List[str] = []
    if not account_slug:
        missing_required.append("account (choose x-superplay-future-intelligence or x-superplay-1024)")
    if not (topic or request.strip()):
        missing_required.append("topic")

    hard_blocks = [c for c in conflicts if c["severity"] == "HARD_BLOCK"]
    status = "CONFLICT_BLOCKED" if hard_blocks else ("NEEDS_CLARIFICATION" if missing_required else "READY_FOR_WORKFLOW")

    assertions: List[Dict[str, Any]] = [
        {"id": "A1_ACCOUNT_BOUND", "rule": f"Target account must be {account_slug or 'SPECIFIED'}", "required": True},
        {"id": "A2_ENTRY_POINT", "rule": "Production must go through scripts/make_content.py (never bypass gates via bare run_v1.py/m5_production.py)", "required": True},
        {"id": "A3_LIGHT_PALETTE", "rule": f"Body visuals use light palette bg={palette['scene_bg']} surface={palette['surface']} accent={palette['accent']}", "required": True},
        {"id": "A4_NO_FAKE_EVIDENCE", "rule": "Generated images/motion are visual support only (evidence_capable=false)", "required": True},
        {"id": "A5_HUMAN_GATE_HONEST", "rule": "Receipts keep production_ready=false and publish_authorized=false until named human review", "required": True},
    ]
    if account_slug == "x-superplay-future-intelligence":
        assertions.append({"id": "A6_FI_ZERO_RECORDING", "rule": "Zero manual desktop recording or mouse cursor frames", "required": True})
    elif account_slug == "x-superplay-1024" and resolved_format in ("VIDEO", "TOPIC"):
        assertions.append({"id": "A6_1024_REAL_EVIDENCE", "rule": "Formal video requires cropped real terminal/UI recording or real captured evidence; state failure/cost/limits honestly", "required": True})
    if merged_edit_scope or flags["lock_other_shots"]:
        assertions.append({
            "id": "A7_PARTIAL_EDIT_LOCK",
            "rule": f"Modify ONLY scoped shots {merged_edit_scope or ['explicitly-named']}; all other shots remain untouched",
            "edit_scope": merged_edit_scope,
            "required": True,
        })
    if effective_preserve_facts:
        assertions.append({
            "id": "A8_PRESERVE_FACTS",
            "rule": "Preserve all existing claim texts/evidence bindings verbatim; edit expression/hooks only where non-claim or re-verify claims",
            "required": True,
        })
    merged_templates = list(dict.fromkeys(([template_id] if template_id else []) + list(flags.get("template_hints") or [])))
    if merged_templates:
        assertions.append({
            "id": "A9_TEMPLATE_LOCK",
            "rule": f"Use requested graphic template(s): {', '.join(merged_templates)}",
            "template_ids": merged_templates,
            "required": True,
        })

    contract: Dict[str, Any] = {
        "schema": CONTRACT_SCHEMA,
        "created_at": _now(),
        "status": status,
        "raw_request": request.strip(),
        "project": project.name if project else None,
        "topic": (topic or request.strip())[:160],
        "account_slug": account_slug,
        "account_name": (dna or {}).get("account"),
        "content_format": resolved_format,
        "platforms": resolved_platforms,
        "aspect_ratio": flags["aspect_ratio"] or ("9:16" if resolved_format == "VIDEO" else "platform-native"),
        "template_id": merged_templates[0] if merged_templates else None,
        "template_ids": merged_templates,
        "constraints": {
            "edit_scope": merged_edit_scope,
            "lock_other_shots": bool(flags["lock_other_shots"] or merged_edit_scope),
            "preserve_facts": effective_preserve_facts,
            "forbid_ai_evidence": True,
            "style_override": effective_style,
            "manual_recording_policy": ((dna or {}).get("evidence") or {}).get("manual_recording"),
        },
        "palette": palette,
        "conflicts": conflicts,
        "missing_required": missing_required,
        "priority_tiers": list(PRIORITY_TIERS),
        "assertions": assertions,
        "production_ready": False,
        "publish_authorized": False,
    }
    contract["contract_sha256"] = _sha256_obj({k: v for k, v in contract.items() if k != "created_at"})
    return contract


def _probe_local_capabilities(root: Path) -> Dict[str, Any]:
    """Check what local, non-paid runtimes exist without modifying anything."""
    import shutil

    huashu_candidates = [
        root / ".runtime" / "huashu-motion" / "cli" / "om.js",
        root.parent / ".runtime" / "huashu-motion" / "cli" / "om.js",
        Path("D:/Projects/X-SuperPlay-ContentOps/.runtime/huashu-motion/cli/om.js"),
    ]
    huashu_cli = next((p for p in huashu_candidates if p.is_file()), None)
    easel_v030 = (root / ".runtime" / "easel-v030").is_dir() or Path("D:/Projects/X-SuperPlay-ContentOps/.runtime/easel-v030").is_dir()
    return {
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "node": bool(shutil.which("node")),
        "huashu_motion_om_cli": str(huashu_cli) if huashu_cli else None,
        "huashu_formal_render_hint": "node <om.js> render <film> --fps 24 --workers 1 --silent" if huashu_cli else None,
        "easel_v030_present": easel_v030,
        "paid_providers_authorized": False,
    }


def _select_progressive_skills(root: Path, content_format: str, account_slug: Optional[str]) -> List[Dict[str, Any]]:
    """Return ONLY the 3-6 skills directly relevant to this task (progressive disclosure)."""
    registry = _read_json(root / "runtime" / "skill-registry.json") or {}
    declared = {row["id"]: row for row in registry.get("skills") or [] if isinstance(row, dict) and row.get("id")}
    shared_root = Path.home() / ".agents" / "skills"

    selected: List[Dict[str, Any]] = []

    def add_skill(skill_id: str, stage: str, why: str, *, local_path: Optional[Path] = None, kind: str = "ADVISORY_SKILL") -> None:
        reg = declared.get(skill_id)
        path = local_path
        if path is None:
            if reg and reg.get("discovery", {}).get("root") == "repo":
                path = root / reg["discovery"]["dir"] / "SKILL.md"
            elif (root / "skills" / skill_id / "SKILL.md").is_file():
                path = root / "skills" / skill_id / "SKILL.md"
            elif (shared_root / skill_id / "SKILL.md").is_file():
                path = shared_root / skill_id / "SKILL.md"
        selected.append({
            "id": skill_id,
            "stage": stage,
            "status": "DECLARED_CAPABILITY" if reg else kind,
            "installed": bool(path and path.is_file()),
            "path": str(path) if path and path.is_file() else None,
            "canonical_code": reg.get("canonical_path") if reg else None,
            "why": why,
        })

    add_skill("contentops-production-gates", "gates", "Fail-closed VIDEO / GRAPHIC_TEXT preflight gates")

    if content_format in ("VIDEO", "TOPIC"):
        add_skill("x-superplay-copy-orchestrator", "copy", "Single canonical topic copy + audience/evidence dual spine (advisory; validate via repo gates)")
        add_skill("shuorenhua", "polish", "Remove Chinese AI tropes while preserving facts and technical register")
        add_skill("x-superplay-huashu-motion", "motion", "Account-DNA local non-paid Huashu Art Motion renderer")
        add_skill("x-superplay-design-direction", "visual", "One coherent visual direction + anti-fatigue guard (advisory)")
        if account_slug == "x-superplay-1024":
            add_skill("x-superplay-capture-plan", "capture", "Cropped real screen recording brief for 1024 evidence beats")
            add_skill("x-superplay-broll-production", "assets", "Evidence-first B-roll & real capture plan before acquisition")
    if content_format in ("GRAPHIC_TEXT", "TOPIC"):
        add_skill("x-superplay-copy-orchestrator", "copy", "Unified evidence-bound copy before platform-native rewrite")
        add_skill("x-superplay-design-direction", "visual", "Non-template editorial hierarchy & token consistency")
        add_skill("shuorenhua", "polish", "Remove Chinese AI tropes while preserving facts and technical register")

    # Deduplicate by id preserving order
    seen = set()
    deduped = []
    for item in selected:
        if item["id"] not in seen:
            seen.add(item["id"])
            deduped.append(item)
    return deduped


def build_context_pack(contract: Dict[str, Any], *, root: Path, project: Optional[Path] = None) -> Dict[str, Any]:
    """Build the minimal-sufficient progressive Context Pack for one task."""
    root = Path(root).resolve()
    slug = contract.get("account_slug")
    dna = _load_account_dna(root, slug)
    fmt = contract["content_format"]
    proj_arg = f"projects/{project.name}" if project else "projects/<slug>"

    account_summary: Dict[str, Any] = {}
    if dna:
        narrative = dna.get("narrative") or {}
        evidence = dna.get("evidence") or {}
        account_summary = {
            "slug": slug,
            "name": dna.get("account"),
            "role": dna.get("role"),
            "promise": dna.get("promise"),
            "decision_question": dna.get("decision_question"),
            "core_audience": dna.get("core_audience") or dna.get("audience") or [],
            "excluded_audience": dna.get("excluded") or [],
            "prompt_file": dna.get("prompt"),
            "narrative_template": narrative.get("template") or [],
            "target_duration_s": narrative.get("target_duration_s"),
            "speech_rate_cpm": narrative.get("speech_rate_cpm"),
            "evidence_mode": evidence.get("mode"),
            "manual_recording": evidence.get("manual_recording"),
            "forbidden_effects": (dna.get("brand") or {}).get("forbidden_effects") or [],
            "qc_rules": dna.get("qc_rules") or [],
            "benchmarks": [b.get("account") for b in ((dna.get("benchmarks") or {}).get("priority") or [])],
        }

    workflow_steps: List[Dict[str, str]] = []
    if contract["status"] == "CONFLICT_BLOCKED":
        workflow_steps.append({
            "step": "0_resolve_conflicts",
            "action": "STOP and report HARD_BLOCK conflicts to the Owner before creating or modifying deliverables.",
        })
    else:
        if fmt in ("VIDEO", "TOPIC"):
            aspect_note = (
                "Render separate native 9:16 (Douyin/XHS) and native 16:9 (Bilibili) cuts"
                if "bilibili" in contract["platforms"] and any(p in contract["platforms"] for p in ("douyin", "xiaohongshu_video", "shipinhao"))
                else f"Target aspect {contract['aspect_ratio']}"
            )
            workflow_steps.extend([
                {"step": "1_research_value", "command": f"python scripts/preresearch.py check --project {proj_arg}",
                 "purpose": "Verify real sources, information delta, and signed pre-copy research receipt before copy."},
                {"step": "2_copy_and_polish", "command": f"python scripts/copy_quality.py {proj_arg}/script/script.json --format video",
                 "purpose": "Draft natural spoken Chinese copy (zero AI filler, concrete numbers/boundaries), run copy_quality + editorial check, then obtain copy_review.py --approve."},
                {"step": "3_director_plan", "command": f"python scripts/direct_video.py compile --spec {proj_arg}/director-spec.json --out-dir {proj_arg}/motion/film",
                 "purpose": f"Compile multi-role Director Plan into account-DNA light-palette Huashu Motion scenes ({aspect_note})."},
                {"step": "4_formal_render", "command": f"python scripts/render_film.py --film {proj_arg}/motion/film --out {proj_arg}/final/candidate.mp4 --mode formal --workers 1",
                 "purpose": "Run om check -> om render --workers 1 for continuous video (never substitute --mode animatic preview as final video)."},
                {"step": "5_gates_and_qc", "command": f"python scripts/make_content.py check --project {proj_arg} && python scripts/qc_video.py {proj_arg}",
                 "purpose": "Verify production gates + technical/visual QC + instruction adherence; keep production_ready=false for Owner review."},
            ])
        if fmt in ("GRAPHIC_TEXT", "TOPIC"):
            workflow_steps.extend([
                {"step": "G1_draft_and_value", "command": f"python scripts/copy_quality.py {proj_arg}/02_draft/draft.md --format article",
                 "purpose": "Write native long-form article or graphic copy with concrete findings, trade-offs, and source citations (no video script copy-paste)."},
                {"step": "G2_graphic_templates", "command": f"python scripts/render_graphic_templates.py render --account {slug or 'x-superplay-future-intelligence'} --input {proj_arg}/graphic-spec.json --out-dir {proj_arg}/assets/cards",
                 "purpose": "Render account-DNA light-palette PNG cards/covers + native WeChat GZH HTML / Zhihu / CSDN markdown."},
                {"step": "G3_package_and_validate", "command": f"python scripts/make_content.py check --project {proj_arg} && python scripts/render_article.py {proj_arg}",
                 "purpose": "Build offline graphic package & validate GZH HTML; keep production_ready=false & publish_authorized=false."},
            ])

    pack = {
        "schema": CONTEXT_PACK_SCHEMA,
        "generated_at": _now(),
        "contract_sha256": contract["contract_sha256"],
        "status": contract["status"],
        "progressive_disclosure": {
            "tier1_loaded": ["AGENTS.md", "task-contract", "priority-tiers"],
            "tier2_loaded": [f"config/accounts/{slug}.json"] if slug else [],
            "tier3_on_demand": [
                "config/design/design-tokens.json",
                "config/style/editorial-style-guide.json",
                "docs/QUALITY-STANDARD.md",
            ],
        },
        "task_contract": contract,
        "account_dna": account_summary,
        "active_visual_tokens": contract["palette"],
        "applicable_skills": _select_progressive_skills(root, fmt, slug),
        "local_runtimes": _probe_local_capabilities(root),
        "workflow_steps": workflow_steps,
        "production_ready": False,
        "publish_authorized": False,
    }
    return pack


def verify_instruction_adherence(
    contract: Dict[str, Any],
    *,
    actual_account: Optional[str] = None,
    used_entry_point: Optional[str] = None,
    rendered_bg_colors: Sequence[str] = (),
    changed_shots: Sequence[str] = (),
    modified_claims: Sequence[str] = (),
    generated_used_as_evidence: bool = False,
    manual_recording_present: bool = False,
    hard_conflicts_refused: bool = True,
) -> Dict[str, Any]:
    """Deterministic L2 verification of agent execution against the Task Contract."""
    checks: List[Dict[str, Any]] = []

    hard_blocks = [c for c in (contract.get("conflicts") or []) if c.get("severity") == "HARD_BLOCK"]
    if hard_blocks:
        checks.append({
            "id": "CONFLICT_HANDLING",
            "ok": bool(hard_conflicts_refused),
            "detail": f"{len(hard_blocks)} hard conflict(s) detected; refused={hard_conflicts_refused}",
        })

    expected_acc = contract.get("account_slug")
    if expected_acc:
        ok = (actual_account == expected_acc) if actual_account else False
        checks.append({"id": "ACCOUNT_MATCH", "ok": ok,
                       "detail": f"expected={expected_acc}, actual={actual_account}"})

    if used_entry_point is not None:
        ok = "make_content" in used_entry_point or "direct_video" in used_entry_point or "render_graphic_templates" in used_entry_point
        checks.append({"id": "PRODUCTION_ENTRY", "ok": ok,
                       "detail": f"entry={used_entry_point}"})

    checks.append({
        "id": "NO_GENERATED_AS_EVIDENCE",
        "ok": not generated_used_as_evidence,
        "detail": "generated assets kept support-only" if not generated_used_as_evidence else "VIOLATION: generated asset used as evidence",
    })

    if expected_acc == "x-superplay-future-intelligence":
        checks.append({
            "id": "FI_NO_MANUAL_RECORDING",
            "ok": not manual_recording_present,
            "detail": "zero manual recordings" if not manual_recording_present else "VIOLATION: manual recording present on FI",
        })

    if rendered_bg_colors and (contract.get("palette") or {}).get("dark_body_cards_forbidden"):
        dark_bgs = [c for c in rendered_bg_colors if c.strip().upper() in ("#000000", "#0B0F14", "#0F1117", "#111111")]
        checks.append({
            "id": "LIGHT_PALETTE_COMPLIANCE",
            "ok": not dark_bgs,
            "detail": "all body backgrounds use light DNA tokens" if not dark_bgs else f"VIOLATION: dark body background(s) {dark_bgs}",
        })

    constraints = contract.get("constraints") or {}
    if constraints.get("lock_other_shots") and constraints.get("edit_scope"):
        allowed = {s.casefold() for s in constraints["edit_scope"]}
        stray = [s for s in changed_shots if s.casefold() not in allowed]
        checks.append({
            "id": "PARTIAL_EDIT_SCOPE",
            "ok": not stray,
            "detail": "only scoped shots changed" if not stray else f"VIOLATION: modified out-of-scope shot(s) {stray}",
        })

    if constraints.get("preserve_facts"):
        checks.append({
            "id": "PRESERVE_FACTS",
            "ok": not modified_claims,
            "detail": "verified claims preserved" if not modified_claims else f"VIOLATION: altered factual claim(s) {list(modified_claims)}",
        })

    passed = all(c["ok"] for c in checks)
    return {
        "schema": ADHERENCE_SCHEMA,
        "contract_sha256": contract.get("contract_sha256"),
        "passed": passed,
        "checks": checks,
        "production_ready": False,
        "publish_authorized": False,
    }


def write_contract_and_pack(project: Path, contract: Dict[str, Any], pack: Dict[str, Any]) -> Dict[str, Path]:
    """Persist receipts/task-contract.json and receipts/context-pack.json inside project."""
    project = Path(project).resolve()
    c_path = project / CONTRACT_FILE
    p_path = project / CONTEXT_PACK_FILE
    c_path.parent.mkdir(parents=True, exist_ok=True)
    c_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    p_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"contract": c_path, "context_pack": p_path}
