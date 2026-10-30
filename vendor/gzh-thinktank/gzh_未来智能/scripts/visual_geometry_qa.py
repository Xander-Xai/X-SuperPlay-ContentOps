#!/usr/bin/env python3
"""Geometry and canvas-background checks for deterministic article visuals.

Semantic QA answers "does the source contain the promised labels?".  This
module answers the different question "does the rendered diagram remain a
valid graph?".  Renderers may provide an explicit ``geometry-contract-v1``
metadata block, or mark simple SVG nodes/edges with ``data-role`` attributes.

The checker is intentionally conservative: a relationship diagram without an
auditable geometry contract is blocked rather than treated as a decorative
image.  Raster-only illustrative images are not geometry-checked; technical
facts must use an editable deterministic source first.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET


GEOMETRY_CONTRACT = "geometry-contract-v1"
DEFAULT_BODY_BACKGROUND = "#F4F0E8"


def _num(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value).strip().replace("px", ""))
    except (TypeError, ValueError):
        return default


def _point(value: object) -> tuple[float, float] | None:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return (_num(value[0]), _num(value[1]))
    if isinstance(value, dict):
        return (_num(value.get("x")), _num(value.get("y")))
    return None


def _bbox(value: object) -> tuple[float, float, float, float] | None:
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        return (_num(value[0]), _num(value[1]), _num(value[2]), _num(value[3]))
    if isinstance(value, dict):
        return (
            _num(value.get("x")),
            _num(value.get("y")),
            _num(value.get("width", value.get("w"))),
            _num(value.get("height", value.get("h"))),
        )
    return None


def _expand(box: tuple[float, float, float, float], margin: float) -> tuple[float, float, float, float]:
    x, y, w, h = box
    return (x - margin, y - margin, w + 2 * margin, h + 2 * margin)


def _inside(point: tuple[float, float], box: tuple[float, float, float, float], margin: float = 0.0) -> bool:
    x, y = point
    bx, by, bw, bh = _expand(box, margin)
    return bx <= x <= bx + bw and by <= y <= by + bh


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float], eps: float = 1e-6) -> bool:
    return (
        min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
        and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps
    )


def _segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    eps = 1e-6
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    if ((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)) and ((o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)):
        return True
    return (
        abs(o1) <= eps and _on_segment(a, b, c)
        or abs(o2) <= eps and _on_segment(a, b, d)
        or abs(o3) <= eps and _on_segment(c, d, a)
        or abs(o4) <= eps and _on_segment(c, d, b)
    )


def _collinear_overlap(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]) -> bool:
    """Return True when two collinear segments overlap beyond a point."""
    if abs(_orientation(a, b, c)) > 1e-6 or abs(_orientation(a, b, d)) > 1e-6:
        return False
    if abs(b[0] - a[0]) >= abs(b[1] - a[1]):
        overlap = min(max(a[0], b[0]), max(c[0], d[0])) - max(min(a[0], b[0]), min(c[0], d[0]))
    else:
        overlap = min(max(a[1], b[1]), max(c[1], d[1])) - max(min(a[1], b[1]), min(c[1], d[1]))
    return overlap > 2.0


def _segment_hits_box(a: tuple[float, float], b: tuple[float, float], box: tuple[float, float, float, float], margin: float = 0.0) -> bool:
    expanded = _expand(box, margin)
    if _inside(a, expanded) or _inside(b, expanded):
        return True
    x, y, w, h = expanded
    corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    return any(_segments_intersect(a, b, corners[i], corners[(i + 1) % 4]) for i in range(4))


def _polyline_hits_box(points: list[tuple[float, float]], box: tuple[float, float, float, float], margin: float = 0.0) -> bool:
    return any(_segment_hits_box(a, b, box, margin) for a, b in zip(points, points[1:]))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _svg_root(source_text: str) -> ET.Element | None:
    try:
        return ET.fromstring(source_text)
    except ET.ParseError:
        return None


def _metadata(root: ET.Element) -> dict[str, Any] | None:
    for node in root.iter():
        if _local_name(node.tag) != "metadata":
            continue
        if node.attrib.get("id") != "visual-geometry-contract":
            continue
        raw = "".join(node.itertext()).strip()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None
    return None


def _fallback_svg_geometry(root: ET.Element) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read simple data-role-marked rectangles and lines.

    This keeps the contract usable for small hand-authored SVGs without
    requiring every renderer to duplicate a JSON graph manifest.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for index, element in enumerate(root.iter()):
        role = str(element.attrib.get("data-role") or "").lower()
        tag = _local_name(element.tag).lower()
        if role == "node" and tag == "rect":
            nodes.append({
                "id": str(element.attrib.get("data-node-id") or f"node-{index}"),
                "bbox": [
                    _num(element.attrib.get("x")),
                    _num(element.attrib.get("y")),
                    _num(element.attrib.get("width")),
                    _num(element.attrib.get("height")),
                ],
            })
        if role == "edge" and tag == "line":
            edge = {
                "id": str(element.attrib.get("data-edge-id") or f"edge-{index}"),
                "points": [
                    [_num(element.attrib.get("x1")), _num(element.attrib.get("y1"))],
                    [_num(element.attrib.get("x2")), _num(element.attrib.get("y2"))],
                ],
            }
            if element.attrib.get("data-junction-group"):
                edge["junction_group"] = element.attrib["data-junction-group"]
            if element.attrib.get("data-overlap-group"):
                edge["overlap_group"] = element.attrib["data-overlap-group"]
            edges.append(edge)
    return nodes, edges


def _edge_points(edge: dict[str, Any]) -> list[tuple[float, float]]:
    raw = edge.get("points") or edge.get("route") or []
    points = [_point(value) for value in raw] if isinstance(raw, list) else []
    return [value for value in points if value is not None]


def _node_map(nodes: Iterable[dict[str, Any]]) -> dict[str, tuple[float, float, float, float]]:
    result: dict[str, tuple[float, float, float, float]] = {}
    for index, node in enumerate(nodes):
        box = _bbox(node.get("bbox"))
        if box and box[2] > 0 and box[3] > 0:
            result[str(node.get("id") or f"node-{index}")] = box
    return result


def validate_geometry_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if str(contract.get("contract") or GEOMETRY_CONTRACT) != GEOMETRY_CONTRACT:
        errors.append("geometry metadata contract 必须为 geometry-contract-v1")
    nodes = contract.get("nodes") if isinstance(contract.get("nodes"), list) else []
    edges = contract.get("edges") if isinstance(contract.get("edges"), list) else []
    boxes = _node_map(nodes)
    if not boxes and edges:
        errors.append("geometry contract 有连线但没有有效节点边界框")
    seen: set[str] = set()
    for node_id in boxes:
        if node_id in seen:
            errors.append(f"节点 id 重复：{node_id}")
        seen.add(node_id)
    parsed_edges: list[tuple[str, list[tuple[float, float]], str, str]] = []
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"连线记录 {index} 不是对象")
            continue
        edge_id = str(edge.get("id") or f"edge-{index}")
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        points = _edge_points(edge)
        if len(points) < 2:
            errors.append(f"连线 {edge_id} 缺少至少两个路径点")
            continue
        if source and source not in boxes:
            errors.append(f"连线 {edge_id} 的 source 不存在：{source}")
        if target and target not in boxes:
            errors.append(f"连线 {edge_id} 的 target 不存在：{target}")
        source_port = _point(edge.get("source_port")) or points[0]
        target_port = _point(edge.get("target_port")) or points[-1]
        if source and not _inside(source_port, boxes[source], 28):
            errors.append(f"连线 {edge_id} 起点没有落在 source 端口附近：{source}")
        if target and not _inside(target_port, boxes[target], 28):
            errors.append(f"连线 {edge_id} 终点没有落在 target 端口附近：{target}")
        for node_id, box in boxes.items():
            if node_id in {source, target}:
                continue
            if _polyline_hits_box(points, box, margin=6):
                errors.append(f"连线 {edge_id} 穿过非端点节点：{node_id}")
        parsed_edges.append((edge_id, points, source, target))
    # A graph edge may share its declared endpoint with another edge, but two
    # unrelated routes must never cross or overlap in the visible canvas.
    for index, (left_id, left_points, left_source, left_target) in enumerate(parsed_edges):
        for right_id, right_points, right_source, right_target in parsed_edges[index + 1 :]:
            left_meta = next((edge for edge in edges if str(edge.get("id") or "") == left_id), {})
            right_meta = next((edge for edge in edges if str(edge.get("id") or "") == right_id), {})
            if left_meta.get("overlap_group") and left_meta.get("overlap_group") == right_meta.get("overlap_group"):
                continue
            left_cross = left_meta.get("cross_group") if isinstance(left_meta.get("cross_group"), list) else [left_meta.get("cross_group")]
            right_cross = right_meta.get("cross_group") if isinstance(right_meta.get("cross_group"), list) else [right_meta.get("cross_group")]
            if (right_meta.get("overlap_group") and right_meta.get("overlap_group") in left_cross) or (left_meta.get("overlap_group") and left_meta.get("overlap_group") in right_cross):
                continue
            junction_group = left_meta.get("junction_group") and left_meta.get("junction_group") == right_meta.get("junction_group")
            shared = {left_source, left_target} & {right_source, right_target}
            for a, b in zip(left_points, left_points[1:]):
                for c, d in zip(right_points, right_points[1:]):
                    if not _segments_intersect(a, b, c, d):
                        continue
                    # Allow an exact shared endpoint only when the graph says
                    # the edges share a node; collinear overlap remains a fail.
                    endpoint_touch = any(
                        math.dist(p, q) <= 2.0
                        for p in (a, b)
                        for q in (c, d)
                    )
                    if _collinear_overlap(a, b, c, d):
                        endpoint_touch = False
                    if not ((shared and endpoint_touch) or (junction_group and endpoint_touch)):
                        errors.append(f"连线交叉或重叠：{left_id} × {right_id}")
                        break
                else:
                    continue
                break
    return list(dict.fromkeys(errors))


def _canvas_background(root: ET.Element) -> str:
    for element in root.iter():
        if _local_name(element.tag) == "rect" and element.attrib.get("data-role") == "canvas":
            return str(element.attrib.get("fill") or "").strip()
    for element in root.iter():
        if _local_name(element.tag) == "rect":
            return str(element.attrib.get("fill") or "").strip()
    return ""


def background_errors(source_text: str, suffix: str, expected: str) -> list[str]:
    expected = str(expected or "").strip().lower()
    if not expected:
        return []
    if suffix.lower() == ".svg":
        root = _svg_root(source_text)
        actual = _canvas_background(root) if root is not None else ""
        if not actual:
            return ["SVG 缺少可识别的画布背景"]
        if actual.lower() != expected:
            return [f"画布背景不一致：实际 {actual}，合同要求 {expected}"]
        return []
    if suffix.lower() in {".html", ".htm"}:
        if not re.search(r'data-background-token\s*=\s*["\']background["\']', source_text, flags=re.I):
            return ["HTML 缺少 data-background-token=background 的画布声明"]
        if expected not in source_text.lower():
            return [f"HTML 源未声明合同画布背景：{expected}"]
    return []


def check_source(
    source_path: Path,
    *,
    geometry_required: bool = False,
    expected_background: str = DEFAULT_BODY_BACKGROUND,
) -> list[str]:
    if not source_path.is_file():
        return [f"几何审核源文件不存在：{source_path}"]
    text = source_path.read_text(encoding="utf-8", errors="replace")
    errors = background_errors(text, source_path.suffix, expected_background)
    if source_path.suffix.lower() != ".svg":
        return errors
    root = _svg_root(text)
    if root is None:
        return errors + ["SVG 无法解析，几何审核阻断"]
    contract = _metadata(root)
    if contract is not None:
        errors.extend(validate_geometry_contract(contract))
        return list(dict.fromkeys(errors))
    nodes, edges = _fallback_svg_geometry(root)
    if geometry_required and not edges:
        errors.append("关系图缺少 geometry-contract-v1 或 data-role=edge 连线证据")
    if edges:
        boxes = _node_map(nodes)
        for edge in edges:
            points = _edge_points(edge)
            if len(points) < 2:
                continue
            source_candidates = [node_id for node_id, box in boxes.items() if _inside(points[0], box, 28)]
            target_candidates = [node_id for node_id, box in boxes.items() if _inside(points[-1], box, 28)]
            if source_candidates:
                edge["source"] = source_candidates[0]
            if target_candidates:
                edge["target"] = target_candidates[-1]
        errors.extend(validate_geometry_contract({"contract": GEOMETRY_CONTRACT, "nodes": nodes, "edges": edges}))
    return list(dict.fromkeys(errors))


__all__ = ["GEOMETRY_CONTRACT", "DEFAULT_BODY_BACKGROUND", "background_errors", "check_source", "validate_geometry_contract"]
