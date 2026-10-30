#!/usr/bin/env python3
"""Render a Mermaid diagram through the local matrix adapter.

This is a small, source-neutral adapter.  It uses the already vendored
``beautiful-mermaid`` runtime when available and keeps the external
``mcp-mermaid`` project as a protocol reference only.  No network call or
upstream source checkout is performed by this command.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "skills" / "beautiful-mermaid" / "scripts" / "render-diagram.ts"
ALLOWED_THEMES = {
    "zinc-light",
    "zinc-dark",
    "tokyo-night",
    "tokyo-night-storm",
    "tokyo-night-light",
    "catppuccin-mocha",
    "catppuccin-latte",
    "nord",
    "nord-light",
    "dracula",
    "github-light",
    "github-dark",
    "solarized-light",
    "solarized-dark",
    "one-dark",
}
FORBIDDEN_MARKUP = ("<br/>", "<br />", "<b>", "<i>")


def _npx() -> str:
    command = shutil.which("npx.cmd") or shutil.which("npx")
    if not command:
        raise RuntimeError("未找到 npx；请先安装 Node.js 18+ 和 beautiful-mermaid 依赖")
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Mermaid .mmd 文件")
    parser.add_argument("--output", required=True, type=Path, help="输出 SVG 文件")
    parser.add_argument("--theme", default="github-light", choices=sorted(ALLOWED_THEMES))
    args = parser.parse_args()

    source = args.input.expanduser().resolve()
    target = args.output.expanduser().resolve()
    if not source.is_file():
        print(f"DIAGRAM BLOCKED: 输入不存在：{source}", file=sys.stderr)
        return 1
    if not RENDERER.is_file():
        print(f"DIAGRAM BLOCKED: 本地 Mermaid 渲染器不存在：{RENDERER}", file=sys.stderr)
        return 1

    diagram = source.read_text(encoding="utf-8")
    bad = next((marker for marker in FORBIDDEN_MARKUP if marker in diagram), None)
    if bad:
        print(f"DIAGRAM BLOCKED: Mermaid 标签含禁用 HTML：{bad}", file=sys.stderr)
        return 1
    if not diagram.strip():
        print("DIAGRAM BLOCKED: Mermaid 输入为空", file=sys.stderr)
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    command = [_npx(), "--no-install", "ts-node", str(RENDERER), str(source), "--output", str(target), "--theme", args.theme]
    result = subprocess.run(command, cwd=RENDERER.parent.parent, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        detail = (result.stdout + result.stderr).strip()
        print(f"DIAGRAM BLOCKED: 本地 Mermaid 渲染失败\n{detail}", file=sys.stderr)
        return result.returncode
    if not target.is_file() or not target.read_text(encoding="utf-8", errors="replace").lstrip().startswith("<svg"):
        print("DIAGRAM BLOCKED: 渲染器没有输出有效 SVG", file=sys.stderr)
        return 1
    print(f"DIAGRAM RENDERED: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
