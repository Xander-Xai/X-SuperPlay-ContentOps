#!/usr/bin/env python3
"""Deterministic, account-themed renderer for code / pseudocode visuals (RC7).

科普文章里，强公式/架构内容应给出「可运行代码实现」，复杂、短篇幅讲不清的
机制应给「伪代码」。这两类内容都是精确文本，绝不能用图像模型去「画」——
否则会出现伪造 API、无法核验的符号。本脚本做确定性渲染：

- 输出 HTML 代码卡（正文直接内嵌，移动端友好，账号主题配色）。
- 输出 SVG 代码卡作为 fallback 图片（visual plan 的 asset）。

配色来自 profiles/visual-styles.yaml 的 design_tokens（单一来源，RC3），
不在此硬编码颜色。
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]



def _default_account() -> str:
    """Return the fixed account id of this split workflow target."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from account_context import ACCOUNT_ID
        return ACCOUNT_ID
    except Exception as exc:
        raise RuntimeError("workflow identity unavailable") from exc

def _account_choices() -> tuple[str, ...]:
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from account_context import ACCOUNT_IDS
        return tuple(sorted(ACCOUNT_IDS))
    except Exception as exc:
        raise RuntimeError("workflow identity unavailable") from exc

def load_tokens(account: str | None = None) -> dict[str, Any]:
    if not account:
        account = _default_account()
    try:
        import yaml  # type: ignore

        data = yaml.safe_load((ROOT / "profiles" / "visual-styles.yaml").read_text(encoding="utf-8"))
    except (ImportError, OSError, ValueError):
        data = {}
    data = data if isinstance(data, dict) else {}
    defaults = data.get("design_tokens_default") if isinstance(data.get("design_tokens_default"), dict) else {}
    accounts = data.get("accounts") if isinstance(data.get("accounts"), dict) else {}
    acct = accounts.get(account) if isinstance(accounts, dict) else {}
    if not isinstance(acct, dict):
        acct = {}
    block = acct.get("design_tokens") if isinstance(acct.get("design_tokens"), dict) else {}
    tokens = dict(defaults)
    tokens.update({k: v for k, v in block.items() if k and v})
    tokens.setdefault("background", "#F4F0E8")
    tokens.setdefault("surface", "#FFFCF7")
    tokens.setdefault("ink", "#17324D")
    tokens.setdefault("muted", "#5E6872")
    tokens.setdefault("vermilion", "#B24A2B")
    tokens.setdefault("signal", "#557A96")
    tokens.setdefault("code_background", "#F1F4F5")
    tokens.setdefault("code_border", "#C9D5DD")
    tokens.setdefault("code_keyword", "#A23E25")
    tokens.setdefault("code_string", "#2F6F7E")
    tokens.setdefault("code_number", "#8A5A44")
    tokens.setdefault("code_comment", "#75808A")
    tokens.setdefault("code_function", "#8C4A2D")
    tokens.setdefault("font_stack", "'PingFang SC', 'Microsoft YaHei', sans-serif")
    tokens.setdefault("mono_stack", "'JetBrains Mono', 'SFMono-Regular', Consolas, monospace")
    return tokens


KEYWORDS = {
    "def", "class", "return", "if", "else", "elif", "for", "while", "import", "from",
    "as", "with", "try", "except", "finally", "raise", "lambda", "yield", "in", "not",
    "and", "or", "is", "None", "True", "False", "self", "async", "await", "pass",
    "break", "continue", "global", "assert", "print", "function", "const", "let", "var",
    "public", "private", "int", "float", "string", "void", "for", "foreach", "end",
    "then", "do", "while", "repeat", "begin", "return", "if", "else", "elif",
}

# Q③ / Enhancement A: code_style 信号 → 代码卡右上角标签的范式说明。
# 语义来自视觉路由器的 code_style 信号；空串表示沿用旧版「代码实现 / 伪代码」标签。
STYLE_LABELS = {
    "teaching": "NumPy 直觉",
    "production": "PyTorch 实战",
    "pseudocode": "伪代码",
}

# 方案 D：语言标签中文化 + 默认语言（text / 空）不显示，避免"伪代码 · text"残留。
LANGUAGE_DISPLAY = {
    "python": "Python",
    "py": "Python",
    "bash": "Shell",
    "sh": "Shell",
    "shell": "Shell",
    "javascript": "JS",
    "js": "JS",
    "typescript": "TS",
    "ts": "TS",
    "yaml": "YAML",
    "yml": "YAML",
    "json": "JSON",
    "sql": "SQL",
    "go": "Go",
    "rust": "Rust",
    "java": "Java",
    "cpp": "C++",
    "c": "C",
    "text": "",
    "": "",
}


def _language_label(language: str) -> str:
    """中文化语言标签；空/text 不显示（避免「伪代码 · text」残留）。"""
    key = (language or "").strip().lower()
    return LANGUAGE_DISPLAY.get(key, language or "")


def highlight(line: str) -> str:
    """Lightweight tokenizer: comments, strings, numbers, keywords, calls."""
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == "#" or line[i:i + 2] in {"//", "--"} or line[i:i + 3] == "::=":
            out.append(f'<span class="c">{html.escape(line[i:])}</span>')
            break
        if ch in {"'", '"'}:
            quote = ch
            j = i + 1
            while j < n and line[j] != quote:
                if line[j] == "\\":
                    j += 2
                else:
                    j += 1
            if j < n:
                j += 1
            out.append(f'<span class="s">{html.escape(line[i:j])}</span>')
            i = j
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and line[i + 1].isdigit()):
            j = i
            while j < n and (line[j].isdigit() or line[j] in {".", "e", "E", "+", "-"}):
                j += 1
            out.append(f'<span class="n">{html.escape(line[i:j])}</span>')
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (line[j].isalnum() or line[j] == "_"):
                j += 1
            word = line[i:j]
            if word in KEYWORDS:
                out.append(f'<span class="k">{html.escape(word)}</span>')
            elif j < n and line[j] == "(":
                out.append(f'<span class="f">{html.escape(word)}</span>')
            else:
                out.append(html.escape(word))
            i = j
            continue
        out.append(html.escape(ch))
        i += 1
    return "".join(out)


def render_html(code: str, account: str, title: str, kind: str, language: str, code_style: str = "") -> str:
    tokens = load_tokens(account)
    kind_label = "代码实现" if kind == "code" else "伪代码"
    style_label = STYLE_LABELS.get(code_style, kind_label)
    lang_label = _language_label(language)
    lines = code.replace("\r\n", "\n").split("\n")
    body_rows = []
    for idx, raw in enumerate(lines, 1):
        body_rows.append(
            f'<div class="ln"><span class="num">{idx}</span>'
            f'<span class="code">{highlight(raw) if kind == "code" else html.escape(raw)}</span></div>'
        )
    body = "\n".join(body_rows)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body {{ margin:0; background:{tokens['background']}; font-family:{tokens['font_stack']};
    -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale; }}
  .card {{ width:680px; background:{tokens['code_background']};
    border:1px solid {tokens['code_border']}; border-radius:12px; overflow:hidden;
    box-shadow:0 5px 16px rgba(23,50,77,.08); }}
  .bar {{ display:flex; align-items:center; gap:8px; padding:10px 14px;
    background:{tokens['surface']}; border-bottom:1px solid {tokens['code_border']}; }}
  .dot {{ width:10px; height:10px; border-radius:50%; }}
  .dot.a {{ background:{tokens['vermilion']}; }}
  .dot.b {{ background:{tokens['muted']}; }}
  .dot.c {{ background:#C9C2B4; }}
  .title {{ margin-left:8px; font-size:14px; font-weight:600; color:{tokens['ink']}; }}
  .tag {{ margin-left:auto; font-size:12px; color:{tokens['signal']};
    border:1px solid {tokens['code_border']}; border-radius:999px; padding:2px 10px; }}
  .body {{ padding:12px 14px; font-family:{tokens['mono_stack']}; font-size:13.5px;
    line-height:1.7; color:{tokens['ink']}; overflow-x:hidden; }}
  .ln {{ display:flex; gap:12px; white-space:pre-wrap; overflow-wrap:anywhere; }}
  .num {{ color:{tokens['muted']}; user-select:none; min-width:22px; text-align:right; }}
  .k {{ color:{tokens['code_keyword']}; font-weight:700; }}
  .s {{ color:{tokens['code_string']}; }}
  .n {{ color:{tokens['code_number']}; }}
  .c {{ color:{tokens['code_comment']}; font-style:italic; }}
  .f {{ color:{tokens['code_function']}; font-weight:600; }}
</style></head>
<body data-background-token="background"><div class="card">
  <div class="bar">
    <span class="dot a"></span><span class="dot b"></span><span class="dot c"></span>
    <span class="title">{html.escape(title)}</span>
    <span class="tag">{style_label}{(" · " + lang_label) if lang_label else ""}</span>
  </div>
  <div class="body" data-role="code">{body}</div>
</div></body></html>"""


def estimate_height(code: str, kind: str = "code") -> int:
    """Return a tight Chrome screenshot height for a code/pseudocode card.

    The HTML card is max-width 680px centered on a plain background.  This
    estimate matches the CSS used in render_html() closely enough to remove
    most of the bottom whitespace without under-shooting.
    """
    lines = code.replace("\r\n", "\n").split("\n")
    # The card is rasterized at 720px (680px card + a 20px safety gutter).
    # With the current 13.5px mono font, the usable code column fits about
    # 82 characters.  The old 52-character heuristic over-counted nearly
    # every import line and produced a 1,060px canvas for a 30-line snippet,
    # leaving a large beige tail below the actual card.  Keep the estimate
    # tied to the renderer's real width and line-height instead.
    char_capacity = 82
    wrapped_lines = sum(max(1, (len(line) + char_capacity - 1) // char_capacity) for line in lines)
    line_h = 24 if kind == "pseudocode" else 23
    top = 54   # title bar + body top padding
    bottom = 32 # body bottom padding + border + 8px export gutter
    # WeChat's body image contract requires at least 300px of usable canvas;
    # keep a short snippet readable instead of exporting a 240px strip.
    return max(320, top + wrapped_lines * line_h + bottom)


def render_svg(code: str, account: str, title: str, kind: str, language: str, code_style: str = "") -> str:
    tokens = load_tokens(account)
    kind_label = "代码实现" if kind == "code" else "伪代码"
    style_label = STYLE_LABELS.get(code_style, kind_label)
    lines = code.replace("\r\n", "\n").split("\n")[:18]
    line_h = 20
    pad = 16
    top = 44
    width = 680
    height = top + pad + len(lines) * line_h + pad
    rows = []
    for idx, raw in enumerate(lines, 1):
        y = top + idx * line_h - 5
        safe = html.escape(raw[:74]) or " "
        rows.append(
            f'<text x="{pad+34}" y="{y}" font-family="{tokens["mono_stack"]}" '
            f'font-size="13" fill="{tokens["ink"]}">{safe}</text>'
            f'<text x="{pad}" y="{y}" font-family="{tokens["mono_stack"]}" '
            f'font-size="13" fill="{tokens["muted"]}" text-anchor="end">{idx}</text>'
        )
    body = "\n".join(rows)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="{width}" height="{height}" rx="12" fill="{tokens['code_background']}" stroke="{tokens['code_border']}"/>
<rect width="{width}" height="{top}" rx="12" fill="{tokens['surface']}"/>
<circle cx="24" cy="22" r="5" fill="{tokens['vermilion']}"/>
<circle cx="42" cy="22" r="5" fill="{tokens['muted']}"/>
<circle cx="60" cy="22" r="5" fill="#C9C2B4"/>
<text x="80" y="27" font-family="{tokens['font_stack']}" font-size="14" font-weight="600" fill="{tokens['ink']}">{html.escape(title)}</text>
<text x="{width-16}" y="27" text-anchor="end" font-family="{tokens['font_stack']}" font-size="12" fill="{tokens['muted']}">{style_label}{(" · " + _language_label(language)) if _language_label(language) else ""}</text>
{body}
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", required=True, help="代码/伪代码文件路径，或内联文本")
    parser.add_argument("--account", default=_default_account(), choices=_account_choices())
    parser.add_argument("--kind", default="code", choices=("code", "pseudocode"))
    parser.add_argument("--language", default="python")
    parser.add_argument("--title", default="代码片段")
    parser.add_argument("--code-style", dest="code_style", default=None,
                        choices=("teaching", "production", "pseudocode"),
                        help="代码卡表达范式：teaching=NumPy 直觉 / production=PyTorch 实战 / pseudocode=伪代码")
    parser.add_argument("--output", required=True, help="输出目录")
    args = parser.parse_args()

    code_path = Path(args.code)
    code = code_path.read_text(encoding="utf-8") if code_path.is_file() else args.code
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    # 未显式指定时按 kind 推断：伪代码保持伪代码，真实代码默认 PyTorch 实战。
    code_style = args.code_style or ("pseudocode" if args.kind == "pseudocode" else "production")

    html_path = out / "code-card.html"
    svg_path = out / "code-card.svg"
    html_path.write_text(render_html(code, args.account, args.title, args.kind, args.language, code_style=code_style), encoding="utf-8")
    svg_path.write_text(render_svg(code, args.account, args.title, args.kind, args.language, code_style=code_style), encoding="utf-8")
    print(json.dumps({
        "html": str(html_path), "svg": str(svg_path), "account": args.account,
        "kind": args.kind, "language": args.language, "code_style": code_style,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
