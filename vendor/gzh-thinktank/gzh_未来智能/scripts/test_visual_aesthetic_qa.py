#!/usr/bin/env python3
"""Regression tests for objective SVG visual hygiene checks."""

from __future__ import annotations

import tempfile
from pathlib import Path

from visual_aesthetic_qa import check_svg


def _svg(*, arrow_points: str, label_x: int = 150) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="220" data-layout-archetype="stateful-graph">'
        '<rect data-role="canvas" width="300" height="220" fill="#F4F0E8"/>'
        '<rect x="20" y="20" width="260" height="180" fill="#FFFCF7" stroke="#557A96"/>'
        '<rect data-role="node" data-node-id="a" x="40" y="70" width="80" height="40"/>'
        '<rect data-role="node" data-node-id="b" x="180" y="70" width="80" height="40"/>'
        '<line data-role="edge" data-arrowhead="true" data-edge-id="a-b" x1="120" y1="90" x2="180" y2="90"/>'
        f'<polygon data-role="arrowhead" data-edge-id="a-b" points="{arrow_points}"/>'
        f'<text data-role="edge-label" data-edge-id="a-b" x="{label_x}" y="45" font-size="15">reads</text>'
        '<text data-role="footer" x="40" y="165" font-size="12">footer</text>'
        '</svg>'
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aesthetic-qa-") as raw:
        path = Path(raw) / "good.svg"
        path.write_text(_svg(arrow_points="180,90 167,83 167,97"), encoding="utf-8")
        assert check_svg(path)["status"] == "passed"

        path.write_text(_svg(arrow_points="180,90 193,81 193,99"), encoding="utf-8")
        # A triangle whose base lies beyond the line endpoint points backward
        # relative to the edge and must be rejected.
        assert any("箭头方向" in issue for issue in check_svg(path)["errors"])

        path.write_text(_svg(arrow_points="180,90 167,83 167,97", label_x=90).replace('y="45"', 'y="90"'), encoding="utf-8")
        assert any("边标签落入节点" in issue for issue in check_svg(path)["errors"])

    print("test_visual_aesthetic_qa.py: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
