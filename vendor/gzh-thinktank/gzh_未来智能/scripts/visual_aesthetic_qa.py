#!/usr/bin/env python3
"""Objective visual hygiene checks for editable SVG article diagrams.

Geometry QA answers whether an edge intersects a node.  This companion checks
the visual grammar that the former gate missed: routed edges must terminate
with one arrowhead, edge labels may not sit inside nodes or on unrelated
edges, nodes must stay inside the safe frame, and footer/callout text may not
be clipped by the canvas.  It is deliberately conservative and blocks
technical diagrams when these facts cannot be proven from the SVG source.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


CONTRACT = "visual-aesthetic-contract-v1"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _num(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value).replace("px", ""))
    except (TypeError, ValueError):
        return default


def _box(element: ET.Element) -> tuple[float, float, float, float]:
    return (
        _num(element.attrib.get("x")),
        _num(element.attrib.get("y")),
        _num(element.attrib.get("width")),
        _num(element.attrib.get("height")),
    )


def _inside_box(box: tuple[float, float, float, float], outer: tuple[float, float, float, float], margin: float = 0.0) -> bool:
    x, y, w, h = box
    ox, oy, ow, oh = outer
    return x >= ox + margin and y >= oy + margin and x + w <= ox + ow - margin and y + h <= oy + oh - margin


def _segments_cross(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]) -> bool:
    def orient(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    return ((o1 > 0 > o2) or (o1 < 0 < o2)) and ((o3 > 0 > o4) or (o3 < 0 < o4))


def _bbox_overlap(left: tuple[float, float, float, float], right: tuple[float, float, float, float], margin: float = 0.0) -> bool:
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    return not (
        lx + lw < rx - margin
        or rx + rw < lx - margin
        or ly + lh < ry - margin
        or ry + rh < ly - margin
    )


def check_svg(path: Path, declared_layout: str = "") -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not path.is_file():
        return {"status": "failed", "errors": [f"SVG 不存在：{path}"], "warnings": []}
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except (ET.ParseError, OSError) as exc:
        return {"status": "failed", "errors": [f"SVG 无法解析：{exc}"], "warnings": []}

    width = _num(root.attrib.get("width"))
    height = _num(root.attrib.get("height"))
    if width <= 0 or height <= 0:
        errors.append("SVG 缺少有效宽高")
    canvas = next((node for node in root.iter() if _local(node.tag) == "rect" and node.attrib.get("data-role") == "canvas"), None)
    frame = next((node for node in root.iter() if _local(node.tag) == "rect" and node.attrib.get("data-role") == "frame"), None)
    if frame is None:
        frame = next((node for node in root.iter() if _local(node.tag) == "rect" and node.attrib.get("data-role") != "canvas" and node.attrib.get("stroke")), None)
    if frame is not None and frame.attrib.get("data-role") == "frame" and str(frame.attrib.get("data-qa-only") or "").lower() not in {"true", "1"} and str(frame.attrib.get("stroke") or "").lower() not in {"", "none", "transparent"}:
        errors.append("safe-area frame 只能作为 QA 元数据，不能出现在最终画面")
    requires_frame = str(root.attrib.get("data-requires-safe-frame") or "").lower() in {"true", "1"}
    if canvas is None or frame is None:
        if requires_frame:
            errors.append("缺少 canvas/frame safe-area 证据")
        frame_box = (36.0, 36.0, max(0.0, width - 72), max(0.0, height - 72))
    else:
        frame_box = _box(frame)

    layout = str(root.attrib.get("data-layout-archetype") or declared_layout or "")
    if not layout:
        errors.append("SVG 缺少 data-layout-archetype；无法证明构图族与认知任务匹配")

    nodes: dict[str, tuple[float, float, float, float]] = {}
    for element in root.iter():
        if _local(element.tag) == "rect" and element.attrib.get("data-role") == "node":
            node_id = str(element.attrib.get("data-node-id") or "")
            nodes[node_id] = _box(element)
            if not _inside_box(nodes[node_id], frame_box, 12):
                errors.append(f"节点越过 safe frame：{node_id}")

    edges: list[dict[str, Any]] = []
    arrowheads: dict[str, list[tuple[float, float]]] = {}
    for element in root.iter():
        if _local(element.tag) == "polygon" and element.attrib.get("data-role") == "arrowhead":
            raw_points = str(element.attrib.get("points") or "").split()
            parsed: list[tuple[float, float]] = []
            for raw in raw_points:
                if "," not in raw:
                    continue
                x, y = raw.split(",", 1)
                parsed.append((_num(x), _num(y)))
            if parsed:
                arrowheads[str(element.attrib.get("data-edge-id") or "")]=parsed
            continue
        if _local(element.tag) != "line" or element.attrib.get("data-role") != "edge":
            continue
        edge_id = str(element.attrib.get("data-edge-id") or "edge")
        a = (_num(element.attrib.get("x1")), _num(element.attrib.get("y1")))
        b = (_num(element.attrib.get("x2")), _num(element.attrib.get("y2")))
        edges.append({
            "id": edge_id,
            "a": a,
            "b": b,
            "junction": str(element.attrib.get("data-junction-group") or ""),
            "arrowhead": str(element.attrib.get("data-arrowhead") or "true").lower() == "true",
        })
        for point in (a, b):
            if not (frame_box[0] <= point[0] <= frame_box[0] + frame_box[2] and frame_box[1] <= point[1] <= frame_box[1] + frame_box[3]):
                errors.append(f"连线端点越过 safe frame：{edge_id}")

    for edge in edges:
        if not edge["arrowhead"]:
            continue
        polygon = arrowheads.get(edge["id"])
        if not polygon or len(polygon) < 3:
            errors.append(f"连线缺少可验证箭头几何：{edge['id']}")
            continue
        end = edge["b"]
        tip = min(polygon, key=lambda point: math.dist(point, end))
        base = [point for point in polygon if point != tip]
        if len(base) >= 2:
            base_center = (sum(point[0] for point in base) / len(base), sum(point[1] for point in base) / len(base))
            dx, dy = end[0] - edge["a"][0], end[1] - edge["a"][1]
            norm = max(1.0, math.hypot(dx, dy))
            direction = (dx / norm, dy / norm)
            if (base_center[0] - end[0]) * direction[0] + (base_center[1] - end[1]) * direction[1] >= -1.0:
                errors.append(f"箭头方向与连线不一致：{edge['id']}")

    groups: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        if edge["junction"]:
            groups.setdefault(edge["junction"], []).append(edge)
    for group, members in groups.items():
        arrow_count = sum(1 for member in members if member["arrowhead"])
        if arrow_count != 1:
            errors.append(f"路由组 {group} 必须只有一个终点箭头，当前 {arrow_count} 个")
        if len(members) - 1 > 3:
            errors.append(f"路由组 {group} 转折过多：{len(members) - 1} turns")

    labels: list[dict[str, Any]] = []
    for element in root.iter():
        if _local(element.tag) != "text":
            continue
        role = str(element.attrib.get("data-role") or "")
        x, y = _num(element.attrib.get("x")), _num(element.attrib.get("y"))
        size = max(10.0, _num(element.attrib.get("font-size"), 15.0))
        text = "".join(element.itertext()).strip()
        if role == "edge-label":
            labels.append({
                "id": str(element.attrib.get("data-edge-id") or ""),
                "text": text,
                "bbox": (x - max(8.0, len(text) * size * 0.25), y - size, max(16.0, len(text) * size * 0.5), size * 1.2),
            })
        if role == "footer":
            if y > height - 42:
                errors.append(f"footer 可能被画布裁切：baseline={y}, height={height}")
            if y < height * 0.72:
                warnings.append(f"footer 未落在底部安全区：baseline={y}, height={height}")

    for label in labels:
        for node_id, node_box in nodes.items():
            if _bbox_overlap(label["bbox"], node_box, 0):
                errors.append(f"边标签落入节点：{label['text']} × {node_id}")
        for edge in edges:
            if edge["id"] == label["id"]:
                continue
            a, b = edge["a"], edge["b"]
            # A line passing through a label box is an objectively ambiguous
            # reading order even when it does not touch a node.
            corners = [
                (label["bbox"][0], label["bbox"][1]),
                (label["bbox"][0] + label["bbox"][2], label["bbox"][1]),
                (label["bbox"][0] + label["bbox"][2], label["bbox"][1] + label["bbox"][3]),
                (label["bbox"][0], label["bbox"][1] + label["bbox"][3]),
            ]
            if any(_segments_cross(a, b, corners[idx], corners[(idx + 1) % 4]) for idx in range(4)):
                errors.append(f"边标签被其他连线穿过：{label['text']} × {edge['id']}")

    if layout == "stateful-graph" and len(edges) > 12:
        warnings.append(f"stateful-graph 连线数量偏高：{len(edges)}")
    if layout == "hand-drawn-flow":
        if len(nodes) < 3 or len(edges) < 2:
            errors.append("hand-drawn-flow 缺少足够的节点/关系，不能作为机制图放行")
        if len(labels) > max(1, len(edges)):
            errors.append("hand-drawn-flow 存在未绑定或过量关系标签")
    return {"status": "failed" if errors else ("warning" if warnings else "passed"), "errors": list(dict.fromkeys(errors)), "warnings": list(dict.fromkeys(warnings)), "metrics": {"nodes": len(nodes), "edges": len(edges), "edge_labels": len(labels), "layout": layout}}


def check_article(article: Path, sources: list[str], source_layouts: dict[str, str] | None = None) -> dict[str, Any]:
    records = []
    errors: list[str] = []
    warnings: list[str] = []
    for raw in sources:
        path = (article / raw.replace("\\", "/")).resolve()
        if path.suffix.lower() in {".html", ".htm"}:
            # KaTeX/code/formula backends intentionally keep an editable HTML
            # source.  It is not an SVG and must not be sent through an XML
            # geometry parser; validate existence/non-empty and let the HTML
            # checker own markup semantics.
            try:
                text = path.read_text(encoding="utf-8")
                result = {
                    "status": "passed" if len(text.strip()) >= 80 else "failed",
                    "errors": [] if len(text.strip()) >= 80 else ["HTML 可编辑源过短"],
                    "warnings": [],
                }
            except OSError as exc:
                result = {"status": "failed", "errors": [f"HTML 可编辑源无法读取：{exc}"], "warnings": []}
        else:
            result = check_svg(path, (source_layouts or {}).get(raw.replace("\\", "/"), ""))
        records.append({"source": raw, **result})
        errors.extend(f"{raw}: {item}" for item in result.get("errors", []))
        warnings.extend(f"{raw}: {item}" for item in result.get("warnings", []))
    return {"schema_version": 1, "contract": CONTRACT, "status": "failed" if errors else ("warning" if warnings else "passed"), "errors": errors, "warnings": warnings, "records": records}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--source", action="append", default=[])
    args = parser.parse_args()
    sources = args.source
    if not sources:
        contract_path = args.article / "visual-contract.json"
        try:
            document = json.loads(contract_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            document = {}
        sources = [str(unit.get("diagram_source") or "") for unit in document.get("units", []) if isinstance(unit, dict) and str(unit.get("id")) != "cover" and unit.get("diagram_source")]
        source_layouts = {
            str(unit.get("diagram_source") or "").replace("\\", "/"): str(unit.get("layout_archetype") or "")
            for unit in document.get("units", [])
            if isinstance(unit, dict) and unit.get("diagram_source")
        }
    else:
        source_layouts = {}
    report = check_article(args.article.resolve(), sources, source_layouts)
    (args.article / "visual-aesthetic-review.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "errors": report["errors"], "warnings": report["warnings"]}, ensure_ascii=False))
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
