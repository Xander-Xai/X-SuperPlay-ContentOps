#!/usr/bin/env python3
"""Compile an evidence-first visual director plan for a WeChat article.

The compiler adapts the local video matrix's director-plan ideas to a static
article: every image gets a viewer job, visual owner, source/rights strategy,
continuity group, safe area, deterministic fallback and a model-ready prompt.
It never calls an image API; the separate generation command consumes the
reviewed prompt files after the visual gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from visual_backend_registry import backend_spec, route_backend, validate_record
from visual_semantic_router import route_section as semantic_route
from visual_depth_contract import enrich_unit as enrich_visual_depth_unit
from workspace_paths import resolve_article_workspace


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENDPOINT = "https://apihub.agnes-ai.com/v1/images/generations"
DEFAULT_MODEL = "agnes-image-2.1-flash"
PROMPT_CONTRACT = "prompt-v2"
DIRECTOR_CONTRACT = "visual-director-v1"

# Copy language is a semantic choice, not a by-product of the image model.
# A cover needs one compact, internationally scannable topic signal. Body
# diagrams serve a Chinese article reader first, so they default to Chinese
# and keep English only where it is the stable name of a framework/API/code.
COVER_LANGUAGE_POLICY = {
    "scope": "cover-only",
    "display_language": "english-required",
    "rule": "封面必须有与主题直接相关、可审计的英文信息；由确定性叠层渲染，不交给生图模型写字。",
    "exceptions": ["产品名、框架名、API 名、代码标识符"],
}
BODY_LANGUAGE_POLICY = {
    "scope": "body-visuals",
    "display_language": "zh-CN-first",
    "rule": "正文图优先使用清晰自然的中文；仅在中文不如原术语准确时保留英文，例如 LangGraph、StateGraph、AgentState、API、代码。",
    "exceptions": ["产品名、框架名、API 名、代码标识符、国际通用术语"],
}



def _default_account() -> str:
    """Return the fixed account id of this split workflow target."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from account_context import ACCOUNT_ID
        return ACCOUNT_ID
    except Exception as exc:
        raise RuntimeError("workflow identity unavailable") from exc

def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (ImportError, OSError, ValueError):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slug(value: str) -> str:
    cleaned = re.sub(r"[^\w\-]+", "-", value, flags=re.UNICODE).strip("-")
    return cleaned[:48] or "visual"


def account_tokens(account: str) -> dict[str, Any]:
    """Single-source design tokens for an account (RC3).

    Scripts must read palette/type ramps from here instead of hardcoding hex
    values.  Falls back to the repository-wide default if an account omits
    its own ``design_tokens`` block.
    """
    data = visual_styles()
    defaults = data.get("design_tokens_default") if isinstance(data.get("design_tokens_default"), dict) else {}
    account_cfg = account_visual_config(account)
    tokens = dict(defaults)
    account_tokens_block = account_cfg.get("design_tokens") if isinstance(account_cfg.get("design_tokens"), dict) else {}
    tokens.update({k: v for k, v in account_tokens_block.items() if k and v})
    return tokens


def lighting_swatches(account: str) -> str:
    """Human-readable color names derived from the account design tokens."""
    tokens = account_tokens(account)
    ink = str(tokens.get("ink", "#17324D")).lstrip("#").upper()
    vermilion = str(tokens.get("vermilion", "#B24A2B")).lstrip("#").upper()
    signal = str(tokens.get("signal", "#557A96")).lstrip("#").upper()
    return f"墨蓝 #{ink}、朱砂 #{vermilion} 与少量电蓝信号 #{signal}"


def article_path(raw: str) -> Path:
    return resolve_article_workspace(raw, allow_test_fixture=True)


def headings(article: Path) -> list[str]:
    source = article / "article.md"
    if not source.is_file():
        source = article / "draft.md"
    text = source.read_text(encoding="utf-8", errors="replace") if source.is_file() else ""
    return [match.group(1).strip() for match in re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.M)]


def claim_ids(article: Path) -> list[str]:
    data = {}
    try:
        data = json.loads((article / "sources.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    claims = data.get("claims", []) if isinstance(data, dict) else []
    return [str(item.get("id")) for item in claims[:2] if isinstance(item, dict) and str(item.get("id", "")).strip()]


MAX_CODE_SNIPPET_CHARS = 3000


def section_code_snippets(article: Path) -> dict[str, list[dict[str, str]]]:
    """按二级章节从 article.md 提取 fenced code 块（方案 A）。

    code/pseudocode 视觉任务必须携带真实代码：渲染端只认 contract 的
    ``code`` / ``code_snippet`` 字段，缺省时会退化为把 ``expected_elements``
    当代码渲染（产出“关键词列表”冒充代码）。此函数在编译计划时按章节
    归属提取正文里的 ```lang ... ``` 块，作为这些字段的来源。

    返回 {section_heading: [{"language", "code"}, ...]}，按文档顺序；
    封面引言（首个 ``## `` 之前的段落）归入空标题键。
    """
    source = article / "article.md"
    if not source.is_file():
        source = article / "draft.md"
    if not source.is_file():
        return {}
    sections: dict[str, list[dict[str, str]]] = {}
    current = ""
    in_fence = False
    fence_lang = ""
    fence_buf: list[str] = []
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
            continue
        if line.strip().startswith("```"):
            if not in_fence:
                in_fence = True
                fence_lang = line.strip()[3:].strip()
                fence_buf = []
            else:
                in_fence = False
                code = "\n".join(fence_buf).strip()
                if code:
                    sections.setdefault(current, []).append({
                        "language": fence_lang,
                        "code": code[:MAX_CODE_SNIPPET_CHARS],
                    })
            continue
        if in_fence:
            fence_buf.append(line)
    return sections


def code_hint_for(heading: str, kind: str, has_code: bool) -> str:
    """code/pseudocode 任务缺少真实代码时给人工/编排的补充提示。"""
    if has_code or str(kind or "").strip().lower() not in {"code", "pseudocode"}:
        return ""
    if str(kind or "").strip().lower() == "code":
        return f"本节省略了可直接运行的实现代码：建议补充「{heading}」的 PyTorch / NumPy 实现后再生成配图"
    return f"本节省略了伪代码步骤：建议补充「{heading}」的伪代码流程后再生成配图"


def visual_styles() -> dict[str, Any]:
    return load_yaml(ROOT / "profiles" / "visual-styles.yaml")


def account_visual_config(account: str) -> dict[str, Any]:
    data = visual_styles()
    accounts = data.get("accounts") if isinstance(data.get("accounts"), dict) else {}
    value = accounts.get(account) if isinstance(accounts, dict) else {}
    cfg = dict(value) if isinstance(value, dict) else {}
    # Merge the global body_visual_policy so per-account overrides can be sparse.
    policy = data.get("body_visual_policy") if isinstance(data.get("body_visual_policy"), dict) else {}
    cfg.setdefault("body_visual_policy", policy)
    return cfg


def body_word_count(article: Path) -> int:
    """Count CJK characters in the rendered body, excluding YAML/JSON metadata."""
    source = article / "article.md"
    if not source.is_file():
        source = article / "draft.md"
    if not source.is_file():
        return 0
    text = source.read_text(encoding="utf-8", errors="replace")
    # Drop fenced code blocks so snippet-heavy deep tutorials are not penalized.
    text = re.sub(r"```[\s\S]*?```", " ", text)
    # Drop inline code and URLs as noise.
    text = re.sub(r"`[^`]+`", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    return len(re.findall(r"[一-鿿]", text))


def target_body_visual_count(article: Path, account_cfg: dict[str, Any]) -> int:
    """Compute a dynamic target clamped by account/global limits (Enhancement #2)."""
    policy = account_cfg.get("body_visual_policy") if isinstance(account_cfg.get("body_visual_policy"), dict) else {}
    words_per_visual = int(policy.get("words_per_visual") or 600)
    min_body = int(policy.get("min_body_visuals") or 2)
    policy_max = int(policy.get("max_body_visual_count") or 8)
    account_limit = int(account_cfg.get("body_visual_count") or 5)
    global_max = int(visual_styles().get("max_body_visual_count") or 8)
    upper = min(policy_max, account_limit, global_max)
    words = body_word_count(article)
    if words_per_visual <= 0:
        target = account_limit
    else:
        target = max(min_body, round(words / words_per_visual))
    # A user can explicitly request an opening information map.  It is not a
    # decorative fifth card: it establishes the reading frame before the
    # chapter-level visuals take over.  Permit exactly one extra body visual,
    # still bounded by the account/global ceiling and recorded in the brief.
    brief = load_yaml(article / "visual-brief.yaml")
    if str(brief.get("visual_density_override") or "").strip() == "user-requested-opening-map":
        target += 1
    target = min(target, upper)
    # The distribution gate requires a closing anchor for long-form articles.
    # A three-anchor plan on a 7+ section article necessarily ends in the
    # first third, so reserve one additional slot when the account ceiling
    # permits it.  The article still has to author the closing image anchor;
    # this only prevents the quota from making a passing distribution
    # impossible.
    section_count = len(re.findall(r"^##\s+", (article / "article.md").read_text(encoding="utf-8", errors="replace"), flags=re.MULTILINE)) if (article / "article.md").is_file() else 0
    if section_count >= 7 and target >= 3 and upper >= 4:
        target = max(target, 4)
    if section_count >= 7 and target >= 4 and upper >= 5:
        target = max(target, 5)
    return max(target, min_body)


# Keep the old name for callers that expect a plain dict from visual-styles.yaml.
_visual_styles = visual_styles


def public_brand(account: str, account_cfg: dict[str, Any] | None = None) -> str:
    cfg = account_cfg or account_visual_config(account)
    return str(cfg.get("public_brand") or cfg.get("display_name") or ("AI哨兵" if account == "sentinel" else "X超玩•未来智能")).strip()


def visual_route(kind: str, heading: str = "", body: str = "") -> dict[str, str]:
    """Choose a renderer from section semantics and preserve the audit reason."""
    route = semantic_route(heading, body, str(kind or ""))
    return {
        "visual_type": str(route["visual_type"]),
        "content_signal": str(route["content_signal"]),
        "render_backend": str(route["render_backend"]),
        "fallback": str(route["fallback"]),
        "route_rule": str(route["id"]),
        "recommended_skill": str(route["recommended_skill"]),
        "layout_archetype": str(route["layout_archetype"]),
        "secondary_backend": str(route.get("secondary_backend") or ""),
        "secondary_skill": str(route.get("secondary_skill") or ""),
        "route_reason": str(route["reason"]),
        "route_confidence": str(route.get("route_confidence", 1.0)),
        "code_style": str(route.get("code_style") or route.get("features", {}).get("code_style") or ""),
    }


def normalize_reference_images(values: object, article: Path) -> list[str]:
    """Keep public plan files free of machine-specific absolute paths."""
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        candidate = Path(value)
        if candidate.is_absolute():
            try:
                value = str(candidate.resolve().relative_to(article.resolve()))
            except ValueError:
                value = f"external-reference:{candidate.name}"
        normalized.append(value.replace("\\", "/"))
    return normalized


def kind_profile(kind: str) -> tuple[str, str, str, str]:
    value = kind.lower().strip()
    if value in {"qkv", "shape", "attention", "numeric", "multihead", "kv-cache", "checklist"}:
        return (
            "diagram",
            "正文语义绑定的可编辑技术图，节点、公式和关系必须与视觉合同逐项一致",
            "KaTeX HTML/SVG；必要时使用 beautiful-mermaid 或 excalidraw-diagram",
            "不要生成泛化流程词、无法核验的数字、伪造界面或与章节无关的装饰节点",
        )
    if value == "summary-cards":
        return (
            "diagram",
            "双卡片总结：左卡 30 秒基础版、右卡 1 分钟扩展版；每卡顶部带时间徽章和标题，主体是 4~6 行要点圆点；底部一行口诀",
            "确定性 SVG（双卡片 + 圆点列表 + 顶部色条徽章）",
            "不要捏造数字、不要堆长文；圆点不超过 6 行；保持左右两卡视觉对称",
        )
    if value == "concept-map":
        return (
            "diagram",
            "按当前视觉合同生成的分层概念图：底层承载基础概念，顶层承载应用结论；每层带当前主题标题与一行副标题；左侧带阅读箭头",
            "确定性 SVG（金字塔层级 + 标题副标题 + 左侧上升箭头）",
            "层级数固定 5；底层最宽；颜色从浅到深；不要画流程线",
        )
    if value in {"concept-architecture", "mechanism", "mechanism-illustration", "technical-illustration", "scene", "illustration"}:
        return (
            "illustration",
            "抽象机制的概念场景：用视觉隐喻表达层级、状态变化或因果关系，不冒充真实系统截图",
            "beautiful-mermaid / Excalidraw / SVG；外部模型不可用时使用当前主题的确定性本地插画",
            "不要生成真实产品界面、可核验数字、代码、长中文或官方标识；只保留极少量可删短标签",
        )
    if value in {"architecture", "flow", "diagram"}:
        return (
            "diagram",
            "可编辑的机制关系图，抽象节点与连接线，预留中文标注安全区",
            "beautiful-mermaid 或 excalidraw-diagram；失败时使用 SVG/HTML",
            "不要生成长段文字、代码、数字、真实产品界面或伪造证据",
        )
    if value == "formula-code-map":
        return (
            "diagram",
            "公式↔代码左右对照卡：左侧 KaTeX 公式，右侧对应代码行，中间用数字徽章标注映射关系",
            "render_formula_code_map.mjs（KaTeX + 代码高亮 + 账号主题）；不调用图像模型",
            "不要省略公式与代码的对应关系；不要捏造 API；映射项必须能在正文找到出处",
        )
    if value == "card-deck":
        return (
            "illustration",
            "多张信息卡组成的卡组：一个视觉位并列展示 3-5 个要点，每张卡顶部有编号与标题，主体为短句要点",
            "render_interactive_card_deck.py（SVG 卡组 + 静态 HTML 降级）；不调用图像模型",
            "不要堆叠长段落；每张卡要点不超过 6 条；必须有静态 HTML 降级完整可读",
        )
    if value == "excalidraw-style":
        return (
            "diagram",
            "手绘草图风格机制关系图：带轻微抖动的矩形节点、曲线连线和箭头，模拟白板手绘质感",
            "render_excalidraw_style.py（ rough SVG + Chrome 栅格化）；不调用图像模型",
            "节点标签必须准确；连线关系必须与正文一致；不要生成长段说明文字",
        )
    if value in {"code", "pseudocode"}:
        label = "可运行代码实现" if value == "code" else "伪代码逻辑卡片"
        return (
            "diagram",
            f"确定性渲染的{label}：语法高亮、账号主题配色、可核验的符号与缩进；"
            f"{'代码必须可运行、变量名与正文一致' if value == 'code' else '伪代码用自然语言 + 关键符号表达步骤'}",
            "deterministic code-block（HTML/SVG，账号主题）；不调用图像模型",
            "不要编造 API、不要出现无法核验的数字；"
            "代码/伪代码为精确内容，禁止交给 Agnes 生成图像",
        )
    if value in {"comparison", "evidence-strip"}:
        return (
            "illustration",
            "信息层次清晰的比较/清单视觉，重点区域有留白",
            "HTML/SVG 信息图；渲染失败时阻断，不得降级为无关文字海报",
            "不要生成无法核验的统计数字、品牌界面或过密小字",
        )
    return (
        "illustration",
        "与章节结论相关的概念场景插画，突出一个可记忆的视觉隐喻",
        "当前主题的确定性 SVG/HTML 或用户授权素材；渲染失败时阻断",
        "不要出现可被误认成事实的截图、新闻画面或人物身份",
    )


def generation_mode(kind: str, visual_owner: str | None = None) -> str:
    """Return the production owner for a visual.

    Technical diagrams remain deterministic so labels and relationships are
    exact.  Agnes is used for the cover and for explicitly conceptual
    illustrations, where semantic alignment and composition matter more than
    literal text accuracy.
    """
    value = kind.lower().strip()
    owner = (visual_owner or "").lower().strip()
    if owner in {"diagram", "evidence", "screen-recording"}:
        return "deterministic"
    if value in {"qkv", "shape", "attention", "numeric", "multihead", "kv-cache", "checklist", "comparison", "summary-cards", "concept-map", "architecture", "flow", "diagram", "code", "pseudocode", "formula-code-map", "card-deck", "excalidraw-style", "data", "evidence-strip"}:
        return "deterministic"
    return "agnes"


def cover_copy_for(title: str, article: Path) -> dict[str, Any]:
    """Build a compact, exact-English cover message from the active topic.

    Text-in-image is deliberately *not* delegated to Agnes: even when English
    is more reliable than CJK, a generated headline is still not an auditable
    or accessibility-safe source of truth.  These four short lines are later
    rendered by the deterministic cover compositor.  The fallback remains
    topic-sensitive for articles outside the LangGraph series.
    """
    source = ""
    for candidate in (article / "article.md", article / "draft.md"):
        if candidate.is_file():
            source = candidate.read_text(encoding="utf-8", errors="replace")[:8000]
            break
    normalized = f"{title}\n{source}".lower()
    if "langgraph" in normalized or "stategraph" in normalized:
        return {
            "eyebrow": "STATEFUL AGENT SYSTEMS",
            "headline": "STATEGRAPH → PRODUCTION",
            "keywords": "STATE  ·  FLOW  ·  MEMORY  ·  CONTROL",
            "caption": "A practical map for reliable AI agents",
            "motif": "stateful-agent-loop",
            "motif_expected": ["STATE", "AGENTSTATE", "FLOW", "CHECKPOINT", "HUMAN GATE"],
            "motif_forbidden": ["VECTOR DB", "TOP-K", "GROUNDED ANSWER"],
        }

    if "rag" in normalized or "检索增强生成" in normalized or "retrieval-augmented" in normalized:
        # The cover is rendered into a ~2.35:1 card and is usually viewed at
        # 390px wide in WeChat.  Keep the primary message short enough to use
        # a genuinely legible display size instead of shrinking a sentence
        # until it becomes decorative noise.
        return {
            "eyebrow": "RAG",
            "headline": "ENGINEERING MAP",
            "keywords": "RETRIEVE  ·  GROUND  ·  EVALUATE",
            "caption": "From query to a traceable answer",
            "motif": "rag-retrieval-loop",
            "motif_expected": ["QUERY", "EMBED", "VECTOR DB", "TOP-K", "GROUNDED ANSWER"],
            "motif_forbidden": ["STATE", "AGENTSTATE", "STATEGRAPH", "CHECKPOINT", "HUMAN GATE"],
        }

    english_terms = [
        term.upper()
        for term in re.findall(r"[A-Za-z][A-Za-z0-9+.#/_-]{2,}", title)
        if term.lower() not in {"the", "and", "from", "with", "into", "for"}
    ]
    # ``dict.fromkeys`` returns a view in modern Python, which is not
    # subscriptable.  Materialise the de-duplicated terms before applying the
    # deterministic three-term limit used by the cover prompt.
    topic = " · ".join(list(dict.fromkeys(english_terms))[:3]) or "AI SYSTEMS"
    return {
        "eyebrow": topic,
        "headline": "A PRACTICAL ENGINEERING MAP",
        "keywords": "CONCEPT  ·  SYSTEM  ·  PRACTICE",
        "caption": "What it is, how it works, and how it ships",
        "motif": "generic-engineering-loop",
        "motif_expected": ["INPUT", "PROCESS", "OUTPUT"],
        "motif_forbidden": ["AGENTSTATE", "STATEGRAPH"],
    }


def language_policy_for(*, cover: bool, brief: dict[str, Any]) -> dict[str, Any]:
    """Return the explicit per-asset copy-language contract.

    ``visual-brief.yaml`` may add contextual notes, but it may not weaken the
    two audience rules: English is compulsory only for the topic-facing cover;
    explanatory body visuals are Chinese-first.
    """
    defaults = COVER_LANGUAGE_POLICY if cover else BODY_LANGUAGE_POLICY
    configured = brief.get("language_policy")
    policy = dict(defaults)
    if isinstance(configured, dict):
        policy["article_note"] = str(configured.get("article_note") or "").strip()
    return policy


def prompt_text(*, title: str, section: str, kind: str, purpose: str, art_direction: str,
                visual_owner: str, fallback: str, claims: list[str], safe_area: str,
                continuity_group: str, generation: str, ratio: str, cover: bool = False,
                account: str | None = None, cover_copy: dict[str, Any] | None = None,
                language_policy: dict[str, Any] | None = None,
                expected_elements: list[str] | None = None,
                diagram_data: dict[str, Any] | None = None) -> str:
    # Never put the long article title or brand name in an Agnes image prompt
    # for a cover.  Image models tend to hallucinate exactly the words they
    # are shown; the title and brand belong in the trusted HTML/SVG overlay
    # layer, while Agnes supplies only the illustrative background.
    subject = (
        "A calm tactile editorial paper-collage background about continuity: one solid navy path passes through three large abstract paper forms and arrives at one vermilion point; no words"
        if cover
        else f"公众号文章《{title}》的章节“{section}”认知锚点"
    )
    scene = (
        "Warm ivory paper-cut scene. Place the simple path-and-three-forms composition in the RIGHT 42% only; use a single broad route, not a graph. Keep the LEFT 58% almost empty for a trusted title overlay. No screens, no cards, no charts, no dashboards, no diagrams, no wire bundles."
        if cover
        else f"围绕章节“{section}”构成一个单一视觉隐喻；读者目标：{purpose}"
    )
    style = f"{art_direction}；克制、专业、移动端优先；高信息密度但不拥挤"
    lighting = f"柔和纸面光与低对比阴影，使用{lighting_swatches(account)}"
    composition = "Generate at 21:9 and crop safely to 2.35:1; visual subject lives on the right, the left is quiet editorial negative space for the post-render English overlay" if cover else f"{ratio} 横向构图，主体居中偏上，四周保留 10% 安全边距"
    quality = "清晰边缘、真实 PNG、无水印、无品牌冒用、可在 390px 手机宽度辨识；生成媒体仅作 illustrative"
    negative = (
        "Negative: any words, pseudo-text, letters, Chinese characters, numbers, code, labels, charts, axes, dashboard widgets, dense wire bundles, or fake UI are severe defects; the generated background must contain no text."
        "无写实照片、无 3D 渲染、无品牌 logo、无通用科技感拼贴、无伪造界面或证据。"
    )
    copy_constraint = (
        f"Constraints: {kind_profile(kind)[3]}；all exact cover copy is rendered after generation by a deterministic SVG overlay. "
        f"Planned English cover copy: {(cover_copy or {}).get('eyebrow', '')} / {(cover_copy or {}).get('headline', '')} / {(cover_copy or {}).get('keywords', '')}."
        if cover
        else f"Constraints: {kind_profile(kind)[3]}；正文图文字以中文为主，只有框架名、API 名、代码标识符或中文表达更不准确的术语保留英文；不把中文标题强行翻成英文。"
    )
    lines = [
        f"Subject: {subject}",
        f"Scene / Environment: {scene}",
        f"Style: {style}",
        f"Lighting: {lighting}",
        f"Composition: {composition}",
        f"Quality Requirements: {quality}",
        copy_constraint,
        negative,
    ]
    if not cover and str(generation).strip().lower() == "deterministic":
        labels = [str(value).strip() for value in (expected_elements or []) if str(value).strip()]
        edges = []
        if isinstance(diagram_data, dict):
            edges = [
                f"{item.get('source', '')}->{item.get('target', '')}"
                for item in diagram_data.get("edges", [])
                if isinstance(item, dict) and str(item.get("source") or "").strip() and str(item.get("target") or "").strip()
            ]
        lines.append("Exact text/labels/edges: " + ", ".join(labels[:8] or [purpose]))
        lines.append("Typed edges: " + ", ".join(edges[:8] or ["source->target"]))
        lines.append("Negative: no watermark, fake UI, random decoration, or unrelated topic labels.")
    return "\n".join(lines) + "\n"


def compile_plan(article: Path, provider: str, model: str | None, endpoint: str | None) -> dict[str, Any]:
    article_meta = load_yaml(article / "article.yaml")
    brief = load_yaml(article / "visual-brief.yaml")
    title = str(article_meta.get("title") or brief.get("title") or article.name)
    account = str(article_meta.get("account") or brief.get("account") or _default_account()).strip().lower()
    account_cfg = account_visual_config(account)
    art_direction = str(brief.get("art_direction") or account_cfg.get("art_direction") or "克制、清晰、移动端优先")
    selected_model = model or DEFAULT_MODEL if provider == "agnes" else model or "local-fallback"
    selected_endpoint = endpoint or DEFAULT_ENDPOINT if provider == "agnes" else endpoint or "local"
    claims = claim_ids(article)
    safe_area = str(brief.get("safe_area") or "关键主体和信息位于画布 10% 内边距；公众号标题由 HTML 后置叠加")
    continuity_group = str(brief.get("continuity_group") or f"{account}-editorial-visual-system")
    source_policy = str(brief.get("source_policy") or "证据素材优先；确定性图优先；Agnes 仅用于 illustrative 视觉增强")
    rights_policy = str(brief.get("rights_policy") or "生成图标记 illustrative；不冒充事实证据；人工复核后方可发布")
    anti_fatigue = brief.get("anti_fatigue") if isinstance(brief.get("anti_fatigue"), dict) else {}
    max_streak = int(anti_fatigue.get("max_consecutive_generated", account_cfg.get("max_consecutive_generated_cards", 2)) or 2)
    cover = brief.get("cover", {}) if isinstance(brief.get("cover"), dict) else {}
    records: list[dict[str, Any]] = []

    brand = public_brand(account, account_cfg)
    cover_copy = cover_copy_for(title, article)
    cover_language_policy = language_policy_for(cover=True, brief=brief)
    cover_prompt = prompt_text(
        title=title, section="封面", kind="cover", purpose=f"在首屏建立文章主题和 {brand} 品牌识别",
        art_direction=art_direction, visual_owner="illustration", fallback="text_poster.py", claims=[],
        safe_area=safe_area, continuity_group=continuity_group, generation="agnes", ratio="21:9", cover=True,
        account=account, cover_copy=cover_copy, language_policy=cover_language_policy,
    )
    records.append({
        "id": "cover",
        "path": "imgs/prompts/00-cover.md",
        "asset": str(cover.get("asset") or "imgs/cover.png"),
        "kind": "cover",
        "visual_owner": "illustration",
        "viewer_job": f"首屏用可信英文主题文案清晰说明文章主题：{cover_copy['headline']}；背景只承担氛围与视觉隐喻。",
        "section": "封面",
        "section_heading": "封面",
        "fallback": "text_poster.py",
        "generation_mode": "agnes",
        "source_strategy": "generated-illustrative",
        "rights_status": "pending-human-review",
        "continuity_group": continuity_group,
        "safe_area": safe_area,
        "reference_images": [],
        "prompt": cover_prompt,
        "size": "2K",
        "ratio": "21:9",
        "crop_target_ratio": str(cover.get("ratio") or "2.35:1"),
        "claims": [],
        # These are rendered by the deterministic cover overlay rather than
        # trusted to the image model, so English remains exact and inspectable.
        "cover_copy": cover_copy,
        "language_policy": cover_language_policy,
        "expected_elements": [
            str(cover_copy.get(field, ""))
            for field in ("eyebrow", "headline", "keywords", "caption")
            if str(cover_copy.get(field, "")).strip()
        ] + [str(value) for value in cover_copy.get("motif_expected", []) if str(value).strip()],
        "forbidden_elements": [str(value) for value in cover_copy.get("motif_forbidden", []) if str(value).strip()],
        "cover_motif": str(cover_copy.get("motif") or ""),
        "source_excerpt_sha256": hashlib.sha256(f"封面:{title}".encode("utf-8")).hexdigest(),
        "render_backend": "agnes-or-brand-cover",
        "content_signal": "cover",
        "public_brand": brand,
        "requested_backend": "agnes-or-brand-cover",
        "execution_backend": "agnes-or-brand-cover",
        "fallback_reason": "",
        "semantic_threshold": 1.0,
        "skill_evaluation": [],
    })

    body = brief.get("body_visuals", []) if isinstance(brief.get("body_visuals"), list) else []
    code_snippets = section_code_snippets(article)
    for position, item in enumerate(body, 1):
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or f"body-{position:02d}")
        index_match = re.fullmatch(r"body-(\d{2,})", item_id)
        # A dedicated opener is body-00.  Preserve its numeric prefix so
        # rebuilding a prompt plan does not renumber every existing asset.
        index = int(index_match.group(1)) if index_match else position
        kind = str(item.get("kind") or "illustration")
        route = visual_route(kind, str(item.get("section") or ""), str(item.get("source_excerpt") or ""))
        kind = str(route.get("visual_type") or kind)
        profile_owner, scene_hint, fallback, constraints = kind_profile(kind)
        visual_owner = str(item.get("visual_owner") or profile_owner)
        mode = str(item.get("generation_mode") or generation_mode(kind, visual_owner))
        item_language_policy = language_policy_for(cover=False, brief=brief)
        purpose = str(item.get("purpose") or scene_hint)
        # 视觉简报必须显式提供本节 claim_ids。绝不把整篇文章的 claims
        # 静默绑定到每一张图，否则一张图会“看似有证据”却实际解释了
        # 不相关的章节。
        raw_claims = item.get("claim_ids")
        item_claims = (
            [str(value).strip() for value in raw_claims if str(value).strip()]
            if isinstance(raw_claims, list)
            else []
        )
        ratio = str(item.get("ratio") or "4:3")
        size = str(item.get("size") or ("1K" if mode == "agnes" else "1024x768"))
        item_continuity = str(item.get("continuity_group") or continuity_group)
        item_safe_area = str(item.get("safe_area") or safe_area)
        item_fallback = str(item.get("fallback") or route.get("fallback") or fallback)
        source_strategy = str(item.get("source_strategy") or ("deterministic-renderer" if mode == "deterministic" else "generated-illustrative"))
        rights_status = str(item.get("rights_status") or ("user-owned-or-official" if mode == "deterministic" else "pending-human-review"))
        reference_images = normalize_reference_images(item.get("reference_images"), article)
        # 方案 A：按章节从正文提取真实代码片段，避免 code/pseudocode 卡
        # 退化渲染 expected_elements（关键词列表冒充代码）。
        heading_key = str(item.get("section_heading") or item.get("section") or f"章节 {index}")
        _snippets = code_snippets.get(heading_key, [])
        _first_snippet = _snippets[0] if _snippets else {}
        _code_text = str(_first_snippet.get("code") or "").strip()
        _code_lang = str(_first_snippet.get("language") or "").strip()
        # 方案 A 联动：code/pseudocode 卡的语义契约随渲染内容对齐——
        # expected_elements 必须是代码卡必然渲染的元素：章节标题（title）、
        # 实际范式标签（STYLE_LABELS，与 render_code_block 保持一致）、
        # 以及代码中的独立单词 token（highlight 按 token 包裹，正文句子
        # 或带空格/反斜杠的连续串在 HTML 中并不连续，无法作为匹配项）。
        _kind_label = "代码实现" if str(kind).strip().lower() == "code" else "伪代码"
        _code_style_key = str(item.get("code_style") or "").strip()
        if not _code_style_key:
            _code_style_key = "pseudocode" if str(kind).strip().lower() == "pseudocode" else "production"
        _style_label = {
            "teaching": "NumPy 直觉",
            "production": "PyTorch 实战",
            "pseudocode": "伪代码",
        }.get(_code_style_key, _kind_label)
        if str(kind).strip().lower() in {"code", "pseudocode"}:
            _expected_elements = [heading_key, _style_label]
            if _code_text:
                _tokens = [tok for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_-]{1,}", _code_text) if len(tok) >= 2]
                _expected_elements.extend(list(dict.fromkeys(_tokens))[:3])
        elif str(kind).strip().lower() == "excalidraw-style":
            # A custom diagram_data contract may expose concrete labels and
            # evidence rows.  Preserve those visible anchors; only the plain
            # fallback sketch uses the section heading as its single anchor.
            _custom_expected = [str(value).strip() for value in item.get("expected_elements", []) if str(value).strip()]
            _expected_elements = _custom_expected if item.get("diagram_data") and _custom_expected else [heading_key]
        else:
            _expected_elements = [str(value) for value in item.get("expected_elements", []) if str(value).strip()]
        prompt = prompt_text(
            title=title,
            section=str(item.get("section") or f"章节 {index}"),
            kind=kind,
            purpose=purpose,
            art_direction=art_direction,
            visual_owner=visual_owner,
            fallback=item_fallback,
            claims=[str(value) for value in item_claims if str(value).strip()],
            safe_area=item_safe_area,
            continuity_group=item_continuity,
            generation=mode,
            ratio=ratio,
            account=account, language_policy=item_language_policy,
            expected_elements=_expected_elements,
            diagram_data=item.get("diagram_data") if isinstance(item.get("diagram_data"), dict) else {},
        )
        records.append({
            "id": item_id,
            "path": f"imgs/prompts/{index:02d}-{slug(str(item.get('id') or f'body-{index:02d}'))}.md",
            "asset": str(item.get("asset") or f"imgs/section-{index:02d}.png"),
            "kind": kind,
            "section": str(item.get("section") or f"章节 {index}"),
            "visual_owner": visual_owner,
            "viewer_job": purpose,
            "language_policy": item_language_policy,
            "fallback": item_fallback,
            "constraints": constraints,
            "generation_mode": mode,
            "source_strategy": source_strategy,
            "rights_status": rights_status,
            "continuity_group": item_continuity,
            "safe_area": item_safe_area,
            "reference_images": [str(value) for value in reference_images],
            "prompt": prompt,
            "size": size,
            "ratio": ratio,
            "claims": [str(value) for value in item_claims if str(value).strip()],
            "section_heading": str(item.get("section_heading") or item.get("section") or f"章节 {index}"),
            "cognitive_role": str(item.get("cognitive_role") or ""),
            "code": _code_text,
            "code_snippet": _code_text,
            "language": _code_lang,
            "code_hint": code_hint_for(heading_key, kind, bool(_code_text)),
            "expected_elements": _expected_elements,
            "forbidden_elements": [str(value) for value in item.get("forbidden_elements", []) if str(value).strip()],
            "source_excerpt_sha256": str(item.get("source_excerpt_sha256") or ""),
            "source_excerpt": str(item.get("source_excerpt") or ""),
            "semantic_features": item.get("semantic_features") if isinstance(item.get("semantic_features"), dict) else {},
            "route_rule": str(item.get("route_rule") or route.get("route_rule") or ""),
            "route_reason": str(item.get("route_reason") or route.get("route_reason") or ""),
            "route_confidence": item.get("route_confidence", route.get("route_confidence", 1.0)),
            "recommended_skill": str(item.get("recommended_skill") or route.get("recommended_skill") or ""),
            "layout_archetype": str(item.get("layout_archetype") or route.get("layout_archetype") or ""),
            "secondary_backend": str(item.get("secondary_backend") or route.get("secondary_backend") or ""),
            "secondary_skill": str(item.get("secondary_skill") or route.get("secondary_skill") or ""),
            "skill_evaluation": item.get("skill_evaluation") if isinstance(item.get("skill_evaluation"), list) else route.get("skill_evaluation", []),
            "render_backend": str(item.get("render_backend") or route.get("render_backend") or ("svg" if mode == "deterministic" else "agnes")),
            "content_signal": str(item.get("content_signal") or route.get("content_signal") or "concept"),
            "code_style": str(item.get("code_style") or route.get("code_style") or ""),
            "public_brand": brand,
            "requested_backend": str(item.get("requested_backend") or route.get("render_backend") or ""),
            "execution_backend": str(item.get("execution_backend") or route.get("render_backend") or ""),
            "fallback_reason": str(item.get("fallback_reason") or ""),
            "semantic_threshold": float(item.get("semantic_threshold", 1.0) or 1.0),
            "geometry_required": bool(item.get("geometry_required")),
            "canvas_background": str(item.get("canvas_background") or ""),
            "surface_background": str(item.get("surface_background") or ""),
            # RC7 / 修复：显式 mermaid/diagram 图源从视觉简报透传到记录，
            # 再写入 visual-contract.json，避免 compile_plan 重建合同后
            # beautiful-mermaid 后端退化为稀疏自动连线图（glyph 密度不足阻断
            # illustrated 门禁）。空字符串表示未提供，渲染器走自动布线。
            "mermaid": str(item.get("mermaid") or ""),
            "diagram": str(item.get("diagram") or ""),
            "diagram_data": item.get("diagram_data") if isinstance(item.get("diagram_data"), dict) else {},
            "layout_archetype": str(item.get("layout_archetype") or route.get("layout_archetype") or ""),
            "source_raster_required": bool(item.get("source_raster_required", mode == "deterministic")),
            "depth_contract": str(item.get("depth_contract") or ""),
            "reader_question": str(item.get("reader_question") or ""),
            "answer_sentence": str(item.get("answer_sentence") or ""),
            "visual_thesis": str(item.get("visual_thesis") or ""),
            "entities": item.get("entities", []) if isinstance(item.get("entities"), list) else [],
            "relations": item.get("relations", []) if isinstance(item.get("relations"), list) else [],
            "evidence_ids": item.get("evidence_ids", []) if isinstance(item.get("evidence_ids"), list) else [],
            "layout_grammar": str(item.get("layout_grammar") or ""),
            "must_explain": item.get("must_explain", []) if isinstance(item.get("must_explain"), list) else [],
            "fallback_backend": str(item.get("fallback_backend") or ""),
            "fallback_trigger": str(item.get("fallback_trigger") or ""),
            "fallback_semantic_equivalence": str(item.get("fallback_semantic_equivalence") or ""),
        })

    # ── Visual diversity guard ──────────────────────────────────────────
    # Prevent all body sections from collapsing into a single visual form,
    # which produces visually monotonous articles.  Layout archetypes are the
    # meaningful unit here: a comparison board, state-loop board and
    # architecture board are different visual arguments even when their
    # semantic kind is architecture.
    body_records = [r for r in records if r.get("id", "").startswith("body-")]
    type_counts: dict[str, int] = {}
    for rec in body_records:
        vt = str(rec.get("layout_archetype") or rec.get("kind") or "").strip().lower()
        if vt:
            type_counts[vt] = type_counts.get(vt, 0) + 1
    diversity_warnings: list[str] = []
    total_body = max(1, len(body_records))
    for vt, count in type_counts.items():
        if count / total_body > 0.6:
            diversity_warnings.append(
                f"视觉多样性警告：layout_archetype '{vt}' 占正文图片的 {count}/{total_body} ({count*100//total_body}%)，超过 60% 上限"
            )
    for i in range(1, len(body_records)):
        prev_type = str(body_records[i - 1].get("layout_archetype") or body_records[i - 1].get("kind") or "").strip().lower()
        curr_type = str(body_records[i].get("layout_archetype") or body_records[i].get("kind") or "").strip().lower()
        if prev_type and curr_type and prev_type == curr_type:
            diversity_warnings.append(
                f"视觉多样性警告：相邻正文图 {body_records[i-1].get('id')} 和 {body_records[i].get('id')} 使用了相同的 layout_archetype '{curr_type}'"
            )

    backend_errors = [error for record in records for error in validate_record(record) if record.get("id") != "cover"]
    if backend_errors:
        raise ValueError("视觉后端合同无效：" + "；".join(backend_errors))

    # ── RC4 / Q② / Enhancement #2: body-visual count ceiling ─────────────
    # 数量校验必须放在写盘之前（fail-fast）：超限说明 visual-brief.yaml 过度指定了
    # 正文图，若等到提示词文件全部落盘后再 raise SystemExit，进程终止会留下无法自动
    # 清理的垃圾文件。提前到这里即可在写任何文件前中断。
    body_records = [r for r in records if str(r.get("id")) != "cover"]
    body_count = len(body_records)
    limit = target_body_visual_count(article, account_cfg)
    if body_count > limit:
        policy = account_cfg.get("body_visual_policy") if isinstance(account_cfg.get("body_visual_policy"), dict) else {}
        wpv = int(policy.get("words_per_visual") or 600)
        words = body_word_count(article)
        raise SystemExit(
            f"插图数量超限：账号 {account} 当前正文约 {words} 字，"
            f"按每 {wpv} 字 1 图的动态配额最多 {limit} 张正文图"
            f"（account 上限 {account_cfg.get('body_visual_count') or 5}；"
            f"全局上限 {visual_styles().get('max_body_visual_count') or 8}）。"
            f"当前计划 {body_count} 张。请精简 visual-brief.yaml 的 body_visuals，"
            f"或调整 profiles/visual-styles.yaml 的 body_visual_policy.words_per_visual。"
        )

    prompt_dir = article / "imgs" / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_files: list[dict[str, Any]] = []
    for record in records:
        path = article / record["path"]
        frontmatter = {
            "provider": provider,
            "requested_provider": provider,
            "model": selected_model,
            "size": record["size"],
            "ratio": record.get("ratio"),
            "quality": "high",
            "visual_owner": record["visual_owner"],
            "generation_mode": record["generation_mode"],
            "section": record["section"],
            "kind": record["kind"],
            "cognitive_role": record.get("cognitive_role", ""),
            "viewer_job": record["viewer_job"],
            "fallback": record["fallback"],
            "claim_ids": record["claims"],
            "continuity_group": record["continuity_group"],
            "safe_area": record["safe_area"],
            "reference_images": record["reference_images"],
            "cover_copy": record.get("cover_copy", {}),
            "cover_motif": record.get("cover_motif", ""),
            "language_policy": record.get("language_policy", {}),
            "generated_media_disclosure": "illustrative",
            "expected_elements": record.get("expected_elements", []),
            "forbidden_elements": record.get("forbidden_elements", []),
            "source_excerpt_sha256": record.get("source_excerpt_sha256", ""),
            "render_backend": record.get("render_backend", ""),
            "content_signal": record.get("content_signal", "concept"),
            "code_style": record.get("code_style", ""),
            "public_brand": record.get("public_brand", brand),
            "requested_backend": record.get("requested_backend", record.get("render_backend", "")),
            "execution_backend": record.get("execution_backend", record.get("render_backend", "")),
            "fallback_reason": record.get("fallback_reason", ""),
            "geometry_required": record.get("geometry_required", False),
            "canvas_background": record.get("canvas_background", ""),
            "surface_background": record.get("surface_background", ""),
            "semantic_features": record.get("semantic_features", {}),
            "skill_evaluation": record.get("skill_evaluation", []),
            "mermaid": record.get("mermaid", ""),
            "diagram": record.get("diagram", ""),
        }
        try:
            import yaml  # type: ignore

            header = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
        except ImportError:
            header = json.dumps(frontmatter, ensure_ascii=False, indent=2)
        content = f"---\n{header}\n---\n{record['prompt']}"
        path.write_text(content, encoding="utf-8")
        # Windows text mode may normalize LF to CRLF on disk.  Hash the bytes
        # that visual_qa.py will actually verify, not the pre-write string.
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        prompt_files.append({
            "id": record["id"],
            "path": record["path"],
            "asset": record["asset"],
            "sha256": digest,
            "provider": provider,
            "requested_provider": provider,
            "model": selected_model,
            "section": record["section"],
            "kind": record["kind"],
            "generation_mode": record["generation_mode"],
            "size": record["size"],
            "ratio": record.get("ratio"),
            "visual_owner": record["visual_owner"],
            "viewer_job": record["viewer_job"],
            "fallback": record["fallback"],
            "claim_ids": record["claims"],
            "source_strategy": record["source_strategy"],
            "rights_status": record["rights_status"],
            "continuity_group": record["continuity_group"],
            "safe_area": record["safe_area"],
            "reference_images": record["reference_images"],
            "cover_copy": record.get("cover_copy", {}),
            "cover_motif": record.get("cover_motif", ""),
            "language_policy": record.get("language_policy", {}),
            "section_heading": record.get("section_heading", record.get("section", "")),
            "expected_elements": record.get("expected_elements", []),
            "forbidden_elements": record.get("forbidden_elements", []),
            "source_excerpt_sha256": record.get("source_excerpt_sha256", ""),
            "render_backend": record.get("render_backend", ""),
            "content_signal": record.get("content_signal", "concept"),
            "code_style": record.get("code_style", ""),
            "public_brand": record.get("public_brand", brand),
            "requested_backend": record.get("requested_backend", record.get("render_backend", "")),
            "execution_backend": record.get("execution_backend", record.get("render_backend", "")),
            "fallback_reason": record.get("fallback_reason", ""),
            "semantic_features": record.get("semantic_features", {}),
            "skill_evaluation": record.get("skill_evaluation", []),
            "semantic_threshold": record.get("semantic_threshold", 1.0),
            "mermaid": record.get("mermaid", ""),
            "diagram": record.get("diagram", ""),
            "diagram_data": record.get("diagram_data", {}),
            "geometry_required": record.get("geometry_required", False),
            "canvas_background": record.get("canvas_background", ""),
            "surface_background": record.get("surface_background", ""),
            "status": "planned",
        })

    director_records = [{
        "id": record["id"],
        "asset": record["asset"],
        "section": record["section"],
        "kind": record["kind"],
        "viewer_job": record["viewer_job"],
        "fallback": record["fallback"],
        "visual_owner": record["visual_owner"],
        "generation_mode": record["generation_mode"],
        "source_strategy": record["source_strategy"],
        "rights_status": record["rights_status"],
        "claim_ids": record["claims"],
        "fallback": record["fallback"],
        "continuity_group": record["continuity_group"],
        "safe_area": record["safe_area"],
        "prompt_file": record["path"],
        "reference_images": record["reference_images"],
        "cover_copy": record.get("cover_copy", {}),
        "cover_motif": record.get("cover_motif", ""),
        "language_policy": record.get("language_policy", {}),
        "section_heading": record.get("section_heading", record.get("section", "")),
        "cognitive_role": record.get("cognitive_role", ""),
        "expected_elements": record.get("expected_elements", []),
        "forbidden_elements": record.get("forbidden_elements", []),
        "source_excerpt_sha256": record.get("source_excerpt_sha256", ""),
        "render_backend": record.get("render_backend", ""),
        "content_signal": record.get("content_signal", "concept"),
        "route_rule": record.get("route_rule", ""),
        "route_reason": record.get("route_reason", ""),
        "recommended_skill": record.get("recommended_skill", ""),
        "secondary_backend": record.get("secondary_backend", ""),
        "secondary_skill": record.get("secondary_skill", ""),
        "public_brand": record.get("public_brand", brand),
        "requested_backend": record.get("requested_backend", record.get("render_backend", "")),
        "execution_backend": record.get("execution_backend", record.get("render_backend", "")),
        "fallback_reason": record.get("fallback_reason", ""),
        "semantic_features": record.get("semantic_features", {}),
        "skill_evaluation": record.get("skill_evaluation", []),
        "semantic_threshold": record.get("semantic_threshold", 1.0),
        "mermaid": record.get("mermaid", ""),
        "diagram": record.get("diagram", ""),
        "diagram_data": record.get("diagram_data", {}),
        "layout_archetype": record.get("layout_archetype", ""),
        "source_raster_required": record.get("source_raster_required", record.get("generation_mode") == "deterministic"),
        "depth_contract": record.get("depth_contract", ""),
        "reader_question": record.get("reader_question", ""),
        "answer_sentence": record.get("answer_sentence", ""),
        "visual_thesis": record.get("visual_thesis", ""),
        "entities": record.get("entities", []),
        "relations": record.get("relations", []),
        "evidence_ids": record.get("evidence_ids", []),
        "layout_grammar": record.get("layout_grammar", ""),
        "must_explain": record.get("must_explain", []),
        "fallback_backend": record.get("fallback_backend", ""),
        "fallback_trigger": record.get("fallback_trigger", ""),
        "fallback_semantic_equivalence": record.get("fallback_semantic_equivalence", ""),
        "geometry_required": record.get("geometry_required", False),
        "canvas_background": record.get("canvas_background", ""),
        "surface_background": record.get("surface_background", ""),
        "status": "ready",
    } for record in records]
    visual_direction = {
        "family": str(brief.get("image_theme") or account_cfg.get("image_theme") or "editorial-atlas"),
        "art_direction": art_direction,
        "safe_area": safe_area,
        "source_policy": source_policy,
        "rights_policy": rights_policy,
        "anti_fatigue": {
            "max_consecutive_generated": max_streak,
            "same_continuity_group": True,
            "prefer_different_composition": True,
        },
    }
    director_plan = {
        "schema_version": 1,
        "contract": DIRECTOR_CONTRACT,
        "status": "ready",
        "account": account,
        "title": title,
        "visual_direction": visual_direction,
        "records": director_records,
        "review": {"required_before_generation": True, "reviewer_type": "pending"},
    }
    write_json(article / "visual-director-plan.json", director_plan)
    contract_units = [{
        "id": record["id"],
        "section_heading": record.get("section_heading", record.get("section", "")),
        "cognitive_role": record.get("cognitive_role", ""),
        "visual_type": record.get("kind", "concept"),
        "viewer_job": record["viewer_job"],
        "language_policy": record.get("language_policy", {}),
        "cover_copy": record.get("cover_copy", {}),
        "cover_motif": record.get("cover_motif", ""),
        "fallback": record["fallback"],
        "expected_elements": record.get("expected_elements", []),
        "forbidden_elements": record.get("forbidden_elements", []),
        "claim_ids": record["claims"],
        "code": record.get("code", ""),
        "code_snippet": record.get("code_snippet", ""),
        "language": record.get("language", ""),
        "code_hint": record.get("code_hint", ""),
        "render_backend": record.get("render_backend", ""),
        "content_signal": record.get("content_signal", "concept"),
        "route_rule": record.get("route_rule", ""),
        "route_reason": record.get("route_reason", ""),
        "recommended_skill": record.get("recommended_skill", ""),
        "secondary_backend": record.get("secondary_backend", ""),
        "secondary_skill": record.get("secondary_skill", ""),
        "public_brand": record.get("public_brand", brand),
        "requested_backend": record.get("requested_backend", record.get("render_backend", "")),
        "execution_backend": record.get("execution_backend", record.get("render_backend", "")),
        "fallback_reason": record.get("fallback_reason", ""),
        "semantic_features": record.get("semantic_features", {}),
        "output": record["asset"],
        "asset": record["asset"],
        "generation_mode": record["generation_mode"],
        "provider": provider,
        "source_excerpt": record.get("source_excerpt", ""),
        "source_excerpt_sha256": record.get("source_excerpt_sha256", ""),
        "semantic_threshold": record.get("semantic_threshold", 1.0),
        "mermaid": record.get("mermaid", ""),
        "diagram": record.get("diagram", ""),
        "diagram_data": record.get("diagram_data", {}),
        "layout_archetype": record.get("layout_archetype", ""),
        "source_raster_required": record.get("source_raster_required", record.get("generation_mode") == "deterministic"),
        "depth_contract": record.get("depth_contract", ""),
        "reader_question": record.get("reader_question", ""),
        "answer_sentence": record.get("answer_sentence", ""),
        "visual_thesis": record.get("visual_thesis", ""),
        "entities": record.get("entities", []),
        "relations": record.get("relations", []),
        "evidence_ids": record.get("evidence_ids", []),
        "layout_grammar": record.get("layout_grammar", ""),
        "must_explain": record.get("must_explain", []),
        "fallback_backend": record.get("fallback_backend", ""),
        "fallback_trigger": record.get("fallback_trigger", ""),
        "fallback_semantic_equivalence": record.get("fallback_semantic_equivalence", ""),
        "geometry_required": record.get("geometry_required", False),
        "canvas_background": record.get("canvas_background", ""),
        "surface_background": record.get("surface_background", ""),
    } for record in records]
    contract_units = [
        enrich_visual_depth_unit(unit, article)
        if str(unit.get("id") or "") != "cover" else unit
        for unit in contract_units
    ]
    # The cover is already the first record in ``records``; keep a single
    # cover unit so semantic QA counts remain one-to-one with prompt files.
    write_json(article / "visual-contract.json", {
        "schema_version": 1,
        "contract": "visual-contract-v1",
        "status": "ready",
        "article": title,
        "background_contract": brief.get("background_contract", {}),
        "units": contract_units,
    })
    director_lines = [
        f"# 视觉导演计划｜{title}",
        "",
        f"- 账号：{account}",
        f"- 视觉系统：{visual_direction['family']}",
        f"- 证据策略：{source_policy}",
        f"- 生成素材版权策略：{rights_policy}",
        f"- 移动端安全区：{safe_area}",
        f"- 连续生图上限：{max_streak} 张",
        "",
        "| 素材 | 读者任务 | 视觉负责人 | 生成模式 | 来源策略 | fallback | 状态 |",
        "|---|---|---|---|---|---|---|",
    ]
    for record in director_records:
        director_lines.append(
            f"| {record['id']} | {record['viewer_job']} | {record['visual_owner']} | {record['generation_mode']} | {record['source_strategy']} | {record['fallback']} | {record['status']} |"
        )
    (article / "visual-director-plan.md").write_text("\n".join(director_lines) + "\n", encoding="utf-8")

    plan = {
        "schema_version": 2,
        "generation_contract": PROMPT_CONTRACT,
        "status": "planned",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "account": account,
        "title": title,
        "public_brand": brand,
        "provider": provider,
        "requested_provider": provider,
        "endpoint": selected_endpoint,
        "model": selected_model,
        "visual_direction": visual_direction,
        "generation_policy": {
            "generated_media_is_illustrative": True,
            "diagrams_prefer_deterministic_renderer": True,
            "max_consecutive_generated_cards": max_streak,
            "mobile_width": 390,
            "rights_review_required": True,
            "personal_skill_contract": "agnes-image-21-flash",
            "formula_renderer": "katex-html-chrome-tight-v3",
            "technical_visuals_require_deterministic": True,
            "backend_registry": "scripts/visual_backend_registry.py",
            "semantic_router": "visual_qa.semantic_features",
            "capability_registry": "profiles/visual-capability-registry.yaml",
            "skill_evaluation_artifact": "skill-evaluation.json",
        },
        "visual_director_plan": "visual-director-plan.json",
        "visual_contract": "visual-contract.json",
        "prompt_files": prompt_files,
        "diversity_warnings": diversity_warnings,
    }
    write_json(article / "image-generation-plan.json", plan)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True)
    parser.add_argument("--provider", default="agnes", choices=("agnes", "local"))
    parser.add_argument("--model")
    parser.add_argument("--endpoint")
    args = parser.parse_args()
    article = article_path(args.article)
    if not article.is_dir():
        raise SystemExit(f"文章目录不存在：{article}")
    plan = compile_plan(article, args.provider, args.model, args.endpoint)
    # RC1: enforce the prompt contract immediately after compiling.  A leaking
    # prompt is a regression, not a runtime surprise, so fail the command.
    from prompt_contract import validate_plan

    violations = validate_plan(article)
    if violations:
        raise SystemExit("提示词契约校验失败：\n" + "\n".join(f"- {v}" for v in violations))
    print(json.dumps({"status": plan["status"], "provider": plan["provider"], "prompt_count": len(plan["prompt_files"]), "output": str(article / "image-generation-plan.json")}, ensure_ascii=False, indent=2))
    for warning in plan.get("diversity_warnings", []):
        print(f"⚠ {warning}", file=__import__("sys").stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
