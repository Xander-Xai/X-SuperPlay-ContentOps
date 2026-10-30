#!/usr/bin/env python3
"""Render an editable, deterministic visual anchor for a WeChat section.

This is the static counterpart to Agnes: exact labels and relationships are
drawn in SVG, then Chrome rasterizes the SVG to a PNG accepted by WeChat. The
SVG is kept next to the PNG so a future editor can adjust the diagram without
regenerating an AI image.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MATH_RENDERER = ROOT / "scripts" / "render_math_visual.mjs"
MERMAID_RENDERER = ROOT / "scripts" / "render_mermaid_visual.mjs"
FORMULA_CODE_RENDERER = ROOT / "scripts" / "render_formula_code_map.mjs"
CARD_DECK_RENDERER = ROOT / "scripts" / "render_interactive_card_deck.py"
EXCALIDRAW_RENDERER = ROOT / "scripts" / "render_excalidraw_style.py"
TECHNICAL_TYPES = {"qkv", "shape", "attention", "numeric", "checklist"}
CHROME_CANDIDATES = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
)



def _default_account() -> str:
    """Return the fixed account id of this split workflow target."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from account_context import ACCOUNT_ID
        return ACCOUNT_ID
    except Exception as exc:
        raise RuntimeError("workflow identity unavailable") from exc

def load_design_tokens(account: str | None = None) -> dict:
    if not account:
        account = _default_account()
    """Single-source palette for deterministic SVGs (RC3).

    Technical diagrams are predominantly the thinktank account, so the default
    is its ``design_tokens`` block in ``profiles/visual-styles.yaml``.  Falls
    back to the repository default tokens if the account omits its own.
    """
    try:
        import yaml  # type: ignore

        data = yaml.safe_load((ROOT / "profiles" / "visual-styles.yaml").read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    defaults = data.get("design_tokens_default") if isinstance(data.get("design_tokens_default"), dict) else {}
    accounts = data.get("accounts") if isinstance(data.get("accounts"), dict) else {}
    account_block = accounts.get(account, {}) if isinstance(accounts.get(account), dict) else {}
    tokens = dict(defaults)
    tokens.update({k: v for k, v in account_block.get("design_tokens", {}).items() if k and v})
    # Map the diagram renderer's historical key names onto design tokens.
    return {
        "paper": tokens.get("background", "#F4F0E8"),
        "surface": tokens.get("surface", "#FFFCF7"),
        "ink": tokens.get("ink", "#17324D"),
        "muted": tokens.get("muted", "#5E6872"),
        "accent": tokens.get("vermilion", "#B24A2B"),
        "line": tokens.get("signal", "#557A96"),
    }


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def chrome_path() -> Path | None:
    for candidate in CHROME_CANDIDATES:
        if candidate.is_file():
            return candidate
    found = shutil.which("chrome")
    return Path(found) if found else None


def canvas_height_for(visual_type: str) -> int:
    """Keep each exported canvas close to the amount of content it contains."""
    return {
        "qkv": 720,
        "shape": 520,
        "attention": 620,
        "numeric": 660,
        "multihead": 640,
        "kv-cache": 760,
        "summary-cards": 1000,
        "concept-map": 820,
        "checklist": 640,
        # RC7:代码卡是逐行内容,给足纵向空间避免尾部被裁切。
        "code": 860,
        "pseudocode": 780,
        # Enhancement #4:公式↔代码对照卡左右分栏,默认高度。
        "formula-code-map": 720,
        # Enhancement #5:信息卡组，默认 560。
        "card-deck": 560,
        # Enhancement #6:手绘草图关系图。
        "excalidraw-style": 720,
        "stateful-graph": 760,
        "checkpoint-timeline": 760,
        "runtime-boundary": 760,
        "decision-matrix": 800,
        "agent-building-map": 1200,
        # Mechanism/architecture boards need a second evidence lane and a
        # conclusion line; the previous 620px canvas forced the annotation
        # onto the bottom border.
        "architecture": 720,
        "board": 720,
        "relationship-board": 720,
        "comparison-board": 720,
        "architecture-board": 720,
        "state-loop-board": 720,
        "progressive-checklist": 640,
        "formula-code-duality": 720,
        "runnable-snippet": 860,
        "pseudocode-card": 780,
        "stacked-card-deck": 560,
        "sketch-relationship-map": 720,
        "two-lane-timeline": 760,
        "branch-and-merge": 640,
        "matrix-to-heatmap": 660,
        "tensor-shape-pipeline": 520,
        "five-stage-pipeline": 620,
        "library-retrieval-map": 720,
        "causal-map": 720,
    }.get(str(visual_type or "").strip().lower(), 620)


def nodes_for(kind: str) -> list[str]:
    value = kind.lower().strip()
    if value == "flow":
        return ["输入", "检查", "放行", "回读"]
    if value == "checklist":
        return ["有计划", "有证据", "有复核", "可交接"]
    if value in {"code", "data"}:
        return ["参数", "执行", "结果", "限制"]
    if value in {"comparison", "evidence-strip"}:
        return ["现状", "证据", "判断"]
    return ["目标", "关系", "门禁", "资产"]


def _spec_unit(spec_path: Path, spec_id: str, *, require_elements: bool = True) -> dict:
    """读取视觉合同里的单个素材单元。

    默认强制 ``expected_elements``（图上每个元素都要能在正文找到出处）。
    代码卡是唯一例外：当单元直接携带精确的 ``code`` / ``code_snippet``
    时，代码本身就是可核对的出处，调用方传 ``require_elements=False``，
    再由代码分支自己确认二者至少有一个非空。
    """
    try:
        data = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise SystemExit(f"视觉合同无法解析：{spec_path}")
    if data.get("contract") != "visual-contract-v1":
        raise SystemExit("视觉合同 contract 必须为 visual-contract-v1")
    for unit in data.get("units", []):
        if isinstance(unit, dict) and str(unit.get("id")) == spec_id:
            if require_elements and not unit.get("expected_elements"):
                raise SystemExit(f"视觉合同缺少 expected_elements：{spec_id}")
            return unit
    raise SystemExit(f"视觉合同不存在素材：{spec_id}")


def _render_math_source(spec_path: Path, spec_id: str, source_path: Path, account: str) -> dict:
    unit = _spec_unit(spec_path, spec_id)
    visual_type = str(unit.get("visual_type") or unit.get("kind") or "").strip().lower()
    if visual_type not in TECHNICAL_TYPES:
        return unit
    result = subprocess.run(
        ["node", str(MATH_RENDERER), "--spec", str(spec_path), "--spec-id", spec_id, "--output", str(source_path), "--account", account],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if result.returncode:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or f"数学视觉渲染失败：{spec_id}")
    return unit


def _render_mermaid_source(spec_path: Path, spec_id: str, source_path: Path, account: str) -> dict:
    result = subprocess.run(
        [
            "node", str(MERMAID_RENDERER),
            "--spec", str(spec_path), "--spec-id", spec_id,
            "--output", str(source_path), "--account", account,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if result.returncode:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or f"Mermaid 视觉渲染失败：{spec_id}")
    return _spec_unit(spec_path, spec_id)


def _render_formula_code_map_source(spec_path: Path, spec_id: str, source_path: Path, account: str) -> dict:
    """Enhancement #4: formula ↔ code side-by-side mapping card."""
    result = subprocess.run(
        [
            "node", str(FORMULA_CODE_RENDERER),
            "--spec", str(spec_path), "--spec-id", spec_id,
            "--output", str(source_path), "--account", account,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if result.returncode:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or f"公式代码对照卡渲染失败：{spec_id}")
    return _spec_unit(spec_path, spec_id)


def _render_card_deck_source(spec_path: Path, spec_id: str, svg_output: Path, account: str) -> dict:
    """Enhancement #5: SVG card deck + static HTML fallback."""
    html_output = svg_output.with_suffix(".fallback.html")
    result = subprocess.run(
        [
            sys.executable, str(CARD_DECK_RENDERER),
            "--spec", str(spec_path), "--spec-id", spec_id,
            "--svg-output", str(svg_output),
            "--html-output", str(html_output),
            "--account", account,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if result.returncode:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or f"卡组渲染失败：{spec_id}")
    return _spec_unit(spec_path, spec_id)


def _render_excalidraw_style_source(spec_path: Path, spec_id: str, svg_output: Path, account: str) -> dict:
    """Render native Excalidraw JSON plus SVG/PNG-compatible sidecars."""
    excalidraw_output = svg_output.with_suffix(".excalidraw.json")
    result = subprocess.run(
        [
            sys.executable, str(EXCALIDRAW_RENDERER),
            "--spec", str(spec_path), "--spec-id", spec_id,
            "--svg-output", str(svg_output),
            "--excalidraw-output", str(excalidraw_output),
            "--account", account,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if result.returncode:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or f"手绘图渲染失败：{spec_id}")
    return _spec_unit(spec_path, spec_id)


def _render_code_source(spec_path: Path, spec_id: str, source_path: Path, account: str) -> dict:
    """RC7:把视觉合同里的代码 / 伪代码渲染成账号主题的 HTML 代码卡。

    代码是精确内容，绝不能交给图像模型，因此这里走确定性渲染:
    合同的 ``code`` / ``code_snippet`` 字段是首选来源；只声明了
    ``expected_elements`` 的伪代码单元则按步骤逐行拼装，保证图上每一行
    都能在正文里找到出处。

    Enhancement #7: 返回按代码行数估计的紧凑高度，避免截图下方留空白。
    """
    from render_code_block import render_html, estimate_height  # 局部导入,避免影响纯 SVG 路径

    unit = _spec_unit(spec_path, spec_id, require_elements=False)
    kind = "pseudocode" if str(unit.get("visual_type") or unit.get("kind") or "").lower() == "pseudocode" else "code"
    snippet = str(unit.get("code") or unit.get("code_snippet") or "").strip()
    if not snippet:
        # 方案 A：contract 携带 code_hint 时优先展示人工补充提示，
        # 不再把 expected_elements 关键词列表当代码渲染。
        hint = str(unit.get("code_hint") or "").strip()
        if hint:
            expected = [str(value).strip() for value in unit.get("expected_elements", []) if str(value).strip()]
            # Keep every contract label visible in the editable code card.
            # This prevents a renderer-side wording change (e.g. “实战” vs
            # “实现”) from making semantic QA depend on a brittle substring.
            anchors = "\n".join(f"# 视觉锚点：{value}" for value in expected)
            snippet = f"{anchors}\n# {hint}" if anchors else f"# {hint}"
            kind = "pseudocode"
        else:
            steps = [str(value).strip() for value in unit.get("expected_elements", []) if str(value).strip()]
            if not steps:
                raise SystemExit(f"代码卡缺少 code/expected_elements：{spec_id}")
            snippet = "\n".join(f"{index}. {step}" for index, step in enumerate(steps, 1))
            kind = "pseudocode"
    language = str(unit.get("language") or ("text" if kind == "pseudocode" else "python")).strip()
    title = str(unit.get("section_heading") or unit.get("section") or ("伪代码" if kind == "pseudocode" else "代码实现"))
    # Q③ / Enhancement A: 从视觉合同读取 code_style 信号（teaching / production /
    # pseudocode），未声明时按 kind 推断；它决定代码卡右上角范式标签。
    code_style = str(unit.get("code_style") or ("pseudocode" if kind == "pseudocode" else "production")).strip()
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(render_html(snippet, account, title, kind, language, code_style=code_style), encoding="utf-8")
    unit["estimated_height"] = estimate_height(snippet, kind)
    return unit


def _text(x: float, y: float, value: str, *, size: int = 28, color: str = "#17324D", weight: str = "600", anchor: str = "middle", role: str = "") -> str:
    role_attr = f' data-role="{esc(role)}"' if role else ""
    return (
        f'<text{role_attr} x="{x}" y="{y}" text-anchor="{anchor}" '
        f'font-family="Times New Roman, Microsoft YaHei, Segoe UI, sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="{color}">{esc(value)}</text>'
    )


def _description_lines(value: str, limit: int = 56) -> tuple[str, str]:
    """Split a reader task without cutting identifiers such as thread_id."""
    text = str(value or "").strip()
    if len(text) <= limit:
        return text, ""
    first = text[:limit]
    candidates = [first.rfind(mark) for mark in (" ", "，", "。", "、", "：", "；")]
    cut = max(candidates)
    if cut < int(limit * 0.55):
        cut = limit
    return first[:cut].strip(), text[cut:].strip()[:limit]


def _label_lines(label: str, size: float, max_width: float) -> list[str]:
    """Wrap a node label before it reaches a connector or card boundary.

    SVG does not auto-wrap text.  A single long ``text`` node was therefore
    able to sit directly on an arrow (for example ``Embedding 一致性`` in a
    130px comparison node).  Use a small, deterministic width estimate that
    treats CJK glyphs as full-width and Latin glyphs as half-width, preserving
    words where possible and hard-breaking only as a last resort.
    """
    text = str(label or "").strip()
    if not text:
        return [""]
    units = max(1.0, max_width / max(float(size), 1.0))

    def weight(value: str) -> float:
        return sum(1.0 if ord(ch) > 0x2E80 else 0.56 for ch in value)

    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if current and weight(candidate) > units:
            lines.append(current)
            current = word
        elif not current and weight(word) > units:
            # Hard-break overlong identifiers while keeping the source text
            # semantically recoverable through normalized visible text.
            chunk = ""
            for char in word:
                if chunk and weight(chunk + char) > units:
                    lines.append(chunk)
                    chunk = char
                else:
                    chunk += char
            current = chunk
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [text]


def _centered_label(x: float, y: float, width: float, height: float, label: str, size: int) -> str:
    lines = _label_lines(label, size, max_width=max(24.0, width - 24.0))
    line_gap = size * 1.12
    first_y = y + height / 2 - (len(lines) - 1) * line_gap / 2 + size * 0.35
    tspans = "".join(
        f'{" " if idx else ""}<tspan x="{x + width / 2}" dy="{0 if idx == 0 else line_gap:.1f}">{esc(line)}</tspan>'
        for idx, line in enumerate(lines)
    )
    return (
        f'<text data-role="node" x="{x + width / 2}" y="{first_y:.1f}" text-anchor="middle" '
        f'font-family="Times New Roman, Microsoft YaHei, Segoe UI, sans-serif" font-size="{size}" '
        f'font-weight="700" fill="#17324D">{tspans}</text>'
    )


def _box(x: float, y: float, width: float, height: float, label: str, *, accent: bool = False, size: int = 24, palette: dict | None = None) -> str:
    palette = palette or load_design_tokens()
    stroke = palette["accent"] if accent else palette["line"]
    return (
        f'<rect data-role="node" data-node-id="{esc(label)[:40]}" data-node-bbox="{x},{y},{width},{height}" x="{x}" y="{y}" width="{width}" height="{height}" rx="16" '
        f'fill="{palette["paper"]}" stroke="{stroke}" stroke-width="3"/>'
        + _centered_label(x, y, width, height, label, size)
    )


def _arrow(x1: float, y1: float, x2: float, y2: float, *, palette: dict | None = None) -> str:
    palette = palette or load_design_tokens()
    edge_id = f"edge-{x1}-{y1}-{x2}-{y2}"
    polygon = _arrow_polygon(x1, y1, x2, y2, palette["line"], edge_id=edge_id)
    return (
        f'<line data-role="edge" data-arrowhead="true" data-edge-id="{edge_id}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{palette["line"]}" stroke-width="6"/>'
        f'{polygon}'
    )


def _arrow_polygon(x1: float, y1: float, x2: float, y2: float, color: str, length: float = 13, half_width: float = 6.5, edge_id: str = "") -> str:
    """Return an arrowhead aligned with the actual edge direction."""
    dx, dy = x2 - x1, y2 - y1
    norm = max(1.0, (dx * dx + dy * dy) ** 0.5)
    ux, uy = dx / norm, dy / norm
    bx, by = x2 - ux * length, y2 - uy * length
    px, py = -uy * half_width, ux * half_width
    points = f"{x2},{y2} {bx + px},{by + py} {bx - px},{by - py}"
    edge_attr = f' data-edge-id="{esc(edge_id)}"' if edge_id else ""
    return f'<polygon data-role="arrowhead"{edge_attr} points="{points}" fill="{color}"/>'


def _horizontal_flow(labels: list[str], widths: list[float], *, y: float,
                     gap: float = 20, start: float = 82, size: int = 20,
                     accents: set[int] | None = None, palette: dict | None = None) -> list[str]:
    """Lay out a flow inside the 82..1118 safe area without clipping."""
    accents = accents or set()
    parts: list[str] = []
    x = start
    for idx, label in enumerate(labels):
        box_width = widths[idx]
        parts.append(_box(x, y, box_width, 90, label, accent=idx in accents, size=size, palette=palette))
        if idx < len(labels) - 1:
            next_x = x + box_width + gap
            parts.append(_arrow(x + box_width + 5, y + 45, next_x - 5, y + 45, palette=palette))
        x += box_width + gap
    return parts


def _typed_arrow(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    relation_type: str,
    *,
    palette: dict | None = None,
    edge_id: str = "",
    junction_group: str = "",
    arrowhead: bool = True,
    label_dx: float = 0,
    label_dy: float = 0,
) -> str:
    palette = palette or load_design_tokens()
    edge_id = esc(edge_id or relation_type)
    label = esc(relation_type)
    mid_x = (x1 + x2) / 2 + label_dx
    mid_y = (y1 + y2) / 2 - 10 + label_dy
    junction_attr = f' data-junction-group="{esc(junction_group)}"' if junction_group else ""
    label_markup = (
        f'<text data-role="edge-label" data-edge-id="{edge_id}" x="{mid_x}" y="{mid_y}" text-anchor="middle" '
        f'font-family="Times New Roman, Microsoft YaHei, Segoe UI, sans-serif" font-size="15" '
        f'font-weight="700" fill="{palette["accent"]}">{label}</text>'
        if label else ""
    )
    arrow_markup = (
        _arrow_polygon(x1, y1, x2, y2, palette["line"], edge_id=edge_id)
        if arrowhead else ""
    )
    return (
        f'<line data-role="edge" data-arrowhead="{"true" if arrowhead else "false"}" data-edge-id="{edge_id}" data-edge-type="{label}"{junction_attr} '
        f'x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{palette["line"]}" stroke-width="4"/>'
        f'{arrow_markup}'
        f'{label_markup}'
    )


def _depth_metadata(unit: dict[str, Any]) -> str:
    payload = {
        "contract": "visual-depth-contract-v1",
        "reader_question": unit.get("reader_question", ""),
        "claim_ids": unit.get("claim_ids", []),
        "evidence_ids": unit.get("evidence_ids", []),
        "relations": unit.get("relations", []),
        "fallback_backend": unit.get("fallback_backend", ""),
    }
    return f'<metadata id="visual-depth-contract">{esc(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))}</metadata>'


def _render_stateful_graph(unit: dict[str, Any], palette: dict) -> list[str]:
    parts = [_depth_metadata(unit)]
    parts.append(_text(90, 370, "状态模型：节点返回增量，Reducer 合并 channel，条件边决定下一跳", size=18, color=palette["muted"], weight="600", anchor="start"))
    parts.append(_box(80, 420, 220, 100, "AgentState", accent=True, size=24, palette=palette))
    parts.append(_box(360, 420, 220, 100, "fetch node", size=22, palette=palette))
    parts.append(_box(650, 365, 250, 90, "state_update[messages]", size=20, accent=True, palette=palette))
    parts.append(_box(650, 470, 250, 80, "Reducer: operator.add", size=19, palette=palette))
    parts.append(_box(360, 585, 220, 72, "route_next", size=20, palette=palette))
    parts.append(_box(650, 585, 180, 72, "analyze", size=20, palette=palette))
    parts.append(_box(930, 585, 180, 72, "report / END", size=20, accent=True, palette=palette))
    parts.append(_typed_arrow(300, 470, 360, 470, "reads", palette=palette, edge_id="r-reads"))
    parts.append(_typed_arrow(580, 450, 650, 410, "returns", palette=palette, edge_id="r-returns"))
    parts.append(_typed_arrow(775, 455, 775, 470, "merges", palette=palette, edge_id="r-merges", label_dx=150))
    # The reducer box itself names the channel update.  Keeping this as a
    # typed annotation (rather than a perimeter arrow) preserves the claim
    # without introducing a misleading crossing through the state graph.
    parts.append(_text(1030, 555, "updates → messages channel", size=16, color=palette["accent"], weight="700", anchor="middle"))
    parts.append(_typed_arrow(470, 520, 470, 585, "branches", palette=palette, edge_id="r-branches"))
    parts.append(_typed_arrow(580, 620, 650, 620, "true", palette=palette, edge_id="r-analyze"))
    report_junction = "false-route"
    parts.append(_typed_arrow(580, 620, 600, 560, "false", palette=palette, edge_id="r-report-a", junction_group=report_junction, arrowhead=False, label_dx=26))
    parts.append(_typed_arrow(600, 560, 910, 560, "", palette=palette, edge_id="r-report-b", junction_group=report_junction, arrowhead=False))
    parts.append(_typed_arrow(910, 560, 910, 635, "", palette=palette, edge_id="r-report-c", junction_group=report_junction, arrowhead=False))
    parts.append(_typed_arrow(910, 635, 930, 635, "", palette=palette, edge_id="r-report-d", junction_group=report_junction))
    parts.append(_text(90, 710, "删除任一关系，读者就无法解释“状态如何被更新、合并并转向下一节点”", size=17, color=palette["accent"], weight="700", anchor="start", role="footer"))
    return parts


def _render_checkpoint_timeline(unit: dict[str, Any], palette: dict) -> list[str]:
    parts = [_depth_metadata(unit)]
    parts.append(_text(90, 370, "checkpoint 生命周期：每个执行边界留下可定位、可恢复的轨迹", size=18, color=palette["muted"], weight="600", anchor="start"))
    labels = ["invoke", "node complete", "checkpoint", "interrupt", "Command(resume)", "new checkpoint"]
    x_positions = [60, 245, 430, 615, 800, 985]
    for index, label in enumerate(labels):
        parts.append(_box(x_positions[index], 415, 150, 82, label, accent=index in {2, 5}, size=17, palette=palette))
        if index < len(labels) - 1:
            relation = ["executes", "persists", "pauses", "resumes", "forks"][index]
            parts.append(_typed_arrow(x_positions[index] + 150, 456, x_positions[index + 1] - 5, 456, relation, palette=palette, edge_id=f"timeline-{index}", label_dy=-42))
    parts.append(_box(90, 570, 230, 72, "thread_id=user-42", accent=True, size=19, palette=palette))
    parts.append(_box(450, 570, 250, 72, "StateSnapshot", size=20, palette=palette))
    parts.append(_box(830, 570, 270, 72, "Memory / SQLite / Redis", size=19, palette=palette))
    parts.append(_typed_arrow(165, 498, 190, 570, "scopes", palette=palette, edge_id="thread-scope"))
    parts.append(_typed_arrow(525, 498, 525, 570, "stores", palette=palette, edge_id="checkpoint-store"))
    parts.append(_typed_arrow(700, 606, 830, 606, "backend", palette=palette, edge_id="backend-choice"))
    parts.append(_text(90, 690, "同一 thread_id 读取最近成功点；interrupt 不丢状态，resume 产生新的执行轨迹", size=17, color=palette["accent"], weight="700", anchor="start", role="footer"))
    return parts


def _render_runtime_boundary(unit: dict[str, Any], palette: dict) -> list[str]:
    parts = [_depth_metadata(unit)]
    parts.append(_text(90, 370, "生产边界：请求路径与状态/恢复路径必须同时可见", size=18, color=palette["muted"], weight="600", anchor="start"))
    parts.append(_box(65, 415, 220, 100, "FastAPI", accent=True, size=24, palette=palette))
    parts.append(_box(345, 415, 245, 100, "LangGraph runtime", size=21, palette=palette))
    parts.append(_box(650, 415, 220, 100, "Checkpointer", accent=True, size=21, palette=palette))
    parts.append(_box(930, 415, 220, 100, "SQLite / Redis", size=20, palette=palette))
    parts.append(_typed_arrow(285, 465, 345, 465, "request", palette=palette, edge_id="api-runtime", label_dy=-52))
    parts.append(_typed_arrow(590, 465, 650, 465, "persists", palette=palette, edge_id="runtime-checkpointer", label_dy=-52))
    parts.append(_typed_arrow(870, 465, 930, 465, "backend", palette=palette, edge_id="checkpointer-store", label_dy=-52))
    parts.append(_box(155, 585, 220, 72, "thread_id", size=21, palette=palette))
    parts.append(_box(490, 585, 220, 72, "lock / retry", accent=True, size=20, palette=palette))
    parts.append(_box(825, 585, 250, 72, "node metrics / trace", size=19, palette=palette))
    parts.append(_typed_arrow(455, 515, 265, 585, "scopes", palette=palette, edge_id="scope-thread"))
    parts.append(_typed_arrow(590, 515, 600, 585, "guards", palette=palette, edge_id="lock-retry"))
    parts.append(_typed_arrow(760, 515, 950, 585, "observes", palette=palette, edge_id="observability"))
    parts.append(_text(90, 690, "单实例看持久化，多实例还要看共享存储、并发锁和可观测性", size=17, color=palette["accent"], weight="700", anchor="start", role="footer"))
    return parts


def _render_decision_matrix(unit: dict[str, Any], palette: dict) -> list[str]:
    parts = [_depth_metadata(unit)]
    parts.append(_text(90, 370, "后端决策矩阵：先看生命周期与部署边界，再选 saver", size=18, color=palette["muted"], weight="600", anchor="start"))
    headers = ["后端", "适用场景", "持久化", "并发/边界"]
    values = [
        ["MemorySaver", "原型 / 单测", "进程内", "重启即失"],
        ["SqliteSaver", "单机生产", "文件事务", "低并发 / 写锁"],
        ["RedisSaver", "多实例生产", "共享存储", "网络延迟 / 运维"],
    ]
    xs = [70, 310, 565, 820]
    widths = [210, 225, 225, 300]
    for col, (x, width, label) in enumerate(zip(xs, widths, headers)):
        parts.append(_box(x, 405, width, 60, label, accent=True, size=19, palette=palette))
    for row, row_values in enumerate(values):
        y = 490 + row * 75
        for col, (x, width, label) in enumerate(zip(xs, widths, row_values)):
            parts.append(_box(x, y, width, 58, label, accent=row == 1 and col == 0, size=17, palette=palette))
    parts.append(_typed_arrow(180, 730, 470, 730, "choose-by-boundary", palette=palette, edge_id="choose-backend"))
    parts.append(_text(90, 750, "没有真实 benchmark 时，不伪造延迟数字；用可核验的适用条件替代装饰性数据", size=17, color=palette["accent"], weight="700", anchor="start", role="footer"))
    return parts


def _render_agent_building_map(unit: dict[str, Any], palette: dict) -> list[str]:
    """Mobile-first opening map: one large state + three operational layers."""
    parts = [_depth_metadata(unit)]
    geometry_nodes = [
        {"id": "state", "bbox": [60, 280, 780, 170]},
        {"id": "flow", "bbox": [60, 555, 240, 180]},
        {"id": "memory", "bbox": [330, 555, 240, 180]},
        {"id": "control", "bbox": [600, 555, 240, 180]},
        {"id": "run-context", "bbox": [60, 845, 780, 92]},
    ]
    geometry_edges = [
        {"id": "map-drives", "source": "state", "target": "flow", "points": [[180, 455], [180, 548]]},
        {"id": "map-persists", "source": "flow", "target": "memory", "points": [[305, 645], [325, 645]]},
        {"id": "map-resumes", "source": "memory", "target": "control", "points": [[575, 645], [595, 645]]},
    ]
    geometry = {
        "contract": "geometry-contract-v1",
        "canvas": {"width": 900, "height": 1200, "background": palette["paper"]},
        "nodes": geometry_nodes,
        "edges": geometry_edges,
    }
    parts.append(f'<metadata id="visual-geometry-contract">{esc(json.dumps(geometry, ensure_ascii=False, separators=(",", ":")))}</metadata>')
    parts.append(_text(60, 88, "AGENT 工程 / 开篇总览", size=20, color=palette["accent"], weight="700", anchor="start"))
    parts.append(_text(60, 150, "构建可靠 Agent 的四层系统", size=44, color=palette["ink"], weight="800", anchor="start", role="node"))
    parts.append(_text(60, 198, "一套可靠系统，要把四个工程问题说清。", size=23, color=palette["muted"], weight="500", anchor="start"))
    parts.append(f'<line x1="60" y1="228" x2="840" y2="228" stroke="{palette["line"]}" stroke-width="3"/>')
    parts.append(f'<rect data-role="node" data-node-id="state" data-node-bbox="60,280,780,170" x="60" y="280" width="780" height="170" rx="26" fill="#17324D" stroke="#17324D" stroke-width="3"/>')
    parts.append(_text(100, 332, "01 / 状态 STATE", size=22, color="#D7E0E6", weight="700", anchor="start", role="node"))
    parts.append(_text(100, 398, "AgentState：跨步骤信息显式保留", size=31, color="#FFFCF7", weight="800", anchor="start", role="node"))
    parts.append(_text(100, 430, "显式状态让执行可追踪、可检查。", size=18, color="#D7E0E6", weight="500", anchor="start", role="node"))
    cards = [(60, "02 / 流程 FLOW", "节点与边", "下一步如何决定？", palette["line"], palette["surface"]), (330, "03 / 持久化 MEMORY", "检查点", "从哪里恢复？", palette["accent"], "#FFF6F0"), (600, "04 / 控制 CONTROL", "中断 + API", "谁来审批？", palette["line"], palette["surface"])]
    for x, top, label, question, stroke, fill in cards:
        parts.append(f'<rect data-role="node" data-node-id="{top.split(" / ")[-1].lower()}" data-node-bbox="{x},555,240,180" x="{x}" y="555" width="240" height="180" rx="22" fill="{fill}" stroke="{stroke}" stroke-width="3"/>')
        parts.append(_text(x + 24, 603, top, size=16, color=palette["accent"], weight="700", anchor="start", role="node"))
        parts.append(_text(x + 24, 660, label, size=27, color=palette["ink"], weight="800", anchor="start", role="node"))
        parts.append(_text(x + 24, 704, question, size=18, color=palette["muted"], weight="600", anchor="start", role="node"))
    parts.append(_typed_arrow(180, 455, 180, 548, "驱动", palette=palette, edge_id="map-drives", label_dx=64, label_dy=-16))
    # Keep the label above the flow/memory lane; the edge itself is only a
    # narrow 20px bridge, so the default offset would sit inside both nodes.
    parts.append(_typed_arrow(305, 645, 325, 645, "持久化", palette=palette, edge_id="map-persists", label_dy=-110))
    # Keep the short label above the memory/control lane. At ``-50`` its
    # baseline falls inside the control node's top edge and aesthetic QA
    # correctly reports a label/node collision.
    parts.append(_typed_arrow(575, 645, 595, 645, "恢复", palette=palette, edge_id="map-resumes", label_dy=-110))
    parts.append(f'<rect data-role="node" data-node-id="run-context" data-node-bbox="60,845,780,92" x="60" y="845" width="780" height="92" rx="46" fill="#EAF0F2" stroke="{palette["line"]}" stroke-width="2"/>')
    parts.append(_text(450, 888, "同一运行上下文", size=23, color=palette["ink"], weight="800", role="node"))
    parts.append(_text(450, 919, "thread_id + 持久化", size=21, color=palette["accent"], weight="700", role="node"))
    parts.append(_text(450, 1055, "把文章读成一组相互关联的工程决策，", size=20, color=palette["muted"], weight="600"))
    parts.append(_text(450, 1084, "而不是框架功能的堆叠。", size=20, color=palette["muted"], weight="600"))
    return parts


def semantic_svg(unit: dict, index: int, account: str | None = None) -> str:
    if not account:
        account = _default_account()
    """Render a small but real visual argument from a semantic contract."""
    width = 1200
    title = str(unit.get("section_heading") or unit.get("section") or "视觉锚点")
    description = str(unit.get("viewer_job") or "一张图只承担一个认知动作")
    visual_type = str(unit.get("visual_type") or unit.get("kind") or "concept").lower()
    height = canvas_height_for(str(unit.get("layout_archetype") or visual_type))
    palette = load_design_tokens(account)
    description_line_1, description_line_2 = _description_lines(description)
    diagram_data = unit.get("diagram_data") if isinstance(unit.get("diagram_data"), dict) else {}
    layout_archetype = str(unit.get("layout_archetype") or diagram_data.get("layout_archetype") or "").strip().lower()
    if layout_archetype == "agent-building-map":
        width = 900
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" data-background-token="background" data-layout-archetype="{esc(layout_archetype)}">',
        f'<rect data-role="canvas" data-background-token="background" width="{width}" height="{height}" fill="{palette["paper"]}"/>',
        f'<rect x="36" y="36" width="{width-72}" height="{height-72}" rx="24" fill="{palette["surface"]}" stroke="{palette["line"]}" stroke-width="3"/>',
    ]
    if layout_archetype != "agent-building-map":
        parts.extend([
            _text(82, 104, f"{index:02d} {visual_type.upper()}", size=24, color=palette["accent"], weight="700", anchor="start"),
            _text(82, 178, title[:34], size=36, color=palette["ink"], weight="700", anchor="start"),
            f'<line x1="82" y1="224" x2="1118" y2="224" stroke="{palette["line"]}" stroke-width="4"/>',
            _text(82, 290, description_line_1, size=23, color=palette["muted"], weight="400", anchor="start"),
            _text(82, 326, description_line_2, size=23, color=palette["muted"], weight="400", anchor="start"),
        ])
    if layout_archetype == "stateful-graph":
        parts.extend(_render_stateful_graph(unit, palette))
        visual_type = "stateful-graph"
    elif layout_archetype == "checkpoint-timeline":
        parts.extend(_render_checkpoint_timeline(unit, palette))
        visual_type = "checkpoint-timeline"
    elif layout_archetype == "runtime-boundary":
        parts.extend(_render_runtime_boundary(unit, palette))
        visual_type = "runtime-boundary"
    elif layout_archetype == "decision-matrix":
        parts.extend(_render_decision_matrix(unit, palette))
        visual_type = "decision-matrix"
    elif layout_archetype == "agent-building-map":
        parts.extend(_render_agent_building_map(unit, palette))
        visual_type = "agent-building-map"
    elif layout_archetype == "editorial-split-board":
        # Editorial split: one dominant thesis field + one evidence rail.
        # This is intentionally asymmetric so a technical article does not
        # collapse into three interchangeable rounded-card grids.
        labels = [str(item.get("label") or "").strip() for item in diagram_data.get("nodes", []) if isinstance(item, dict)]
        labels = labels[:6] or [str(value).strip() for value in unit.get("expected_elements", []) if str(value).strip()][:6]
        rail_positions = [430, 468, 506, 544, 582, 620]
        geometry_nodes = [{"id": "thesis", "bbox": [92, 382, 360, 258]}]
        geometry_nodes.extend({"id": f"evidence-{idx}", "bbox": [550, y - 20, 360, 30]} for idx, y in enumerate(rail_positions))
        geometry_edges = [
            {"id": f"evidence-edge-{idx}", "source": f"evidence-{idx}", "target": f"evidence-{idx + 1}", "points": [[570, y + 8], [570, rail_positions[idx + 1] - 20]]}
            for idx, y in enumerate(rail_positions[:-1])
        ]
        geometry_payload = {"contract": "geometry-contract-v1", "canvas": {"width": width, "height": height, "background": palette["paper"]}, "nodes": geometry_nodes, "edges": geometry_edges}
        parts.append(f'<metadata id="visual-geometry-contract">{esc(json.dumps(geometry_payload, ensure_ascii=False, separators=(",", ":")))}</metadata>')
        left_title = str(diagram_data.get("left_title") or "状态写入")
        right_title = str(diagram_data.get("right_title") or "恢复证据")
        parts.append(f'<path d="M92 382 L92 640" stroke="{palette["accent"]}" stroke-width="8" stroke-linecap="round"/>')
        parts.append(_text(125, 410, "01", size=22, color=palette["accent"], weight="700", anchor="start"))
        parts.append(_text(125, 470, left_title, size=44, color=palette["ink"], weight="700", anchor="start"))
        parts.append(_text(125, 520, "把一次执行变成", size=22, color=palette["muted"], weight="500", anchor="start"))
        parts.append(_text(125, 554, "可回放的状态轨迹", size=30, color=palette["ink"], weight="700", anchor="start"))
        parts.append(_text(125, 620, "写入 · 定位 · 续跑", size=18, color=palette["accent"], weight="700", anchor="start"))
        parts.append(f'<line x1="520" y1="376" x2="520" y2="650" stroke="{palette["line"]}" stroke-width="2" stroke-dasharray="2 12"/>')
        parts.append(_text(570, 410, right_title, size=22, color=palette["accent"], weight="700", anchor="start"))
        rail_y = rail_positions
        for idx, label in enumerate(labels[:6]):
            y = rail_y[idx]
            parts.append(f'<circle cx="570" cy="{y-8}" r="10" fill="{palette["accent"] if idx == 0 else palette["line"]}"/>')
            parts.append(_text(606, y, label, size=22 if len(label) < 15 else 18, color=palette["ink"], weight="700", anchor="start", role="node"))
            if idx < min(5, len(labels[:6]) - 1):
                parts.append(f'<line x1="570" y1="{y+8}" x2="570" y2="{rail_y[idx+1]-22}" stroke="{palette["line"]}" stroke-width="3"/>')
                parts.append(f'<polygon points="570,{rail_y[idx+1]-18} 563,{rail_y[idx+1]-30} 577,{rail_y[idx+1]-30}" fill="{palette["line"]}"/>')
        callout = str(diagram_data.get("callout") or "同一 thread_id，让恢复从最近成功点继续")
        parts.append(f'<path d="M820 432 Q1040 432 1080 520 T1040 636" fill="none" stroke="{palette["accent"]}" stroke-width="3" opacity="0.75"/>')
        callout_line_1, callout_line_2 = _description_lines(callout, limit=18)
        parts.append(_text(820, 484, callout_line_1, size=16, color=palette["muted"], weight="600", anchor="start"))
        if callout_line_2:
            parts.append(_text(820, 512, callout_line_2, size=16, color=palette["muted"], weight="600", anchor="start"))
        parts.append(_text(1080, 660, "一个状态源 · 多次可恢复执行", size=16, color=palette["accent"], weight="700", anchor="end"))
        visual_type = "editorial-split"
    elif layout_archetype in {"comparison-board", "architecture-board", "relationship-board", "state-loop-board"}:
        # Mechanism boards are evidence-led compositions: a clear visual
        # argument, not a row of equally weighted template cards.  The exact
        # labels and edges come from the current section's diagram_data.
        board_nodes = [item for item in diagram_data.get("nodes", []) if isinstance(item, dict)]
        labels = [str(item.get("label") or "").strip() for item in board_nodes if str(item.get("label") or "").strip()]
        labels = labels[:6] or [str(value).strip() for value in unit.get("expected_elements", []) if str(value).strip()][:6]
        if layout_archetype == "comparison-board":
            left_title = str(diagram_data.get("left_title") or "现有做法")
            right_title = str(diagram_data.get("right_title") or "结构化做法")
            parts.append(f'<rect x="70" y="360" width="500" height="230" rx="22" fill="{palette["surface"]}" stroke="{palette["line"]}" stroke-width="3"/>')
            parts.append(f'<rect x="630" y="360" width="500" height="230" rx="22" fill="{palette["surface"]}" stroke="{palette["accent"]}" stroke-width="3"/>')
            parts.append(_text(100, 405, left_title, size=24, color=palette["muted"], weight="700", anchor="start"))
            parts.append(_text(660, 405, right_title, size=24, color=palette["accent"], weight="700", anchor="start"))
            parts.append(f'<circle cx="600" cy="470" r="30" fill="{palette["accent"]}"/>')
            parts.append(_text(600, 478, "VS", size=18, color="#FFFCF7", weight="700"))
            split = max(1, min(3, (len(labels) + 1) // 2))
            left_labels = [str(value).strip() for value in diagram_data.get("left_nodes", []) if str(value).strip()] or labels[:split]
            right_labels = [str(value).strip() for value in diagram_data.get("right_nodes", []) if str(value).strip()] or labels[split:]
            if not right_labels:
                right_labels = ["状态显式化", "流程可恢复", "执行可审计"]
            for idx, label in enumerate(left_labels[:3]):
                x = 100 + idx * 150
                parts.append(_box(x, 465, 130, 72, label, accent=False, size=16, palette=palette))
                if idx < min(2, len(left_labels) - 1):
                    parts.append(_arrow(x + 135, 501, x + 148, 501, palette=palette))
            for idx, label in enumerate(right_labels[:3]):
                x = 660 + idx * 150
                parts.append(_box(x, 465, 130, 72, label, accent=idx == len(right_labels[:3]) - 1, size=16, palette=palette))
                if idx < min(2, len(right_labels) - 1):
                    parts.append(_arrow(x + 135, 501, x + 148, 501, palette=palette))
            parts.append(_text(600, 620, "读者先看结构差异，再回到正文代码验证实现", size=18, color=palette["muted"], weight="600"))
        else:
            parts.append(f'<rect x="70" y="360" width="1060" height="280" rx="22" fill="{palette["surface"]}" stroke="{palette["line"]}" stroke-width="3"/>')
            board_title = "状态回放" if layout_archetype == "state-loop-board" else "系统边界"
            parts.append(_text(100, 405, board_title, size=24, color=palette["accent"], weight="700", anchor="start"))
            if layout_archetype == "state-loop-board":
                task_line_1, task_line_2 = "理解 checkpoint 写入、thread_id 回读", "与断点恢复"
            elif layout_archetype == "architecture-board":
                task_line_1, task_line_2 = "理解 API 入口、执行路径", "与状态恢复边界"
            else:
                task_line_1, task_line_2 = _description_lines(description, limit=38)
            parts.append(_text(1100, 396, "读者任务：" + task_line_1, size=16, color=palette["muted"], weight="400", anchor="end"))
            if task_line_2:
                parts.append(_text(1100, 419, task_line_2, size=16, color=palette["muted"], weight="400", anchor="end"))
            split = max(2, min(3, (len(labels) + 1) // 2))
            top_labels, bottom_labels = labels[:split], labels[split:]
            top_y, bottom_y = 455, 535
            def _board_lane(items: list[str], y: int, accent_last: bool = False) -> None:
                if not items:
                    return
                box_w = 250 if len(items) <= 3 else 190
                gap = 35
                start = int((1200 - (len(items) * box_w + (len(items) - 1) * gap)) / 2)
                for idx, label in enumerate(items[:4]):
                    x = start + idx * (box_w + gap)
                    parts.append(_box(x, y, box_w, 64, label, accent=accent_last and idx == len(items[:4]) - 1, size=16, palette=palette))
                    if idx < min(3, len(items) - 1):
                        parts.append(_arrow(x + box_w + 7, y + 32, x + box_w + gap - 7, y + 32, palette=palette))
            _board_lane(top_labels, top_y, accent_last=False)
            _board_lane(bottom_labels, bottom_y, accent_last=True)
            board_note = (
                "checkpoint 写入 → thread_id 回读 → 从断点继续"
                if layout_archetype == "state-loop-board"
                else "上层是请求/执行路径，下层是状态/证据/恢复路径"
            )
            parts.append(_text(600, 625, board_note, size=18, color=palette["muted"], weight="600"))
        visual_type = "board"
    if visual_type == "qkv":
        parts += [_box(90, 420, 190, 110, "X · 输入", accent=True, size=22, palette=palette)]
        parts += [_arrow(290, 475, 390, 475, palette=palette)]
        lane_y = [350, 465, 580]
        lane_labels = [("Q · 查询", "我想找什么"), ("K · 匹配", "我如何被找到"), ("V · 传递", "我真正提供什么")]
        for idx, (label, sub) in enumerate(lane_labels):
            y = lane_y[idx]
            parts.append(f'<rect x="410" y="{y}" width="690" height="90" rx="18" fill="{palette["paper"]}" stroke="{palette["accent"] if idx == 0 else palette["line"]}" stroke-width="3"/>')
            parts.append(_text(455, y + 38, label, size=23, color=palette["ink"], weight="700", anchor="start", role="lane"))
            parts.append(_text(455, y + 68, sub, size=18, color=palette["muted"], weight="400", anchor="start"))
            parts.append(_text(935, y + 52, ["Q = XW_Q", "K = XW_K", "V = XW_V"][idx], size=22, color=palette["ink"], weight="600", anchor="middle", role="formula"))
            parts.append(_arrow(300, 475, 405, y + 45, palette=palette))
        parts.append(_text(595, 690, "Q、K 决定注意力权重；V 负责携带真正被汇总的内容", size=22, color=palette["muted"]))
    elif visual_type == "shape":
        labels = ["X[n,d_model]", "Q[n_q,d_k]", "K[n_k,d_k]", "V[n_k,d_v]", "QKᵀ[n_q,n_k]"]
        parts += _horizontal_flow(labels, [180, 180, 180, 180, 180], y=490, gap=20, start=110, size=18, accents={0, 4}, palette=palette)
    elif visual_type == "attention":
        labels = ["Score", "缩放 √d_k", "Mask", "Softmax（Key）", "V 加权汇总"]
        parts += _horizontal_flow(labels, [170, 175, 150, 190, 180], y=490, gap=20, start=167, size=18, accents={0, 4}, palette=palette)
    elif visual_type == "numeric":
        expected_numeric = [str(value).strip() for value in unit.get("expected_elements", []) if str(value).strip()]
        # Generic numeric sections must render their authored values.  Keep
        # the historical attention example only when the contract explicitly
        # contains those labels; never inject Transformer math into another
        # topic.
        labels = expected_numeric[:4] if expected_numeric and not any("QK" in value or "A₁" in value for value in expected_numeric) else ["QKᵀ = [[1,1],[0,1]]", "A₁ = [0.50, 0.50]", "A₂ = [0.33, 0.67]", "O = AV"]
        parts += _horizontal_flow(labels, [240] * len(labels), y=490, gap=24, start=84, size=17, accents={0, len(labels) - 1}, palette=palette)
    elif visual_type == "multihead":
        parts += [_box(100, 350, 260, 90, "Self-Attention", accent=True, palette=palette), _box(100, 470, 260, 90, "Cross-Attention", palette=palette)]
        parts += [_arrow(380, 395, 500, 395, palette=palette), _arrow(380, 515, 500, 515, palette=palette)]
        parts += [_box(530, 405, 250, 100, "Multi-Head", accent=True, palette=palette), _arrow(800, 455, 910, 455, palette=palette), _box(930, 405, 190, 100, "W_O", accent=True, palette=palette)]
    elif visual_type == "kv-cache":
        parts += [_text(110, 360, "阶段 1 · 批量建立历史", size=20, color=palette["muted"], anchor="start")]
        parts += [_box(100, 385, 220, 90, "Prefill", accent=True, palette=palette), _arrow(330, 430, 455, 430, palette=palette), _box(480, 385, 230, 90, "K_cache / V_cache", palette=palette)]
        parts += [_text(110, 535, "阶段 2 · 每步只追加新 token", size=20, color=palette["muted"], anchor="start")]
        parts += [_box(100, 560, 220, 90, "qₜ,kₜ,vₜ", accent=True, palette=palette), _arrow(330, 605, 455, 605, palette=palette), _box(480, 560, 230, 90, "历史 K/V + 新 K/V", palette=palette), _arrow(720, 605, 850, 605, palette=palette), _box(875, 560, 220, 90, "Decode", accent=True, palette=palette)]
        parts += [_text(595, 700, "省掉历史前缀的重复前向；当前 Query 仍读取完整历史", size=22, color=palette["muted"])]
    elif visual_type == "summary-cards":
        # 双卡片：左 30 秒基础版 / 右 1 分钟扩展版
        # 每卡顶部有版本标签 + 副标题，主体是 4~5 行要点
        card_top, card_h = 360, 540
        card_w, gap = 510, 50
        right_x = 95 + card_w + gap
        # 卡片背景（surface）
        for x in (95, right_x):
            parts.append(
                f'<rect x="{x}" y="{card_top}" width="{card_w}" height="{card_h}" rx="20" '
                f'fill="{palette["surface"]}" stroke="{palette["line"]}" stroke-width="3"/>'
            )
        # 卡片顶部色条 + 版本徽章
        for x, label, badge in (
            (95, "30 秒基础版", "30s"),
            (right_x, "1 分钟扩展版", "1m"),
        ):
            parts.append(f'<rect x="{x}" y="{card_top}" width="{card_w}" height="60" rx="20" fill="{palette["accent"]}"/>')
            parts.append(f'<rect x="{x}" y="{card_top + 30}" width="{card_w}" height="30" fill="{palette["accent"]}"/>')
            parts.append(_text(x + 30, card_top + 40, badge, size=24, color="#FFFCF7", weight="700", anchor="start"))
            parts.append(_text(x + 100, card_top + 40, label, size=22, color="#FFFCF7", weight="700", anchor="start"))
        # 30 秒要点
        expected = [str(value).strip() for value in unit.get("expected_elements", []) if str(value).strip()]
        if not expected:
            raise SystemExit("summary-cards 视觉合同缺少当前主题的 expected_elements")
        split_at = max(1, min(4, (len(expected) + 1) // 2))
        short_lines = expected[:split_at]
        long_lines = expected[split_at:split_at + 6] or expected[:6]
        line_y = card_top + 110
        for line in short_lines:
            parts.append(f'<circle cx="{95 + 30}" cy="{line_y - 6}" r="6" fill="{palette["accent"]}"/>')
            parts.append(_text(95 + 50, line_y, line, size=20, color=palette["ink"], weight="500", anchor="start"))
            line_y += 60
        line_y = card_top + 100
        for line in long_lines:
            parts.append(f'<circle cx="{right_x + 30}" cy="{line_y - 6}" r="5" fill="{palette["line"]}"/>')
            parts.append(_text(right_x + 50, line_y, line, size=18, color=palette["ink"], weight="500", anchor="start"))
            line_y += 48
        # 底部口诀
        parts.append(_text(95, card_top + card_h + 50, "一句话：Q/K 决定权重，V 决定内容", size=22, color=palette["muted"], weight="600", anchor="start"))
    elif visual_type == "concept-map":
        # 5 层金字塔：从底向上 L1 Q/K/V → L2 Score → L3 5步 Attention → L4 Multi-Head → L5 KV Cache
        # 顶窄底宽，每层用不同 accent 颜色
        width = 1200
        layer_gap = 70
        layer_h = 56
        expected = [str(value).strip() for value in unit.get("expected_elements", []) if str(value).strip()]
        if not expected:
            raise SystemExit("concept-map 视觉合同缺少当前主题的 expected_elements")
        layers = []
        for layer_index, label in enumerate(expected[:5]):
            colors = [palette["paper"], "#EFE3D6", "#E6D2BF", "#D9B89C", palette["accent"]]
            layers.append((f"L{layer_index + 1} · {label}", "当前主题概念层", 1080 - layer_index * 150, colors[layer_index]))
        # 反向画：L5 在最顶
        for idx, (title, sub, w, color) in enumerate(layers):
            x = (width - w) // 2
            y = 350 + (len(layers) - 1 - idx) * layer_gap
            parts.append(
                f'<rect x="{x}" y="{y}" width="{w}" height="{layer_h}" rx="10" '
                f'fill="{color}" stroke="{palette["line"]}" stroke-width="2"/>'
            )
            text_color = "#FFFCF7" if color == palette["accent"] else palette["ink"]
            parts.append(_text(x + 24, y + 36, title, size=20, color=text_color, weight="700", anchor="start"))
            parts.append(_text(x + w - 24, y + 36, sub, size=15, color=text_color, weight="500", anchor="end"))
        # 左侧阅读箭头（从底指向顶）
        arrow_x = 70
        for idx in range(len(layers) - 1):
            y_from = 350 + (len(layers) - 1 - idx) * layer_gap + layer_h // 2
            y_to = 350 + (len(layers) - 1 - idx - 1) * layer_gap + layer_h // 2
            parts.append(f'<line x1="{arrow_x}" y1="{y_from}" x2="{arrow_x}" y2="{y_to}" stroke="{palette["accent"]}" stroke-width="3"/>')
            parts.append(f'<polygon points="{arrow_x},{y_to} {arrow_x - 6},{y_to + 10} {arrow_x + 6},{y_to + 10}" fill="{palette["accent"]}"/>')
        arrow_end_y = 350 + (len(layers) - 1) * layer_gap + layer_h // 2
        parts.append(_text(arrow_x, arrow_end_y + 35, "掌握层级", size=18, color=palette["accent"], weight="700", anchor="middle"))
    elif visual_type == "checklist":
        labels = [str(value).strip() for value in unit.get("expected_elements", []) if str(value).strip()]
        if not labels:
            raise SystemExit("checklist 视觉合同缺少当前主题的 expected_elements")
        for idx, label in enumerate(labels):
            x = 100 + (idx % 3) * 350
            # Keep the second row inside the 36px safe frame on the compact
            # checklist canvas (640px high); the previous 515+90 endpoint
            # clipped the bottom border by one pixel.
            y = 360 + (idx // 3) * 125
            parts.append(_box(x, y, 260, 90, label, accent=idx in {0, 4}, palette=palette))
            # A checklist is an acceptance instrument, not merely a set of
            # labels.  Keep a visible checkbox role so both humans and the
            # content gate can distinguish it from a generic card.
            parts.append(f'<rect data-role="checkbox" data-check-id="check-{idx + 1}" x="{x + 16}" y="{y + 25}" width="34" height="34" rx="6" fill="none" stroke="{palette["accent"]}" stroke-width="4"/>')
            parts.append(_text(x + 33, y + 50, "✓", size=24, color=palette["accent"], weight="800"))
    elif visual_type in {"relationship", "architecture", "flow", "timeline", "branch", "diagram"}:
        # A relationship visual is a topology claim, not a collection of
        # labels.  Render the contract evidence as real nodes and explicit
        # data-role=edge connectors so geometry QA can verify the topology.
        labels = [str(value).strip() for value in unit.get("expected_elements", []) if str(value).strip()]
        if not labels:
            raise SystemExit(f"{visual_type} 视觉合同缺少当前主题的 expected_elements")
        labels = labels[:6]
        gap = 24
        box_width = min(230, max(150, int((1000 - gap * (len(labels) - 1)) / len(labels))))
        total_width = len(labels) * box_width + (len(labels) - 1) * gap
        start = max(70, int((width - total_width) / 2))
        parts += _horizontal_flow(
            labels,
            [box_width] * len(labels),
            y=470,
            gap=gap,
            start=start,
            size=18 if box_width < 190 else 20,
            accents={0, len(labels) - 1},
            palette=palette,
        )
    elif visual_type in {
        "board",
        "editorial-split",
        "stateful-graph",
        "checkpoint-timeline",
        "runtime-boundary",
        "decision-matrix",
        "agent-building-map",
    }:
        pass
    else:
        expected = [str(value) for value in unit.get("expected_elements", [])]
        for idx, label in enumerate(expected[:5]):
            x = 100 + (idx % 3) * 350
            y = 450 + (idx // 3) * 150
            parts.append(_box(x, y, 260, 90, label, accent=idx == 0, palette=palette))
    parts += ["</svg>"]
    svg_str = "".join(parts)
    # ── Height overflow assertion ──────────────────────────────────────
    # Estimate the lowest y-coordinate used by any element in the SVG.
    # If it exceeds the canvas height, raise immediately instead of
    # producing a clipped PNG that someone has to notice by eye.
    max_y = 0
    for m in re.finditer(r'\by="([0-9.]+)"', svg_str):
        max_y = max(max_y, float(m.group(1)))
    # Also check rect/line y2 attributes
    for m in re.finditer(r'\by2="([0-9.]+)"', svg_str):
        max_y = max(max_y, float(m.group(1)))
    # Add some tolerance for stroke width and text descenders
    if max_y > height - 10:
        raise SystemExit(
            f"模板内容溢出：visual_type='{visual_type}', "
            f"estimated_max_y={max_y:.0f}, canvas_height={height}. "
            f"请在 canvas_height_for() 中增大 '{visual_type}' 的高度。"
        )
    return svg_str


def svg_document(title: str, description: str, kind: str, index: int, account: str | None = None) -> str:
    if not account:
        account = _default_account()
    nodes = nodes_for(kind)
    palette = load_design_tokens(account)
    width, height = 1200, canvas_height_for(kind)
    node_y = 470
    node_w, node_h = 190, 86
    start_x = (width - (len(nodes) * node_w + (len(nodes) - 1) * 48)) // 2
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" data-background-token="background" data-layout-archetype="{esc(kind)}">',
        f'<rect data-role="canvas" data-background-token="background" width="{width}" height="{height}" fill="{palette["paper"]}"/>',
        f'<rect x="36" y="36" width="{width-72}" height="{height-72}" rx="24" fill="{palette["surface"]}" stroke="{palette["line"]}" stroke-width="3"/>',
        f'<text x="82" y="104" font-family="Times New Roman, Microsoft YaHei, Segoe UI, sans-serif" font-size="24" font-weight="700" fill="{palette["accent"]}">{index:02d} {esc(kind.upper())}</text>',
        f'<text x="82" y="178" font-family="Times New Roman, Microsoft YaHei, Segoe UI, sans-serif" font-size="38" font-weight="700" fill="{palette["ink"]}">{esc(title[:32])}</text>',
        f'<line x1="82" y1="224" x2="1118" y2="224" stroke="{palette["line"]}" stroke-width="4"/>',
        f'<text x="82" y="294" font-family="Times New Roman, Microsoft YaHei, Segoe UI, sans-serif" font-size="24" fill="{palette["muted"]}">{esc(description[:54])}</text>',
        f'<text x="82" y="334" font-family="Times New Roman, Microsoft YaHei, Segoe UI, sans-serif" font-size="24" fill="{palette["muted"]}">{esc(description[54:108])}</text>',
    ]
    for idx, label in enumerate(nodes):
        x = start_x + idx * (node_w + 48)
        if idx < len(nodes) - 1:
            arrow_x1 = x + node_w + 8
            arrow_x2 = x + node_w + 40
            parts.append(f'<line x1="{arrow_x1}" y1="{node_y+node_h/2}" x2="{arrow_x2}" y2="{node_y+node_h/2}" stroke="{palette["line"]}" stroke-width="6"/>')
            parts.append(f'<polygon points="{arrow_x2},{node_y+node_h/2} {arrow_x2-14},{node_y+node_h/2-10} {arrow_x2-14},{node_y+node_h/2+10}" fill="{palette["line"]}"/>')
        parts.append(f'<rect x="{x}" y="{node_y}" width="{node_w}" height="{node_h}" rx="14" fill="{palette["paper"]}" stroke="{palette["accent"] if idx in {0, len(nodes)-1} else palette["line"]}" stroke-width="3"/>')
        parts.append(f'<text x="{x+node_w/2}" y="{node_y+54}" text-anchor="middle" font-family="Times New Roman, Microsoft YaHei, Segoe UI, sans-serif" font-size="28" font-weight="700" fill="{palette["ink"]}">{esc(label)}</text>')
    parts.extend([
        "</svg>",
    ])
    return "".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--kind", default="architecture")
    parser.add_argument("--index", type=int, default=1)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--svg-output", type=Path)
    parser.add_argument("--spec", type=Path, help="visual-contract.json")
    parser.add_argument("--spec-id", default="", help="visual contract unit id")
    parser.add_argument("--account", default=_default_account(), choices=(_default_account(),), help="固定为本工作流账号")
    args = parser.parse_args()

    output = args.output.expanduser().resolve()
    svg_output = (args.svg_output or output.with_suffix(".svg")).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    svg_output.parent.mkdir(parents=True, exist_ok=True)
    source_is_html = False
    code_height: int | None = None  # Enhancement #7:代码卡的自适应截图高度
    if args.spec:
        spec_path = args.spec.expanduser()
        if not spec_path.is_absolute():
            spec_path = ROOT / spec_path
        spec_path = spec_path.resolve()
        # 先宽松读取以判定类型；代码卡自带精确 code 时不需要 expected_elements，
        # 其余所有路径下面立即补回严格校验，门禁强度不变。
        unit = _spec_unit(spec_path, args.spec_id or "body-01", require_elements=False)
        visual_type = str(unit.get("visual_type") or unit.get("kind") or "").strip().lower()
        backend = str(unit.get("execution_backend") or unit.get("render_backend") or "").strip().lower()
        is_code_card = backend == "code-block" or visual_type in {"code", "pseudocode"}
        if not is_code_card and not unit.get("expected_elements"):
            raise SystemExit(f"视觉合同缺少 expected_elements：{args.spec_id or 'body-01'}")
        # Exact formula panels and the checklist use the KaTeX-backed HTML
        # renderer. Relationship/timeline visuals intentionally use editable
        # SVG so one article can combine more than one visual language.
        if backend == "beautiful-mermaid":
            # beautiful-mermaid 现在会同时写出 .svg 与 .html wrapper；用 HTML 截屏
            # 才能保留账号背景色，避免黑块或透明底。
            _render_mermaid_source(spec_path, args.spec_id or "body-05", svg_output, args.account)
            source_is_html = True
        elif backend == "code-block" or visual_type in {"code", "pseudocode"}:
            # RC7:代码 / 伪代码走确定性 HTML 代码卡,再由 Chrome 栅格化。
            # Enhancement #7: 用代码行数估计紧凑高度，消除下方留白。
            source_path = svg_output.with_suffix(".html")
            code_unit = _render_code_source(spec_path, args.spec_id or "body-01", source_path, args.account)
            code_height = int(code_unit.get("estimated_height") or canvas_height_for(visual_type))
            source_is_html = True
        elif backend == "formula-code-map" or visual_type == "formula-code-map":
            # Enhancement #4: 公式↔代码对照卡
            source_path = svg_output.with_suffix(".html")
            _render_formula_code_map_source(spec_path, args.spec_id or "body-01", source_path, args.account)
            source_is_html = True
        elif backend == "interactive-card-deck" or visual_type == "card-deck":
            # Enhancement #5: 信息卡组，一个视觉位承载多张卡片
            _render_card_deck_source(spec_path, args.spec_id or "body-01", svg_output, args.account)
            source_is_html = False
        elif backend in {"excalidraw", "excalidraw-style"} or visual_type in {"excalidraw", "excalidraw-style"}:
            # Native Excalidraw JSON is the editable source; SVG is the
            # deterministic sidecar and fallback used by article QA.
            _render_excalidraw_style_source(spec_path, args.spec_id or "body-01", svg_output, args.account)
            source_is_html = False
        elif backend == "deterministic-infographic" and str(unit.get("layout_archetype") or "").strip().lower() in {"decision-matrix", "comparison-board"}:
            # The local decision-matrix adapter is an infographic backend but
            # still emits the same editable SVG source and typed rows.  It is
            # not a generic math card and therefore must use the semantic
            # renderer for this contract.
            svg_output.write_text(semantic_svg(unit, args.index, args.account), encoding="utf-8")
        elif backend == "deterministic-infographic" and visual_type == "checklist":
            # Checklists are deterministic SVGs with visible checkbox roles;
            # routing them through the math HTML renderer would reduce them to
            # a generic title/label card and fail the content contract.
            svg_output.write_text(semantic_svg(unit, args.index, args.account), encoding="utf-8")
        elif backend.startswith("katex-") or backend == "deterministic-infographic":
            source_path = svg_output.with_suffix(".html")
            _render_math_source(spec_path, args.spec_id or "body-01", source_path, args.account)
            source_is_html = True
        else:
            svg_output.write_text(semantic_svg(unit, args.index, args.account), encoding="utf-8")
    else:
        svg_output.write_text(svg_document(args.title, args.description, args.kind, args.index, args.account), encoding="utf-8")

    chrome = chrome_path()
    if chrome:
        with tempfile.TemporaryDirectory(prefix="gzh-anchor-") as tmp:
            source_path = svg_output.with_suffix(".html") if source_is_html else svg_output
            url = source_path.as_uri()
            if code_height is not None:
                # 代码卡按实际行数裁剪，短代码不再拖一大截空白
                height = code_height
            elif args.spec and backend == "beautiful-mermaid":
                height = 420
            else:
                # Custom semantic layouts carry their own canvas geometry;
                # using only the generic visual type would crop decision
                # matrices/timelines before the footer and invalidate the
                # declared raster dimensions.
                height = canvas_height_for(
                    str(unit.get("layout_archetype") or visual_type) if args.spec else args.kind
                )
            # Code cards are authored at 680px plus a small margin.  Capturing
            # them in a 1200px viewport used to export a mostly empty canvas
            # (and a distracting scrollbar), making the infographic look weak
            # even though the code itself was correct.  Crop the raster to
            # the actual card width; technical SVGs keep the 1200px canvas.
            capture_width = 720 if code_height is not None else (900 if args.spec and str(unit.get("layout_archetype") or "").strip().lower() == "agent-building-map" else 1200)
            command = [str(chrome), "--headless", "--disable-gpu", "--no-sandbox", f"--window-size={capture_width},{height}", f"--screenshot={output}", url]
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
            if result.returncode == 0 and output.is_file() and output.stat().st_size >= 1024:
                print(f"VISUAL ANCHOR RENDERED: {output} ({'katex-html' if source_is_html else 'svg'})")
                return 0

    # A browser is preferred because it preserves the editable SVG as the
    # source of truth.  Pillow is a last-resort raster fallback handled by the
    # article image generator so this command never leaves an HTML-only asset.
    print("VISUAL ANCHOR BLOCKED: Chrome 未能把 SVG 栅格化", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
