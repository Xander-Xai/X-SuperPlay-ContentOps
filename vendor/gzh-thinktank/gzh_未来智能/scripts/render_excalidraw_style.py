#!/usr/bin/env python3
"""Render an Excalidraw-style hand-drawn SVG diagram (Enhancement #6).

The excalidraw-diagram skill currently only produces ``.excalidraw`` JSON and
has no local PNG renderer.  This script fills that gap: it reads a simple
``nodes`` / ``edges`` visual contract and emits a hand-sketched SVG that can be
rasterized by Chrome.

Style choices intentionally mimic Excalidraw defaults:
* slightly wobbly strokes (seeded randomness for reproducibility)
* cross-hatch fill for selected shapes
* hand-written font stack
* account-aware palette from design_tokens
"""

from __future__ import annotations

import argparse
import html
import json
import math
import random
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from render_visual_anchor import chrome_path, load_design_tokens  # noqa: E402

CANVAS_W = 1200
CANVAS_H = 720
NODE_W = 220
NODE_H = 90



def _default_account() -> str:
    """Return the fixed account id of this split workflow target."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from account_context import ACCOUNT_ID
        return ACCOUNT_ID
    except Exception as exc:
        raise RuntimeError("workflow identity unavailable") from exc

def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def node_font_size(label: str) -> int:
    """Keep long technical identifiers inside their hand-drawn node."""
    length = len(str(label))
    if length >= 22:
        return 15
    if length >= 18:
        return 17
    return 20


def rough_line(x1: float, y1: float, x2: float, y2: float, stroke: str, width: float = 2.5, seed: int = 0) -> str:
    rng = random.Random(seed)
    mid_x = (x1 + x2) / 2 + rng.uniform(-4, 4)
    mid_y = (y1 + y2) / 2 + rng.uniform(-4, 4)
    return (
        f'<path d="M{x1:.1f},{y1:.1f} Q{mid_x:.1f},{mid_y:.1f} {x2:.1f},{y2:.1f}" '
        f'fill="none" stroke="{stroke}" stroke-width="{width}" stroke-linecap="round"/>'
    )


def rough_rect(x: float, y: float, w: float, h: float, stroke: str, fill: str, seed: int = 0) -> str:
    rng = random.Random(seed)
    d = []
    corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    for i in range(4):
        x1, y1 = corners[i]
        x2, y2 = corners[(i + 1) % 4]
        cx = (x1 + x2) / 2 + rng.uniform(-3, 3)
        cy = (y1 + y2) / 2 + rng.uniform(-3, 3)
        cmd = "M" if i == 0 else "L"
        d.append(f"{cmd}{x1:.1f},{y1:.1f} Q{cx:.1f},{cy:.1f} {x2:.1f},{y2:.1f}")
    d.append("Z")
    return f'<path d="{" ".join(d)}" fill="{fill}" stroke="{stroke}" stroke-width="2.5" stroke-linejoin="round"/>'


def arrow_head(x: float, y: float, angle: float, stroke: str) -> str:
    a1 = angle - math.radians(28)
    a2 = angle + math.radians(28)
    r = 12
    x1 = x - r * math.cos(a1)
    y1 = y - r * math.sin(a1)
    x2 = x - r * math.cos(a2)
    y2 = y - r * math.sin(a2)
    return f'<path d="M{x1:.1f},{y1:.1f} L{x:.1f},{y:.1f} L{x2:.1f},{y2:.1f}" fill="none" stroke="{stroke}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'


def audit_arrowhead(x: float, y: float, angle: float, edge_id: str) -> str:
    a1 = angle - math.radians(28)
    a2 = angle + math.radians(28)
    radius = 12
    p1 = (x - radius * math.cos(a1), y - radius * math.sin(a1))
    p2 = (x - radius * math.cos(a2), y - radius * math.sin(a2))
    points = f"{p1[0]:.1f},{p1[1]:.1f} {x:.1f},{y:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return f'<polygon data-role="arrowhead" data-edge-id="{esc(edge_id)}" points="{points}" fill="none" stroke="none"/>'


def routed_edge(points: list[tuple[float, float]], stroke: str, *, edge_id: str = "", width: float = 3.0) -> str:
    """Draw a deterministic polyline whose route can be audited separately."""
    if len(points) < 2:
        return ""
    d = "M" + ",".join(f"{x:.1f}" for x in points[0])
    for x, y in points[1:]:
        d += f" L{x:.1f},{y:.1f}"
    attrs = f' data-edge-id="{esc(edge_id)}"' if edge_id else ""
    return f'<path data-role="edge"{attrs} d="{d}" fill="none" stroke="{stroke}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>'


def geometry_metadata(nodes: list[dict], edges: list[dict], *, background: str, canvas_height: int | None = None) -> str:
    payload = {
        "contract": "geometry-contract-v1",
        "canvas": {"width": CANVAS_W, "height": canvas_height or CANVAS_H, "background": background},
        "nodes": nodes,
        "edges": edges,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f'<metadata id="visual-geometry-contract">{esc(raw)}</metadata>'


def _excalidraw_base(element_id: str, element_type: str, x: float, y: float, width: float, height: float, seed: int, *,
                     stroke: str, background: str, roughness: int = 1) -> dict:
    """Create a valid Excalidraw element envelope.

    The native JSON is kept as a first-class editable source.  The SVG and PNG
    sidecars are rendered from the same contract, so an editor can open the
    JSON in Excalidraw without losing the hand-drawn intent.
    """
    return {
        "id": element_id,
        "type": element_type,
        "x": round(x, 2),
        "y": round(y, 2),
        "width": round(width, 2),
        "height": round(height, 2),
        "angle": 0,
        "strokeColor": stroke,
        "backgroundColor": background,
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": roughness,
        "opacity": 100,
        "seed": seed,
        "version": 1,
        "versionNonce": seed * 97 + 11,
        "isDeleted": False,
        "groupIds": [],
        "boundElements": [],
        "updated": 1,
        "link": None,
        "locked": False,
        "frameId": None,
        "customData": {"source": "scripts/render_excalidraw_style.py"},
    }


def _excalidraw_text(element_id: str, value: str, x: float, y: float, width: float, height: float, seed: int, *,
                     color: str, container_id: str | None = None, font_size: int = 20) -> dict:
    element = _excalidraw_base(
        element_id,
        "text",
        x,
        y,
        width,
        height,
        seed,
        stroke=color,
        background="transparent",
        roughness=1,
    )
    element.update(
        {
            "text": value,
            "originalText": value,
            "fontSize": font_size,
            "fontFamily": 3,
            "textAlign": "center",
            "verticalAlign": "middle",
            "containerId": container_id,
            "lineHeight": 1.25,
            "baseline": round(height * 0.8, 2),
            "rawText": value,
        }
    )
    return element


def build_stateful_excalidraw_json(tokens: dict) -> dict:
    """Editable Excalidraw counterpart of the custom stateful SVG layout."""
    elements: list[dict] = []
    shapes = [
        ("state_context", "ellipse", 60, 190, 220, 130, "AgentState\nmessages: [history]\nnext_step: \"report\"", 16, tokens["accent"], "#FFF3E9"),
        ("fetch_node", "rectangle", 320, 210, 200, 100, "fetch node\nfetch_data(state)\nreturn {…}", 17, tokens["line"], tokens["surface"]),
        ("delta_note", "rectangle", 560, 210, 220, 100, "state_update[messages]\n{\"messages\": [+1]}\n只返回增量", 15, tokens["accent"], "#FFF8ED"),
        ("reducer_funnel", "rectangle", 850, 185, 230, 140, "Reducer: operator.add\nold + delta\nmessages′ 写回状态", 16, tokens["accent"], "#FFF3E9"),
        ("route_decision", "diamond", 885, 405, 190, 120, "route_next\nneed_analysis?", 16, tokens["accent"], "#FFF8ED"),
        ("analyze_end", "ellipse", 615, 580, 220, 70, "analyze\n继续处理", 16, tokens["line"], tokens["surface"]),
        ("report_end", "ellipse", 920, 580, 220, 70, "report / END\n结束执行", 16, tokens["accent"], "#FFF3E9"),
    ]
    elements.append(_excalidraw_text("stateful_meta", "STATEGRAPH / ONE PASS", 60, 35, 420, 24, 9000, color=tokens["accent"], font_size=15))
    elements.append(_excalidraw_text("stateful_title", "读状态，合并增量，再决定下一跳", 60, 62, 700, 40, 9001, color=tokens["ink"], font_size=28))
    elements.append(_excalidraw_text("stateful_description", "一条节点执行轨迹：State → Delta → Reducer → Conditional edge", 60, 105, 760, 28, 9002, color=tokens["muted"], font_size=16))
    shape_ids: dict[str, str] = {}
    for index, (shape_id, shape_type, x, y, width, height, value, font_size, stroke, background) in enumerate(shapes):
        box = _excalidraw_base(
            shape_id, shape_type, x, y, width, height, 12000 + index,
            stroke=stroke, background=background, roughness=1,
        )
        label_id = f"{shape_id}_text"
        text = _excalidraw_text(
            label_id, value, x + 10, y + 18, width - 20, height - 28, 12100 + index,
            color=tokens["ink"], container_id=shape_id, font_size=font_size,
        )
        box["boundElements"] = [{"type": "text", "id": label_id}]
        box["customData"].update({"semantic_shape": shape_id, "source": "stateful-graph"})
        elements.extend([box, text])
        shape_ids[shape_id] = shape_id

    arrows = [
        ("state_to_fetch", "state_context", "fetch_node", [(290, 255), (310, 255)], "读取 state"),
        ("fetch_to_delta", "fetch_node", "delta_note", [(530, 260), (550, 260)], "返回 delta"),
        ("delta_to_reducer", "delta_note", "reducer_funnel", [(790, 260), (840, 260)], "合并"),
        ("reducer_to_route", "reducer_funnel", "route_decision", [(965, 335), (965, 395)], "合并后路由"),
        ("route_to_analyze", "route_decision", "analyze_end", [(915, 515), (830, 580)], "condition=true"),
        ("route_to_report", "route_decision", "report_end", [(1045, 515), (1030, 580)], "condition=false"),
    ]
    for index, (arrow_id, source_id, target_id, points, label) in enumerate(arrows):
        (sx, sy), (tx, ty) = points
        arrow = _excalidraw_base(
            arrow_id, "arrow", sx, sy, tx - sx, ty - sy, 13000 + index,
            stroke=tokens["muted"], background="transparent", roughness=1,
        )
        arrow.update(
            {
                "points": [[0, 0], [round(tx - sx, 2), round(ty - sy, 2)]],
                "lastCommittedPoint": None,
                "startBinding": {"elementId": source_id, "focus": 0, "gap": 8, "fixedPoint": [0.5, 0.5]},
                "endBinding": {"elementId": target_id, "focus": 0, "gap": 8, "fixedPoint": [0.5, 0.5]},
                "startArrowhead": None,
                "endArrowhead": "arrow",
            }
        )
        elements.append(arrow)
        label_positions = [(265, 185), (505, 185), (800, 185), (990, 350), (840, 535), (1040, 535)]
        lx, ly = label_positions[index]
        elements.append(_excalidraw_text(f"{arrow_id}_label", label, lx - 55, ly - 12, 110, 24, 13100 + index, color=tokens["muted"], font_size=13))
    elements.append(_excalidraw_text("stateful_footer", "节点读 state → 返回 channel 增量 → reducer 合并 → 条件边选择下一跳", 60, 660, 940, 24, 14000, color=tokens["ink"], font_size=14))
    return {
        "type": "excalidraw",
        "version": 2,
        "source": "https://github.com/excalidraw/excalidraw",
        "elements": elements,
        "appState": {
            "viewBackgroundColor": tokens["paper"],
            "gridSize": None,
            "gridStep": 5,
            "scrollX": 0,
            "scrollY": 0,
            "zoom": {"value": 1},
            "theme": "light",
        },
        "files": {},
        "customData": {
            "contract": "excalidraw-source-v1",
            "renderer": "scripts/render_excalidraw_style.py",
            "layout": "stateful-graph",
            "semantic_shapes": [shape[0] for shape in shapes],
            "semantic_arrows": [arrow[0] for arrow in arrows],
        },
    }


def build_excalidraw_json(title: str, description: str, nodes: list[dict], edges: list[dict], tokens: dict) -> dict:
    """Build a native Excalidraw document from the same graph used by the SVG."""
    labels = {str(node.get("label") or "") for node in nodes}
    if {"route_next", "analyze", "report / END"}.issubset(labels) and len(nodes) >= 7:
        return build_stateful_excalidraw_json(tokens)
    positions = layout_nodes(nodes)
    elements: list[dict] = []
    title_id = "title"
    elements.append(
        _excalidraw_text(title_id, title or "机制关系图", 80, 24, CANVAS_W - 160, 42, 9001,
                         color=tokens["accent"], font_size=28)
    )
    if description:
        elements.append(
            _excalidraw_text("description", description, 80, 68, CANVAS_W - 160, 30, 9002,
                             color=tokens["muted"], font_size=16)
        )

    node_boxes: dict[str, dict] = {}
    for index, node in enumerate(nodes):
        node_id = str(node.get("id") or index)
        x, y = positions[node_id]
        stroke = tokens["accent"] if node.get("accent") else tokens["line"]
        box_id = f"node-{node_id}"
        label_id = f"label-{node_id}"
        box = _excalidraw_base(
            box_id, "rectangle", x, y, NODE_W, NODE_H, 10000 + index,
            stroke=stroke, background=tokens["surface"], roughness=1,
        )
        label = str(node.get("label") or node.get("title") or node_id)
        text = _excalidraw_text(
            label_id, label, x + 10, y + 24, NODE_W - 20, 42, 10100 + index,
            color=tokens["ink"], container_id=box_id, font_size=node_font_size(label),
        )
        box["boundElements"] = [{"type": "text", "id": label_id}]
        elements.extend([box, text])
        node_boxes[node_id] = {"id": box_id, "x": x, "y": y, "w": NODE_W, "h": NODE_H}

    for index, edge in enumerate(edges):
        source = str(edge.get("source") or edge.get("from") or "")
        target = str(edge.get("target") or edge.get("to") or "")
        if source not in node_boxes or target not in node_boxes:
            continue
        src = node_boxes[source]
        dst = node_boxes[target]
        sx = src["x"] + src["w"]
        sy = src["y"] + src["h"] / 2
        tx = dst["x"]
        ty = dst["y"] + dst["h"] / 2
        if tx < sx:
            sx = src["x"]
            tx = dst["x"] + dst["w"]
        arrow_id = f"edge-{index}"
        arrow = _excalidraw_base(
            arrow_id, "arrow", sx, sy, tx - sx, ty - sy, 11000 + index,
            stroke=tokens["accent"], background="transparent", roughness=1,
        )
        arrow.update(
            {
                "points": [[0, 0], [round(tx - sx, 2), round(ty - sy, 2)]],
                "lastCommittedPoint": None,
                "startBinding": {
                    "elementId": src["id"],
                    "focus": 0,
                    "gap": 8,
                    "fixedPoint": [1, 0.5],
                },
                "endBinding": {
                    "elementId": dst["id"],
                    "focus": 0,
                    "gap": 8,
                    "fixedPoint": [0, 0.5],
                },
                "startArrowhead": None,
                "endArrowhead": "arrow",
            }
        )
        elements.append(arrow)
        label = str(edge.get("label") or "").strip()
        if label:
            elements.append(
                _excalidraw_text(
                    f"edge-label-{index}", label,
                    (sx + tx) / 2 - 50, (sy + ty) / 2 - 24, 100, 28, 11100 + index,
                    color=tokens["muted"], font_size=14,
                )
            )

    return {
        "type": "excalidraw",
        "version": 2,
        "source": "https://github.com/excalidraw/excalidraw",
        "elements": elements,
        "appState": {
            "viewBackgroundColor": tokens["paper"],
            "gridSize": None,
            "gridStep": 5,
            "scrollX": 0,
            "scrollY": 0,
            "zoom": {"value": 1},
            "theme": "light",
        },
        "files": {},
        "customData": {
            "contract": "excalidraw-source-v1",
            "renderer": "scripts/render_excalidraw_style.py",
            "layout": "hand-drawn-flow",
            "node_ids": [str(node.get("id") or index) for index, node in enumerate(nodes)],
            "edge_ids": [f"edge-{index}" for index, _ in enumerate(edges)],
        },
    }


def _native_renderer() -> Path | None:
    candidates = [
        Path(__file__).resolve().parents[1] / "skills" / "excalidraw-skill-pack" / "packages" / "renderer-python" / ".venv" / "Scripts" / "python.exe",
        Path(__file__).resolve().parents[1] / "skills" / "excalidraw-skill-pack" / "packages" / "renderer-python" / ".venv" / "bin" / "python",
    ]
    return next((path for path in candidates if path.is_file()), None)


def render_native_excalidraw(document_path: Path, output: Path) -> bool:
    """Use the installed Excalidraw renderer when available."""
    renderer = _native_renderer()
    if not renderer:
        return False
    command = [
        str(renderer), "-c", "from excalidraw_render.cli import main; raise SystemExit(main())",
        str(document_path), "--theme", "default-sketchy",
        "--output", str(output), "--scale", "1", "--width", str(CANVAS_W),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and output.is_file() and output.stat().st_size >= 1024


def layout_nodes(nodes: list[dict], edges: list[dict] | None = None) -> dict[str, tuple[float, float]]:
    """Simple layered layout for a small graph (≤ 8 nodes)."""
    labels = {str(node.get("label") or "") for node in nodes}
    if {"route_next", "analyze", "report / END"}.issubset(labels) and len(nodes) >= 7:
        # A state graph is not a generic two-row grid: route_next is a fan-out
        # hub and its two outcomes need a clear left/right landing zone.
        preferred = {
            "AgentState": (48, 180),
            "fetch node": (300, 180),
            "state_update[messages]": (552, 180),
            "Reducer: operator.add": (804, 180),
            "route_next": (552, 410),
            "analyze": (300, 560),
            "report / END": (804, 560),
        }
        positions = {}
        for index, node in enumerate(nodes):
            nid = str(node.get("id") or index)
            label = str(node.get("label") or "")
            positions[nid] = preferred.get(label, (48 + (index % 4) * 252, 180 + (index // 4) * 230))
        return positions
    count = len(nodes)
    positions = {}
    if count <= 3:
        cols = count
        rows = 1
    elif count <= 6:
        cols = 3
        rows = 2
    else:
        cols = 4
        rows = 2
    gap_x = (CANVAS_W - cols * NODE_W) / (cols + 1)
    gap_y = (CANVAS_H - 180 - rows * NODE_H) / (rows + 1)
    for i, node in enumerate(nodes):
        col = i % cols
        row = i // cols
        x = gap_x + col * (NODE_W + gap_x)
        y = 120 + gap_y + row * (NODE_H + gap_y)
        positions[str(node.get("id") or i)] = (x, y)
    return positions


def _text(x: float, y: float, value: str, *, size: int = 20, color: str = "#17324D", weight: str = "600", anchor: str = "middle", role: str = "node", edge_id: str = "") -> str:
    role_attr = f' data-role="{esc(role)}"' if role else ""
    edge_attr = f' data-edge-id="{esc(edge_id)}"' if edge_id else ""
    return (
        f'<text{role_attr}{edge_attr} x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'fill="{color}" font-size="{size}" font-weight="{weight}" '
        f'font-family="PingFang SC, Microsoft YaHei, Segoe UI, sans-serif">{esc(value)}</text>'
    )


def _arrow_between(x1: float, y1: float, x2: float, y2: float, stroke: str, seed: int = 0) -> str:
    return routed_edge([(x1, y1), (x2, y2)], stroke, width=3) + arrow_head(x2, y2, math.atan2(y2 - y1, x2 - x1), stroke)


def build_routing_svg(title: str, description: str, data: dict, tokens: dict) -> str:
    """Render the MoE idea as a fan-out/convergence argument, not equal cards."""
    paper, ink, muted = tokens["paper"], tokens["ink"], tokens["muted"]
    accent, line, surface = tokens["accent"], tokens["line"], tokens["surface"]
    experts = [str(value) for value in data.get("experts", []) if str(value).strip()] or [f"专家 E{i}" for i in range(1, 9)]
    active = {str(value) for value in data.get("active_experts", []) if str(value).strip()} or {experts[1], experts[5]}
    weights = [str(value) for value in data.get("weights", []) if str(value).strip()] or ["0.62", "0.38"]
    input_label = str(data.get("input") or "Token x")
    router_label = str(data.get("router") or "门控路由")
    output_label = str(data.get("output") or "加权输出 y")
    geometry_nodes: list[dict] = []
    geometry_edges: list[dict] = []

    def add_node(node_id: str, x: float, y: float, w: float, h: float) -> None:
        geometry_nodes.append({"id": node_id, "bbox": [x, y, w, h]})

    def add_edge(edge_id: str, points: list[tuple[float, float]], source: str = "", target: str = "", **extra: object) -> None:
        geometry_edges.append({"id": edge_id, "source": source, "target": target, "points": [[x, y] for x, y in points], **extra})

    parts = [
        f'<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}" data-background-token="background" data-layout-archetype="fan-out-routing">',
        f'<rect data-role="canvas" data-background-token="background" width="{CANVAS_W}" height="{CANVAS_H}" fill="{paper}"/>',
        _text(CANVAS_W / 2, 52, "MOE · FAN-OUT ROUTING", size=16, color=accent, weight="700", role="meta"),
        _text(CANVAS_W / 2, 92, title, size=28, color=ink, weight="700"),
        _text(CANVAS_W / 2, 124, description, size=18, color=muted, weight="400", role="meta"),
        _text(600, 166, "稀疏激活不是少加载参数，而是让每个 token 只走 Top-K 条专家路径", size=21, color=ink, weight="700"),
    ]
    # Main causal path: input → router → fan-out experts → weighted merge.
    add_node("input", 56, 270, 174, 108)
    parts.append(rough_rect(56, 270, 174, 108, accent, surface, seed=11))
    parts += [_text(143, 315, input_label, size=24, color=ink, weight="700"), _text(143, 350, "同一个 token", size=16, color=muted, weight="400", role="meta")]
    add_node("router", 278, 244, 214, 160)
    parts.append(rough_rect(278, 244, 214, 160, accent, paper, seed=12))
    parts += [_text(385, 300, router_label, size=24, color=ink, weight="700"), _text(385, 335, "对 N 个专家打分", size=16, color=muted, weight="400", role="meta"), _text(385, 368, "Top-K 选择", size=19, color=accent, weight="700")]
    input_route = [(232, 324), (270, 324)]
    add_edge("input-to-router", input_route, "input", "router")
    parts.append(_arrow_between(232, 324, 270, 324, line, 1))
    parts.append(_text(252, 304, "x", size=16, color=muted, weight="600", role="meta"))
    # Use a routing spine so fan-out branches stay legible instead of
    # crossing through the expert labels.
    parts.append(_arrow_between(492, 324, 520, 324, line, 2))
    parts.append(routed_edge([(520, 200), (520, 390)], line, edge_id="routing-spine", width=3))

    grid_x, grid_y, cell_w, cell_h, gap = 545, 218, 104, 62, 15
    for i, label in enumerate(experts[:8]):
        row, col = divmod(i, 4)
        x, y = grid_x + col * (cell_w + gap), grid_y + row * (cell_h + 24)
        is_active = label in active or f"E{i + 1}" in active or f"专家 E{i + 1}" in active
        stroke = accent if is_active else line
        fill = "#FFF3E9" if is_active else surface
        node_id = f"E{i + 1}"
        add_node(node_id, x, y, cell_w, cell_h)
        parts.append(rough_rect(x, y, cell_w, cell_h, stroke, fill, seed=40 + i))
        parts.append(_text(x + cell_w / 2, y + 29, label, size=17, color=ink, weight="700"))
        parts.append(_text(x + cell_w / 2, y + 50, "激活" if is_active else "休眠", size=13, color=accent if is_active else muted, weight="700", role="meta"))
        # Fan-out uses an outside corridor per column.  The old straight
        # spokes ran through E1/E2/E3 labels; explicit orthogonal routing keeps
        # every edge outside non-endpoint nodes.
        center_y = y + cell_h / 2
        bus_y = 200 if row == 0 else 390
        corridor_x = [537, 656, 775, 894][col]
        route = [(520, bus_y), (corridor_x, bus_y), (corridor_x, center_y), (x - 8, center_y)]
        edge_id = f"router-to-{node_id}"
        add_edge(edge_id, route, "router", node_id, source_port=[520, 324], junction_group="router-spine", overlap_group=f"fanout-{'top' if row == 0 else 'bottom'}")
        parts.append(routed_edge(route, accent if is_active else line, edge_id=edge_id, width=3))
        parts.append(arrow_head(x - 8, center_y, 0.0, accent if is_active else line))

    output_x, output_y, output_w, output_h = 1028, 270, 144, 108
    add_node("output", output_x, output_y, output_w, output_h)
    parts.append(rough_rect(output_x, output_y, output_w, output_h, accent, surface, seed=99))
    parts += [_text(1100, 315, output_label, size=22, color=ink, weight="700"), _text(1100, 350, "专家加权合并", size=15, color=muted, weight="400", role="meta")]
    weight_index = 0
    for i, label in enumerate(experts[:8]):
        row, col = divmod(i, 4)
        x, y = grid_x + col * (cell_w + gap), grid_y + row * (cell_h + 24)
        if label in active or f"E{i + 1}" in active or f"专家 E{i + 1}" in active:
            weight = weights[weight_index] if weight_index < len(weights) else "权重"
            weight_index += 1
            center_y = y + cell_h / 2
            if row == 0:
                # Use the gap between the two expert rows; routing above the
                # top row would intersect the fan-out bus at y=200.
                route = [(x + cell_w + 8, center_y), (776, 292), (1018, 292), (1018, 300), (1020, 300)]
                label_y = 282
            else:
                # Drop below the bottom fan-out bus, then merge.  The explicit
                # cross_group records the intentional T-junction with that
                # shared trunk; arbitrary crossings remain blocking.
                route = [(x + cell_w + 8, center_y), (776, 410), (1018, 410), (1018, 348), (1020, 348)]
                label_y = 430
            edge_id = f"{label}-to-output"
            add_edge(edge_id, route, f"E{i + 1}", "output", cross_group="fanout-bottom" if row == 1 else "")
            parts.append(routed_edge(route, accent, edge_id=edge_id, width=3))
            parts.append(arrow_head(route[-1][0], route[-1][1], math.atan2(route[-1][1] - route[-2][1], route[-1][0] - route[-2][0]), accent))
            parts.append(_text(930, label_y, weight, size=15, color=accent, weight="700", role="meta"))

    # Semantic callouts teach the key distinction and are also visible QA anchors.
    parts.append(rough_rect(64, 500, 500, 112, line, surface, seed=140))
    parts += [_text(92, 532, "稠密模型", size=20, color=ink, weight="700", anchor="start"), _text(92, 566, "每个 token 都经过全部 FFN 专家", size=18, color=muted, weight="400", anchor="start"), _text(92, 596, "总参数 = 每次计算的全部路径", size=17, color=ink, weight="600", anchor="start")]
    parts.append(rough_rect(594, 500, 556, 112, accent, "#FFF3E9", seed=141))
    parts += [_text(622, 532, "稀疏激活", size=20, color=ink, weight="700", anchor="start"), _text(622, 566, f"Top-K 只激活 {len(active)} 个专家，其余保持休眠", size=18, color=muted, weight="400", anchor="start"), _text(622, 596, "激活计算 ≠ 显存占用", size=17, color=accent, weight="700", anchor="start")]
    parts.insert(3, geometry_metadata(geometry_nodes, geometry_edges, background=paper))
    parts.append("</svg>")
    return "".join(parts)


def build_comparison_svg(title: str, description: str, data: dict, tokens: dict) -> str:
    """Render model comparison as two scales + routing badges, not a card chain."""
    paper, ink, muted = tokens["paper"], tokens["ink"], tokens["muted"]
    accent, line, surface = tokens["accent"], tokens["line"], tokens["surface"]
    rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    rows = [row for row in rows if isinstance(row, dict)]
    if not rows:
        rows = [{"model": "当前主题模型", "total": "总参数", "active": "激活参数", "route": "Top-K", "total_ratio": 1.0, "active_ratio": 0.6}]
    max_rows = rows[:5]
    total_x, active_x, bar_w = 330, 680, 230
    max_total = max(float(row.get("total_ratio") or 0) for row in max_rows) or 1.0
    max_active = max(float(row.get("active_ratio") or 0) for row in max_rows) or 1.0
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}" data-background-token="background" data-layout-archetype="comparison-bars">',
        f'<rect data-role="canvas" data-background-token="background" width="{CANVAS_W}" height="{CANVAS_H}" fill="{paper}"/>',
        _text(CANVAS_W / 2, 52, "MOE · MODEL LANDSCAPE", size=16, color=accent, weight="700", role="meta"),
        _text(CANVAS_W / 2, 92, title, size=28, color=ink, weight="700"),
        _text(CANVAS_W / 2, 124, description, size=18, color=muted, weight="400", role="meta"),
        _text(330, 176, "模型 / 总参数", size=17, color=muted, weight="700"),
        _text(total_x + bar_w / 2, 176, "容量尺度", size=17, color=muted, weight="700"),
        _text(active_x + bar_w / 2, 176, "单 token 激活尺度", size=17, color=muted, weight="700"),
        _text(1084, 176, "路由", size=17, color=muted, weight="700"),
    ]
    parts.insert(3, geometry_metadata([], [], background=paper))
    for i, row in enumerate(max_rows):
        y = 220 + i * 74
        model = str(row.get("model") or "模型")
        total = str(row.get("total") or "—")
        active_value = str(row.get("active") or "—")
        route = str(row.get("route") or "Top-K")
        total_ratio = max(0.04, min(1.0, float(row.get("total_ratio") or 0) / max_total))
        active_ratio = max(0.08, min(1.0, float(row.get("active_ratio") or 0) / max_active))
        parts.append(_text(72, y + 26, model, size=18, color=ink, weight="700", anchor="start"))
        parts.append(_text(72, y + 52, f"总 {total} · 激活 {active_value}", size=14, color=muted, weight="400", anchor="start", role="meta"))
        parts.append(rough_rect(total_x, y, bar_w, 24, line, surface, seed=200 + i))
        parts.append(f'<rect x="{total_x}" y="{y}" width="{bar_w * total_ratio:.1f}" height="24" rx="10" fill="{line}"/>')
        parts.append(rough_rect(active_x, y, bar_w, 24, accent, "#FFF3E9", seed=220 + i))
        parts.append(f'<rect x="{active_x}" y="{y}" width="{bar_w * active_ratio:.1f}" height="24" rx="10" fill="{accent}"/>')
        parts.append(_text(total_x + bar_w + 12, y + 18, total, size=15, color=ink, weight="700", anchor="start"))
        parts.append(_text(active_x + bar_w + 12, y + 18, active_value, size=15, color=accent, weight="700", anchor="start"))
        parts.append(rough_rect(1060, y - 2, 100, 30, accent if i == 0 else line, "#FFF3E9" if i == 0 else surface, seed=240 + i))
        parts.append(_text(1110, y + 18, route, size=14, color=ink, weight="700"))
    parts.append(rough_rect(72, 610, 1088, 52, accent, "#FFF3E9", seed=280))
    parts.append(_text(616, 643, "总参数决定容量，激活参数代理计算；两者都不能直接等于显存或端到端延迟", size=19, color=ink, weight="700"))
    parts.append("</svg>")
    return "".join(parts)


def _rough_ellipse(cx: float, cy: float, rx: float, ry: float, stroke: str, fill: str, seed: int = 0) -> str:
    """Draw a gently imperfect ellipse without introducing a card grid."""
    rng = random.Random(seed)
    dx = rng.uniform(-2, 2)
    dy = rng.uniform(-2, 2)
    k = 0.5522848
    return (
        f'<path d="M{cx - rx:.1f},{cy + dy:.1f} '
        f'C{cx - rx:.1f},{cy - k * ry + dy:.1f} {cx - k * rx + dx:.1f},{cy - ry:.1f} {cx + dx:.1f},{cy - ry:.1f} '
        f'C{cx + k * rx + dx:.1f},{cy - ry:.1f} {cx + rx:.1f},{cy - k * ry + dy:.1f} {cx + rx:.1f},{cy + dy:.1f} '
        f'C{cx + rx:.1f},{cy + k * ry + dy:.1f} {cx + k * rx + dx:.1f},{cy + ry:.1f} {cx + dx:.1f},{cy + ry:.1f} '
        f'C{cx - k * rx + dx:.1f},{cy + ry:.1f} {cx - rx:.1f},{cy + k * ry + dy:.1f} {cx - rx:.1f},{cy + dy:.1f} Z" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="2.5" stroke-linejoin="round"/>'
    )


def _rough_cloud(cx: float, cy: float, w: float, h: float, stroke: str, fill: str, seed: int = 0) -> str:
    """Draw a context cloud: state is a shared context, not a process card."""
    rng = random.Random(seed)
    left, right = cx - w / 2, cx + w / 2
    top, bottom = cy - h / 2, cy + h / 2
    bumps = [rng.uniform(-3, 3) for _ in range(8)]
    d = (
        f"M{left + 18:.1f},{cy + 18 + bumps[0]:.1f} "
        f"C{left - 4 + bumps[1]:.1f},{cy + 2:.1f} {left + 4 + bumps[2]:.1f},{top + 22:.1f} {left + 34:.1f},{top + 22:.1f} "
        f"C{left + 42:.1f},{top - 2 + bumps[3]:.1f} {left + 84:.1f},{top - 5:.1f} {left + 102:.1f},{top + 18:.1f} "
        f"C{left + 130:.1f},{top - 10 + bumps[4]:.1f} {left + 184:.1f},{top + 3:.1f} {left + 184:.1f},{top + 28:.1f} "
        f"C{right + 2:.1f},{top + 25:.1f} {right + 8:.1f},{cy + 16:.1f} {right - 16:.1f},{cy + 24:.1f} "
        f"C{right - 15:.1f},{bottom + 4 + bumps[5]:.1f} {right - 65:.1f},{bottom + 5:.1f} {right - 82:.1f},{bottom - 14:.1f} "
        f"C{right - 112:.1f},{bottom + 12 + bumps[6]:.1f} {left + 66:.1f},{bottom + 7:.1f} {left + 56:.1f},{bottom - 15:.1f} "
        f"C{left + 20:.1f},{bottom - 5 + bumps[7]:.1f} {left - 4:.1f},{cy + 30:.1f} {left + 18:.1f},{cy + 18 + bumps[0]:.1f} Z"
    )
    return f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="2.5" stroke-linejoin="round"/>'


def _rough_diamond(x: float, y: float, w: float, h: float, stroke: str, fill: str, seed: int = 0) -> str:
    rng = random.Random(seed)
    points = [
        (x + w / 2 + rng.uniform(-3, 3), y),
        (x + w + rng.uniform(-3, 3), y + h / 2),
        (x + w / 2 + rng.uniform(-3, 3), y + h),
        (x + rng.uniform(-3, 3), y + h / 2),
    ]
    raw = " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
    return f'<polygon points="{raw}" fill="{fill}" stroke="{stroke}" stroke-width="2.5" stroke-linejoin="round"/>'


def _rough_funnel(x: float, y: float, w: float, h: float, stroke: str, fill: str, seed: int = 0) -> str:
    rng = random.Random(seed)
    top_left = x + rng.uniform(-3, 3)
    top_right = x + w + rng.uniform(-3, 3)
    bottom_left = x + w * 0.2 + rng.uniform(-3, 3)
    bottom_right = x + w * 0.8 + rng.uniform(-3, 3)
    return (
        f'<path d="M{top_left:.1f},{y:.1f} L{top_right:.1f},{y:.1f} '
        f'L{bottom_right:.1f},{y + h:.1f} L{bottom_left:.1f},{y + h:.1f} Z" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="2.5" stroke-linejoin="round"/>'
    )


def _audit_line(edge_id: str, start: tuple[float, float], end: tuple[float, float], *, junction: str = "") -> str:
    junction_attr = f' data-junction-group="{esc(junction)}"' if junction else ""
    return (
        f'<line data-role="edge" data-edge-id="{esc(edge_id)}" data-arrowhead="true"{junction_attr} '
        f'x1="{start[0]:.1f}" y1="{start[1]:.1f}" x2="{end[0]:.1f}" y2="{end[1]:.1f}" stroke="none"/>'
        + audit_arrowhead(end[0], end[1], math.atan2(end[1] - start[1], end[0] - start[0]), edge_id)
    )


def build_stateful_graph_svg(title: str, description: str, data: dict, tokens: dict) -> str:
    """Render StateGraph as a visual argument, not seven equal cards.

    The primary path is a left-to-right transformation.  Shape vocabulary is
    semantic: context cloud → action → data delta → reducer funnel → decision
    diamond → terminal outcomes.  The small evidence strings make the
    mechanism concrete enough to teach from the image alone.
    """
    paper, ink, muted = tokens["paper"], tokens["ink"], tokens["muted"]
    accent, line, surface = tokens["accent"], tokens["line"], tokens["surface"]
    nodes = [
        {"id": "n0", "label": "AgentState", "bbox": [60, 190, 220, 130]},
        {"id": "n1", "label": "fetch node", "bbox": [320, 210, 200, 100]},
        {"id": "n2", "label": "state_update[messages]", "bbox": [560, 210, 220, 100]},
        {"id": "n3", "label": "Reducer: operator.add", "bbox": [850, 185, 230, 140]},
        {"id": "n4", "label": "route_next", "bbox": [885, 405, 190, 120]},
        {"id": "n5", "label": "analyze", "bbox": [615, 580, 220, 70]},
        {"id": "n6", "label": "report / END", "bbox": [920, 580, 220, 70]},
    ]
    edges = [
        {"id": "edge-0", "source": "n0", "target": "n1", "label": "读取 state", "start": (290, 255), "end": (310, 255)},
        {"id": "edge-1", "source": "n1", "target": "n2", "label": "返回 delta", "start": (530, 260), "end": (550, 260)},
        {"id": "edge-2", "source": "n2", "target": "n3", "label": "合并", "start": (790, 260), "end": (840, 260)},
        {"id": "edge-3", "source": "n3", "target": "n4", "label": "合并后路由", "start": (965, 335), "end": (965, 395)},
        {"id": "edge-4", "source": "n4", "target": "n5", "label": "condition=true", "start": (915, 515), "end": (830, 580)},
        {"id": "edge-5", "source": "n4", "target": "n6", "label": "condition=false", "start": (1045, 515), "end": (1030, 580)},
    ]
    geometry_nodes = [{"id": node["id"], "bbox": node["bbox"]} for node in nodes]
    geometry_edges = [{"id": edge["id"], "source": edge["source"], "target": edge["target"], "points": [[*edge["start"]], [*edge["end"]]]} for edge in edges]
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="760" viewBox="0 0 {CANVAS_W} 760" data-background-token="background" data-backend="excalidraw" data-renderer="scripts/render_excalidraw_style.py" data-layout-archetype="stateful-graph" data-requires-safe-frame="true">',
        f'<rect data-role="canvas" data-background-token="background" width="{CANVAS_W}" height="760" fill="{paper}"/>',
        '<rect data-role="frame" data-qa-only="true" x="36" y="36" width="1128" height="688" fill="none" stroke="none"/>',
        geometry_metadata(geometry_nodes, geometry_edges, background=paper, canvas_height=760),
        _text(60, 58, "STATEGRAPH / ONE PASS", size=15, color=accent, weight="700", anchor="start", role="meta"),
        _text(60, 94, "读状态，合并增量，再决定下一跳", size=30, color=ink, weight="700", anchor="start"),
        _text(60, 122, "一条节点执行轨迹：State → Delta → Reducer → Conditional edge", size=17, color=muted, weight="400", anchor="start", role="meta"),
        _text(60, 160, "01 读取与产出", size=15, color=muted, weight="700", anchor="start", role="meta"),
        _text(850, 160, "02 合并与路由", size=15, color=muted, weight="700", anchor="start", role="meta"),
    ]
    # Main semantic shapes.
    parts.append(_rough_cloud(170, 255, 220, 130, accent, "#FFF3E9", seed=20))
    parts.append(_text(170, 238, "AgentState", size=22, color=ink, weight="700", role="node"))
    parts.append(_text(170, 268, "messages: [history]", size=15, color=muted, weight="600", role="meta"))
    parts.append(_text(170, 290, "next_step: \"report\"", size=15, color=muted, weight="600", role="meta"))

    parts.append(rough_rect(320, 210, 200, 100, line, surface, seed=30))
    parts.append(_text(420, 244, "fetch node", size=21, color=ink, weight="700", role="node"))
    parts.append(_text(420, 272, "fetch_data(state)", size=15, color=muted, weight="600", role="meta"))
    parts.append(_text(420, 294, "return {…}", size=15, color=accent, weight="700", role="meta"))

    parts.append(rough_rect(560, 210, 220, 100, accent, "#FFF8ED", seed=40))
    parts.append(f'<path d="M760,210 L780,230 L780,210 Z" fill="{accent}" opacity="0.18"/>')
    parts.append(_text(670, 244, "state_update[messages]", size=16, color=ink, weight="700", role="node"))
    parts.append(_text(670, 274, '{"messages": [+1]}', size=15, color=accent, weight="700", role="meta"))
    parts.append(_text(670, 296, "只返回增量，不搬运全量 state", size=14, color=muted, weight="600", role="meta"))

    parts.append(_rough_funnel(850, 185, 230, 140, accent, "#FFF3E9", seed=50))
    parts.append(_text(965, 232, "Reducer: operator.add", size=16, color=ink, weight="700", role="node"))
    parts.append(_text(965, 267, "old + delta", size=19, color=accent, weight="700", role="meta"))
    parts.append(_text(965, 294, "messages′ 写回状态", size=15, color=muted, weight="600", role="meta"))

    parts.append(_rough_diamond(885, 405, 190, 120, accent, "#FFF8ED", seed=60))
    parts.append(_text(980, 456, "route_next", size=19, color=ink, weight="700", role="node"))
    parts.append(_text(980, 482, "need_analysis?", size=15, color=muted, weight="600", role="meta"))

    parts.append(_rough_ellipse(725, 615, 110, 35, line, surface, seed=70))
    parts.append(_text(725, 610, "analyze", size=19, color=ink, weight="700", role="node"))
    parts.append(_text(725, 632, "继续处理", size=14, color=muted, weight="600", role="meta"))
    parts.append(_rough_ellipse(1030, 615, 110, 35, accent, "#FFF3E9", seed=71))
    parts.append(_text(1030, 610, "report / END", size=18, color=ink, weight="700", role="node"))
    parts.append(_text(1030, 632, "结束执行", size=14, color=accent, weight="700", role="meta"))

    # Draw the arrows after the shapes so the route is visually dominant but
    # still stops at the node boundary; labels sit in dedicated whitespace.
    audit_edges = []
    label_positions = [(300, 174), (540, 174), (815, 174), (1015, 365), (875, 548), (1080, 548)]
    for edge, (lx, ly) in zip(edges, label_positions):
        start, end = edge["start"], edge["end"]
        parts.append(routed_edge([start, end], muted, edge_id=edge["id"], width=3))
        parts.append(arrow_head(end[0], end[1], math.atan2(end[1] - start[1], end[0] - start[0]), muted))
        parts.append(_text(lx, ly, edge["label"], size=13, color=muted, weight="700", role="edge-label", edge_id=edge["id"]))
        audit_edges.append(_audit_line(edge["id"], start, end))
    parts.append(_text(60, 678, "读者拿走：节点读完整 state → 返回 channel 增量 → reducer 合并 → 条件边选择 analyze 或 report", size=15, color=ink, weight="700", anchor="start", role="footer"))
    audit_nodes = "".join(
        f'<rect data-role="node" data-node-id="{node["id"]}" x="{node["bbox"][0]}" y="{node["bbox"][1]}" width="{node["bbox"][2]}" height="{node["bbox"][3]}" fill="none" stroke="none"/>'
        for node in nodes
    )
    parts.append(f'<g data-role="qa-geometry">{"".join(audit_edges)}{audit_nodes}</g>')
    parts.append("</svg>")
    return "".join(parts)


def build_svg(title: str, description: str, nodes: list[dict], edges: list[dict], tokens: dict, unit: dict | None = None) -> str:
    unit = unit or {}
    data = unit.get("diagram_data") if isinstance(unit.get("diagram_data"), dict) else {}
    archetype = str(unit.get("layout_archetype") or data.get("layout_archetype") or "").strip().lower()
    if archetype == "stateful-graph":
        return build_stateful_graph_svg(title, description, data, tokens)
    if archetype == "fan-out-routing":
        return build_routing_svg(title, description, data, tokens)
    if archetype == "comparison-bars":
        return build_comparison_svg(title, description, data, tokens)

    paper = tokens["paper"]
    ink = tokens["ink"]
    muted = tokens["muted"]
    accent = tokens["accent"]
    line = tokens["line"]
    surface = tokens["surface"]

    positions = layout_nodes(nodes, edges)
    node_els = []
    audit_nodes = []
    geometry_nodes: list[dict] = []
    for i, node in enumerate(nodes):
        nid = str(node.get("id") or i)
        x, y = positions[nid]
        color = accent if node.get("accent") else line
        fill = surface
        geometry_nodes.append({"id": nid, "bbox": [x, y, NODE_W, NODE_H]})
        node_els.append(rough_rect(x, y, NODE_W, NODE_H, color, fill, seed=i * 7))
        audit_nodes.append(f'<rect data-role="node" data-node-id="{esc(nid)}" x="{x:.1f}" y="{y:.1f}" width="{NODE_W}" height="{NODE_H}" fill="none" stroke="none"/>')
        label = str(node.get("label") or node.get("title") or nid)
        node_els.append(_text(x + NODE_W / 2, y + NODE_H / 2 + 6, label, size=node_font_size(label), color=ink, weight="600"))

    edge_els = []
    audit_edges = []
    geometry_edges: list[dict] = []
    for i, edge in enumerate(edges):
        src = str(edge.get("source") or edge.get("from") or "")
        dst = str(edge.get("target") or edge.get("to") or "")
        if src not in positions or dst not in positions:
            continue
        sx, sy = positions[src]
        tx, ty = positions[dst]
        if abs(tx - sx) >= abs(ty - sy):
            start = (sx + NODE_W + 8, sy + NODE_H / 2) if tx > sx else (sx - 8, sy + NODE_H / 2)
            end = (tx - 8, ty + NODE_H / 2) if tx > sx else (tx + NODE_W + 8, ty + NODE_H / 2)
        else:
            start = (sx + NODE_W / 2, sy + NODE_H + 8) if ty > sy else (sx + NODE_W / 2, sy - 8)
            end = (tx + NODE_W / 2, ty - 8) if ty > sy else (tx + NODE_W / 2, ty + NODE_H + 8)
        route = [start, end]
        geometry_edges.append({"id": f"edge-{i}", "source": src, "target": dst, "points": [[x, y] for x, y in route]})
        edge_els.append(routed_edge(route, muted, edge_id=f"edge-{i}", width=3))
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        edge_els.append(arrow_head(end[0], end[1], angle, muted))
        audit_edges.append(f'<line data-role="edge" data-edge-id="edge-{i}" data-arrowhead="true" x1="{start[0]:.1f}" y1="{start[1]:.1f}" x2="{end[0]:.1f}" y2="{end[1]:.1f}" stroke="none"/>')
        audit_edges.append(audit_arrowhead(end[0], end[1], angle, f"edge-{i}"))
        if edge.get("label"):
            mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
            horizontal = abs(end[0] - start[0]) >= abs(end[1] - start[1])
            label_y = my - 56 if horizontal else my
            edge_els.append(_text(mx, label_y, str(edge["label"]), size=13, color=muted, weight="600", role="edge-label", edge_id=f"edge-{i}"))

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}" data-background-token="background" data-backend="excalidraw" data-renderer="scripts/render_excalidraw_style.py" data-layout-archetype="hand-drawn-flow" data-requires-safe-frame="true">
  <rect data-role="canvas" data-background-token="background" width="{CANVAS_W}" height="{CANVAS_H}" fill="{paper}"/>
  <rect data-role="frame" data-qa-only="true" x="36" y="36" width="{CANVAS_W - 72}" height="{CANVAS_H - 72}" fill="none" stroke="none"/>
  {geometry_metadata(geometry_nodes, geometry_edges, background=paper)}
  <text x="{CANVAS_W / 2}" y="56" text-anchor="middle" fill="{accent}" font-size="16" font-weight="700" letter-spacing="2">SKETCH DIAGRAM · {esc(title[:34])}</text>
  <text x="{CANVAS_W / 2}" y="92" text-anchor="middle" fill="{ink}" font-size="28" font-weight="700">{esc(title)}</text>
  <text x="{CANVAS_W / 2}" y="120" text-anchor="middle" fill="{muted}" font-size="18">{esc(description)}</text>
  {''.join(edge_els)}
  {''.join(node_els)}
  <g data-role="qa-geometry">{''.join(audit_edges)}{''.join(audit_nodes)}</g>
</svg>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an Excalidraw-style SVG diagram.")
    parser.add_argument("--account", default=_default_account(), choices=(_default_account(),))
    parser.add_argument("--title", default="架构草图")
    parser.add_argument("--description", default="手绘风格机制关系图")
    parser.add_argument("--nodes", default="", help='JSON list of {id, label, accent?}')
    parser.add_argument("--edges", default="", help='JSON list of {source, target, label?}')
    parser.add_argument("--output", default="", help="Output PNG path (optional)")
    parser.add_argument("--svg-output", default="", help="Keep SVG source")
    parser.add_argument("--excalidraw-output", default="", help="Keep native Excalidraw JSON source")
    parser.add_argument("--spec", default="")
    parser.add_argument("--spec-id", default="")
    args = parser.parse_args()

    nodes: list[dict] = []
    edges: list[dict] = []
    title = args.title
    description = args.description
    if args.spec and args.spec_id:
        spec = json.loads(Path(args.spec).resolve().read_text(encoding="utf-8"))
        unit = next((u for u in spec.get("units", []) if str(u.get("id")) == args.spec_id), {})
        title = str(unit.get("section_heading") or unit.get("section") or args.title)
        description = str(unit.get("viewer_job") or args.description)
        nodes = unit.get("nodes") or []
        edges = unit.get("edges") or []
    if args.nodes:
        try:
            nodes = json.loads(args.nodes)
        except json.JSONDecodeError:
            pass
    if args.edges:
        try:
            edges = json.loads(args.edges)
        except json.JSONDecodeError:
            pass
    if not nodes:
        nodes = [{"id": "A", "label": "输入"}, {"id": "B", "label": "处理"}, {"id": "C", "label": "输出"}]
        edges = [{"source": "A", "target": "B"}, {"source": "B", "target": "C"}]

    tokens = load_design_tokens(args.account)
    svg = build_svg(title, description, nodes, edges, tokens, unit if args.spec and args.spec_id else None)

    svg_path = Path(args.svg_output).resolve() if args.svg_output else None
    excalidraw_path = Path(args.excalidraw_output).resolve() if args.excalidraw_output else None
    output = Path(args.output).resolve() if args.output else None
    if svg_path:
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        svg_path.write_text(svg, encoding="utf-8")
    if excalidraw_path:
        excalidraw_path.parent.mkdir(parents=True, exist_ok=True)
        document = build_excalidraw_json(title, description, nodes, edges, tokens)
        excalidraw_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)

    # When a native source is requested, prefer the installed Excalidraw
    # renderer.  The SVG remains beside it as a transparent, deterministic
    # fallback and a source-to-raster comparison target.
    render_receipt = svg_path.with_suffix(".render.json") if svg_path else None
    if output and excalidraw_path and render_native_excalidraw(excalidraw_path, output):
        if render_receipt:
            render_receipt.write_text(json.dumps({"status": "passed", "renderer": "excalidraw-skill-pack-renderer", "source": str(excalidraw_path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "role": "excalidraw",
            "account": args.account,
            "png": str(output),
            "svg": str(svg_path) if svg_path else "",
            "excalidraw": str(excalidraw_path),
            "renderer": "excalidraw-skill-pack-renderer",
        }, ensure_ascii=False))
        return 0

    chrome = chrome_path()
    if output:
        if not chrome:
            print("EXCALIDRAW STYLE BLOCKED: 未找到 Chrome", flush=True)
            return 1
        source = svg_path or output.with_suffix(".svg")
        if not svg_path:
            source.write_text(svg, encoding="utf-8")
        command = [str(chrome), "--headless", "--disable-gpu", "--no-sandbox", f"--window-size={CANVAS_W},{CANVAS_H}", f"--screenshot={output}", source.as_uri()]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
        if result.returncode != 0 or not output.is_file() or output.stat().st_size < 1024:
            print("EXCALIDRAW STYLE BLOCKED: Chrome 栅格化失败", flush=True)
            return 1
        if render_receipt:
            render_receipt.write_text(json.dumps({"status": "fallback", "renderer": "chrome-svg-fallback", "source": str(svg_path), "fallback_reason": "native Excalidraw renderer unavailable or failed"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "role": "excalidraw-style",
        "account": args.account,
        "png": str(output) if output else "",
        "svg": str(svg_path) if svg_path else "",
        "excalidraw": str(excalidraw_path) if excalidraw_path else "",
        "renderer": "chrome-svg-fallback" if output else "svg-only",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
