#!/usr/bin/env python3
"""Semantic article-section to visual backend routing."""

from __future__ import annotations

import re
import argparse
import json
from pathlib import Path
from typing import Any

from visual_backend_registry import route_backend


RULES = (
    {
        "id": "R18-comparison",
        "when": lambda h, b, f: False,
        "visual_type": "comparison",
        "content_signal": "comparison",
        "render_backend": "deterministic-infographic",
        "fallback": "deterministic-infographic",
        "recommended_skill": "deterministic SVG / typed-comparison-contract",
        "layout_archetype": "comparison-board",
        "secondary_backend": "deterministic-svg",
        "secondary_skill": "deterministic-svg",
        "reason": "工程选型需要保留两侧条件与边界，避免把不同规模方案混成单一结论",
    },
    {
        "id": "R20-decision-matrix",
        "when": lambda h, b, f: (
            f["decision_matrix_signal"]
            and not f["checklist_signal"]
            and not f["checkpoint_signal"]
            and not f["runtime_boundary_signal"]
        ),
        "visual_type": "checklist",
        "content_signal": "comparison",
        "render_backend": "deterministic-infographic",
        "fallback": "deterministic-svg",
        "recommended_skill": "deterministic infographic / typed-decision-contract",
        "layout_archetype": "decision-matrix",
        "secondary_backend": "deterministic-svg",
        "secondary_skill": "deterministic-svg",
        "reason": "存在多后端/适用条件时使用决策矩阵，保留条件与风险，不输出无数据装饰图",
    },
    {
        "id": "R01-checklist",
        "when": lambda h, b, f: (
            f["checklist_signal"]
            and not f["stateful_signal"]
            and not f["checkpoint_signal"]
            and not f["runtime_boundary_signal"]
            and not f["decision_matrix_signal"]
        ),
        "visual_type": "checklist",
        "content_signal": "checklist",
        "render_backend": "deterministic-infographic",
        "fallback": "deterministic-checklist",
        "recommended_skill": "baoyu-infographic / html-infographic",
        "layout_archetype": "progressive-checklist",
        "secondary_backend": "excalidraw",
        "secondary_skill": "excalidraw-diagram",
        "reason": "验收/清单任务需要分组与进度感，而不是公式卡片",
    },
    {
        "id": "R17-stateful-graph",
        "when": lambda h, b, f: (
            f["stateful_signal"]
            and f["relationship_signal"]
            and not f["checkpoint_signal"]
            and not f["runtime_boundary_signal"]
        ),
        "visual_type": "architecture",
        "content_signal": "state",
        "render_backend": "deterministic-svg",
        "fallback": "deterministic-svg",
        "recommended_skill": "deterministic SVG / typed-state-contract",
        "layout_archetype": "stateful-graph",
        "secondary_backend": "beautiful-mermaid",
        "secondary_skill": "beautiful-mermaid",
        "reason": "StateGraph/Reducer/conditional edge 等机制必须显式表达读写、合并和分支，禁止退化为线性标签图",
    },
    {
        "id": "R18-checkpoint-timeline",
        "when": lambda h, b, f: f["checkpoint_signal"] and f["timeline_signal"],
        "visual_type": "architecture",
        "content_signal": "timeline",
        "render_backend": "deterministic-svg",
        "fallback": "deterministic-svg",
        "recommended_skill": "deterministic SVG / checkpoint-timeline-contract",
        "layout_archetype": "checkpoint-timeline",
        "secondary_backend": "beautiful-mermaid",
        "secondary_skill": "beautiful-mermaid",
        "reason": "checkpoint/thread_id/interrupt 是生命周期时序，必须画保存、暂停和恢复，不得用代码卡替代",
    },
    {
        "id": "R19-runtime-boundary",
        "when": lambda h, b, f: (
            f["runtime_boundary_signal"]
            and (f["relationship_signal"] or f["stateful_signal"])
        ),
        "visual_type": "architecture",
        "content_signal": "relationship",
        "render_backend": "deterministic-svg",
        "fallback": "deterministic-svg",
        "recommended_skill": "deterministic SVG / runtime-boundary-contract",
        "layout_archetype": "runtime-boundary",
        "secondary_backend": "beautiful-mermaid",
        "secondary_skill": "beautiful-mermaid",
        "reason": "API、运行时、存储和并发边界需要带端口的系统边界图",
    },
    {
        # Enhancement #4 / RC7: 同节同时出现公式与可运行代码 -> 生成公式↔代码对照卡。
        # 这是「理论+实战」最强的单张图，优于单独的公式图或代码图。
        "id": "R14-formula-code-map",
        "when": lambda h, b, f: f["formula_count"] >= 1 and f["strong_code_signal"],
        "visual_type": "formula-code-map",
        "content_signal": "formula-code-map",
        "render_backend": "formula-code-map",
        "fallback": "katex-html-composite",
        "recommended_skill": "render_formula_code_map.mjs (KaTeX + code side-by-side)",
        "layout_archetype": "formula-code-duality",
        "secondary_backend": "code-block",
        "secondary_skill": "render_code_block.py",
        "reason": "同节既有公式又有代码时，逐行对照是最佳表达",
    },
    {
        # RC7:作者显式给出代码块 / 标题点名要代码时，代码卡片就是本节的主视觉。
        # 放在 R02~R08 之前,否则「Attention 的代码实现」会被公式流程图抢走。
        "id": "R11-code-implementation",
        "when": lambda h, b, f: f["strong_code_signal"],
        "visual_type": "code",
        "content_signal": "code",
        "render_backend": "code-block",
        "fallback": "deterministic-svg",
        "recommended_skill": "deterministic code-block (HTML/SVG, account-themed)",
        "layout_archetype": "runnable-snippet",
        "secondary_backend": "beautiful-mermaid",
        "secondary_skill": "beautiful-mermaid",
        "reason": "强公式/架构/关系内容应给出可运行代码实现，而非仅插图",
    },
    {
        # RC7:复杂机制且篇幅讲不清 → 用伪代码卡片压缩逻辑步骤。
        "id": "R12-pseudocode",
        "when": lambda h, b, f: f["strong_pseudocode_signal"] and not f["strong_code_signal"],
        "visual_type": "pseudocode",
        "content_signal": "pseudocode",
        "render_backend": "code-block",
        "fallback": "deterministic-svg",
        "recommended_skill": "deterministic code-block (HTML/SVG, account-themed)",
        "layout_archetype": "pseudocode-card",
        "secondary_backend": "beautiful-mermaid",
        "secondary_skill": "beautiful-mermaid",
        "reason": "复杂、短篇幅讲不清的机制用伪代码表达逻辑步骤",
    },
    {
        # Enhancement #5: 一个视觉位承载多张信息卡（Q/K/V、步骤组、对比组）。
        "id": "R15-card-deck",
        "when": lambda h, b, f: f["card_deck_signal"],
        "visual_type": "card-deck",
        "content_signal": "card-deck",
        "render_backend": "interactive-card-deck",
        "fallback": "deterministic-svg",
        "recommended_skill": "render_interactive_card_deck.py (SVG deck + static HTML fallback)",
        "layout_archetype": "stacked-card-deck",
        "secondary_backend": "deterministic-infographic",
        "secondary_skill": "html-infographic",
        "reason": "多要点并列展示时，卡组比长段落或单张大图更节省视觉位",
    },
    {
        # Enhancement #6: 用户明确要求手绘/草图风格时，用 sketchy SVG 渲染。
        "id": "R16-excalidraw-style",
        "when": lambda h, b, f: f["excalidraw_signal"],
        "visual_type": "excalidraw-style",
        "content_signal": "relationship",
        "render_backend": "excalidraw-style",
        "fallback": "deterministic-svg",
        "recommended_skill": "render_excalidraw_style.py (hand-drawn SVG)",
        "layout_archetype": "sketch-relationship-map",
        "secondary_backend": "beautiful-mermaid",
        "secondary_skill": "beautiful-mermaid",
        "reason": "手绘草图风格更贴合教程/探索氛围",
    },
    {
        "id": "R02-kv-cache-timeline",
        "when": lambda h, b, f: f["kv_cache_signal"] and f["timeline_signal"],
        "visual_type": "kv-cache",
        "content_signal": "timeline",
        "render_backend": "deterministic-svg",
        "fallback": "deterministic-svg",
        "recommended_skill": "deterministic SVG / tldraw whiteboard",
        "layout_archetype": "two-lane-timeline",
        "secondary_backend": "excalidraw",
        "secondary_skill": "tldraw-skill / excalidraw-diagram",
        "reason": "Prefill→Cache→Decode 是状态变化，必须用时序/泳道表达",
    },
    {
        "id": "R03-multihead-branch",
        "when": lambda h, b, f: f["multihead_signal"] and f["relationship_signal"] and not f["shape_heading"] and not f["attention_heading"],
        "visual_type": "multihead",
        "content_signal": "relationship",
        "render_backend": "beautiful-mermaid",
        "fallback": "deterministic-svg",
        "recommended_skill": "beautiful-mermaid",
        "layout_archetype": "branch-and-merge",
        "secondary_backend": "excalidraw",
        "secondary_skill": "excalidraw-diagram",
        "reason": "Self/Cross 来源与多头汇合是分支关系，不是线性步骤",
    },
    {
        "id": "R04-numeric-proof",
        "when": lambda h, b, f: f["numeric_signal"] and f["matrix_signal"] and f["formula_count"] >= 2 and (f["numeric_heading"] or not (f["shape_heading"] or f["attention_heading"] or f["qkv_heading"])),
        "visual_type": "numeric",
        "content_signal": "math",
        "render_backend": "katex-html-composite",
        "fallback": "deterministic-infographic",
        "recommended_skill": "KaTeX composite + HTML infographic",
        "layout_archetype": "matrix-to-heatmap",
        "secondary_backend": "deterministic-infographic",
        "secondary_skill": "baoyu-infographic / html-infographic",
        "reason": "精确矩阵与数值必须确定性渲染，同时用热力图表达权重变化",
    },
    {
        "id": "R05-shape-contract",
        "when": lambda h, b, f: f["shape_signal"] and f["formula_count"] >= 1 and f["shape_heading"],
        "visual_type": "shape",
        "content_signal": "math",
        "render_backend": "katex-html-composite",
        "fallback": "deterministic-math-html",
        "recommended_skill": "KaTeX composite",
        "layout_archetype": "tensor-shape-pipeline",
        "secondary_backend": "beautiful-mermaid",
        "secondary_skill": "beautiful-mermaid",
        "reason": "Shape 是可核验合同，公式优先；关系复杂时补投影流向图",
    },
    {
        "id": "R06-attention-pipeline",
        "when": lambda h, b, f: f["attention_signal"] and not f["shape_heading"] and not f["qkv_heading"],
        "visual_type": "attention",
        "content_signal": "math",
        "render_backend": "katex-html-composite",
        "fallback": "deterministic-svg",
        "recommended_skill": "KaTeX composite + beautiful-mermaid sequence",
        "layout_archetype": "five-stage-pipeline",
        "secondary_backend": "beautiful-mermaid",
        "secondary_skill": "beautiful-mermaid",
        "reason": "Attention 同时有精确公式与五步流程，采用公式主图+流程辅图",
    },
    {
        "id": "R07-qkv-metaphor",
        "when": lambda h, b, f: f["qkv_signal"] and f["qkv_heading"],
        "visual_type": "qkv",
        "content_signal": "math",
        "render_backend": "katex-html-composite",
        "fallback": "deterministic-svg",
        "recommended_skill": "KaTeX composite + Excalidraw whiteboard",
        "layout_archetype": "library-retrieval-map",
        "secondary_backend": "excalidraw",
        "secondary_skill": "excalidraw-diagram",
        "reason": "Q/K/V 既有精确投影，也有图书馆检索隐喻，不能只画同质卡片",
    },
    {
        "id": "R08-relationship",
        "when": lambda h, b, f: f["relationship_signal"],
        "visual_type": "architecture",
        "content_signal": "relationship",
        "render_backend": "beautiful-mermaid",
        "fallback": "deterministic-svg",
        "recommended_skill": "beautiful-mermaid / tldraw-skill",
        "layout_archetype": "causal-map",
        "secondary_backend": "excalidraw",
        "secondary_skill": "excalidraw-diagram",
        "reason": "因果/调用链优先使用可编辑关系图",
    },
    {
        "id": "R09-concept",
        "when": lambda h, b, f: f["concept_signal"],
        "visual_type": "concept",
        "content_signal": "concept",
        "render_backend": "agnes",
        "fallback": "deterministic-svg",
        "recommended_skill": "Agnes Image 2.1 Flash / canvas-design",
        "layout_archetype": "metaphor-scene",
        "secondary_backend": "excalidraw",
        "secondary_skill": "excalidraw-diagram",
        "reason": "抽象隐喻适合插画，但精确标签仍需后置叠加",
    },
    {
        "id": "R10-default",
        "when": lambda h, b, f: True,
        "visual_type": "concept",
        "content_signal": "concept",
        "render_backend": "deterministic-svg",
        "fallback": "deterministic-svg",
        "recommended_skill": "deterministic SVG",
        "layout_archetype": "single-claim-anchor",
        "secondary_backend": "",
        "secondary_skill": "",
        "reason": "没有足够信号时使用单一认知锚点并留出扩展位",
    },
)

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "profiles" / "visual-capability-registry.yaml"


def load_capability_registry() -> dict[str, Any]:
    try:
        import yaml  # type: ignore
        value = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (ImportError, OSError, ValueError):
        return {}


def _task_types_for_route(route: dict[str, Any]) -> set[str]:
    visual_type = str(route.get("visual_type") or "").lower()
    signal = str(route.get("content_signal") or "").lower()
    tasks = {visual_type, signal}
    if visual_type == "qkv":
        tasks.update({"formula", "exact_math", "metaphor"})
    if visual_type == "shape":
        tasks.update({"formula", "exact_math", "diagram"})
    if visual_type == "attention":
        tasks.update({"formula", "sequence", "flow"})
    if visual_type == "numeric":
        tasks.update({"numeric", "data", "matrix"})
    if visual_type == "multihead":
        tasks.update({"relationship", "branch"})
    if visual_type == "kv-cache":
        tasks.update({"timeline", "state"})
    if visual_type == "checklist":
        tasks.update({"checklist", "comparison"})
    if visual_type == "code":
        tasks.update({"code", "implementation", "exact_text"})
    if visual_type == "pseudocode":
        tasks.update({"pseudocode", "algorithm", "procedure"})
    if visual_type == "formula-code-map":
        tasks.update({"formula", "code", "implementation", "exact_text"})
    if visual_type == "card-deck":
        tasks.update({"card_deck", "comparison", "checklist", "concept"})
    if visual_type == "excalidraw-style":
        tasks.update({"diagram", "relationship", "flow", "concept"})
    if visual_type == "architecture" and signal == "state":
        tasks.update({"state", "checkpoint", "typed_relation", "branch", "recovery"})
    return tasks


def evaluate_capabilities(route: dict[str, Any]) -> list[dict[str, Any]]:
    registry = load_capability_registry()
    capabilities = registry.get("capabilities") if isinstance(registry.get("capabilities"), list) else []
    task_types = _task_types_for_route(route)
    exact_task = bool(task_types & {"formula", "exact_math", "shape", "numeric", "matrix", "evidence"})
    primary = str(route.get("render_backend") or "").lower()
    secondary = str(route.get("secondary_backend") or "").lower()
    evaluations: list[dict[str, Any]] = []
    for capability in capabilities:
        if not isinstance(capability, dict):
            continue
        skill_id = str(capability.get("skill_id") or "")
        backend = str(capability.get("backend") or "").lower()
        declared = {str(item).lower() for item in capability.get("task_types", []) if str(item).strip()}
        overlap = sorted(task_types & declared)
        status = str(capability.get("execution_status") or "unknown").lower()
        fit = 1.0 if overlap else 0.18
        exactness = 1.0 if not exact_task or bool(capability.get("exact_text")) else 0.0
        integration = 1.0 if status == "integrated" else 0.35 if status == "advisory" else 0.0
        deterministic = 1.0 if bool(capability.get("deterministic")) else 0.35 if not exact_task else 0.0
        mobile = float(capability.get("mobile_score") or 0.5)
        score = round(0.38 * fit + 0.25 * exactness + 0.18 * integration + 0.12 * deterministic + 0.07 * mobile, 4)
        if backend == primary:
            selection = "primary"
        elif backend == secondary and status == "integrated":
            selection = "secondary"
        elif backend == secondary:
            selection = "advisory-secondary"
        else:
            selection = "candidate" if overlap else "rejected"
        eligible = bool(overlap) and status == "integrated" and exactness > 0
        if selection == "primary":
            reason = "命中导演主后端"
        elif selection == "secondary" and eligible:
            reason = "命中可执行辅助后端"
        elif selection == "advisory-secondary":
            reason = "语义适配，但当前仓库只有说明 Skill，未接入执行适配器"
        elif not overlap:
            reason = "任务类型不匹配"
        elif exactness == 0:
            reason = "精确内容禁止使用非精确文字后端"
        elif status != "integrated":
            reason = f"执行状态为 {status}"
        else:
            reason = "候选能力未被当前主/备路由选中"
        evaluations.append({
            "skill_id": skill_id,
            "backend": backend,
            "task_overlap": overlap,
            "execution_status": status,
            "adapter": str(capability.get("adapter") or ""),
            "score": score,
            "eligible": eligible,
            "selection": selection,
            "reason": reason,
            "fallback": str(capability.get("fallback") or ""),
        })
    return sorted(evaluations, key=lambda item: (-float(item["score"]), item["skill_id"]))


def _sanitize_execution_refs(route: dict[str, Any]) -> dict[str, Any]:
    """Keep advisory skills visible as references, never as execution routes."""
    evaluations = route.get("skill_evaluation") if isinstance(route.get("skill_evaluation"), list) else []
    integrated = {str(item.get("backend") or "").lower() for item in evaluations if isinstance(item, dict) and item.get("execution_status") == "integrated"}
    advisory: list[str] = []
    secondary = str(route.get("secondary_backend") or "").lower()
    if secondary and secondary not in integrated:
        advisory.append(secondary)
        route["secondary_backend"] = ""
        route["secondary_skill"] = ""
    for item in evaluations:
        if not isinstance(item, dict):
            continue
        if item.get("selection") == "advisory-secondary":
            item["selection"] = "reference"
            item["reason"] = "仅作灵感/能力参考，不允许作为执行后端"
            advisory.append(str(item.get("backend") or ""))
    route["advisory_references"] = sorted({value for value in advisory if value})
    return route

def semantic_features(heading: str, body: str) -> dict[str, Any]:
    text = f"{heading}\n{body}"
    lower = text.lower()
    formula_count = len(re.findall(r"(?<!\\)\$\$?.+?\$\$?", text, flags=re.S))
    code_count = len(re.findall(r"^\x60{3}", body, flags=re.M)) // 2
    table_present = "|" in body and "---" in body
    numeric_signal = bool(re.search(r"\b\d+(?:\.\d+)?\b|矩阵|权重|数值|Shape", text, flags=re.I))
    matrix_signal = bool(re.search(r"矩阵|\bQK\^?T\b|\bQKᵀ\b|bmatrix|热力|权重", text, flags=re.I))
    relationship_signal = bool(re.search(r"来源|投影|流程|连接|汇总|映射|比较|区别|分支|合并|依赖", text))
    stateful_signal = bool(re.search(
        r"StateGraph|AgentState|状态图|状态对象|Reducer|reducer|checkpoint|Checkpointer|thread_id|interrupt|Command\(resume",
        text, flags=re.I,
    ))
    checkpoint_signal = bool(re.search(
        r"checkpoint|Checkpointer|thread_id|interrupt|Command\(resume|断点|恢复|回放|time travel",
        text, flags=re.I,
    ))
    runtime_boundary_signal = bool(re.search(
        r"FastAPI|API 服务|API服务|多实例|并发控制|锁|Redis|SqliteSaver|MemorySaver|运行时",
        text, flags=re.I,
    ))
    decision_matrix_signal = bool(re.search(
        r"MemorySaver|SqliteSaver|RedisSaver", text, flags=re.I,
    )) and (table_present or bool(re.search(r"怎么挑|选型|适用阶段|生产选型", text)))
    timeline_signal = bool(re.search(r"Prefill|Decode|追加|缓存|阶段|时序|历史", text, flags=re.I))
    concept_signal = bool(re.search(r"类比|直觉|为什么|理解|隐喻|图书馆|检索", text))
    checklist_signal = bool(re.search(r"验收|清单|逐项回答|检查表|自测", text))
    # RC7 / Q③:科普文章需要明确的「代码 vs 伪代码」判定。
    # 强公式、架构、关系 → 给出可运行代码实现；复杂、短篇幅讲不清 → 伪代码。
    # 注意「伪代码」内部包含「代码」，用负向回顾排除，否则伪代码会被误判为代码实现。
    code_signal = bool(re.search(
        r"(?<!伪)(代码|代码片段)|实现|手敲|手写|实战|部署|跑通|可运行|runnable|demo|示例|sample",
        text, flags=re.I,
    )) or code_count > 0
    pseudocode_signal = bool(re.search(
        r"伪代码|伪码|pseudocode|算法步骤|procedure|算法流程|步骤描述", text, flags=re.I,
    ))
    # 「强信号」= 作者显式表达要代码/伪代码：正文里真的有围栏代码块，或标题点名。
    # 只有强信号才可以抢占 R02~R08 的公式/架构主图；弱信号仅作为补充建议，
    # 避免一句「实现原理」把 Attention 公式图挤掉。
    pseudocode_heading = bool(re.search(r"伪代码|伪码|pseudocode|算法步骤|算法流程", heading, flags=re.I))
    code_heading = bool(re.search(
        r"(?<!伪)代码|实现|implementation|\bcode\b|手敲|手写|跑通|可运行", heading, flags=re.I,
    )) and not pseudocode_heading
    card_deck_signal = bool(re.search(
        r"卡组|三联卡|滑动卡片|多图|信息卡|对比卡|步骤卡|要点卡|card deck|flip card|翻牌", text, flags=re.I,
    ))
    excalidraw_signal = bool(re.search(
        r"手绘|草图|sketch|excalidraw|涂鸦|手画", text, flags=re.I,
    ))
    strong_code_signal = code_count > 0 or code_heading
    strong_pseudocode_signal = pseudocode_heading or (
        pseudocode_signal and not strong_code_signal
        and bool(re.search(r"伪代码|伪码|pseudocode", text, flags=re.I))
    )
    # Q③ / Enhancement A: code_style 信号 —— 决定代码卡的表达范式（RC7 补充）。
    #   teaching   = NumPy 直觉（通俗、手把手、小白友好的直觉实现）
    #   production = PyTorch 实战（工程、部署、可运行、工业级落地）
    #   pseudocode = 伪代码（复杂机制、短篇幅讲不清，走步骤化表达）
    # 仅在确实存在代码 / 伪代码上下文时才给出非空值；其它视觉类型保持空串，
    # 避免把“实战”“直觉”等词误用到纯概念章节。
    teaching_signal = bool(re.search(
        r"直觉|直观|通俗|小白|从零|手把手|教学|教程|numpy|np\.|基础版|一步步|"
        r"step[\s-]?by[\s-]?step|tutorial|beginner|理解原理|讲清楚概念|通俗理解",
        text, flags=re.I,
    ))
    production_signal = bool(re.search(
        r"工程|实战|部署|训练|推理|可运行|工业级|pytorch|torch|生产级|production|"
        r"deploy|落地|真实项目|可复现|工程化",
        text, flags=re.I,
    ))
    has_code_context = bool(
        code_signal or strong_code_signal or pseudocode_signal or strong_pseudocode_signal
    )
    if not has_code_context:
        code_style = ""
    elif strong_pseudocode_signal or pseudocode_signal:
        code_style = "pseudocode"
    elif teaching_signal:
        code_style = "teaching"
    elif production_signal:
        code_style = "production"
    else:
        code_style = "production"
    kv_cache_signal = bool(re.search(r"KV\s*Cache|K_cache|V_cache", text, flags=re.I))
    multihead_signal = bool(re.search(r"Multi[- ]?Head|Cross[- ]?Attention|子空间", text, flags=re.I))
    shape_signal = bool(re.search(r"Shape|投影|维度|张量", text, flags=re.I))
    attention_signal = bool(re.search(r"Attention|Softmax|Mask|Score|缩放", text, flags=re.I))
    upper = text.upper()
    qkv_heading = bool(re.search(r"Q[/、]K[/、]V", heading, flags=re.I))
    qkv_signal = qkv_heading and not bool(re.search(r"Attention|Shape|Cache|Multi|Score", heading, flags=re.I))
    numeric_heading = bool(re.search(r"手算|数值|案例|矩阵", heading))
    shape_heading = bool(re.search(r"Shape|投影|张量", heading, flags=re.I))
    attention_heading = bool(re.search(r"Attention|Softmax|Mask|Score|缩放", heading, flags=re.I))
    return {
        "formula_count": formula_count,
        "code_block_count": code_count,
        "table_present": table_present,
        "numeric_signal": numeric_signal,
        "matrix_signal": matrix_signal,
        "relationship_signal": relationship_signal,
        "stateful_signal": stateful_signal,
        "checkpoint_signal": checkpoint_signal,
        "runtime_boundary_signal": runtime_boundary_signal,
        "decision_matrix_signal": decision_matrix_signal,
        "timeline_signal": timeline_signal,
        "concept_signal": concept_signal,
        "checklist_signal": checklist_signal,
        "code_signal": code_signal,
        "pseudocode_signal": pseudocode_signal,
        "card_deck_signal": card_deck_signal,
        "excalidraw_signal": excalidraw_signal,
        "code_heading": code_heading,
        "pseudocode_heading": pseudocode_heading,
        "strong_code_signal": strong_code_signal,
        "strong_pseudocode_signal": strong_pseudocode_signal,
        "code_style": code_style,
        "kv_cache_signal": kv_cache_signal,
        "multihead_signal": multihead_signal,
        "shape_signal": shape_signal,
        "attention_signal": attention_signal,
        "qkv_signal": qkv_signal,
        "qkv_heading": qkv_heading,
        "numeric_heading": numeric_heading,
        "shape_heading": shape_heading,
        "attention_heading": attention_heading,
        "keyword_hits": [k for k in ("Q/K/V", "Shape", "Softmax", "Multi-Head", "KV Cache", "Prefill", "Decode") if k.lower() in lower],
    }


#: 篇幅低于该字数、又扛着强机制的小节，正文讲不透，需要伪代码兜底。
PSEUDOCODE_BODY_BUDGET = 900


def code_supplement(visual_type: str, features: dict[str, Any], body: str) -> str:
    """RC7:主视觉之外，判断本节是否还需要补一段代码 / 伪代码。

    规则来自用户诉求:
      - 强公式 / 架构 / 关系 + 有代码意图  -> 补「可运行代码实现」
      - 机制复杂但篇幅不足以讲透          -> 补「伪代码」压缩逻辑步骤
    主视觉本身已经是代码或伪代码时不再重复补充。
    """
    if visual_type in {"code", "pseudocode"}:
        return ""
    heavy = (
        features.get("formula_count", 0) >= 1
        or features.get("attention_signal")
        or features.get("shape_signal")
        or features.get("qkv_signal")
        or features.get("multihead_signal")
        or features.get("relationship_signal")
        or features.get("kv_cache_signal")
    )
    if not heavy:
        return ""
    if features.get("code_signal"):
        return "code"
    if len(body.strip()) < PSEUDOCODE_BODY_BUDGET:
        return "pseudocode"
    return ""


def route_section(heading: str, body: str, explicit_kind: str = "") -> dict[str, Any]:
    features = semantic_features(heading, body)
    explicit = explicit_kind.strip().lower()
    selected = None
    if explicit:
        explicit_rules = [rule for rule in RULES if rule["visual_type"] == explicit]
        # Checklist is an authored acceptance instrument.  Prefer its
        # progressive-checklist contract over the earlier decision-matrix
        # rule when both feature sets happen to be true.
        if explicit == "checklist":
            explicit_rules.sort(key=lambda rule: 0 if rule.get("id") == "R01-checklist" else 1)
        for rule in explicit_rules:
            if explicit == "checklist":
                features["checklist_signal"] = True
            elif explicit == "kv-cache":
                features["kv_cache_signal"] = True
                features["timeline_signal"] = True
            elif explicit == "multihead":
                features["multihead_signal"] = True
                features["relationship_signal"] = True
            elif explicit == "numeric":
                features["numeric_signal"] = True
                features["matrix_signal"] = True
            elif explicit == "shape":
                features["shape_signal"] = True
            elif explicit == "attention":
                features["attention_signal"] = True
            elif explicit == "qkv":
                features["qkv_signal"] = True
            elif explicit == "code":
                features["code_signal"] = True
                features["strong_code_signal"] = True
            elif explicit == "pseudocode":
                features["pseudocode_signal"] = True
                features["strong_pseudocode_signal"] = True
            elif explicit == "formula-code-map":
                features["formula_count"] = max(features.get("formula_count", 0), 1)
                features["strong_code_signal"] = True
            elif explicit == "card-deck":
                features["card_deck_signal"] = True
            elif explicit == "excalidraw-style":
                features["excalidraw_signal"] = True
            # Honour the author's explicit visual_type: once a known type is
            # requested it is selected directly instead of silently falling
            # back to the default concept when its `when` predicate is False.
            # Its backend is resolved by the shared ``route_backend`` contract
            # (the same authority build_image_prompt_plan uses), so an explicit
            # technical type still lands on the correct deterministic backend.
            selected = dict(rule)
            selected["render_backend"] = route_backend(rule["content_signal"], explicit)
            selected["fallback"] = selected["render_backend"]
            break
    if selected is None:
        selected = next(rule for rule in RULES if rule["when"](heading, body, features))
    result = {key: value for key, value in selected.items() if key != "when"}
    result["features"] = features
    result["code_style"] = features.get("code_style", "")
    result["route_confidence"] = 1.0 if selected["id"] != "R10-default" else 0.55
    result["code_supplement"] = code_supplement(result["visual_type"], features, body)
    result["skill_evaluation"] = evaluate_capabilities(result)
    return _sanitize_execution_refs(result)


def _sections(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", text))
    result: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result.append((match.group(1).strip(), text[match.end():end].strip()))
    return result


def _contract_linked_routes(article: Path, computed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer the authored visual contract when one exists.

    The semantic router is also used as a standalone article-level auditor,
    so it normally emits one route per ``##`` section.  Once ``visual_qa
    plan`` has created a visual contract, however, the contract is the
    authoritative list of *published visual anchors*.  Re-emitting all prose
    sections here used to make ``visual-routing.json`` disagree with the
    actual images (for example, a Checkpointer board was reported as a code
    card).  Merge the computed semantic evidence into the contract-linked
    units instead of silently replacing their authored layout.
    """
    path = article / "visual-contract.json"
    if not path.is_file():
        return computed
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return computed
    units = document.get("units") if isinstance(document, dict) else None
    if not isinstance(units, list):
        return computed
    authored = [unit for unit in units if isinstance(unit, dict) and str(unit.get("id", "")).startswith("body-")]
    if not authored:
        return computed
    by_section = {str(item.get("section", "")): item for item in computed}
    result: list[dict[str, Any]] = []
    for unit in authored:
        unit_id = str(unit.get("id") or "")
        section = str(unit.get("section_heading") or "")
        evidence = by_section.get(section, {})
        diagram_data = unit.get("diagram_data") if isinstance(unit.get("diagram_data"), dict) else {}
        authored_route = {
            "id": unit_id,
            "section": section,
            "primary_backend": str(unit.get("execution_backend") or unit.get("render_backend") or evidence.get("primary_backend") or ""),
            "secondary_backend": unit.get("secondary_backend") or evidence.get("secondary_backend", ""),
            "route_rule": str(unit.get("route_rule") or evidence.get("route_rule") or "contract-authored"),
            "route_reason": str(unit.get("route_reason") or evidence.get("route_reason") or "视觉合同已明确该锚点的可编辑布局"),
            "recommended_skill": str(unit.get("recommended_skill") or evidence.get("recommended_skill") or "deterministic-svg"),
            "secondary_skill": str(unit.get("secondary_skill") or evidence.get("secondary_skill") or ""),
            "layout_archetype": str(diagram_data.get("layout_archetype") or unit.get("layout_archetype") or evidence.get("layout_archetype") or ""),
            "route_confidence": evidence.get("route_confidence", 1.0),
            "code_supplement": evidence.get("code_supplement", ""),
            "semantic_features": unit.get("semantic_features") if isinstance(unit.get("semantic_features"), dict) else evidence.get("semantic_features", {}),
            "skill_evaluation": unit.get("skill_evaluation") if isinstance(unit.get("skill_evaluation"), list) and unit.get("skill_evaluation") else evidence.get("skill_evaluation", []),
            "source_excerpt_sha256": str(unit.get("source_excerpt_sha256") or ""),
            "contract_linked": True,
        }
        result.append(_sanitize_execution_refs(authored_route))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    args = parser.parse_args()
    article = args.article.expanduser().resolve()
    source = article / "article.md"
    if not source.is_file():
        raise SystemExit(f"VISUAL ROUTER BLOCKED: 缺少 {source}")
    routes = []
    for index, (heading, body) in enumerate(_sections(source.read_text(encoding="utf-8")), 1):
        route = route_section(heading, body)
        routes.append({
            "id": f"body-{index:02d}",
            "section": heading,
            "primary_backend": route["render_backend"],
            "secondary_backend": route.get("secondary_backend", ""),
            "route_rule": route["id"],
            "route_reason": route["reason"],
            "recommended_skill": route["recommended_skill"],
            "secondary_skill": route.get("secondary_skill", ""),
            "layout_archetype": route["layout_archetype"],
            "route_confidence": route["route_confidence"],
            "code_supplement": route["code_supplement"],
            "semantic_features": route["features"],
            "skill_evaluation": route["skill_evaluation"],
        })
    routes = _contract_linked_routes(article, routes)
    output = article / "visual-routing.json"
    output.write_text(json.dumps({
        "schema_version": 1,
        "contract": "visual-semantic-routing-v1",
        "status": "passed",
        "router": "scripts/visual_semantic_router.py",
        "scope": "contract-linked-visuals" if any(item.get("contract_linked") for item in routes) else "article-sections",
        "decision_order": [rule["id"] for rule in RULES],
        "routes": routes,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evaluation_path = article / "skill-evaluation.json"
    evaluation_path.write_text(json.dumps({
        "schema_version": 1,
        "contract": "visual-skill-evaluation-v1",
        "status": "passed",
        "registry": "profiles/visual-capability-registry.yaml",
        "routes": [
            {"id": item["id"], "section": item["section"], "evaluations": item["skill_evaluation"]}
            for item in routes
        ],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"VISUAL ROUTER PASSED: {len(routes)} sections -> {output}; skill evaluation -> {evaluation_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
