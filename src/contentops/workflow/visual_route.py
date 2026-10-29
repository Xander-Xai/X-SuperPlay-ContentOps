"""Visual route: choose the safest picture for a scene, and say why.

The route is a planning decision, not a generation call. It answers one
question per scene: what kind of picture can carry this sentence *without
lying*? A screenshot must stay a screenshot; a number or a code identifier
cannot be invented by an image model; a generated illustration may decorate an
idea but may never stand in for a result.

The precedence is deliberate: exact evidence first, editable diagrams next,
generated illustration last.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

SCHEMA = "contentops.visual-route/v1"

ROUTES = (
    "formula_derivation",
    "evidence_screen_recording",
    "architecture_diagram",
    "data_chart",
    "infographic_summary",
    "xiaohei_illustration",
    "xiaohei_scene",
    "concept_illustration",
    "designed_card",
)

EVIDENCE_ROUTES = {"evidence_screen_recording"}
GENERATED_ROUTES = {"xiaohei_illustration", "xiaohei_scene",
                    "concept_illustration", "designed_card"}
EDITABLE_ROUTES = {"formula_derivation", "architecture_diagram", "data_chart",
                   "infographic_summary"}

#: Ordered keyword sets. The first match wins, which is the precedence rule.
PATTERNS = (
    ("evidence_screen_recording",
     ("录屏", "终端", "截图", "实测", "运行结果", "官方页面", "仓库", "命令行", "dashboard")),
    ("formula_derivation",
     ("公式", "推导", "证明", "方程", "计算过程", "attention 公式")),
    ("architecture_diagram",
     ("架构", "链路", "调用链", "模块", "依赖", "数据流", "流程图")),
    ("data_chart",
     ("对比", "趋势", "指标", "排行", "百分比", "耗时", "benchmark")),
    ("xiaohei_scene",
     ("共鸣", "处境", "打工人", "真实物件", "长卷", "个人经历", "复盘")),
    ("xiaohei_illustration",
     ("配图", "插图", "比喻", "隐喻", "概念图")),
    ("infographic_summary",
     ("总结", "要点", "清单", "步骤")),
    ("designed_card",
     ("标题卡", "引用卡", "金句", "封面")),
)

#: Tokens that a generated picture must never be asked to reproduce.
EXACT_TOKEN = re.compile(r"(\d|[`]|https?://)")
MAX_CONSECUTIVE_GENERATED = 2


def classify_scene(text: str) -> str:
    lowered = str(text or "").lower()
    for route, keywords in PATTERNS:
        if any(keyword.lower() in lowered for keyword in keywords):
            return route
    return "concept_illustration"


def build_route(scene_id: str, text: str, route: Optional[str] = None) -> Dict[str, Any]:
    chosen = route or classify_scene(text)
    if chosen not in ROUTES:
        raise ValueError(f"unknown route {chosen!r}")
    return {
        "scene_id": scene_id,
        "text": text,
        "route": chosen,
        "evidence": chosen in EVIDENCE_ROUTES,
        "generated": chosen in GENERATED_ROUTES,
        "editable": chosen in EDITABLE_ROUTES,
    }


def validate_route(document: Any) -> List[str]:
    if not isinstance(document, dict):
        return ["visual route must be a JSON object"]
    if document.get("schema") != SCHEMA:
        return [f"visual route schema must be {SCHEMA!r}"]
    scenes = document.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return ["scenes must be a non-empty array"]
    errors: List[str] = []
    seen = set()
    run = 0
    for index, scene in enumerate(scenes):
        where = f"scenes[{index}]"
        if not isinstance(scene, dict):
            errors.append(f"{where} must be an object")
            continue
        scene_id = scene.get("scene_id")
        if not isinstance(scene_id, str) or not scene_id.strip():
            errors.append(f"{where}.scene_id must be a non-empty string")
        elif scene_id in seen:
            errors.append(f"{where}.scene_id duplicates {scene_id!r}")
        else:
            seen.add(scene_id)
        route = scene.get("route")
        if route not in ROUTES:
            errors.append(f"{where}.route must be one of {ROUTES}")
            continue
        text = str(scene.get("text") or "")
        if not text.strip():
            errors.append(f"{where}.text must be a non-empty string")
        generated = bool(scene.get("generated"))
        evidence = bool(scene.get("evidence"))
        if evidence != (route in EVIDENCE_ROUTES):
            errors.append(f"{where}.evidence must be {route in EVIDENCE_ROUTES} for route {route!r}")
        if generated != (route in GENERATED_ROUTES):
            errors.append(f"{where}.generated must be {route in GENERATED_ROUTES} for route {route!r}")
        if generated and EXACT_TOKEN.search(text):
            errors.append(f"{where} asks a generated picture to reproduce an exact token "
                          f"(digit, code identifier or URL); route it to evidence or an "
                          f"editable diagram")
        run = run + 1 if generated else 0
        if run > MAX_CONSECUTIVE_GENERATED:
            errors.append(f"{where} makes {run} consecutive generated scenes "
                          f"(max {MAX_CONSECUTIVE_GENERATED})")
    return errors


def route_scenes(scenes: List[Dict[str, str]]) -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "scenes": [build_route(item["scene_id"], item.get("text", ""), item.get("route"))
                   for item in scenes],
    }
