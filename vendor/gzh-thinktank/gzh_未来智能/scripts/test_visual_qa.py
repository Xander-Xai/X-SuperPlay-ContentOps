#!/usr/bin/env python3
"""Regression tests for the visual brief and image quality gate."""

from __future__ import annotations

import importlib.util
import json
import struct
import tempfile
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("visual_qa", ROOT / "scripts" / "visual_qa.py")
assert SPEC and SPEC.loader
visual_qa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(visual_qa)


def png_bytes(width: int = 800, height: int = 400, color: tuple[int, int, int] = (245, 240, 232)) -> bytes:
    """Create a dependency-free RGB PNG large enough for the gate.

    叠加确定性"墨迹"（小暗色块）模拟文字成分，满足正文图信息密度门禁
    （glyph ≥ 12），否则纯色夹具会被新门禁拦截。
    """
    rows = []
    row = b"\x00" + bytes(color) * width
    for _ in range(height):
        rows.append(row)
    raw = bytearray(b"".join(rows))
    rng = __import__("random").Random(20260807)
    for _ in range(240):
        x0, y0 = rng.randrange(width - 6), rng.randrange(height - 3)
        for dx in range(rng.randrange(2, 6)):
            for dy in range(rng.randrange(1, 3)):
                i = ((y0 + dy) * width + (x0 + dx)) * 3 + 1  # 跳过每行 filter byte
                shade = rng.randrange(20, 120)
                raw[i] = shade
                raw[i + 1] = shade
                raw[i + 2] = shade
    raw = bytes(raw)

    def chunk(name: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="visual-qa-") as raw:
        article = Path(raw)
        (article / "imgs").mkdir()
        (article / "article.yaml").write_text("account: sentinel\ntitle: Visual QA\n", encoding="utf-8")
        (article / "article.md").write_text("# Visual QA\n\n## 选题\n\n## 实测\n\n## 结论\n", encoding="utf-8")
        (article / "article.html").write_text(
            '<section><p><span leaf="">Visual QA</span></p>'
            '<img src="imgs/cover.png" alt="封面" />'
            '<img src="imgs/section-01.png" alt="选题" />'
            '<img src="imgs/section-02.png" alt="实测" />'
            '<img src="imgs/section-03.png" alt="结论" /></section>',
            encoding="utf-8",
        )
        (article / "imgs" / "cover.png").write_bytes(png_bytes(color=(245, 240, 232)))
        (article / "imgs" / "section-01.png").write_bytes(png_bytes(color=(230, 243, 242)))
        (article / "imgs" / "section-02.png").write_bytes(png_bytes(color=(255, 244, 238)))
        (article / "imgs" / "section-03.png").write_bytes(png_bytes(color=(229, 238, 247)))
        assert visual_qa.plan(article) == 0
        assert visual_qa.approve(article, "test approval") == 0
        assert visual_qa.check(article) == 0
        sources_path = article / "image-sources.json"
        sources = json.loads(sources_path.read_text(encoding="utf-8"))
        sources["status"] = "passed"
        for item in sources["assets"]:
            item.update({
                "origin": "generated",
                "source": "local-test",
                "license": "fixture",
                "reuse_approved": False,
            })
        sources_path.write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
        assert visual_qa.check(article) == 0
    print("VISUAL QA TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
