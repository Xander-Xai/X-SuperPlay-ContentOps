#!/usr/bin/env python3
"""Lint final WeChat HTML for readable, account-safe code styling."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEX = re.compile(r"#[0-9a-fA-F]{3,8}")


def _rgb(raw: str) -> tuple[int, int, int] | None:
    value = raw.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) not in {6, 8}:
        return None
    try:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def _lum(rgb: tuple[int, int, int]) -> float:
    vals = []
    for channel in rgb:
        x = channel / 255
        vals.append(x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4)
    return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]


def contrast(foreground: str, background: str) -> float:
    fg = _rgb(foreground)
    bg = _rgb(background)
    if not fg or not bg:
        return 0.0
    a, b = sorted((_lum(fg), _lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def check_html(path: Path) -> list[str]:
    if not path.is_file():
        return [f"缺少 HTML：{path.name}"]
    text = path.read_text(encoding="utf-8", errors="replace")
    errors: list[str] = []
    pre_blocks = re.findall(r'<pre\b[^>]*style="([^"]+)"[^>]*>', text, flags=re.I)
    pre_blocks += re.findall(r"<pre\b[^>]*style='([^']+)'[^>]*>", text, flags=re.I)
    if not pre_blocks:
        return errors
    forbidden_dark = {"#172b3e", "#202a30", "#0f2235", "#102536", "#152a3b", "#162b40", "#111827"}
    for index, style in enumerate(pre_blocks, 1):
        bg = re.search(r"background\s*:\s*(#[0-9a-f]{3,8})", style, flags=re.I)
        fg = re.search(r"(?:^|;)\s*color\s*:\s*(#[0-9a-f]{3,8})", style, flags=re.I)
        if not bg or not fg:
            errors.append(f"pre[{index}] 必须显式声明 background 和 color")
            continue
        if bg.group(1).lower() in forbidden_dark:
            errors.append(f"pre[{index}] 使用了禁用的深色代码背景：{bg.group(1)}")
        ratio = contrast(fg.group(1), bg.group(1))
        if ratio < 4.5:
            errors.append(f"pre[{index}] 文本对比度 {ratio:.2f}:1 低于 WCAG AA 4.5:1")
        if not re.search(r"font-family\s*:[^;]*monospace", style, flags=re.I):
            errors.append(f"pre[{index}] 未使用等宽字体栈")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    args = parser.parse_args()
    article = args.article.expanduser()
    if not article.is_absolute():
        article = ROOT / article
    article = article.resolve()
    # Preview HTML belongs to the later final-review stage.  A formatted
    # article must be lintable before that derivative exists; once created it
    # is included automatically.
    paths = [article / "article.html"]
    preview = article / "article_预览.html"
    if preview.is_file():
        paths.append(preview)
    errors = [error for path in paths for error in check_html(path)]
    if errors:
        print("STYLE LINT BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"STYLE LINT PASSED: {len(paths)} HTML files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
