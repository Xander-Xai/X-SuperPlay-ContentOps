#!/usr/bin/env python3
"""Check that a deterministic visual makes the promised visual argument.

The existing semantic checker verifies labels and provenance.  That is
necessary but not sufficient: a stale renderer can place every expected word
in a bullet list while still failing to show a flow, comparison, code path, or
decision.  This checker is intentionally small and dependency-free (apart
from the repository's JSON contract) and focuses on visible SVG structure.

It is a hard gate for deterministic technical visuals.  Illustrative images
still require the byte-bound vision receipt handled by visual_semantic_qa.py.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from PIL import Image  # type: ignore
except ImportError:  # pragma: no cover - source checks remain useful
    Image = None


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "visual-content-qa-v1"

RELATION_TYPES = {"architecture", "flow", "relationship", "branch", "diagram", "timeline"}
COMPARISON_TYPES = {"comparison", "data", "numeric", "evidence"}
CODE_TYPES = {"code", "pseudocode", "implementation", "algorithm"}
CHECKLIST_TYPES = {"checklist"}


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _resolve(article: Path, raw: str) -> Path:
    path = Path(str(raw or ""))
    return path if path.is_absolute() else article / path


def _strip_nonvisual(source: str) -> str:
    # Metadata is an audit record, not visible evidence.  In particular, do
    # not let geometry-contract JSON make a bullet list look like a diagram.
    source = re.sub(r"<metadata\b[^>]*>.*?</metadata>", "", source, flags=re.I | re.S)
    source = re.sub(r"<script\b[^>]*>.*?</script>", "", source, flags=re.I | re.S)
    source = re.sub(r"<style\b[^>]*>.*?</style>", "", source, flags=re.I | re.S)
    return source


def _visible_text(source: str) -> str:
    text = _strip_nonvisual(source)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _count(source: str, pattern: str) -> int:
    return len(re.findall(pattern, _strip_nonvisual(source), flags=re.I | re.S))


def _has_visible_edges(source: str) -> bool:
    visible = _strip_nonvisual(source)
    return bool(
        re.search(r"data-role=[\"']edge[\"']", visible, flags=re.I)
        or re.search(r"data-role=[\"']arrowhead[\"']", visible, flags=re.I)
        or re.search(r"<marker\b", visible, flags=re.I)
    )


def _has_nodes(source: str) -> bool:
    visible = _strip_nonvisual(source)
    return bool(
        re.search(r"data-role=[\"'](?:node|lane|step)[\"']", visible, flags=re.I)
        or _count(visible, r"<rect\b") >= 3
    )


def _has_comparison_structure(source: str) -> bool:
    visible = _strip_nonvisual(source)
    # A comparison needs two visibly separated groups or a tabular header;
    # four labels alone are not a comparison.
    return bool(
        re.search(r"data-layout-archetype=[\"'](?:comparison-board|decision-matrix)[\"']", visible, flags=re.I)
        or re.search(r"\b(?:VS|对比|现有做法|结构化做法|左|右)\b", _visible_text(visible), flags=re.I)
        and _count(visible, r"<rect\b") >= 4
    )


def _has_code_structure(source: str) -> bool:
    visible = _strip_nonvisual(source)
    text = _visible_text(visible)
    if re.search(r"data-role=[\"']code[\"']|<pre\b|<code\b", visible, flags=re.I):
        return True
    line_rows = _count(visible, r"class=[\"'][^\"']*\bln\b[^\"']*[\"']")
    code_spans = _count(visible, r"class=[\"'][^\"']*\bcode\b[^\"']*[\"']")
    structured_rows = line_rows > 0 and code_spans >= line_rows
    runnable_text = "import " in text and "=" in text and "(" in text
    return bool(structured_rows or runnable_text)


def _has_checkboxes(source: str) -> bool:
    visible = _strip_nonvisual(source)
    text = _visible_text(visible)
    return bool(
        re.search(r"data-role=[\"']check(?:box|item)[\"']", visible, flags=re.I)
        or re.search(r"☐|□|✓|✔", text)
        or (re.search(r"<rect\b", visible, flags=re.I) and re.search(r"检查|切分|评估|脱敏|拒答", text))
    )


def _check_unit(article: Path, unit: dict[str, Any]) -> list[str]:
    ident = str(unit.get("id") or "unknown")
    if ident == "cover":
        source_raw = str(
            unit.get("diagram_source")
            or unit.get("editable_source")
            or unit.get("cover_overlay_source")
            or ""
        ).strip()
        source_path = _resolve(article, source_raw)
        if not source_path.is_file():
            return [f"cover: 封面可编辑语义源不存在：{source_raw or '未绑定 cover_overlay_source'}"]
        source = source_path.read_text(encoding="utf-8", errors="replace")
        visible = _visible_text(source)
        expected = [str(item).strip() for item in unit.get("expected_elements", []) if str(item).strip()]
        forbidden = [str(item).strip() for item in unit.get("forbidden_elements", []) if str(item).strip()]
        normalized_visible = re.sub(r"\s+", " ", visible).strip()
        normalized = lambda item: re.sub(r"\s+", " ", item).strip()
        missing = [item for item in expected if normalized(item) not in normalized_visible]
        errors = [f"cover: 可见源缺少 expected_elements：{', '.join(missing)}"] if missing else []
        forbidden_found = [item for item in forbidden if normalized(item) in normalized_visible]
        if forbidden_found:
            errors.append(f"cover: 可见源包含与当前主题冲突的封面标签：{', '.join(forbidden_found)}")
        motif = str(unit.get("cover_motif") or "").strip()
        if not motif:
            errors.append("cover: 视觉合同缺少 cover_motif；封面不能只校验标题文字")
        elif not re.search(rf'data-cover-motif=["\']{re.escape(motif)}["\']', source, flags=re.I):
            errors.append(f"cover: 可编辑源未绑定合同 cover_motif={motif}")
        if not re.search(r'data-cover-safe-frame=["\']150,120,830,620["\']', source, flags=re.I):
            errors.append("cover: 可编辑源缺少 150,120,830,620 safe frame；标题可能越过左侧卡片")
        line_match = re.search(r'data-cover-headline-lines=["\'](\d+)["\']', source, flags=re.I)
        if not line_match:
            errors.append("cover: 可编辑源缺少 data-cover-headline-lines；无法验收标题换行")
        return errors
    source_raw = str(unit.get("diagram_source") or unit.get("source_file") or unit.get("editable_source") or "")
    source_path = _resolve(article, source_raw)
    if not source_path.is_file():
        return [f"{ident}: 可编辑源不存在：{source_raw}"]
    source = source_path.read_text(encoding="utf-8", errors="replace")
    visible = _visible_text(source)
    expected = [str(item).strip() for item in unit.get("expected_elements", []) if str(item).strip()]
    missing = [item for item in expected if item not in visible]
    errors: list[str] = []
    if missing:
        errors.append(f"{ident}: 可见源缺少 expected_elements：{', '.join(missing)}")
    visual_type = str(unit.get("visual_type") or unit.get("kind") or "").strip().lower()
    layout = str(unit.get("layout_archetype") or "").strip().lower()
    if visual_type in RELATION_TYPES:
        if not _has_nodes(source):
            errors.append(f"{ident}: {visual_type} 没有可见节点；标签清单不能代替节点")
        if not _has_visible_edges(source):
            errors.append(f"{ident}: {visual_type} 没有可见连线/箭头；geometry metadata 不能代替画面拓扑")
    if visual_type in COMPARISON_TYPES and not _has_comparison_structure(source):
        errors.append(f"{ident}: {visual_type} 没有两组/表格对比结构；只有指标名不足以表达比较")
    if visual_type in CODE_TYPES and not _has_code_structure(source):
        errors.append(f"{ident}: {visual_type} 没有代码/伪代码结构；标题和依赖名不足以证明可运行骨架")
    if visual_type in CODE_TYPES:
        # A code card must be cropped to its content, not exported into a
        # generic 1,060px viewport.  This catches the exact failure mode where
        # the card ends around y=780 but a large blank tail remains.
        output_raw = str(unit.get("output") or unit.get("asset") or "").strip()
        output_path = _resolve(article, output_raw)
        if Image is not None and output_path.is_file():
            try:
                with Image.open(output_path) as image:
                    width, height = image.size
                line_count = max(1, len(re.findall(r'<div class=["\']ln["\']>', source, flags=re.I)))
                max_height = max(360, 54 + line_count * 24 + 80)
                if height > max_height:
                    errors.append(f"{ident}: 代码卡画布过高 {height}px > 内容上限 {max_height}px；存在底部空白或错误裁切")
                if width < 700 or width > 760:
                    errors.append(f"{ident}: 代码卡宽度 {width}px 不在 680px 卡片安全导出范围")
            except (OSError, ValueError):
                errors.append(f"{ident}: 无法读取代码卡输出尺寸：{output_raw}")
    if visual_type in CHECKLIST_TYPES and not _has_checkboxes(source):
        errors.append(f"{ident}: checklist 没有可勾选/验收结构")
    if layout == "infographic" and visual_type in RELATION_TYPES:
        errors.append(f"{ident}: relation visual 使用 generic infographic 布局；必须选 topology layout")
    return errors


def check(article: Path) -> dict[str, Any]:
    article = article.resolve()
    contract = _json(article / "visual-contract.json")
    errors: list[str] = []
    units = contract.get("units") if isinstance(contract.get("units"), list) else []
    if contract.get("contract") != "visual-contract-v1":
        errors.append("visual-contract.json contract 无效")
    if not units:
        errors.append("visual-contract.json 缺少 units")
    for unit in units:
        if isinstance(unit, dict):
            errors.extend(_check_unit(article, unit))
    return {
        "schema_version": 1,
        "contract": CONTRACT,
        "status": "passed" if not errors else "blocked",
        "article": article.name,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    args = parser.parse_args()
    result = check(args.article)
    (args.article.resolve() / "visual-content-qa.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
