#!/usr/bin/env python3
"""Create and validate the visual brief for a WeChat article.

The command is deliberately local and deterministic.  It does not call an
image model or upload assets.  It turns the visual stage into an auditable
artifact: a brief, an image plan and an image analysis report.

Examples:
    python scripts/visual_qa.py plan --article <external-active/THK-...>
    python scripts/visual_qa.py approve --article <external-active/THK-...> --reason "作者已确认封面候选"
    python scripts/visual_qa.py check --article <external-active/THK-...>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(ROOT / "scripts"))
from article_integrity import sha256_file  # noqa: E402
from build_image_prompt_plan import account_visual_config, cover_copy_for, public_brand, target_body_visual_count, visual_route  # noqa: E402
from build_art_direction import build_art_direction  # noqa: E402
from visual_semantic_router import semantic_features as routed_semantic_features, RULES  # noqa: E402
from visual_contract_audit import audit as audit_visual_contract  # noqa: E402
from visual_taste_review import build_review as build_visual_taste_review  # noqa: E402
from prompt_contract import validate_plan as _validate_prompt_plan  # noqa: E402
from visual_depth_contract import enrich_unit as _enrich_depth_unit  # noqa: E402


STYLES = ROOT / "profiles" / "visual-styles.yaml"
GENERATION_CONTRACT = "prompt-v2"
VISUAL_CONTRACT = "visual-contract-v1"
BACKGROUND_CONTRACT = "background-contract-v1"
GENERIC_LABELS = ["目标", "关系", "门禁", "资产", "输入", "检查", "放行", "回读", "现状", "证据", "判断"]
SEMANTIC_QA = ROOT / "scripts" / "visual_semantic_qa.py"


# Enhancement #8: 每张正文认知锚点都承担一个认知角色，避免同类型图扎堆。
# opener   = 建立问题/隐喻，出现在文章前 1/3
# mechanism= 算法/机制细节，是技术文的核心
# proof    = 数值演算、证据、对比
# checklist= 验收/门禁清单
# bridge   = 连接不同概念的关系图/流程图
# closer   = 总结、卡组、公式-代码对照等收尾锚点
COGNITIVE_ROLES = {"opener", "mechanism", "proof", "checklist", "bridge", "closer"}


def _cognitive_role(visual_type: str, index: int, total: int) -> str:
    """根据视觉类型和在正文视觉序列中的位置分配认知角色。"""
    vt = str(visual_type).lower()
    if vt == "checklist":
        return "checklist"
    if vt in {"numeric", "evidence-strip", "comparison", "data"}:
        return "proof"
    if vt in {"summary-cards", "formula-code-map"}:
        return "closer"
    if vt in {"concept-map", "flow", "architecture", "diagram", "excalidraw-style", "relationship"}:
        if index >= total - 1:
            return "closer"
        return "bridge"
    if vt in {"card-deck"}:
        if index >= total - 1:
            return "closer"
        return "bridge"
    if vt in {"qkv", "attention", "shape", "multihead", "kv-cache", "code", "pseudocode"}:
        return "mechanism"
    if index == 0:
        return "opener"
    if index >= total - 1:
        return "closer"
    return "bridge"


def _visual_distribution_issues(body_visuals: list[dict[str, Any]], total_sections: int) -> list[str]:
    """检查正文视觉锚点是否均匀分布，而不是全挤在中段。

    规则：
    - 第一张图应落在全文前 35%；最后一张图应落在后 35%。
    - 相邻两张图之间的 normalized 间隔不应超过 0.5。
    - 落在中间 40%（0.3~0.7）的图不能超过总数的 60%。
    """
    issues: list[str] = []
    n = len(body_visuals)
    if n <= 2 or total_sections <= 1:
        return issues
    positions = []
    for item in body_visuals:
        idx = item.get("section_index")
        if idx is None:
            # 兼容旧简报：按 body_visuals 自身顺序估算
            idx = len(positions)
        positions.append(idx / (total_sections - 1))
    first, last = positions[0], positions[-1]
    if first > 0.35:
        issues.append(f"第一张认知锚点出现过晚（{first:.0%}），建议在前 1/3 增加开场图")
    if last < 0.65:
        issues.append(f"最后一张认知锚点出现过早（{last:.0%}），建议在结尾增加总结图")
    max_gap = max(positions[i + 1] - positions[i] for i in range(n - 1))
    if max_gap > 0.5:
        issues.append(f"相邻认知锚点间隔过大（{max_gap:.0%}），读者会连续滑过大段无图文字")
    middle_count = sum(1 for p in positions if 0.3 <= p <= 0.7)
    # For a three-anchor article, an intentionally even 0%/33%/67% rhythm is
    # the desired opening/middle/closing cadence.  Larger sets need a stricter
    # middle-band cap because five cards can still look clustered even when
    # their local gaps are equal.
    gaps = [positions[i + 1] - positions[i] for i in range(n - 1)]
    evenly_spaced = max(gaps) - min(gaps) <= 0.2 if gaps else True
    if middle_count / n >= 0.6 and (n > 3 or not evenly_spaced):
        issues.append(f"{middle_count}/{n} 张图挤在文章中段（30%~70%），分布不均")
    return issues


def _yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except ImportError:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
    except (OSError, ValueError):
        return {}


def _hybrid_evidence_paths(article_dir: Path) -> set[str]:
    """Return local image paths owned by the source-evidence appendix.

    These screenshots are evidence exhibits, not cognitive-anchor artwork;
    they must be checked for provenance but should not be forced into the
    visual brief's one-to-one body-visual set.
    """
    path = article_dir / "source-evidence.json"
    if not path.is_file():
        return set()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
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


def _write_yaml(path: Path, value: dict[str, Any]) -> None:
    try:
        import yaml  # type: ignore

        path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")
    except ImportError:
        # JSON is a valid YAML 1.2 document and keeps nested approval and
        # visual lists readable even on a minimal Python installation.
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _article_dir(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()



def _default_account() -> str:
    """Return the fixed account id of this split workflow target."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from account_context import ACCOUNT_ID
        return ACCOUNT_ID
    except Exception as exc:
        raise RuntimeError("workflow identity unavailable") from exc


def _account_choices() -> tuple[str, ...]:
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from account_context import ACCOUNT_IDS
        return tuple(sorted(ACCOUNT_IDS))
    except Exception as exc:
        raise RuntimeError("workflow identity unavailable") from exc

def _account(article_dir: Path) -> str:
    data = _yaml(article_dir / "article.yaml")
    account = str(data.get("account") or _default_account()).strip().lower()
    return account if account in _account_choices() else _default_account()


def _headings(article_dir: Path) -> list[str]:
    source = article_dir / "article.md"
    if not source.is_file():
        source = article_dir / "draft.md"
    text = source.read_text(encoding="utf-8", errors="replace") if source.is_file() else ""
    return [m.group(1).strip() for m in re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.M)]


def _sections(article_dir: Path) -> list[tuple[str, str]]:
    source = article_dir / "article.md"
    if not source.is_file():
        source = article_dir / "draft.md"
    text = source.read_text(encoding="utf-8", errors="replace") if source.is_file() else ""
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.M))
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append((match.group(1).strip(), text[match.end():end].strip()))
    return sections


_SECTION_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((imgs/section-\d+\.(?:png|webp|jpg|jpeg))\)", flags=re.IGNORECASE)


def _authored_asset_mapping_errors(article_dir: Path, body_visuals: list[dict[str, Any]]) -> list[str]:
    """Ensure each authored Markdown image marker matches its visual unit.

    Planning historically selected the right chapters but then reassigned
    sequential filenames, so two manually authored markers could silently
    swap chapter-05/chapter-07 artwork.  The marker is an authored binding;
    it must agree with the brief/contract asset before any later renderer can
    consume it.
    """
    sections = dict(_sections(article_dir))
    errors: list[str] = []
    for item in body_visuals:
        if not isinstance(item, dict):
            continue
        heading = str(item.get("section_heading") or item.get("section") or "").strip()
        expected = str(item.get("asset") or "").strip().replace("\\", "/")
        body = sections.get(heading, "")
        markers = [match.group(1).replace("\\", "/") for match in _SECTION_IMAGE_RE.finditer(body)]
        if not markers or not expected:
            continue
        if len(set(markers)) > 1:
            errors.append(f"章节 {heading} 包含多个不同图片锚点：{', '.join(markers)}")
            continue
        if markers[0] != expected:
            errors.append(f"章节 {heading} 的 Markdown 图片 {markers[0]} 与视觉合同 asset {expected} 不一致")
    return errors


def _semantic_features(heading: str, body: str) -> dict[str, Any]:
    """Extract stable signals used by the visual router and audit report."""
    return routed_semantic_features(heading, body)


def _generic_contract_for(heading: str, body: str) -> dict[str, Any]:
    """Domain-agnostic visual contract for non-Transformer topics.

    只依赖领域中立的小标题信号（清单 / 数值案例 / 关系对比），viewer_job
    与 expected_elements 都从小标题本身派生，claim_ids 一律置空
    （非 Transformer 选题没有 c1–c7 这套 claim 体系）。
    """
    text = f"{heading}\n{body}"
    if any(k in heading for k in ("验收", "清单", "checklist", "要点", "步骤", "步骤说明")):
        return {
            "visual_type": "checklist",
            "viewer_job": f"把『{heading}』的清单逐项核对呈现",
            "expected_elements": [heading[:12]],
            "claim_ids": [],
            "render_backend": "svg",
        }
    if any(k in heading for k in ("手算", "2×2", "2x2", "数值", "案例", "计算", "example", "示例")):
        return {
            "visual_type": "numeric",
            "viewer_job": f"用数值案例核对『{heading}』的关键结论",
            "expected_elements": [heading[:12]],
            "claim_ids": [],
            "render_backend": "svg",
        }
    if any(k in heading for k in ("关系", "对比", "区别", "vs", "VS", "流程", "原理", "机制", "为什么")):
        return {
            "visual_type": "concept",
            "viewer_job": f"解释『{heading}』中的一个具体认知关系",
            "expected_elements": [heading[:12]],
            "claim_ids": [],
            "render_backend": "excalidraw",
        }
    return {
        "visual_type": "concept",
        "viewer_job": f"解释『{heading}』的一个具体认知关系",
        "expected_elements": [heading[:12]],
        "claim_ids": [],
        "render_backend": "excalidraw",
    }


def _visual_contract_for(heading: str, body: str, domain: str = "generic") -> dict[str, Any]:
    """Derive a visual task from section meaning, not a rotating template.

    domain 默认是领域无关的 ``generic``。Transformer 专属模板只能通过
    article.yaml 显式声明 ``topic_domain: transformer`` 启用，不能成为新主题的
    隐式回退。这样新主题不会继承旧文章的 QKV / Softmax / KV Cache 标签。
    """
    if domain != "transformer":
        return _generic_contract_for(heading, body)
    text = f"{heading}\n{body}"
    if "验收" in heading or "清单" in heading:
        return {
            "visual_type": "checklist",
            "viewer_job": "把验收清单逐项映射到 QKV、Shape、Softmax、Multi-Head 和 Cache",
            "expected_elements": ["Q/K/V", "Shape", "Softmax", "Multi-Head", "KV Cache"],
            "claim_ids": ["c1", "c2", "c3", "c4", "c5", "c6", "c7"],
            "render_backend": "svg",
        }
    if "KV Cache" in heading or re.search(r"\bPrefill\b", heading) or re.search(r"\bDecode\b", heading):
        return {
            "visual_type": "kv-cache",
            "viewer_job": "看懂 Prefill 与 Decode 如何写入、追加并读取历史 K/V Cache",
            "expected_elements": ["Prefill", "Decode", "K_cache", "V_cache", "历史"],
            "claim_ids": ["c6", "c7"],
            "render_backend": "svg",
        }
    if "Self" in heading and "Cross" in heading and "Multi" in heading:
        return {
            "visual_type": "multihead",
            "viewer_job": "看懂 Self/Cross 的 QKV 来源、多头并行和 W_O 汇合",
            "expected_elements": ["Self-Attention", "Cross-Attention", "Multi-Head", "W_O"],
            "claim_ids": ["c1", "c5"],
            "render_backend": "svg",
        }
    if "手算" in heading or "2×2" in heading or "2x2" in heading:
        return {
            "visual_type": "numeric",
            "viewer_job": "用 2×2 数值案例核对 Score、Softmax 权重和输出矩阵",
            "expected_elements": ["QKᵀ", "0.50", "0.67", "O"],
            "claim_ids": ["c2", "c3", "c4"],
            "render_backend": "svg",
        }
    if "Shape" in heading or "投影" in heading or "Score" in heading:
        return {
            "visual_type": "shape",
            "viewer_job": "核对 X 投影到 Q/K/V 以及 QKᵀ 的张量 Shape",
            "expected_elements": ["X", "Q", "K", "V", "QKᵀ", "n_q", "n_k"],
            "claim_ids": ["c1", "c2"],
            "render_backend": "svg",
        }
    if "Scaled Dot" in heading or "Softmax" in heading or "Mask" in heading:
        return {
            "visual_type": "attention",
            "viewer_job": "看懂 Attention 的 Score、缩放、Mask、Softmax 与 V 汇总五步",
            "expected_elements": ["Score", "缩放", "Mask", "Softmax", "V"],
            "claim_ids": ["c3", "c4"],
            "render_backend": "svg",
        }
    if "Q" in text and "K" in text and "V" in text:
        return {
            "visual_type": "qkv",
            "viewer_job": "理解 Q 查询、K 匹配、V 传递在一次检索中的关系",
            "expected_elements": ["X", "Q", "K", "V", "查询", "匹配", "传递"],
            "claim_ids": ["c1"],
            "render_backend": "svg",
        }
    return {
        "visual_type": "concept",
        "viewer_job": f"解释“{heading}”的一个具体认知关系",
        "expected_elements": [heading[:12]],
        "claim_ids": [],
        "render_backend": "excalidraw",
    }


def _keywords_from(text: str, limit: int = 6) -> list[str]:
    """从正文抽取候选关键词碎片，供通用合同的 expected_elements 使用。"""
    tokens = re.split(r"[\s，。；;：:、,.!?！？（）()\"'\"'“”0-9×\*]{1,}", text)
    out: list[str] = []
    for t in tokens:
        t = t.strip()
        # Markdown image placeholders and sentence tails are not visual
        # labels.  Keeping them in expected_elements creates impossible
        # contracts such as "[示意图" or "的第一个核心抽象是".
        t = re.sub(r"[`\[（(]+|[`\]）)]+$", "", t).strip()
        if not t or t in {"拥有", "一个", "第一个", "核心", "抽象"} or "示意图" in t or "核心抽象是" in t or t.endswith("核心判断是"):
            continue
        if 2 <= len(t) <= 12 and t not in out:
            out.append(t)
        if len(out) >= limit:
            break
    return out


def _visible_items_from_body(heading: str, body: str, limit: int = 6) -> list[str]:
    """Extract concrete checklist/comparison labels from the current article.

    A visual contract must be grounded in the current topic.  This helper keeps
    generic topics from falling back to a historical Transformer checklist.
    """
    items: list[str] = []
    for raw in str(body or "").splitlines():
        line = raw.strip()
        match = re.match(r"^(?:[-*]|\d+[.)])\s+(?:\*\*)?(.+?)(?:\*\*)?$", line)
        if not match:
            continue
        value = re.sub(r"[`*_]", "", match.group(1)).strip()
        value = re.split(r"[：:]", value, maxsplit=1)[0].strip()
        if 2 <= len(value) <= 24 and value not in items:
            items.append(value)
        if len(items) >= limit:
            break
    if items:
        return items
    heading_items = [part.strip() for part in re.split(r"[、，,；;|]", heading) if part.strip()]
    return (heading_items[:limit] or _keywords_from(f"{heading}\n{body}", limit))


def _board_diagram_data(labels: list[str], *, layout: str, left_title: str = "", right_title: str = "") -> dict[str, Any]:
    """Build a small editable graph contract for mechanism/comparison boards.

    The renderer uses these nodes and edges as geometry evidence.  Labels are
    extracted from the current section; no historical topic vocabulary is
    injected into a new article.
    """
    clean: list[str] = []
    for value in labels:
        # Preserve authored parentheses/plus signs in visible labels (for
        # example ``Query（用户提问）``); only strip Markdown fencing that is
        # not part of the diagram's meaning.
        value = re.sub(r"[`\[\]]+", "", str(value or "")).strip()
        if value and value not in clean and len(value) <= 20:
            clean.append(value)
    clean = clean[:6] or ["核心概念", "执行", "结果"]
    nodes = [{"id": f"n{index}", "label": value, "accent": index in {0, len(clean) - 1}} for index, value in enumerate(clean)]
    edges = [{"source": f"n{index}", "target": f"n{index + 1}"} for index in range(len(clean) - 1)]
    return {
        "layout_archetype": layout,
        "nodes": nodes,
        "edges": edges,
        "left_title": left_title,
        "right_title": right_title,
    }


def _board_terms(text: str, heading: str = "", limit: int = 6) -> list[str]:
    """Extract concrete identifiers and terms for a mechanism board."""
    values: list[str] = []
    for value in re.findall(r"(?:FastAPI|LangGraph|StateGraph|Checkpointer|SqliteSaver|MemorySaver|Redis|thread_id|langgraph serve)", text, flags=re.I):
        value = value.strip().rstrip("/")
        if value and value.casefold() not in {item.casefold() for item in values}:
            values.append(value)
    for value in re.findall(r"`([^`]+)`", text):
        value = value.strip()
        if 2 <= len(value) <= 24 and not value.endswith("/") and value.casefold() not in {item.casefold() for item in values}:
            values.append(value)
    for value in re.findall(r"\b[A-Z][A-Za-z0-9_./-]{2,}\b", text):
        if not value.endswith("/") and value.casefold() not in {item.casefold() for item in values}:
            values.append(value)
    for value in ("checkpoint", "thread_id", "恢复", "状态", "超时", "重试", "流式输出", "并发", "可观测性"):
        if value in text and value.casefold() not in {item.casefold() for item in values}:
            values.append(value)
    for value in _keywords_from(f"{heading}\n{text}", limit=limit * 2):
        if value not in values:
            values.append(value)
    return values[:limit]


def _topic_labels(heading: str, body: str, limit: int = 6) -> list[str]:
    """Prefer authored bullets/steps before incidental paper metadata."""
    authored = _visible_items_from_body(heading, body, limit=limit)
    extracted = _board_terms(f"{heading}\n{body}", heading, limit=limit * 2)
    values: list[str] = []
    for value in [*authored, *extracted]:
        value = str(value).strip()
        if value and value not in values:
            values.append(value)
        if len(values) >= limit:
            break
    return values


def _generic_contract_for(heading: str, body: str) -> dict[str, Any]:
    """领域无关的视觉合同：从标题/正文语义派生，不套用任何 Transformer 专属模板。

    与 _visual_contract_for 的 transformer 分支不同：claim_ids 一律置空
    （非 Transformer 文章没有那套固定的 claim 编号），viewer_job 与
    expected_elements 直接由当前标题/正文派生，换选题也能贴切。
    render_backend 由后续 visual_route 按 visual_type 覆盖。
    """
    text = f"{heading}\n{body}"
    # 验收 / 清单 → 清单卡（不再绑定 QKV/Softmax）
    if "验收" in heading or "清单" in heading or "checklist" in heading.lower():
        items = _visible_items_from_body(heading, body)
        return {
            "visual_type": "checklist",
            "viewer_job": f"把“{heading}”的验收/清单条目逐项呈现",
            "expected_elements": (items[:6] or [heading[:12]]),
            "claim_ids": [],
            "render_backend": "deterministic-infographic",
        }
    # 数值 / 手算 / 案例 → 数值对照
    if ("手算" in heading or "数值" in heading or "案例" in heading
            or "2×2" in heading or "2x2" in heading or re.search(r"\d+×\d+", heading)):
        return {
            "visual_type": "numeric",
            "viewer_job": f"用具体数值案例核对“{heading}”的计算或对比结论",
            "expected_elements": (_keywords_from(text) or [heading[:12]]),
            "claim_ids": [],
            "render_backend": "svg",
        }
    # A comparison is a visual argument, not a code-card decoration.  Detect
    # it before the code-intent rule so “function chain vs state graph” becomes
    # two causal columns with evidence, rather than a one-line placeholder.
    if re.search(r"函数链|状态图|\bvs\b", text, flags=re.I) or any(token in heading for token in ("对比", "差异", "而不是")):
        evidence = _visible_items_from_body(heading, body, limit=6)
        right_nodes = _board_terms(text, heading, limit=6)
        if re.search(r"函数链|状态图|StateGraph", text, flags=re.I):
            structural = re.findall(r"StateGraph|状态(?:对象|显式声明)?|节点|边|持久化|恢复|Checkpointer|interrupt", text, flags=re.I)
            right_nodes = list(dict.fromkeys(structural)) or right_nodes
        left_nodes = evidence[:3]
        labels = [*left_nodes, *right_nodes]
        data = _board_diagram_data(
            labels,
            layout="comparison-board",
            left_title="函数链" if re.search(r"函数链", text) else "旧路径",
            right_title="StateGraph" if re.search(r"StateGraph|状态图", text, flags=re.I) else "结构化路径",
        )
        data["left_nodes"] = left_nodes
        data["right_nodes"] = right_nodes[:3] or ["结构化状态", "显式关系", "可恢复执行"]
        labels = [*left_nodes, *data["right_nodes"]]
        return {
            "visual_type": "architecture",
            "viewer_job": f"对比“{heading}”两种做法的结构差异与工程后果",
            "expected_elements": labels[:6],
            "claim_ids": [],
            "render_backend": "deterministic-svg",
            "content_signal": "relationship",
            "layout_archetype": "comparison-board",
            "diagram_data": data,
        }
    if re.search(r"Checkpointer|断点|time travel|checkpoint", heading, flags=re.I):
        labels = _topic_labels(heading, body, limit=6)
        return {
            "visual_type": "architecture",
            "viewer_job": f"展示“{heading}”如何写入 checkpoint、按 thread_id 回读并恢复执行",
            "expected_elements": labels or [heading[:12]],
            "claim_ids": [],
            "render_backend": "deterministic-svg",
            "content_signal": "relationship",
            "layout_archetype": "state-loop-board",
            "diagram_data": _board_diagram_data(labels, layout="state-loop-board", left_title="执行状态", right_title="持久化与恢复"),
        }
    # API/服务化/部署章节需要呈现系统边界和运行链路，不应被压成伪代码卡。
    if re.search(r"生产落地|API\s*服务|FastAPI|Redis|部署|服务化|架构", text, flags=re.I):
        labels = _topic_labels(heading, body, limit=6)
        return {
            "visual_type": "architecture",
            "viewer_job": f"呈现“{heading}”从入口到运行时与持久化的系统边界",
            "expected_elements": labels or [heading[:12]],
            "claim_ids": [],
            "render_backend": "deterministic-svg",
            "content_signal": "relationship",
            "layout_archetype": "architecture-board",
            "diagram_data": _board_diagram_data(labels, layout="architecture-board", left_title="入口", right_title="运行与持久化"),
        }
    # RC7 / 通用机制（内容驱动，不限 Transformer）：强技术主题（公式/架构/算法/
    # 机制/注意力…）+ 显式代码意图 → 可运行代码实现（理论结合实战）。纯技术主题
    # 无代码意图仍走手绘关系图，不抢占；「无代码/不用代码」等否定表述不触发。
    _has_formula = bool(re.search(r"(?<!\\)\$\$?.+?\$\$?", text, flags=re.S))
    _tech_subject = bool(re.search(
        r"公式|推导|数学|算法|计算|架构|模块|层|Encoder|Decoder|网络|模型|调用链|数据流|"
        r"机制|原理|注意力|Attention|前向|反向|训练|推理|缩放|点积|Softmax|QKV|QKᵀ",
        text, flags=re.I,
    ))
    _neg_code = bool(re.search(r"无代码|不用代码|没有代码|无需代码|不写代码|不附代码|不要代码", text))
    _code_intent = (not _neg_code) and bool(re.search(
        r"可运行代码|跑通|手写|手敲|代码片段|代码实现|用代码|附代码|实现代码|示例代码|"
        r"PyTorch|NumPy|runnable|implementation|\bcode\b|\bdemo\b|实战",
        text, flags=re.I,
    ))
    if (_has_formula or _tech_subject) and _code_intent:
        return {
            "visual_type": "code",
            "viewer_job": (
                f"用可运行代码（默认 PyTorch 实战，基础版可用 NumPy 直觉）"
                f"复现「{heading}」的核心公式或算法，控制在前 40 行内"
            ),
            "expected_elements": (_keywords_from(text) or [heading[:12]]),
            "claim_ids": [],
            "render_backend": "code-block",
        }
    # A section can contain implementation snippets while its reader task is
    # still to understand a graph/state relationship (e.g. nodes, edges,
    # persistence, checkpoints).  Use the shared semantic router as the
    # evidence source instead of letting a vague "concept" fallback erase the
    # topology.  This remains topic-agnostic: the labels are extracted from
    # the current heading/body, never from a historical template.
    routed_features = routed_semantic_features(heading, body)
    if routed_features.get("relationship_signal"):
        labels = _topic_labels(heading, body, limit=6)
        return {
            "visual_type": "architecture",
            "viewer_job": f"呈现“{heading}”中节点、状态与流转关系",
            "expected_elements": (labels or [heading[:12]]),
            "claim_ids": [],
            "render_backend": "deterministic-svg",
            "content_signal": "relationship",
            "layout_archetype": "relationship-board",
            "diagram_data": _board_diagram_data(labels, layout="relationship-board"),
        }
    # 关系 / 对比 / 流程 / 架构 / 结构 / 策略 → 手绘关系图（复用路由表已有的
    # excalidraw-style，走确定性 SVG 后端，避免引入路由表不认识、且会被校验拦掉的
    # 'relationship' 新类型；结构性内容尽量确定性渲染，契合项目防幻觉原则）
    # 中文关键词扩展（方案 B）：方法/做法/思路/路径/方案/决策/取舍/权衡/先后/
    # 优先/顺序/办法 等常见中文技术文章表达都映射到手绘关系图。
    # 注意：「三板斧/三个方法/三个要点」等并列方法论更适合走 code 卡
    # 三个并列块，避免 excalidraw 渲染器硬编码占位词（输入/处理/输出）
    # 误触 GENERIC_LABELS 禁止规则。
    _excalidraw_keys = (
        "关系", "对比", "流程", "架构", "原理", "机制", "步骤", "链路", "演进",
        "结构", "策略",
        "方法", "做法", "思路", "路径", "方案", "决策", "取舍", "权衡",
        "先后", "优先", "顺序", "办法",
    )
    if (
        any(k in heading for k in _excalidraw_keys)
        or "vs" in heading.lower()
        or any(k in body for k in ("对比", "差异", "区别", "先后顺序"))
    ):
        return {
            "visual_type": "excalidraw-style",
            "viewer_job": f"呈现“{heading}”中要素之间的关系、对比或流程",
            "expected_elements": (_keywords_from(text) or [heading[:12]]),
            "claim_ids": [],
            "render_backend": "svg",
        }
    # RC7 / 通用机制（内容驱动，不限 Transformer）：复杂、短篇幅讲不清的机制
    # → 伪代码压缩逻辑步骤。阈值 900 字与路由器 code_supplement 的
    # PSEUDOCODE_BODY_BUDGET 保持一致；仅当标题未命中 excalidraw 关键词
    # （关系/对比/流程/架构…）时才落到这里，避免与手绘关系图冲突。
    _pseudo_intent = bool(re.search(r"伪代码|伪码|pseudocode|算法步骤|算法流程|步骤描述", text, flags=re.I))
    _short_complex = len(body.strip()) < 900 and bool(
        re.search(r"原理|机制|流程|步骤|逻辑|算法|推导|架构", text)
    )
    if _pseudo_intent or _short_complex:
        return {
            "visual_type": "pseudocode",
            "viewer_job": f"用伪代码把「{heading}」的步骤映射成可执行骨架",
            "expected_elements": (_keywords_from(text) or [heading[:12]]),
            "claim_ids": [],
            "render_backend": "code-block",
        }
    # 默认：概念解释也必须有可见关系，而不是一张“标题 + 要点”卡。
    # 用正文关键词生成最小关系板，后续可由作者在 visual-brief.yaml 中
    # 覆盖 nodes/edges；渲染器和 visual_content_qa 会强制检查节点与箭头。
    labels = _topic_labels(heading, body, limit=6)
    return {
        "visual_type": "architecture",
        "viewer_job": f"解释“{heading}”中最重要的一条因果或结构关系",
        "expected_elements": (labels or [heading[:12]]),
        "claim_ids": [],
        "render_backend": "deterministic-svg",
        "content_signal": "relationship",
        "layout_archetype": "relationship-board",
        "diagram_data": _board_diagram_data(labels, layout="relationship-board"),
    }


def _styles() -> dict[str, Any]:
    return _yaml(STYLES)


def _background_contract(account_cfg: dict[str, Any]) -> dict[str, Any]:
    tokens = account_cfg.get("design_tokens") if isinstance(account_cfg.get("design_tokens"), dict) else {}
    styles = _styles()
    defaults = styles.get("design_tokens_default") if isinstance(styles.get("design_tokens_default"), dict) else {}
    canvas = str(tokens.get("background") or defaults.get("background") or "#F4F0E8").strip()
    surface = str(tokens.get("surface") or defaults.get("surface") or "#FFFCF7").strip()
    return {
        "contract": BACKGROUND_CONTRACT,
        "scope": "body",
        "canvas_token": "background",
        "canvas_hex": canvas,
        "surface_token": "surface",
        "surface_hex": surface,
        "strict_canvas": True,
        "cover_policy": "brand-specific",
    }


def _geometry_required(contract: dict[str, Any], route: dict[str, Any]) -> bool:
    """Relationship diagrams must carry auditable connector geometry."""
    visual_type = str(contract.get("visual_type") or route.get("visual_type") or "").strip().lower()
    signal = str(contract.get("content_signal") or route.get("content_signal") or "").strip().lower()
    inferred = signal in {"relationship", "flow", "timeline", "architecture", "branch"} or visual_type in {
        "architecture", "flow", "diagram", "excalidraw-style", "concept-map", "multihead", "kv-cache"
    }
    # A stale contract must not be able to opt a connector-bearing visual out
    # of geometry QA.  Explicit false remains useful only for genuinely
    # non-relational visuals (code, equation, checklist, etc.).
    if inferred:
        return True
    if "geometry_required" in contract:
        return bool(contract.get("geometry_required"))
    return False


def _taste_review_passed(taste_review: dict[str, Any]) -> bool:
    """Read the taste receipt's human status from either supported schema."""
    rubric = taste_review.get("rubric") if isinstance(taste_review.get("rubric"), dict) else {}
    human_status = taste_review.get("human_review_status") or rubric.get("human_review_status")
    return taste_review.get("status") == "passed" and human_status == "passed"


def _intentional_cover_overlay(raw_path: str, generation: dict[str, Any]) -> bool:
    """Whether visible cover lettering is an approved deterministic overlay."""
    return bool(
        str(raw_path or "").replace("\\", "/") == "imgs/cover.png"
        and str(generation.get("cover_overlay_source") or "").strip()
        and "overlay" in str(generation.get("method") or "").lower()
    )


def _article_config() -> dict[str, Any]:
    return _yaml(ROOT / ".aws-article" / "config.yaml")


def _make_brief(article_dir: Path) -> dict[str, Any]:
    account = _account(article_dir)
    account_cfg = _styles().get("accounts", {}).get(account, {})
    background_contract = _background_contract(account_cfg)
    title_data = _yaml(article_dir / "article.yaml")
    # 新主题默认使用领域无关合同；Transformer 仅允许显式 opt-in。
    topic_domain = str(title_data.get("topic_domain") or _article_config().get("topic_domain") or "generic").strip().lower()
    sections = _sections(article_dir)
    headings = [heading for heading, _ in sections]
    count = target_body_visual_count(article_dir, account_cfg)
    density = str(_article_config().get("image_density", "")).strip()
    # “每节一图” is an explicit contract: include every section, including
    # a closing section.  Otherwise use the account's cognitive-anchor cap.
    section_map = {heading: body for heading, body in sections}
    article_markdown = (article_dir / "article.md").read_text(encoding="utf-8", errors="replace") if (article_dir / "article.md").is_file() else ""
    cover_copy = cover_copy_for(str(title_data.get("title") or article_dir.name), article_dir)
    referenced_assets = set(re.findall(r"imgs/section-\d+\.(?:png|webp|jpg|jpeg)", article_markdown, flags=re.I))
    anchored_headings = [
        heading for heading, body in sections
        if any(asset in body for asset in referenced_assets)
    ]
    if referenced_assets and anchored_headings:
        # The markdown image is the source of truth for section association;
        # density must never remap section-02 to the second heading merely
        # because the filename happens to be sequential.
        # “每节一图” describes the desired coverage, but the account's
        # dynamic quota remains a hard upper bound.  Cap the authored anchors
        # so a long article cannot produce an over-limit plan that can never
        # reach illustrated.
        selected = anchored_headings[:count]
    elif "每节" in density or "each" in density.lower():
        selected = headings[:count]
    else:
        # Bind visual units to the sections that actually contain authored
        # image anchors before applying the account density cap.  The old
        # headings[:count] shortcut silently associated section-02/03 with
        # the wrong headings and made the distribution gate report a false
        # "last image too early" result.  For an article without anchors,
        # choose evenly spaced sections so a sparse set still covers the
        # opener, mechanism and conclusion.
        explicit = [
            heading for heading, body in sections
            if re.search(r"!\[[^\]]*\]\(\s*imgs/section-[0-9]+\.png\s*\)", body, flags=re.I)
        ]
        if len(explicit) >= count:
            selected = explicit[:count]
        elif explicit:
            remaining = [heading for heading in headings if heading not in explicit]
            need = max(0, count - len(explicit))
            if need and remaining:
                positions = [round(i * (len(remaining) - 1) / max(need - 1, 1)) for i in range(need)]
                selected = explicit + [remaining[min(pos, len(remaining) - 1)] for pos in positions]
            else:
                selected = explicit
        else:
            if count <= 1:
                selected = headings[:1]
            else:
                positions = [round(i * (len(headings) - 1) / (count - 1)) for i in range(count)]
                selected = [headings[min(pos, len(headings) - 1)] for pos in positions]
    # Preserve explicitly authored visual arguments when re-planning an
    # existing article.  The router still owns the semantic contract, while
    # diagram_data/layout_archetype carry the chosen composition and concrete
    # evidence rows instead of collapsing back to a generic card template.
    previous_brief = _yaml(article_dir / "visual-brief.yaml")
    previous_by_id = {
        str(item.get("id")): item
        for item in (previous_brief.get("body_visuals", []) if isinstance(previous_brief.get("body_visuals"), list) else [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    previous_contract = {}
    contract_path = article_dir / "visual-contract.json"
    if contract_path.is_file():
        try:
            value = json.loads(contract_path.read_text(encoding="utf-8"))
            previous_contract = value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            previous_contract = {}
    for unit in previous_contract.get("units", []) if isinstance(previous_contract.get("units"), list) else []:
        if not isinstance(unit, dict) or not str(unit.get("id") or "").strip():
            continue
        ident = str(unit["id"])
        previous_by_id[ident] = {**previous_by_id.get(ident, {}), **unit}
    visuals = []
    total_visuals = len(selected)
    for index, heading in enumerate(selected, 1):
        section_index = headings.index(heading) if heading in headings else index - 1
        preserved = previous_by_id.get(f"body-{index:02d}", {})
        contract = _visual_contract_for(heading, section_map.get(heading, ""), topic_domain)
        excerpt = section_map.get(heading, "")[:1200]
        excerpt_sha256 = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
        same_authored_source = (
            str(preserved.get("section_heading") or preserved.get("section") or "").strip() == heading
            and str(preserved.get("source_excerpt_sha256") or "").strip() == excerpt_sha256
        )
        if same_authored_source:
            for key in ("expected_elements", "claim_ids", "code", "code_snippet", "code_hint", "language", "code_style"):
                if preserved.get(key) not in (None, "", []):
                    contract[key] = preserved[key]
        features = _semantic_features(heading, section_map.get(heading, ""))
        route = visual_route(contract["visual_type"], heading, section_map.get(heading, ""))
        # Contract-authored board composition is part of the visual argument;
        # do not let the generic router replace it with a one-size-fits-all
        # causal map.
        if contract.get("layout_archetype"):
            route["layout_archetype"] = str(contract["layout_archetype"])
        if contract.get("content_signal"):
            route["content_signal"] = str(contract["content_signal"])
        if isinstance(preserved.get("diagram_data"), dict) and preserved.get("diagram_data") and not contract.get("diagram_data"):
            # An authored visual argument is part of the article brief, not a
            # historical template.  Keep its type, anchors, route and data
            # while recomputing the body excerpt hash from the current text.
            for key in ("kind", "visual_type", "viewer_job", "purpose", "expected_elements", "claim_ids", "render_backend", "requested_backend", "execution_backend", "fallback", "content_signal", "route_rule", "route_reason", "recommended_skill", "layout_archetype", "secondary_backend", "secondary_skill", "visual_owner", "generation_mode", "geometry_required", "source_raster_required", "canvas_background", "surface_background", "depth_contract", "reader_question", "answer_sentence", "visual_thesis", "entities", "relations", "evidence_ids", "layout_grammar", "must_explain", "fallback_backend", "fallback_trigger", "fallback_semantic_equivalence"):
                if key in preserved and preserved.get(key) not in (None, "", []):
                    contract_key = "viewer_job" if key == "purpose" else key
                    contract[contract_key] = preserved[key]
            route["render_backend"] = str(preserved.get("render_backend") or route.get("render_backend") or contract.get("render_backend") or "")
            route["content_signal"] = str(preserved.get("content_signal") or route.get("content_signal") or contract.get("content_signal") or "")
            route["fallback"] = str(preserved.get("fallback") or route.get("fallback") or contract.get("fallback") or "")
            for route_key in ("route_rule", "route_reason", "recommended_skill", "layout_archetype", "secondary_backend", "secondary_skill"):
                if preserved.get(route_key) not in (None, ""):
                    route[route_key] = preserved[route_key]
            # Re-resolve backend ownership for authored comparison/checklist
            # contracts.  A prior brief may carry a stale code-block or SVG
            # backend even after the semantic router has changed the visual
            # type; keeping that stale value creates a cross-ledger drift.
            if str(contract.get("visual_type") or "").strip().lower() in {"comparison", "checklist"}:
                refreshed = visual_route(str(contract.get("visual_type")), heading, section_map.get(heading, ""))
                for route_key in ("render_backend", "content_signal", "fallback", "route_rule", "route_reason", "recommended_skill", "layout_archetype", "secondary_backend", "secondary_skill"):
                    if refreshed.get(route_key) not in (None, ""):
                        route[route_key] = refreshed[route_key]
        contract["render_backend"] = route["render_backend"]
        contract["content_signal"] = route["content_signal"]
        contract["fallback"] = route["fallback"]
        role = _cognitive_role(contract["visual_type"], index - 1, total_visuals)
        visuals.append({
            "id": f"body-{index:02d}",
            "section": heading,
            "section_heading": heading,
            "section_index": section_index,
            "cognitive_role": role,
            "kind": contract["visual_type"],
            "visual_type": contract["visual_type"],
            "purpose": contract["viewer_job"],
            "asset": f"imgs/section-{index:02d}.png",
            "alt": f"{account_cfg.get('alt_prefix', '公众号视觉')}：{contract['viewer_job']}",
            "expected_elements": contract["expected_elements"],
            "forbidden_elements": [value for value in GENERIC_LABELS if value not in contract["expected_elements"]],
            "claim_ids": contract["claim_ids"],
            "render_backend": contract["render_backend"],
            "requested_backend": contract["render_backend"],
            "execution_backend": contract["render_backend"],
            "fallback_reason": "",
            "content_signal": contract["content_signal"],
            "fallback": contract["fallback"],
            "semantic_features": features,
            "route_rule": route.get("route_rule", ""),
            "route_reason": route.get("route_reason", ""),
            "route_confidence": route.get("route_confidence", 1.0),
            "recommended_skill": route.get("recommended_skill", ""),
            "layout_archetype": str(
                contract.get("layout_archetype")
                or preserved.get("layout_archetype")
                or route.get("layout_archetype", "")
            ),
            "diagram_data": (
                contract.get("diagram_data")
                if isinstance(contract.get("diagram_data"), dict) and contract.get("diagram_data")
                else (preserved.get("diagram_data") if isinstance(preserved.get("diagram_data"), dict) else {})
            ),
            "secondary_backend": route.get("secondary_backend", ""),
            "secondary_skill": route.get("secondary_skill", ""),
            "skill_evaluation": route.get("skill_evaluation", []),
            "geometry_required": bool(
                _geometry_required(contract, route)
                or ("geometry_required" in preserved and bool(preserved.get("geometry_required")))
            ),
            "canvas_background": str(preserved.get("canvas_background") or background_contract["canvas_hex"]),
            "surface_background": str(preserved.get("surface_background") or background_contract["surface_hex"]),
            "source_excerpt": excerpt,
            "source_excerpt_sha256": excerpt_sha256,
            "semantic_threshold": 1.0,
            "depth_contract": str(contract.get("depth_contract") or ""),
            "reader_question": str(contract.get("reader_question") or ""),
            "answer_sentence": str(contract.get("answer_sentence") or ""),
            "visual_thesis": str(contract.get("visual_thesis") or ""),
            "entities": contract.get("entities", []),
            "relations": contract.get("relations", []),
            "evidence_ids": contract.get("evidence_ids", []),
            "layout_grammar": str(contract.get("layout_grammar") or ""),
            "must_explain": contract.get("must_explain", []),
            "fallback_backend": str(contract.get("fallback_backend") or ""),
            "fallback_trigger": str(contract.get("fallback_trigger") or ""),
            "fallback_semantic_equivalence": str(contract.get("fallback_semantic_equivalence") or ""),
            "status": "planned",
        })
        for key in ("code", "code_snippet", "code_hint", "language", "code_style"):
            if contract.get(key) not in (None, "", []):
                visuals[-1][key] = contract[key]
    # If an existing article already has concrete image references, do not
    # create orphan visual units for sections that are not actually illustrated.
    # Drafts that still use `placeholder` keep the full planned set and can
    # decide their image density before generation.
    if referenced_assets:
        visuals = [item for item in visuals if str(item.get("asset") or "") in referenced_assets]
    return {
        "schema_version": 1,
        "account": account,
        "title": str(title_data.get("title", article_dir.name)),
        "formatter_theme": str(account_cfg.get("formatter_theme", "default")),
        "image_theme": str(account_cfg.get("image_theme", _default_account() + "-atlas" if _default_account() == "thinktank" else _default_account() + "-radar")),
        "art_direction": str(account_cfg.get("art_direction", "克制、清晰、移动端优先")),
        "approval": {"cover_selection": "pending", "approved_by": "", "approved_at": "", "reason": ""},
        "cover": {
            "asset": "imgs/cover.png",
            "ratio": str(account_cfg.get("cover_ratio", "2.35:1")),
            "candidates": ["cover-candidate-01.png", "cover-candidate-02.png", "cover-candidate-03.png"],
            "selected": "imgs/cover.png",
            "alt": f"{account_cfg.get('alt_prefix', '公众号视觉')}：文章封面",
            "semantic_anchor": f"{cover_copy.get('headline', '')}；motif={cover_copy.get('motif', '')}",
            "motif": str(cover_copy.get("motif") or ""),
            "expected_elements": [str(value) for value in cover_copy.get("motif_expected", []) if str(value).strip()],
            "forbidden_elements": [str(value) for value in cover_copy.get("motif_forbidden", []) if str(value).strip()],
        },
        "body_visuals": visuals,
        "total_sections": len(headings),
        "semantic_contract": VISUAL_CONTRACT,
        "quality": _styles().get("quality", {}),
        "public_brand": public_brand(account, account_cfg),
        "cta": account_cfg.get("cta", {}),
        "background_contract": background_contract,
    }


def plan(article_dir: Path) -> int:
    article_dir.mkdir(parents=True, exist_ok=True)
    brief = _make_brief(article_dir)
    _write_yaml(article_dir / "visual-brief.yaml", brief)
    try:
        build_art_direction(article_dir, overwrite=True)
    except Exception as exc:
        print(f"VISUAL BLOCKED: 无法生成 art-direction.yaml：{exc}", file=sys.stderr)
        return 1
    brand = str(brief.get("public_brand") or public_brand(brief.get("account") or _default_account(), _styles().get("accounts", {}).get(brief.get("account") or _default_account(), {})))
    cover_contract = brief.get("cover", {}) if isinstance(brief.get("cover"), dict) else {}
    units: list[dict[str, Any]] = [{
        "id": "cover",
        "section_heading": "封面",
        "viewer_job": f"首屏识别文章主题和 {brand} 品牌",
        "expected_elements": [str(value) for value in cover_contract.get("expected_elements", []) if str(value).strip()] or [brand],
        "forbidden_elements": [str(value) for value in cover_contract.get("forbidden_elements", []) if str(value).strip()],
        "cover_motif": str(cover_contract.get("motif") or ""),
        "claim_ids": [],
        "render_backend": "agnes-or-brand-cover",
        "output": "imgs/cover.png",
        "asset": "imgs/cover.png",
        "generation_mode": "agnes",
        "provider": "agnes",
        "source_excerpt_sha256": "",
        "public_brand": brand,
        "content_signal": "cover",
        "canvas_background": "",
    }]
    for item in brief["body_visuals"]:
        units.append({
            "id": item["id"],
            "section_heading": item["section_heading"],
            "section_index": item.get("section_index", 0),
            "cognitive_role": item.get("cognitive_role", "bridge"),
            "visual_type": item["visual_type"],
            "viewer_job": item["purpose"],
            "expected_elements": item["expected_elements"],
            "forbidden_elements": item["forbidden_elements"],
            "claim_ids": item["claim_ids"],
            "render_backend": item["render_backend"],
            "requested_backend": item.get("requested_backend", item["render_backend"]),
            "execution_backend": item.get("execution_backend", item["render_backend"]),
            "fallback_reason": item.get("fallback_reason", ""),
            "content_signal": item.get("content_signal", "concept"),
            "semantic_features": item.get("semantic_features", {}),
            "route_rule": item.get("route_rule", ""),
            "route_reason": item.get("route_reason", ""),
            "route_confidence": item.get("route_confidence", 1.0),
            "recommended_skill": item.get("recommended_skill", ""),
            "layout_archetype": item.get("layout_archetype", ""),
            "diagram_data": item.get("diagram_data", {}),
            "secondary_backend": item.get("secondary_backend", ""),
            "secondary_skill": item.get("secondary_skill", ""),
            "skill_evaluation": item.get("skill_evaluation", []),
            "geometry_required": bool(item.get("geometry_required")),
            "canvas_background": item.get("canvas_background", ""),
            "surface_background": item.get("surface_background", ""),
            "public_brand": brand,
            "output": item["asset"],
            "asset": item["asset"],
            "generation_mode": "deterministic",
            "provider": "local-deterministic",
            "source_raster_required": True,
            "source_excerpt": item["source_excerpt"],
            "source_excerpt_sha256": item["source_excerpt_sha256"],
            "semantic_threshold": item["semantic_threshold"],
            **{
                key: item[key]
                for key in ("code", "code_snippet", "code_hint", "language", "code_style")
                if item.get(key) not in (None, "", [])
            },
        })
    # Make the explanatory argument explicit at planning time.  The helper
    # only binds evidence that already exists in evidence-plan.json; missing
    # claims/evidence stay pending and are intentionally blocked later.
    units = [
        _enrich_depth_unit(unit, article_dir) if str(unit.get("id") or "") != "cover" else unit
        for unit in units
    ]
    (article_dir / "visual-contract.json").write_text(
        json.dumps({"schema_version": 1, "contract": VISUAL_CONTRACT, "status": "planned", "lifecycle_status": "planned", "unit_execution_status": "planned", "main_gate_status": "not_advanced", "background_contract": brief.get("background_contract", {}), "units": units}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (article_dir / "visual-routing.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "contract": "visual-semantic-routing-v1",
                "status": "planned",
                "router": "scripts/visual_semantic_router.py",
                "decision_order": [rule["id"] for rule in RULES],
                "routes": [
                    {
                        "id": item["id"],
                        "section": item["section_heading"],
                        "primary_backend": item["render_backend"],
                        "secondary_backend": item.get("secondary_backend", ""),
                        "route_rule": item.get("route_rule", ""),
                        "route_reason": item.get("route_reason", ""),
                        "recommended_skill": item.get("recommended_skill", ""),
                        "layout_archetype": item.get("layout_archetype", ""),
                        "route_confidence": item.get("route_confidence", 1.0),
                        "semantic_features": item.get("semantic_features", {}),
                        "skill_evaluation": item.get("skill_evaluation", []),
                    }
                    for item in brief["body_visuals"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (article_dir / "skill-evaluation.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "contract": "visual-skill-evaluation-v1",
                "status": "planned",
                "registry": "profiles/visual-capability-registry.yaml",
                "routes": [
                    {
                        "id": item["id"],
                        "section": item["section_heading"],
                        "evaluations": item.get("skill_evaluation", []),
                    }
                    for item in brief["body_visuals"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (article_dir / "visual-semantic-review.json").write_text(
        json.dumps({"schema_version": 1, "contract": VISUAL_CONTRACT, "status": "pending", "records": []}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        f"# 图片计划｜{brief['title']}",
        "",
        f"- 账号：{brief['account']}",
        f"- 排版主题：`{brief['formatter_theme']}`",
        f"- 图像主题：`{brief['image_theme']}`",
        f"- 视觉方向：{brief['art_direction']}",
        "- 封面：生成 2～3 个候选，选择后才能通过配图门禁。",
        "- 正文：依据章节正文任务路由到 KaTeX 数学图、Mermaid/SVG 关系图、时间线或 Agnes 概念插画；技术图不得退化为通用文字卡片。",
        "- 深度合同：每张正文图必须声明 reader_question、answer_sentence、typed relations、claim/evidence IDs 与 textual-outline fallback；证据未通过时保持 pending 并阻断 illustrated。",
        "",
        "| 编号 | 章节 | 图像类型 | 认知作用 | 文件 | 替代文本 | 状态 |",
        "|---:|---|---|---|---|---|---|",
    ]
    for item in brief["body_visuals"]:
        lines.append(f"| {item['id']} | {item['section']} | {item['kind']} | {item['purpose']} | `{item['asset']}` | {item['alt']} | {item['status']} |")
    (article_dir / "image-plan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    source_assets = [{
        "path": str(brief["cover"]["asset"]),
        "origin": "generated",
        "source": "",
        "license": "",
        "reuse_approved": False,
    }]
    source_assets.extend({
        "path": str(item["asset"]),
        "origin": "generated",
        "source": "",
        "license": "",
        "reuse_approved": False,
    } for item in brief["body_visuals"])
    (article_dir / "image-sources.json").write_text(
        json.dumps({"schema_version": 1, "status": "pending", "assets": source_assets}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"VISUAL PLAN CREATED: {article_dir / 'visual-brief.yaml'}")
    return 0


def approve(article_dir: Path, reason: str, reviewer_type: str = "agent", reviewer: str = "codex", signed_by: str = "") -> int:
    path = article_dir / "visual-brief.yaml"
    brief = _yaml(path)
    if not brief:
        print("VISUAL BLOCKED: 缺少 visual-brief.yaml，请先运行 plan", file=sys.stderr)
        return 1
    approval = brief.setdefault("approval", {})
    if reviewer_type not in {"agent", "human"} or not reviewer.strip():
        print("VISUAL BLOCKED: reviewer_type 必须是 agent/human 且 reviewer 不能为空", file=sys.stderr)
        return 1
    if reviewer_type == "human" and not signed_by.strip():
        print("VISUAL BLOCKED: human 封面审批必须提供 --signed-by 人工触发身份", file=sys.stderr)
        return 1
    approval.update({
        "cover_selection": "approved",
        "approved_by": reviewer.strip(),
        "reviewer_type": reviewer_type,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
    })
    _write_yaml(path, brief)
    # A3（对抗审查）：封面批准同时写入 append-only 批准事件账本。
    # 门禁不再信任 brief 内自报的 reviewer_type，而是校验 approval-events.json。
    try:
        from record_approval import record as record_approval_event

        record_approval_event(
            article_dir,
            subject="cover_selection",
            reviewer_type=reviewer_type,
            reviewer=reviewer.strip(),
            scope="visual-brief.yaml",
            signed_by=signed_by.strip(),
            summary=reason,
            operator=reviewer.strip() or "visual_qa.py",
        )
    except Exception as exc:  # noqa: BLE001 - 事件账本写入失败视为批准无效
        print(f"VISUAL BLOCKED: 批准事件账本写入失败：{exc}", file=sys.stderr)
        return 1
    print("VISUAL PLAN APPROVED: cover_selection=approved")
    return 0


def _image_size(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as image:
            return image.size
    except (ImportError, OSError):
        return None


def _pixel_text_scrub(path: Path) -> list[str]:
    """Pixel-level sanity scan: blank ratio, extreme aspect, suspicious
    uniform color blocks.  Designed to catch AI-generated images that
    were rendered with garbled text in a single corner (a common
    Agnes / ImageGen failure mode).
    """
    issues: list[str] = []
    try:
        from PIL import Image, ImageStat  # type: ignore
    except ImportError:
        return issues  # Pillow not available -> skip silently
    try:
        with Image.open(path) as raw:
            image = raw.convert("RGB") if raw.mode != "RGB" else raw
            w, h = image.size
            # 1. Blank-ratio check: if >95% pixels are within 5 of each other
            #    (essentially the same color), the image is likely empty.
            stat = ImageStat.Stat(image)
            stddev = sum(stat.stddev) / 3.0
            if stddev < 2.0:
                issues.append(
                    f"图片几乎全空白或纯色：{path.name}（stddev={stddev:.2f}）"
                )
            # 2. Aspect ratio: anything > 4:1 or < 1:4 is suspicious for
            #    body article images (mobile width).
            if w > 0 and h > 0:
                ratio = w / h
                if ratio > 4.0 or ratio < 0.25:
                    issues.append(
                        f"图片宽高比异常：{path.name}（{w}x{h}，ratio={ratio:.2f}）"
                    )
            # 3. Bottom-right quadrant black/white block detection
            #    (common AI artifact signature).
            q_w, q_h = w // 2, h // 2
            if q_w > 0 and q_h > 0:
                quadrant = image.crop((w - q_w, h - q_h, w, h))
                q_stat = ImageStat.Stat(quadrant)
                q_stddev = sum(q_stat.stddev) / 3.0
                q_mean = sum(q_stat.mean) / 3.0
                # Solid block (low variance) that is near-black or near-white
                # in the corner often indicates AI watermark / signature
                # artifact rather than genuine content.
                if q_stddev < 3.0 and (q_mean < 8 or q_mean > 248):
                    issues.append(
                        f"图片右下角疑似 AI 签名/水印残留：{path.name}（mean={q_mean:.1f}, stddev={q_stddev:.1f}）"
                    )
    except (OSError, ValueError):
        issues.append(f"无法加载图片做像素扫描：{path.name}")
    return issues


def _image_refs(article_dir: Path) -> list[str]:
    html = (article_dir / "article.html").read_text(encoding="utf-8", errors="replace") if (article_dir / "article.html").is_file() else ""
    return re.findall(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", html, flags=re.I)


def _glyph_component_count(path: Path, max_dim: int = 240) -> int:
    """Lightweight readable-text detector (RC2).

    Counts small connected ink components in a downscaled grayscale copy.
    Natural-language text (CJK or Latin) appears as many tiny disconnected
    strokes, far more than a clean metaphor illustration carries.  This is a
    cheap, dependency-light stand-in for OCR: it will not name the words, but
    it reliably flags "this AI image is full of readable glyphs" — exactly the
    failure mode where Agnes renders fake QUERY/K/V labels into a cover.

    Returns the number of small ink components, or -1 if Pillow is unavailable
    or the image cannot be read.
    """
    try:
        from PIL import Image
    except ImportError:
        return -1
    try:
        with Image.open(path) as raw:
            image = raw.convert("L")
            w, h = image.size
            scale = max_dim / float(max(w, h))
            image = image.resize((max(1, int(w * scale)), max(1, int(h * scale))))
            pixel_reader = getattr(image, "get_flattened_data", image.getdata)
            px = list(pixel_reader())
        n = len(px)
        if n == 0:
            return -1
        # Background = most common intensity.  Text may be dark-on-light or
        # light-on-dark, so ink = pixels far from background on either side.
        hist: list[int] = [0] * 256
        for v in px:
            hist[v] += 1
        background = int(max(range(256), key=lambda i: hist[i]))
        mean = sum(px) / n
        std = (sum((v - mean) ** 2 for v in px) / n) ** 0.5
        delta = max(24, std * 0.8)
        ink = [1 if abs(v - background) > delta else 0 for v in px]
        ww, hh = image.size
        # Connected-component flood fill on the 1D ink list.
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for y in range(hh):
            for x in range(ww):
                i = y * ww + x
                if not ink[i]:
                    continue
                if x > 0 and ink[i - 1]:
                    union(i, i - 1)
                if y > 0 and ink[i - ww]:
                    union(i, i - ww)
        comp_size: dict[int, int] = {}
        for i in range(n):
            if ink[i]:
                r = find(i)
                comp_size[r] = comp_size.get(r, 0) + 1
        # Text shows up as many *small* components (individual strokes/glyphs).
        return sum(1 for size in comp_size.values() if 3 <= size <= 140)
    except (OSError, ValueError):
        return -1


# Above this many small ink components an AI image is very likely carrying
# readable (and therefore fake, since it should be textless) text.
TEXT_COMPONENT_BLOCK_THRESHOLD = 45

# 增强 1：正文图信息密度门禁阈值。低于该 glyph 数视为"空内容/占位图"：
# 空洞图（孤立圆圈）glyph≈0，仅标题 glyph≈3，真实要点卡/代码卡 ≥19。
MIN_BODY_INFO_GLYPHS = 12


def _hydrate_editable_sources(article_dir: Path, contract: dict[str, Any]) -> bool:
    """Backfill deterministic diagram sources into legacy visual contracts.

    Older generated contracts recorded the raster output and backend but left
    ``diagram_source`` empty, even though ``image-sources.json`` already held
    the editable source path in ``generation.diagram_source``.  The semantic
    QA gate must validate the actual editable artifact, so copy that path into
    the contract before invoking the checker.  This is a provenance repair;
    it does not approve or regenerate any image.
    """
    source_doc_path = article_dir / "image-sources.json"
    if not source_doc_path.is_file() or not isinstance(contract.get("units"), list):
        return False
    try:
        source_doc = json.loads(source_doc_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    assets = source_doc.get("assets") if isinstance(source_doc, dict) else None
    if not isinstance(assets, list):
        return False
    by_path: dict[str, dict[str, Any]] = {}
    for item in assets:
        if not isinstance(item, dict):
            continue
        raw_path = str(item.get("path") or "").strip().replace("\\", "/")
        generation = item.get("generation") if isinstance(item.get("generation"), dict) else {}
        source = str(generation.get("diagram_source") or "").strip().replace("\\", "/")
        if raw_path and (not source or (article_dir / source).is_file()):
            by_path[raw_path] = generation
    changed = False
    for unit in contract.get("units", []):
        if not isinstance(unit, dict):
            continue
        existing = str(unit.get("diagram_source") or unit.get("editable_source") or "").strip()
        if str(unit.get("id") or "") != "cover" and existing and (article_dir / existing).is_file():
            continue
        output = str(unit.get("output") or unit.get("asset") or "").strip().replace("\\", "/")
        generation = by_path.get(output, {})
        source = str(generation.get("diagram_source") or "").strip().replace("\\", "/")
        if source and (article_dir / source).is_file():
            unit["diagram_source"] = source
            changed = True
        requested_provider = str(generation.get("requested_provider") or "").strip()
        execution_provider = str(generation.get("provider") or "").strip()
        if requested_provider:
            unit["requested_provider"] = requested_provider
        if execution_provider:
            unit["provider"] = execution_provider
            unit["execution_provider"] = execution_provider
        if requested_provider and execution_provider and requested_provider.lower() != execution_provider.lower() and not str(unit.get("fallback_reason") or "").strip():
            unit["fallback_reason"] = f"requested_provider={requested_provider}; execution_provider={execution_provider}"
        if requested_provider or execution_provider:
            changed = True
    if changed and os.environ.get("WORKFLOW_GATE_CHECK") != "1":
        contract_path = article_dir / "visual-contract.json"
        contract_path.write_text(
            json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return changed


def check(article_dir: Path, reviewer_type: str = "agent", reviewer: str = "codex") -> int:
    errors: list[str] = []
    warnings: list[str] = []
    brief = _yaml(article_dir / "visual-brief.yaml")
    if not brief:
        errors.append("缺少 visual-brief.yaml")
    else:
        approval = brief.get("approval", {})
        if approval.get("cover_selection") != "approved":
            errors.append("封面候选尚未人工确认：approval.cover_selection 必须为 approved")
        if str(approval.get("approved_by", "")).strip() == "":
            errors.append("视觉简报缺少 approved_by")
        if str(approval.get("reviewer_type", "")).strip() not in {"agent", "human"}:
            errors.append("视觉简报缺少 reviewer_type（agent/human）")
        if not brief.get("formatter_theme") or not brief.get("image_theme"):
            errors.append("视觉简报缺少排版主题或图像主题")
        cover_contract = brief.get("cover", {}) if isinstance(brief.get("cover"), dict) else {}
        if not str(cover_contract.get("motif") or "").strip():
            errors.append("视觉简报缺少封面 motif；封面不能只校验标题文字")
        if not isinstance(cover_contract.get("expected_elements"), list) or not cover_contract.get("expected_elements"):
            errors.append("视觉简报缺少封面 expected_elements")
        if not isinstance(cover_contract.get("forbidden_elements"), list) or not cover_contract.get("forbidden_elements"):
            errors.append("视觉简报缺少封面 forbidden_elements")

    imgs = article_dir / "imgs"
    cover = next((p for p in imgs.glob("cover.*") if p.suffix.lower().lstrip(".") in {"png", "jpg", "jpeg", "webp"}), None)
    if cover is None:
        errors.append("缺少 imgs/cover.*")
    files: list[Path] = [cover] if cover else []
    body_visuals = brief.get("body_visuals", []) if isinstance(brief, dict) else []
    if brief and not body_visuals:
        errors.append("visual-brief.yaml 没有正文认知锚点")
    if isinstance(body_visuals, list):
        errors.extend(f"视觉锚点映射：{issue}" for issue in _authored_asset_mapping_errors(article_dir, body_visuals))
    for item in body_visuals if isinstance(body_visuals, list) else []:
        raw = str(item.get("asset", ""))
        path = (article_dir / raw).resolve()
        if not path.is_file():
            errors.append(f"视觉简报引用的图片不存在：{raw}")
        else:
            files.append(path)
        if not str(item.get("alt", "")).strip():
            errors.append(f"图片缺少替代文本：{raw}")
        if len(str(item.get("purpose", "")).strip()) < 6:
            errors.append(f"图片缺少明确认知作用：{raw}")
        if not isinstance(item.get("claim_ids"), list) or not [str(value).strip() for value in item.get("claim_ids", []) if str(value).strip()]:
            errors.append(f"视觉锚点缺少显式 claim_ids：{raw}；禁止把整篇文章 claims 静默绑定到本节")

    # Enhancement #8: 正文视觉锚点的空间分布与认知角色校验
    if body_visuals:
        total_sections = int(brief.get("total_sections", len(body_visuals)) or len(body_visuals))
        for issue in _visual_distribution_issues(body_visuals, total_sections):
            errors.append(f"视觉分布校验：{issue}")
        roles = [str(item.get("cognitive_role", "")).strip() or "bridge" for item in body_visuals]
        if len(set(roles)) == 1 and len(body_visuals) >= 4:
            warnings.append(f"全部 {len(body_visuals)} 张正文图都是同一认知角色 '{roles[0]}'，建议混合 opener/mechanism/proof/closer 等角色")

    hashes: dict[str, Path] = {}
    dimensions: list[str] = []
    for path in files:
        if not path or not path.is_file():
            continue
        if path.stat().st_size < 1024:
            errors.append(f"图片文件过小或可能损坏：{path.name}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in hashes:
            errors.append(f"图片重复：{hashes[digest].name} 与 {path.name}；每张认知锚点图必须有独立信息作用")
        hashes[digest] = path
        size = _image_size(path)
        if size:
            dimensions.append(f"{path.name}={size[0]}x{size[1]}")
            if size[0] < 600 or size[1] < 300:
                errors.append(f"图片尺寸不足 600x300：{path.name}={size[0]}x{size[1]}")
        else:
            errors.append(f"无法读取图片尺寸：{path.name}；需安装 Pillow 或提供可校验的 PNG/JPG/WebP")
        # Pixel-level text-content sanity scan (catches AI garbled text,
        # # watermark residue, blank images, extreme aspect ratios).
        for issue in _pixel_text_scrub(path):
            warnings.append(issue)
        # 增强 1：正文图信息密度门禁——用轻量字形连通域计数近似"可见文字成分"。
        # 空洞占位图（孤立圆圈/纯色块/仅标题）的 glyph 数极低（0~5），
        # 而真实要点卡/代码卡通常 ≥19。封面是品牌横幅，允许文字较少，不检查。
        if not path.name.startswith("cover"):
            glyphs = _glyph_component_count(path)
            if glyphs >= 0 and glyphs < MIN_BODY_INFO_GLYPHS:
                errors.append(
                    f"正文图信息密度过低（疑似空内容/占位图）：{path.name}"
                    f"（glyph={glyphs}，需 ≥{MIN_BODY_INFO_GLYPHS}）"
                )

    refs = _image_refs(article_dir)
    for raw in refs:
        if raw.startswith(("http://", "https://", "data:")):
            continue
        if not (article_dir / raw).is_file():
            errors.append(f"HTML 引用的图片不存在：{raw}")
    if any("placeholder" in raw.lower() for raw in refs):
        errors.append("HTML 残留 placeholder 图片")
    expected_refs = {
        str(item.get("asset", "")).strip()
        for item in body_visuals
        if isinstance(item, dict) and str(item.get("asset", "")).strip()
    }
    cover_data = brief.get("cover", {}) if isinstance(brief, dict) else {}
    cover_asset = str(
        cover_data.get("selected") or cover_data.get("asset") or ""
    ).strip() if isinstance(cover_data, dict) else ""
    formula_refs: set[str] = set()
    formula_manifest = article_dir / "formula-manifest.json"
    if formula_manifest.is_file():
        try:
            formula_doc = json.loads(formula_manifest.read_text(encoding="utf-8"))
            formula_refs = {
                str(item.get("output", "")).strip()
                for item in formula_doc.get("formulas", [])
                if isinstance(item, dict) and str(item.get("output", "")).strip()
            }
        except (OSError, json.JSONDecodeError):
            formula_refs = set()
    # The cover is a separately uploaded WeChat thumbnail.  If the formatter
    # also places it in the body, ignore that one optional reference while
    # keeping the body-anchor comparison exact.
    evidence_refs = _hybrid_evidence_paths(article_dir)
    actual_refs = {
        raw for raw in refs
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
    source_path = article_dir / "image-sources.json"
    generation_plan_path = article_dir / "image-generation-plan.json"
    director_plan_path = article_dir / "visual-director-plan.json"
    # Legacy fixtures may stop at visual_qa.plan; once a generation plan is
    # present, the new director/provenance contract becomes mandatory.
    if generation_plan_path.is_file() or director_plan_path.is_file():
        generation_plan = json.loads(generation_plan_path.read_text(encoding="utf-8")) if generation_plan_path.is_file() else {}
        director_plan = json.loads(director_plan_path.read_text(encoding="utf-8")) if director_plan_path.is_file() else {}
        if generation_plan_path.is_file() and not (article_dir / "art-direction.yaml").is_file():
            errors.append("生成计划存在但缺少 art-direction.yaml；必须先锁定本篇视觉论点与 fallback")
        # RC1/RC4: the compiled prompt bodies must obey the prompt contract
        # (no operational metadata, has negative constraint).  Validate here
        # so a leaking prompt is caught at the gate, not in production.
        for violation in _validate_prompt_plan(article_dir):
            errors.append(f"提示词契约违规：{violation}")
        if not director_plan_path.is_file() or director_plan.get("contract") != "visual-director-v1":
            errors.append("缺少有效 visual-director-plan.json")
        elif director_plan.get("status") not in {"ready", "approved", "generated"}:
            errors.append("visual-director-plan.json 尚未通过 ready/approved 状态")
        if not generation_plan_path.is_file() or generation_plan.get("generation_contract") != GENERATION_CONTRACT:
            errors.append("缺少有效 image-generation-plan.json（generation_contract=prompt-v2）")
        elif not isinstance(generation_plan.get("prompt_files"), list) or not generation_plan.get("prompt_files"):
            errors.append("image-generation-plan.json 缺少 prompt_files")
        elif generation_plan.get("status") not in {"generated", "partial"}:
            errors.append("image-generation-plan.json 尚未记录执行结果")
        contract_path = article_dir / "visual-contract.json"
        if not contract_path.is_file():
            errors.append("缺少 visual-contract.json；每张图片必须有正文语义合同")
        else:
            # Repair legacy contracts before semantic QA: deterministic
            # sources are already recorded in image-sources.json, but older
            # contracts omitted diagram_source and therefore failed closed.
            _hydrate_editable_sources(article_dir, json.loads(contract_path.read_text(encoding="utf-8")))
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            if contract.get("contract") != VISUAL_CONTRACT:
                errors.append("visual-contract.json contract 无效")
            for unit in contract.get("units", []) if isinstance(contract.get("units"), list) else []:
                if isinstance(unit, dict) and str(unit.get("id")) != "cover" and str(unit.get("status", "")) in {"planned", ""}:
                    errors.append(f"视觉合同素材尚未生成：{unit.get('id', '')}")
        semantic_report = article_dir / "visual-semantic-review.json"
        if not SEMANTIC_QA.is_file():
            errors.append("视觉语义检查器缺失")
        else:
            semantic_result = subprocess.run(
                [sys.executable, str(SEMANTIC_QA), "--article", str(article_dir),
                 "--reviewer-type", reviewer_type, "--reviewer", reviewer],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if semantic_result.returncode:
                detail = (semantic_result.stdout + semantic_result.stderr).strip().splitlines()
                errors.append("图片语义检查失败：" + (detail[-1] if detail else "无输出"))
    # P0 sidecar checks: visual contract drift is blocking.  This command is
    # the machine QA layer; human taste is reported explicitly below and is
    # enforced by workflow_gate.py before illustrated can advance.
    if (article_dir / "visual-routing.json").is_file() or (article_dir / "visual-contract.json").is_file():
        contract_audit = audit_visual_contract(article_dir, write=True)
        for issue in contract_audit.get("errors", []):
            errors.append(f"视觉合同审计：{issue}")
        for issue in contract_audit.get("warnings", []):
            warnings.append(f"视觉合同提示：{issue}")
    # A machine re-check must not erase a prior human taste approval.  Carry
    # the approval forward only when the existing receipt is bound to the
    # current visual brief/contract; build_review will recompute its asset
    # hashes and downgrade stale approvals.
    try:
        existing_raw = json.loads((article_dir / "visual-taste-review.json").read_text(encoding="utf-8"))
        existing_taste = existing_raw if isinstance(existing_raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        existing_taste = {}
    existing_rubric = existing_taste.get("rubric") if isinstance(existing_taste, dict) else {}
    preserve_human = (
        isinstance(existing_rubric, dict)
        and existing_rubric.get("human_review_status") == "passed"
        and str(existing_rubric.get("human_reviewer") or "").strip()
        and existing_taste.get("status") == "passed"
    )
    taste_review = build_visual_taste_review(
        article_dir,
        write=True,
        human_approved=bool(preserve_human),
        human_reviewer=str(existing_rubric.get("human_reviewer") or "") if preserve_human else "",
    )
    for issue in taste_review.get("errors", []):
        errors.append(f"审美旁路审计：{issue}")
    for issue in taste_review.get("warnings", []):
        warnings.append(f"审美旁路提示：{issue}")
    source_doc = json.loads(source_path.read_text(encoding="utf-8")) if source_path.is_file() else {}
    assets = source_doc.get("assets") if isinstance(source_doc, dict) else None
    if isinstance(assets, list):
        changed = False
        try:
            schema_version = int(source_doc.get("schema_version", 1) or 1)
        except (TypeError, ValueError):
            schema_version = 1
        contract_active = source_doc.get("generation_contract") == GENERATION_CONTRACT or schema_version >= 2
        for item in assets:
            if not isinstance(item, dict):
                continue
            raw_path = str(item.get("path", "")).strip()
            origin = str(item.get("origin", "")).strip().lower()
            if source_doc.get("status") == "passed":
                if origin not in {"generated", "reused", "user_provided", "external"}:
                    errors.append(f"素材 {raw_path} 缺少有效 origin")
                if not str(item.get("source", "")).strip() or not str(item.get("license", "")).strip():
                    errors.append(f"素材 {raw_path} 缺少 source/license 元数据")
                if origin == "reused":
                    if item.get("reuse_approved") is not True:
                        errors.append(f"复用素材 {raw_path} 缺少 reuse_approved: true")
                    if not str(item.get("source_ref", "") or item.get("source_article", "")).strip():
                        errors.append(f"复用素材 {raw_path} 缺少 source_ref")
                    if not str(item.get("reuse_reason", "")).strip():
                        errors.append(f"复用素材 {raw_path} 缺少 reuse_reason")
                if contract_active and origin == "generated":
                    generation = item.get("generation")
                    if not isinstance(generation, dict):
                        errors.append(f"生成素材 {raw_path} 缺少 generation provenance")
                    else:
                        for field in ("provider", "model", "method", "prompt_file", "prompt_sha256", "request_sha256", "visual_owner", "viewer_job", "fallback"):
                            if not str(generation.get(field, "")).strip():
                                errors.append(f"生成素材 {raw_path} 缺少 generation.{field}")
                        prompt_raw = str(generation.get("prompt_file", "")).strip()
                        prompt_path = (article_dir / prompt_raw).resolve() if prompt_raw else None
                        if prompt_path and not prompt_path.is_file():
                            errors.append(f"生成素材 {raw_path} 的提示词文件不存在：{prompt_raw}")
                        elif prompt_path and str(generation.get("prompt_sha256", "")).lower() != sha256_file(prompt_path):
                            errors.append(f"生成素材 {raw_path} 的 prompt_sha256 不匹配：{prompt_raw}")
                        provider = str(generation.get("provider", "")).strip().lower()
                        model = str(generation.get("model", "")).strip().lower()
                        if provider == "agnes" and model != "agnes-image-2.1-flash":
                            errors.append(f"生成素材 {raw_path} 的 Agnes model 不正确：{model}")
            if raw_path.startswith(("http://", "https://", "data:")):
                continue
            asset_path = (article_dir / raw_path).resolve()
            if asset_path.is_file():
                digest = sha256_file(asset_path)
                if item.get("sha256") != digest:
                    item["sha256"] = digest
                    changed = True
                # RC2: an Agnes-generated (illustrative) image must be
                # textless; all real text/labels belong in the HTML/SVG
                # overlay layer.  This cheap connected-component heuristic is a
                # *safety net*: a hard OCR gate is the production-grade control,
                # but shipping it as an error would false-block legitimate
                # metaphor illustrations that also contain many small dark
                # regions.  So it flags as a warning the operator must eyeball.
                gen = item.get("generation") if isinstance(item.get("generation"), dict) else {}
                provider = str(gen.get("provider", "")).strip().lower()
                # Covers are intentionally composed from an Agnes background
                # plus a deterministic, auditable English overlay.  Counting
                # that approved overlay as suspected Agnes pseudo-text creates
                # a perpetual false warning; body illustrations remain under
                # the textless-image heuristic.
                intentional_cover_overlay = _intentional_cover_overlay(raw_path, gen)
                if provider == "agnes" and not intentional_cover_overlay and asset_path.suffix.lower().lstrip(".") in {"png", "jpg", "jpeg", "webp"}:
                    glyphs = _glyph_component_count(asset_path)
                    if glyphs >= TEXT_COMPONENT_BLOCK_THRESHOLD:
                        warnings.append(
                            f"生成素材 {raw_path} 可能含有可读文字/伪造标签"
                            f"（连通域数={glyphs}，阈值={TEXT_COMPONENT_BLOCK_THRESHOLD}）；"
                            f"Agnes 图应画面无文字，请确认是插画纹理而非鬼画文字"
                        )
        if changed:
            source_path.write_text(json.dumps(source_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if source_doc.get("status") == "passed" and generation_plan_path.is_file():
        plan_doc = json.loads(generation_plan_path.read_text(encoding="utf-8"))
        pending = [str(item.get("id")) for item in plan_doc.get("prompt_files", []) if isinstance(item, dict) and str(item.get("status", "")) == "planned"]
        if pending:
            errors.append("image-generation-plan.json 仍有未执行素材：" + ", ".join(pending))
    report = [
        "# 图片质量报告",
        "",
        f"- 检查时间：{datetime.now(timezone.utc).isoformat()}",
        f"- 图片文件：{len(files)}",
        f"- HTML 图片引用：{len(refs)}",
        f"- 尺寸：{', '.join(dimensions) if dimensions else '未读取'}",
        f"- 正文画布背景：{((brief.get('background_contract') or {}).get('canvas_hex') if isinstance(brief, dict) else '') or '未声明'}（封面独立策略）",
        "- 几何拓扑：由 visual_semantic_qa.py 调用 visual_geometry_qa.py；关系图无合同则阻断",
        f"- 视觉合同审计：{(article_dir / 'visual-contract-audit.json').name if (article_dir / 'visual-contract-audit.json').is_file() else '未生成'}",
        f"- 审美旁路审计：{(article_dir / 'visual-taste-review.json').name if (article_dir / 'visual-taste-review.json').is_file() else '未生成'}（机器检查与人眼审美分离）",
        f"- 重复提示：{'；'.join(warnings) if warnings else '无'}",
        "",
        "## 结果",
        "",
        f"- 错误：{len(errors)}",
        f"- 警告：{len(warnings)}",
        "- 移动端预览：请在 `final_reviewed` 门禁中确认 390px 宽度截图。",
    ]
    (article_dir / "img_analysis.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    if errors:
        print("VISUAL QA BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    if _taste_review_passed(taste_review):
        print("VISUAL QA PASSED")
    else:
        print("VISUAL QA MACHINE CHECKS PASSED; HUMAN TASTE REVIEW PENDING")
    for warning in warnings:
        print(f"- warning: {warning}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "approve", "check"):
        command = sub.add_parser(name)
        command.add_argument("--article", required=True)
        if name == "approve":
            command.add_argument("--reason", required=True)
            command.add_argument("--signed-by", default="", help="human 审批的人工触发身份")
        if name in ("approve", "check"):
            command.add_argument("--reviewer-type", choices=("agent", "human"), default="agent")
            command.add_argument("--reviewer", default="codex")
    args = parser.parse_args()
    article_dir = _article_dir(args.article)
    if args.command == "plan":
        return plan(article_dir)
    if args.command == "approve":
        return approve(article_dir, args.reason, args.reviewer_type, args.reviewer, args.signed_by)
    return check(article_dir, args.reviewer_type, args.reviewer)


if __name__ == "__main__":
    raise SystemExit(main())
