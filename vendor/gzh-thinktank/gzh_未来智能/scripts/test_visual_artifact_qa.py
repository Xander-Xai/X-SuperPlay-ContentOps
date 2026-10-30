"""Regression tests for source/raster visual artifact checks."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from visual_artifact_qa import check_article

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    Image = None


def _unit() -> dict:
    return {
        "id": "body-01",
        "visual_type": "relationship",
        "diagram_source": "source.svg",
        "output": "out.png",
    }


def test_duplicate_style_and_black_block_are_rejected() -> None:
    if Image is None:
        return
    with tempfile.TemporaryDirectory() as tmp:
        article = Path(tmp)
        (article / "source.svg").write_text(
            '<svg style="--bg:#F4F0E8" style="max-width:100%"><rect fill="var(--missing)"/></svg>',
            encoding="utf-8",
        )
        (article / "source.html").write_text(
            '<svg style="--bg:#F4F0E8" style="max-width:100%"></svg>',
            encoding="utf-8",
        )
        image = Image.new("RGB", (240, 120), "#F4F0E8")
        ImageDraw.Draw(image).rectangle((30, 30, 89, 69), fill="black")
        image.save(article / "out.png")
        result = check_article(article, [_unit()])
        assert result["status"] == "failed"
        assert any("duplicate attributes" in value for value in result["errors"])
        assert any("near-black" in value for value in result["errors"])


def test_code_surface_dark_region_requires_explicit_opt_in() -> None:
    if Image is None:
        return
    with tempfile.TemporaryDirectory() as tmp:
        article = Path(tmp)
        unit = _unit() | {"visual_type": "code", "diagram_source": "source.html"}
        (article / "source.html").write_text('<pre style="background:#172B3E">code</pre>', encoding="utf-8")
        image = Image.new("RGB", (240, 120), "#F4F0E8")
        ImageDraw.Draw(image).rectangle((30, 30, 89, 69), fill="#172B3E")
        image.save(article / "out.png")
        result = check_article(article, [unit])
        assert result["status"] == "failed"
        unit["allow_dark_surface"] = True
        result = check_article(article, [unit])
        assert result["status"] == "passed"


if __name__ == "__main__":
    test_duplicate_style_and_black_block_are_rejected()
    test_code_surface_dark_region_requires_explicit_opt_in()
    print(json.dumps({"status": "passed"}, ensure_ascii=False))
