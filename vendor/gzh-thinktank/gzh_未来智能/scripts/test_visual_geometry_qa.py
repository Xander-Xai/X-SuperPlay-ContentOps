#!/usr/bin/env python3
"""Regression tests for connector topology and body canvas consistency."""

from __future__ import annotations

import tempfile
from pathlib import Path

from visual_geometry_qa import check_source, validate_geometry_contract


def main() -> int:
    good = {
        "contract": "geometry-contract-v1",
        "nodes": [
            {"id": "a", "bbox": [10, 10, 80, 40]},
            {"id": "b", "bbox": [210, 10, 80, 40]},
        ],
        "edges": [{"id": "a-b", "source": "a", "target": "b", "points": [[92, 30], [208, 30]]}],
    }
    assert not validate_geometry_contract(good)

    bad_cross = {
        "contract": "geometry-contract-v1",
        "nodes": [
            {"id": "a", "bbox": [10, 10, 80, 40]},
            {"id": "b", "bbox": [210, 10, 80, 40]},
            {"id": "middle", "bbox": [110, 10, 60, 40]},
        ],
        "edges": [{"id": "a-b", "source": "a", "target": "b", "points": [[92, 30], [208, 30]]}],
    }
    assert any("非端点节点" in item for item in validate_geometry_contract(bad_cross))

    with tempfile.TemporaryDirectory(prefix="geometry-qa-") as raw:
        path = Path(raw) / "diagram.svg"
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="100">'
            '<rect data-role="canvas" width="300" height="100" fill="#F4F0E8"/>'
            '<rect data-role="node" x="10" y="10" width="80" height="40"/>'
            '<rect data-role="node" x="210" y="10" width="80" height="40"/>'
            '<line data-role="edge" x1="92" y1="30" x2="208" y2="30"/>'
            '</svg>',
            encoding="utf-8",
        )
        assert not check_source(path, geometry_required=True, expected_background="#F4F0E8")
        path.write_text(path.read_text(encoding="utf-8").replace("#F4F0E8", "#FFFFFF"), encoding="utf-8")
        assert any("背景" in item for item in check_source(path, geometry_required=True, expected_background="#F4F0E8"))

    print("test_visual_geometry_qa.py: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

